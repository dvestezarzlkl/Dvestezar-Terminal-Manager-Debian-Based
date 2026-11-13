"""SSH-management safety analysis for Firewall Manager.

This module is pure: it parses SSH runtime/config data and decides whether
changed firewall rules may affect an SSH management path. It never mutates UFW.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
import re
from typing import Iterable, Mapping

from .compiler import CompiledFirewall
from .policy import Rule, inspect_before_rules


@dataclass(frozen=True)
class SshManagementPath:
    server_port: int
    client_ip: str = ""
    client_port: int | None = None
    server_ip: str = ""


def current_ssh_path(
    env: Mapping[str, str] | None = None,
) -> SshManagementPath | None:
    source = __import__("os").environ if env is None else env
    raw = str(source.get("SSH_CONNECTION", "")).strip()
    parts = raw.split()
    if len(parts) != 4:
        return None
    client_ip, client_port_raw, server_ip, server_port_raw = parts
    try:
        ip_address(client_ip)
        ip_address(server_ip)
        client_port = int(client_port_raw)
        server_port = int(server_port_raw)
    except (ValueError, TypeError):
        return None
    if not 1 <= client_port <= 65535 or not 1 <= server_port <= 65535:
        return None
    return SshManagementPath(
        server_port=server_port,
        client_ip=client_ip,
        client_port=client_port,
        server_ip=server_ip,
    )


def parse_sshd_ports(output: str) -> tuple[int, ...]:
    ports: set[int] = set()
    for raw in output.splitlines():
        parts = raw.strip().split()
        if len(parts) != 2 or parts[0].lower() != "port":
            continue
        try:
            port = int(parts[1])
        except ValueError:
            continue
        if 1 <= port <= 65535:
            ports.add(port)
    return tuple(sorted(ports))


def configured_ssh_paths(output: str) -> tuple[SshManagementPath, ...]:
    return tuple(SshManagementPath(server_port=port) for port in parse_sshd_ports(output))


def _flatten_current(content: str) -> tuple[Rule, ...]:
    inspection = inspect_before_rules(content)
    result: list[Rule] = []
    for block in inspection.openvpn:
        result.extend(block.rules)
    if inspection.hard_sources is not None:
        result.extend(inspection.hard_sources.rules)
    if inspection.standard is not None:
        result.extend(inspection.standard.rules)
    return tuple(result)


def _flatten_desired(
    compiled: CompiledFirewall,
    family: int,
) -> tuple[Rule, ...]:
    blocks = compiled.ipv4 if family == 4 else compiled.ipv6
    return tuple(rule for block in blocks for rule in block.rules)


def _changed_rules(
    current: tuple[Rule, ...],
    desired: tuple[Rule, ...],
) -> tuple[Rule, ...]:
    if current == desired:
        return ()
    current_counts = Counter(current)
    desired_counts = Counter(desired)
    changed: list[Rule] = []
    for rule, count in (current_counts - desired_counts).items():
        changed.extend([rule] * count)
    for rule, count in (desired_counts - current_counts).items():
        changed.extend([rule] * count)
    # A pure reordering can still alter first-match firewall semantics.
    if not changed:
        return current + desired
    return tuple(changed)


def _option(rule: Rule, name: str) -> str:
    try:
        index = rule.index(name)
    except ValueError:
        return ""
    if index + 1 >= len(rule):
        return ""
    return rule[index + 1]


def _port_matches(spec: str, port: int | None) -> bool:
    if not spec:
        return True
    if port is None:
        return True
    for term in spec.split(","):
        lo_text, sep, hi_text = term.partition(":")
        try:
            lo = int(lo_text)
            hi = int(hi_text) if sep else lo
        except ValueError:
            return True
        if lo <= port <= hi:
            return True
    return False


def _address_matches(
    network_text: str,
    address_text: str,
    *,
    inverted: bool = False,
) -> bool:
    if not network_text or not address_text:
        return True
    try:
        matched = ip_address(address_text) in ip_network(network_text, strict=False)
    except ValueError:
        return True
    return not matched if inverted else matched


def rule_may_match_ssh(rule: Rule, path: SshManagementPath) -> bool:
    if len(rule) < 4 or rule[0] != "-A":
        return True
    chain = rule[1]
    if not chain.endswith("-input"):
        return False

    protocol = _option(rule, "-p")
    if protocol and protocol != "tcp":
        return False

    if path.server_ip:
        server_version = ip_address(path.server_ip).version
        if server_version == 6 and not chain.startswith("ufw6-"):
            return False
        if server_version == 4 and chain.startswith("ufw6-"):
            return False

    if not _address_matches(_option(rule, "-s"), path.client_ip):
        return False

    destination = _option(rule, "-d")
    inverted_destination = False
    if destination:
        destination_index = rule.index("-d")
        inverted_destination = destination_index > 0 and rule[destination_index - 1] == "!"
    if not _address_matches(
        destination,
        path.server_ip,
        inverted=inverted_destination,
    ):
        return False

    if not _port_matches(_option(rule, "--sport"), path.client_port):
        return False
    if not _port_matches(_option(rule, "--dport"), path.server_port):
        return False

    # Interface matches are deliberately not used to prove safety. The current
    # ingress interface is not reliably available from SSH_CONNECTION alone,
    # so ignoring -i can only create a conservative extra acknowledgement.
    return True


def managed_change_requires_ssh_ack(
    *,
    before4: str,
    before6: str | None,
    compiled: CompiledFirewall,
    paths: Iterable[SshManagementPath],
) -> bool:
    probes = tuple(paths)
    if not probes:
        return True

    current4 = _flatten_current(before4)
    desired4 = _flatten_desired(compiled, 4)
    changed4 = _changed_rules(current4, desired4)

    changed6: tuple[Rule, ...] = ()
    if before6 is not None:
        changed6 = _changed_rules(
            _flatten_current(before6),
            _flatten_desired(compiled, 6),
        )

    for probe in probes:
        for rule in changed4 + changed6:
            if rule_may_match_ssh(rule, probe):
                return True
    return False


_NATIVE_PERMISSIVE_IN = re.compile(
    r"^(?P<to>.+?)\s+(?P<action>ALLOW|LIMIT)\s+IN\s+(?P<from>.+)$",
    re.IGNORECASE,
)
_PORT_TOKEN = re.compile(
    r"^(?P<ports>\d+(?:(?:,|:|-)\d+)*)?(?:/(?P<proto>tcp|udp))?$",
    re.IGNORECASE,
)


def _native_target_port_may_match(to_text: str, server_port: int) -> bool:
    cleaned = to_text.replace("(v6)", "").strip()
    if not cleaned or cleaned.lower() == "anywhere":
        return True

    token = cleaned.split()[-1]
    match = _PORT_TOKEN.fullmatch(token)
    if match is None or not match.group("ports"):
        # Named UFW application profiles (OpenSSH, SSH, custom profiles) are
        # intentionally treated as unknown/maybe-SSH rather than guessed safe.
        return True
    if (match.group("proto") or "tcp").lower() == "udp":
        return False

    for raw in re.split(r",", match.group("ports")):
        lo_text, sep, hi_text = re.split(r"(:|-)", raw, maxsplit=1) if (":" in raw or "-" in raw) else (raw, "", "")
        try:
            lo = int(lo_text)
            hi = int(hi_text) if sep else lo
        except ValueError:
            return True
        if lo <= server_port <= hi:
            return True
    return False


def native_rule_requires_ssh_ack(
    rule_text: str,
    paths: Iterable[SshManagementPath],
) -> bool:
    match = _NATIVE_PERMISSIVE_IN.match(rule_text.strip())
    if match is None:
        return False

    probes = tuple(paths)
    if not probes:
        # Deleting a permissive inbound rule is potentially access-breaking
        # when the effective SSH port cannot be identified.
        return True

    rule_is_v6 = "(v6)" in rule_text.lower()
    for probe in probes:
        if probe.server_ip:
            version = ip_address(probe.server_ip).version
            if version == 6 and not rule_is_v6:
                continue
            if version == 4 and rule_is_v6:
                continue
        if _native_target_port_may_match(
            match.group("to"),
            probe.server_port,
        ):
            return True
    return False
