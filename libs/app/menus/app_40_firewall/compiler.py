"""Pure Firewall Manager compiler and managed-block candidate builder.

No filesystem writes, subprocesses, UFW reloads or service changes belong here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from ipaddress import ip_network
import json
from typing import Iterable

from .config import (
    FirewallConfig,
    FirewallRule,
    hard_source_rules,
    legacy_openvpn_mapping,
    managed_standard_rule_ids,
    normalize_config,
)
from .policy import (
    HARD_NAME,
    STANDARD_NAME,
    FirewallPolicyError,
    Rule,
    compile_legacy_openvpn,
    inspect_before_rules,
)


_MAX_COMPILED_ACTIONS = 20000
_REQUIRED_ANCHOR = "# End required lines"


@dataclass(frozen=True)
class DesiredBlock:
    kind: str
    label: str
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class CompiledFirewall:
    ipv4: tuple[DesiredBlock, ...]
    ipv6: tuple[DesiredBlock, ...]
    expired_bans: int
    next_expiry: date | None
    explicit_ipv6: bool


@dataclass(frozen=True)
class CandidateResult:
    content: str
    changed: bool
    current_hash: str
    desired_hash: str
    current_rules: int
    desired_rules: int


def managed_digest(blocks: Iterable[DesiredBlock]) -> str:
    payload = [
        {
            "kind": block.kind,
            "label": block.label,
            "rules": block.rules,
        }
        for block in blocks
    ]
    serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _port_terms(spec: str) -> tuple[str | None, ...]:
    if not spec:
        return (None,)
    return tuple(
        term.replace("-", ":", 1) if "-" in term else term
        for term in spec.split(",")
    )


def _rule_families(rule: FirewallRule) -> set[int]:
    versions: set[int] = set()
    if rule.source:
        versions.add(ip_network(rule.source, strict=False).version)
    if rule.destination:
        versions.add(ip_network(rule.destination, strict=False).version)
    if len(versions) > 1:
        raise FirewallPolicyError(
            f"Rule {rule.rule_id} mixes IPv4 and IPv6 source/destination."
        )
    return versions or {4, 6}


def _compile_standard_rule(
    rule: FirewallRule,
    family: int,
) -> tuple[Rule, ...]:
    if family not in _rule_families(rule):
        return ()

    # UFW uses different built-in before-chain names for IPv4 and IPv6.
    # before.rules:  ufw-before-*
    # before6.rules: ufw6-before-*
    chain_prefix = "ufw6-before" if family == 6 else "ufw-before"
    chain = {
        "input": f"{chain_prefix}-input",
        "output": f"{chain_prefix}-output",
        "forward": f"{chain_prefix}-forward",
    }[rule.direction]
    target = {
        "allow": "ACCEPT",
        "deny": "DROP",
        "reject": "REJECT",
    }[rule.action]

    base: list[str] = ["-A", chain]
    if rule.interface:
        base.extend([
            "-o" if rule.direction == "output" else "-i",
            rule.interface,
        ])

    if rule.protocol != "any":
        protocol = (
            "ipv6-icmp"
            if family == 6 and rule.protocol == "icmp"
            else rule.protocol
        )
        base.extend(["-p", protocol])
        if rule.protocol in {"tcp", "udp"}:
            base.extend(["-m", rule.protocol])

    if rule.source:
        base.extend(["-s", rule.source])
    if rule.destination:
        if rule.destination_invert:
            base.append("!")
        base.extend(["-d", rule.destination])

    actions: list[Rule] = []
    for source_port in _port_terms(rule.src_ports):
        for destination_port in _port_terms(rule.dst_ports):
            action = list(base)
            if source_port is not None:
                action.extend(["--sport", source_port])
            if destination_port is not None:
                action.extend(["--dport", destination_port])
            action.extend(["-j", target])
            actions.append(tuple(action))
            if len(actions) > _MAX_COMPILED_ACTIONS:
                raise FirewallPolicyError(
                    f"Rule {rule.rule_id} expands to too many firewall actions."
                )
    return tuple(actions)


def _hard_source_by_family(
    config: FirewallConfig,
    family: int,
) -> tuple[Rule, ...]:
    result: list[Rule] = []
    for action in hard_source_rules(config):
        source = action[3]
        if ip_network(source, strict=False).version == family:
            if family == 6:
                action = (action[0], "ufw6-before-input", *action[2:])
            result.append(action)
    return tuple(result)


def _explicit_ipv6(config: FirewallConfig) -> bool:
    for rule in config.rules:
        if not rule.enabled:
            continue
        for value in (rule.source, rule.destination):
            if value and ip_network(value, strict=False).version == 6:
                return True
    return False


def compile_firewall(
    config: FirewallConfig,
    *,
    on_date: date | None = None,
) -> CompiledFirewall:
    """Compile local desired state into deterministic IPv4/IPv6 managed blocks."""
    cfg = normalize_config(config)
    managed_ids = managed_standard_rule_ids(cfg)

    ipv4: list[DesiredBlock] = []
    expired_bans = 0
    next_expiry: date | None = None

    for server in cfg.vpn_servers:
        if not any(rule.vpn_server_id == server.server_id for rule in cfg.rules):
            continue
        mapping = legacy_openvpn_mapping(cfg, server.server_id)
        rules, expired, expiry, label = compile_legacy_openvpn(
            mapping,
            on_date=on_date,
            interface=server.interface,
        )
        expired_bans += expired
        if expiry is not None and (next_expiry is None or expiry < next_expiry):
            next_expiry = expiry
        ipv4.append(DesiredBlock("openvpn", label, rules))

    hard4 = _hard_source_by_family(cfg, 4)
    hard6 = _hard_source_by_family(cfg, 6)
    ipv4.append(DesiredBlock("hard_sources", HARD_NAME, hard4))

    standard4: list[Rule] = []
    standard6: list[Rule] = []
    for rule in cfg.rules:
        if (
            not rule.enabled
            or rule.kind != "standard"
            or rule.rule_id in managed_ids
        ):
            continue
        standard4.extend(_compile_standard_rule(rule, 4))
        standard6.extend(_compile_standard_rule(rule, 6))
        if len(standard4) + len(standard6) > _MAX_COMPILED_ACTIONS:
            raise FirewallPolicyError("Firewall policy expands to too many actions.")

    ipv4.append(
        DesiredBlock("standard", STANDARD_NAME, tuple(standard4))
    )
    ipv6 = (
        DesiredBlock("hard_sources", HARD_NAME, hard6),
        DesiredBlock("standard", STANDARD_NAME, tuple(standard6)),
    )

    return CompiledFirewall(
        tuple(ipv4),
        ipv6,
        expired_bans,
        next_expiry,
        _explicit_ipv6(cfg),
    )


def _render_block(block: DesiredBlock) -> list[str]:
    lines = [
        f"# *** BOF {block.label}",
        "# Managed by SysApps Firewall Manager - do not edit inside this block",
    ]
    lines.extend(" ".join(rule) for rule in block.rules)
    lines.append(f"# *** EOF {block.label}")
    return lines


def _filter_commit_anchor(lines: list[str]) -> int:
    in_filter = False
    for index, raw in enumerate(lines):
        line = raw.strip()
        if line == "*filter":
            in_filter = True
            continue
        if in_filter and line == "COMMIT":
            return index
    raise FirewallPolicyError("Cannot find filter-table COMMIT in UFW rules.")


def build_candidate(
    current: str,
    desired: tuple[DesiredBlock, ...],
    *,
    allow_openvpn: bool,
) -> CandidateResult:
    """Replace only SysApps-owned managed blocks and preserve all other lines."""
    inspection = inspect_before_rules(current)
    if not allow_openvpn and inspection.openvpn:
        raise FirewallPolicyError("OpenVPN managed blocks are not valid in IPv6 rules.")

    desired_openvpn = {
        block.label for block in desired if block.kind == "openvpn"
    }
    current_openvpn = {block.label for block in inspection.openvpn}
    unexpected = current_openvpn - desired_openvpn
    if unexpected:
        raise FirewallPolicyError(
            "Existing OpenVPN managed block is not represented by local "
            "firewall.json: " + ", ".join(sorted(unexpected))
        )

    current_blocks: list[DesiredBlock] = [
        DesiredBlock(block.kind, block.label, block.rules)
        for block in inspection.openvpn
    ]
    if inspection.hard_sources is not None:
        current_blocks.append(DesiredBlock(
            "hard_sources",
            inspection.hard_sources.label,
            inspection.hard_sources.rules,
        ))
    if inspection.standard is not None:
        current_blocks.append(DesiredBlock(
            "standard",
            inspection.standard.label,
            inspection.standard.rules,
        ))

    current_hash = managed_digest(current_blocks)
    desired_hash = managed_digest(desired)
    current_rule_count = sum(len(block.rules) for block in current_blocks)
    desired_rule_count = sum(len(block.rules) for block in desired)
    if current_hash == desired_hash:
        return CandidateResult(
            current,
            False,
            current_hash,
            desired_hash,
            current_rule_count,
            desired_rule_count,
        )

    lines = current.splitlines()
    spans: list[tuple[int, int]] = [
        (block.first_line, block.last_line)
        for block in inspection.openvpn
    ]
    if inspection.hard_sources is not None:
        spans.append((
            inspection.hard_sources.first_line,
            inspection.hard_sources.last_line,
        ))
    if inspection.standard is not None:
        spans.append((
            inspection.standard.first_line,
            inspection.standard.last_line,
        ))

    if spans:
        ordered_spans = sorted(spans)
        for (_, previous_last), (next_first, _) in zip(
            ordered_spans,
            ordered_spans[1:],
        ):
            between = lines[previous_last:next_first - 1]
            if any(
                line.strip() and not line.lstrip().startswith("#")
                for line in between
            ):
                raise FirewallPolicyError(
                    "Unmanaged executable UFW rule exists between SysApps "
                    "managed blocks; refusing to change its precedence."
                )
        anchor = min(first for first, _ in spans) - 1
    else:
        anchors = [
            index for index, line in enumerate(lines)
            if line.strip() == _REQUIRED_ANCHOR
        ]
        anchor = anchors[0] + 1 if len(anchors) == 1 else _filter_commit_anchor(lines)

    skip: set[int] = set()
    for first, last in spans:
        skip.update(range(first - 1, last))

    rendered: list[str] = []
    for block in desired:
        rendered.extend(_render_block(block))

    result: list[str] = []
    inserted = False
    for index, line in enumerate(lines):
        if not inserted and index == anchor:
            result.extend(rendered)
            inserted = True
        if index not in skip:
            result.append(line)
    if not inserted:
        result.extend(rendered)

    payload = "\n".join(result) + ("\n" if current.endswith("\n") else "")
    verify = inspect_before_rules(payload)
    if not allow_openvpn and verify.openvpn:
        raise FirewallPolicyError("Generated IPv6 candidate contains OpenVPN block.")

    generated_blocks: list[DesiredBlock] = [
        DesiredBlock(block.kind, block.label, block.rules)
        for block in verify.openvpn
    ]
    if verify.hard_sources is not None:
        generated_blocks.append(DesiredBlock(
            "hard_sources",
            verify.hard_sources.label,
            verify.hard_sources.rules,
        ))
    if verify.standard is not None:
        generated_blocks.append(DesiredBlock(
            "standard",
            verify.standard.label,
            verify.standard.rules,
        ))
    if managed_digest(generated_blocks) != desired_hash:
        raise FirewallPolicyError("Generated managed UFW candidate failed read-back.")

    return CandidateResult(
        payload,
        True,
        current_hash,
        desired_hash,
        current_rule_count,
        desired_rule_count,
    )
