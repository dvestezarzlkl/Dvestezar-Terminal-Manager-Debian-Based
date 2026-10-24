"""Pure, read-only UFW legacy block inspection and effective-rule planning.

This module NEVER writes files, modifies system state or invokes UFW.
Future transactional Apply must be a separate, explicitly guarded component.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from ipaddress import IPv4Address, ip_address, ip_network
import json
from pathlib import Path
import re
import shlex
from typing import Any, Mapping

# Markers as found in the deployed new21 /etc/ufw/before.rules.
_MARKER = re.compile(
    r"^#\s*\*\*\*\s*(BOF|EOF)\s+"
    r"(OpenVPN JB Config - .+|ZLKL Hard Source Allow Config - managed by sys_apps)\s*$"
)
_OPENVPN_PREFIX = "OpenVPN JB Config - "
_HARD_NAME = "ZLKL Hard Source Allow Config - managed by sys_apps"
_IFACE = re.compile(r"^[a-zA-Z0-9_.+-]{1,15}$")
_MAX_SOURCE_BYTES = 1_048_576
_MAX_CLIENTS = 10000


class FirewallPolicyError(ValueError):
    """Invalid or ambiguous policy/managed UFW block; never auto-apply."""


Rule = tuple[str, ...]


@dataclass(frozen=True)
class ManagedBlock:
    kind: str
    label: str
    first_line: int
    last_line: int
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class UfwInspection:
    openvpn: tuple[ManagedBlock, ...]
    hard_sources: ManagedBlock | None


@dataclass(frozen=True)
class FirewallPlan:
    status: str  # NO_CHANGE / CHANGED / MISSING / REVIEW
    current_hash: str
    effective_hash: str
    current_rules: int
    effective_rules: int
    expired_bans: int
    next_expiry: date | None
    reason: str = ""


def _parse_action(line: str) -> Rule:
    try:
        args = shlex.split(line, posix=True)
    except ValueError as exc:
        raise FirewallPolicyError("Malformed managed UFW rule.") from exc
    if len(args) < 4 or args[0] != "-A":
        raise FirewallPolicyError("Unrecognized executable line in managed UFW block.")
    # The legacy script appends an iptables comment to each DROP action.
    # A changed display name or audit timestamp must NOT alter rule semantics.
    output: list[str] = []
    index = 0
    while index < len(args):
        if args[index:index + 3] == ["-m", "comment", "--comment"]:
            if index + 3 >= len(args):
                raise FirewallPolicyError("Malformed iptables comment.")
            index += 4
        else:
            output.append(args[index])
            index += 1
    return tuple(output)


def _action_lines(lines: list[str]) -> tuple[Rule, ...]:
    actions: list[Rule] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        actions.append(_parse_action(line))
    return tuple(actions)


def inspect_before_rules(content: str) -> UfwInspection:
    """Parse owned blocks; allow multiple uniquely identified OpenVPN servers."""
    started: tuple[str, str, int, list[str]] | None = None
    openvpn_blocks: list[ManagedBlock] = []
    hard_sources: ManagedBlock | None = None
    openvpn_labels: set[str] = set()

    for lineno, original in enumerate(content.splitlines(), 1):
        line = original.strip()
        match = _MARKER.fullmatch(line)
        if match:
            boundary, label = match.groups()
            kind = "openvpn" if label.startswith(_OPENVPN_PREFIX) else "hard_sources"
            if boundary == "BOF":
                if started is not None:
                    raise FirewallPolicyError("Nested managed UFW block.")
                if kind == "openvpn":
                    if label in openvpn_labels:
                        raise FirewallPolicyError("Duplicate OpenVPN managed block.")
                elif hard_sources is not None:
                    raise FirewallPolicyError("Duplicate Hard Source managed block.")
                started = (kind, label, lineno, [])
            else:
                if started is None:
                    raise FirewallPolicyError("Managed UFW EOF without BOF.")
                active_kind, active_label, first_line, section = started
                if label != active_label or kind != active_kind:
                    raise FirewallPolicyError("Managed UFW BOF/EOF marker mismatch.")
                block = ManagedBlock(
                    kind, label, first_line, lineno, _action_lines(section)
                )
                if kind == "openvpn":
                    openvpn_blocks.append(block)
                    openvpn_labels.add(label)
                else:
                    hard_sources = block
                started = None
            continue
        if started is not None:
            started[3].append(original)

    if started is not None:
        raise FirewallPolicyError("Managed UFW BOF without EOF.")

    if hard_sources is not None:
        if any(block.last_line >= hard_sources.first_line for block in openvpn_blocks):
            raise FirewallPolicyError(
                "All OpenVPN BAN blocks must precede Hard Source Allow block."
            )
    return UfwInspection(tuple(openvpn_blocks), hard_sources)

def rules_digest(rules: tuple[Rule, ...]) -> str:
    """SHA-256 of ordered effective iptables actions, not generated comments."""
    serialized = json.dumps(rules, separators=(",", ":"), ensure_ascii=True)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _ipv4(value: object, label: str) -> str:
    try:
        parsed = ip_address(str(value))
    except ValueError as exc:
        raise FirewallPolicyError(f"Invalid {label}.") from exc
    if not isinstance(parsed, IPv4Address):
        raise FirewallPolicyError(f"{label} must be IPv4 for legacy OpenVPN.")
    return str(parsed)


def read_legacy_config(path: Path) -> dict[str, Any]:
    """Parse only JSON after the old JS file's exact BOF marker; no execution."""
    try:
        if path.stat().st_size > _MAX_SOURCE_BYTES:
            raise FirewallPolicyError("Legacy policy file exceeds size limit.")
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FirewallPolicyError("Cannot read legacy UFW policy file.") from exc
    lines = source.splitlines()
    starts = [i for i, text in enumerate(lines) if text.strip() == "// BOF JSON CFG"]
    if len(starts) != 1:
        raise FirewallPolicyError("Expected one legacy JSON BOF marker.")
    try:
        cfg = json.loads("\n".join(lines[starts[0] + 1:]))
    except (ValueError, TypeError) as exc:
        raise FirewallPolicyError("Invalid legacy JSON policy.") from exc
    if not isinstance(cfg, dict):
        raise FirewallPolicyError("Legacy policy must be a JSON object.")
    return cfg


def compile_legacy_openvpn(
    cfg: Mapping[str, Any],
    *,
    on_date: date | None = None,
    interface: str = "tun+",
) -> tuple[tuple[Rule, ...], int, date | None, str]:
    """Compile only executable IPv4 actions, with full-day BAN expiry.

    BAN valid to YYYY-MM-DD remains enforced through that calendar day.
    Expiry changes effective rules even when source JSON never changes.
    """
    today = on_date if on_date is not None else datetime.now().astimezone().date()
    if not isinstance(today, date):
        raise FirewallPolicyError("Invalid policy evaluation date.")
    if not _IFACE.fullmatch(interface):
        raise FirewallPolicyError("Invalid OpenVPN interface name.")
    server = _ipv4(cfg.get("server_ip"), "server_ip")
    mask = cfg.get("server_mask")
    if type(mask) is not int or not 0 <= mask <= 32:
        raise FirewallPolicyError("Invalid server_mask.")
    network = ip_network(f"{server}/{mask}", strict=False)
    name = cfg.get("server_name")
    if not isinstance(name, str) or not name.strip() or "\n" in name or "\r" in name:
        raise FirewallPolicyError("Invalid server_name.")
    clients = cfg.get("clients")
    if not isinstance(clients, list) or len(clients) > _MAX_CLIENTS:
        raise FirewallPolicyError("Invalid clients list.")

    rules: list[Rule] = []
    seen: set[str] = set()
    expired = 0
    next_expiry: date | None = None
    for client in clients:
        if not isinstance(client, dict):
            raise FirewallPolicyError("Invalid OpenVPN client.")
        address = _ipv4(client.get("clientIP"), "clientIP")
        if address in seen:
            raise FirewallPolicyError("Duplicate OpenVPN client IP.")
        seen.add(address)
        kind = client.get("type")
        if type(kind) is not int or kind not in (0, 1, 2):
            raise FirewallPolicyError("Unsupported OpenVPN client type.")
        if kind == 0:
            continue
        prefix: Rule = ("-i", interface, "-s", address)
        if kind == 2:
            rules.append(
                ("-A", "ufw-before-forward", *prefix, "!", "-d", server, "-j", "DROP")
            )
            continue
        expiry: date | None = None
        ban_to = client.get("banTo")
        if ban_to not in (None, ""):
            if not isinstance(ban_to, str):
                raise FirewallPolicyError("Invalid banTo.")
            try:
                expiry = date.fromisoformat(ban_to)
                if expiry.isoformat() != ban_to:
                    raise ValueError("Non-canonical date")
            except ValueError as exc:
                raise FirewallPolicyError("Invalid banTo date (YYYY-MM-DD).") from exc
            if today > expiry:
                expired += 1
                continue
            next_day = expiry + timedelta(days=1)
            if next_expiry is None or next_day < next_expiry:
                next_expiry = next_day
        rules.append(("-A", "ufw-before-forward", *prefix, "-j", "DROP"))
        rules.append(("-A", "ufw-before-input", *prefix, "-j", "DROP"))

    label = f"{_OPENVPN_PREFIX}{name.strip()} {network.with_prefixlen}"
    return tuple(rules), expired, next_expiry, label


def plan_legacy_openvpn(
    before_rules: str,
    cfg: Mapping[str, Any],
    *,
    on_date: date | None = None,
    interface: str = "tun+",
) -> FirewallPlan:
    """Pure comparison for one server against a multi-server before.rules."""
    inspection = inspect_before_rules(before_rules)
    expected, expired, next_expiry, label = compile_legacy_openvpn(
        cfg, on_date=on_date, interface=interface
    )
    matches = [block for block in inspection.openvpn if block.label == label]
    old = matches[0] if matches else None
    old_rules = old.rules if old is not None else ()
    current_hash = rules_digest(old_rules)
    effective_hash = rules_digest(expected)
    if old is None:
        if inspection.openvpn:
            status, reason = (
                "REVIEW",
                "Matching OpenVPN managed block not found; existing server blocks require review.",
            )
        else:
            status, reason = "MISSING", "OpenVPN managed UFW block not found."
    elif current_hash == effective_hash:
        status, reason = "NO_CHANGE", ""
    else:
        status, reason = "CHANGED", "Effective OpenVPN UFW rules differ."
    return FirewallPlan(
        status, current_hash, effective_hash, len(old_rules),
        len(expected), expired, next_expiry, reason,
    )
