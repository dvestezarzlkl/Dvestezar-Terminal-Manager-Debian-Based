"""Local user-owned Firewall Manager configuration.

The canonical file is /etc/jb_sys_apps/firewall.json. This module never applies
UFW. It only validates, normalizes, imports legacy policy and atomically stores
local desired rules for this host.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from ipaddress import IPv4Address, ip_address, ip_network
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
from uuid import uuid4

from libs.JBLibs.helper import getConfigPath
from libs.app import g_def as defs

from .policy import FirewallPolicyError, UfwInspection, read_legacy_config

CONFIG_NAME = "firewall.json"
CONFIG_VERSION = 1
_RULE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_IFACE_RE = re.compile(r"^[a-zA-Z0-9_.+-]{1,15}$")
_ALLOWED_DIRECTIONS = {"input", "forward", "output"}
_ALLOWED_ACTIONS = {"allow", "deny", "reject"}
_ALLOWED_PROTOCOLS = {"any", "tcp", "udp", "icmp"}
_ALLOWED_KINDS = {"vpn_ban", "standard"}
_MAX_RULES = 5000


class FirewallConfigError(ValueError):
    pass


@dataclass(frozen=True)
class FirewallRule:
    rule_id: str
    kind: str
    enabled: bool = True
    name: str = ""
    source: str = ""
    destination: str = ""
    destination_invert: bool = False
    direction: str = "input"
    action: str = "allow"
    protocol: str = "any"
    port_from: int | None = None
    port_to: int | None = None
    src_ports: str = ""
    dst_ports: str = ""
    interface: str = ""
    ban_to: str = ""


@dataclass(frozen=True)
class FirewallConfig:
    version: int = CONFIG_VERSION
    openvpn_server_name: str = ""
    openvpn_server_ip: str = ""
    openvpn_server_mask: int | None = None
    openvpn_interface: str = "tun+"
    rules: tuple[FirewallRule, ...] = field(default_factory=tuple)


def config_path(*, create_dir: bool = False) -> Path:
    return getConfigPath(
        configName=CONFIG_NAME,
        appName=defs.APP_NAME,
        fromEtc=defs.CONFIG_ETC,
        createIfNotExist=create_dir,
    )


def new_rule_id() -> str:
    return uuid4().hex


def _network(value: object, label: str, *, required: bool) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise FirewallConfigError(f"{label} is required.")
        return ""
    try:
        return str(ip_network(text, strict=False))
    except ValueError as exc:
        raise FirewallConfigError(f"Invalid {label} IP/network.") from exc


def _port(value: object, label: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise FirewallConfigError(f"Invalid {label}.")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise FirewallConfigError(f"Invalid {label}.") from exc
    if not 1 <= result <= 65535:
        raise FirewallConfigError(f"{label} must be 1..65535.")
    return result


_PORT_LIST_RE = re.compile(r"^[0-9]{1,5}(?:-[0-9]{1,5})?(?:,[0-9]{1,5}(?:-[0-9]{1,5})?)*$")


def normalize_port_spec(value: object, label: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise FirewallConfigError(f"{label} must be a string.")
    text = value.strip()
    if len(text) > 1024:
        raise FirewallConfigError(f"{label} exceeds 1024 characters.")
    if not _PORT_LIST_RE.fullmatch(text):
        raise FirewallConfigError(f"Invalid {label}: expected 80,443,3000-3010.")
    ranges = []
    for token in text.split(","):
        lo, sep, hi = token.partition("-")
        a, b = int(lo), int(hi) if sep else int(lo)
        if not 1 <= a <= b <= 65535:
            raise FirewallConfigError(f"Invalid {label} range (1..65535).")
        ranges.append((a, b))
    ranges.sort()
    if any(a <= prev_b for (_, prev_b), (a, _) in zip(ranges, ranges[1:])):
        raise FirewallConfigError(f"Overlapping or duplicate {label} ranges.")
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


def normalize_rule(data: Mapping[str, Any] | FirewallRule) -> FirewallRule:
    raw = asdict(data) if isinstance(data, FirewallRule) else dict(data)
    rule_id = str(raw.get("rule_id") or "").strip().lower()
    if not _RULE_ID_RE.fullmatch(rule_id):
        raise FirewallConfigError("Invalid firewall rule_id.")
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in _ALLOWED_KINDS:
        raise FirewallConfigError("Unsupported firewall rule kind.")
    name = str(raw.get("name") or "").strip()
    if len(name) > 255 or "\n" in name or "\r" in name:
        raise FirewallConfigError("Invalid firewall rule name.")
    enabled = raw.get("enabled", True)
    if type(enabled) is not bool:
        raise FirewallConfigError("Firewall rule enabled must be boolean.")

    if kind == "vpn_ban":
        source = _network(raw.get("source"), "VPN BAN source", required=True)
        source_network = ip_network(source, strict=False)
        if source_network.prefixlen != source_network.max_prefixlen:
            raise FirewallConfigError("VPN BAN source must identify one IP.")
        if not isinstance(source_network.network_address, IPv4Address):
            raise FirewallConfigError("Legacy OpenVPN VPN BAN source must be IPv4.")
        ban_to = str(raw.get("ban_to") or "").strip()
        if ban_to:
            try:
                parsed = date.fromisoformat(ban_to)
            except ValueError as exc:
                raise FirewallConfigError("VPN BAN date must be YYYY-MM-DD.") from exc
            if parsed.isoformat() != ban_to:
                raise FirewallConfigError("VPN BAN date must be canonical YYYY-MM-DD.")
        return FirewallRule(
            rule_id=rule_id, kind=kind, enabled=enabled, name=name,
            source=source, direction="input", action="deny",
            protocol="any", ban_to=ban_to,
        )

    direction = str(raw.get("direction") or "").strip().lower()
    action = str(raw.get("action") or "").strip().lower()
    protocol = str(raw.get("protocol") or "").strip().lower()
    if direction not in _ALLOWED_DIRECTIONS:
        raise FirewallConfigError("Unsupported firewall direction.")
    if action not in _ALLOWED_ACTIONS:
        raise FirewallConfigError("Unsupported firewall action.")
    if protocol not in _ALLOWED_PROTOCOLS:
        raise FirewallConfigError("Unsupported firewall protocol.")
    source = _network(raw.get("source"), "source", required=False)
    destination = _network(raw.get("destination"), "destination", required=False)
    destination_invert = raw.get("destination_invert", False)
    if type(destination_invert) is not bool:
        raise FirewallConfigError("destination_invert must be boolean.")
    if destination_invert and not destination:
        raise FirewallConfigError("Inverted destination requires a destination.")
    interface = str(raw.get("interface") or "").strip()
    if interface and not _IFACE_RE.fullmatch(interface):
        raise FirewallConfigError("Invalid interface name.")
    port_from = _port(raw.get("port_from"), "port_from")
    port_to = _port(raw.get("port_to"), "port_to")
    if (port_from is None) != (port_to is None):
        raise FirewallConfigError("Both port_from and port_to must be set.")
    if port_from is not None and port_from > port_to:
        raise FirewallConfigError("port_from cannot exceed port_to.")
    src_ports = normalize_port_spec(raw.get("src_ports"), "source ports")
    dst_ports = normalize_port_spec(raw.get("dst_ports"), "destination ports")
    # Legacy version 1: a single range was shown beside the destination.
    if port_from is not None:
        legacy = str(port_from) if port_from == port_to else f"{port_from}-{port_to}"
        if dst_ports and dst_ports != legacy:
            raise FirewallConfigError("Conflicting legacy and destination ports.")
        dst_ports = legacy
    if protocol not in {"tcp", "udp"} and (port_from is not None or src_ports or dst_ports):
        raise FirewallConfigError("Ports are supported only for TCP/UDP.")

    return FirewallRule(
        rule_id=rule_id, kind=kind, enabled=enabled, name=name,
        source=source, destination=destination,
        destination_invert=destination_invert, direction=direction,
        action=action, protocol=protocol, port_from=None, port_to=None,
        src_ports=src_ports, dst_ports=dst_ports, interface=interface,
    )


def normalize_config(data: Mapping[str, Any] | FirewallConfig) -> FirewallConfig:
    raw = asdict(data) if isinstance(data, FirewallConfig) else dict(data)
    if raw.get("version", CONFIG_VERSION) != CONFIG_VERSION:
        raise FirewallConfigError("Unsupported firewall config version.")
    rules_raw = raw.get("rules", ())
    if not isinstance(rules_raw, (list, tuple)) or len(rules_raw) > _MAX_RULES:
        raise FirewallConfigError("Invalid firewall rules list.")
    rules = tuple(normalize_rule(item) for item in rules_raw)
    ids = [item.rule_id for item in rules]
    if len(ids) != len(set(ids)):
        raise FirewallConfigError("Duplicate firewall rule_id.")

    name = str(raw.get("openvpn_server_name") or "").strip()
    ip = str(raw.get("openvpn_server_ip") or "").strip()
    mask = raw.get("openvpn_server_mask")
    interface = str(raw.get("openvpn_interface") or "tun+").strip()
    if any(rule.kind == "vpn_ban" for rule in rules):
        if not name or "\n" in name or "\r" in name:
            raise FirewallConfigError("OpenVPN server name is required for VPN BAN rules.")
        if not ip:
            raise FirewallConfigError("OpenVPN server IP is required for VPN BAN rules.")
        try:
            parsed_openvpn_ip = ip_address(ip)
        except ValueError as exc:
            raise FirewallConfigError("Invalid OpenVPN server IP.") from exc
        if not isinstance(parsed_openvpn_ip, IPv4Address):
            raise FirewallConfigError("OpenVPN server IP must be IPv4.")
        ip = str(parsed_openvpn_ip)
        if type(mask) is not int or not 0 <= mask <= 32:
            raise FirewallConfigError("OpenVPN server mask must be 0..32.")
        if not _IFACE_RE.fullmatch(interface):
            raise FirewallConfigError("Invalid OpenVPN interface.")
    elif mask is not None and (type(mask) is not int or not 0 <= mask <= 32):
        raise FirewallConfigError("OpenVPN server mask must be 0..32.")
    if len(name) > 128:
        raise FirewallConfigError("OpenVPN server name is too long.")

    return FirewallConfig(
        version=CONFIG_VERSION,
        openvpn_server_name=name,
        openvpn_server_ip=ip,
        openvpn_server_mask=mask,
        openvpn_interface=interface or "tun+",
        rules=rules,
    )


def load_config(path: Path | None = None) -> FirewallConfig:
    target = path or config_path(create_dir=False)
    if not target.exists():
        return FirewallConfig()
    if target.is_symlink():
        raise FirewallConfigError("Firewall config must not be a symlink.")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise FirewallConfigError("Cannot read firewall.json.") from exc
    if not isinstance(raw, dict):
        raise FirewallConfigError("firewall.json must contain a JSON object.")
    return normalize_config(raw)


def save_config(config: FirewallConfig, path: Path | None = None) -> Path:
    normalized = normalize_config(config)
    target = path or config_path(create_dir=True)
    if target.exists() and target.is_symlink():
        raise FirewallConfigError("Firewall config must not be a symlink.")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(normalized)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


def replace_rule(config: FirewallConfig, rule: FirewallRule) -> FirewallConfig:
    normalized = normalize_rule(rule)
    changed = False
    items: list[FirewallRule] = []
    for item in config.rules:
        if item.rule_id == normalized.rule_id:
            items.append(normalized)
            changed = True
        else:
            items.append(item)
    if not changed:
        raise FirewallConfigError("Firewall rule was not found.")
    return normalize_config({**asdict(config), "rules": [asdict(x) for x in items]})


def append_rule(config: FirewallConfig, rule: FirewallRule) -> FirewallConfig:
    normalized = normalize_rule(rule)
    if any(item.rule_id == normalized.rule_id for item in config.rules):
        raise FirewallConfigError("Duplicate firewall rule_id.")
    return normalize_config({
        **asdict(config),
        "rules": [*(asdict(x) for x in config.rules), asdict(normalized)],
    })


def delete_rule(config: FirewallConfig, rule_id: str) -> FirewallConfig:
    rules = [item for item in config.rules if item.rule_id != rule_id]
    if len(rules) == len(config.rules):
        raise FirewallConfigError("Firewall rule was not found.")
    return normalize_config({
        **asdict(config),
        "rules": [asdict(x) for x in rules],
    })


def import_legacy(path: Path, inspection: UfwInspection | None = None) -> FirewallConfig:
    """Convert old OpenVPN JSON/JS and optionally current hard-source rules."""
    legacy = read_legacy_config(path)
    rules: list[FirewallRule] = []
    for client in legacy.get("clients", []):
        kind = client.get("type")
        if kind == 1:
            rules.append(FirewallRule(
                new_rule_id(), "vpn_ban", True,
                str(client.get("clientName") or "").strip(),
                source=str(client.get("clientIP") or "").strip(),
                ban_to=str(client.get("banTo") or "").strip(),
            ))
        elif kind == 2:
            rules.append(FirewallRule(
                new_rule_id(), "standard", True,
                str(client.get("clientName") or "").strip() + " - VPN isolation",
                source=str(client.get("clientIP") or "").strip(),
                destination=str(legacy.get("server_ip") or "").strip(),
                destination_invert=True, direction="forward", action="deny",
                protocol="any", interface="tun+",
            ))
    if inspection is not None and inspection.hard_sources is not None:
        for action in inspection.hard_sources.rules:
            # Adopt only the exact legacy hard-source semantic. Unknown actions
            # stay outside local config and require explicit operator review.
            if (
                len(action) == 6 and action[:2] == ("-A", "ufw-before-input")
                and action[2] == "-s" and action[4:] == ("-j", "ACCEPT")
            ):
                source = action[3]
                rules.append(FirewallRule(
                    new_rule_id(), "standard", True,
                    f"Imported trusted source {source}", source=source,
                    direction="input", action="allow", protocol="any",
                ))

    return normalize_config({
        "version": CONFIG_VERSION,
        "openvpn_server_name": legacy.get("server_name", ""),
        "openvpn_server_ip": legacy.get("server_ip", ""),
        "openvpn_server_mask": legacy.get("server_mask"),
        "openvpn_interface": "tun+",
        "rules": [asdict(rule) for rule in rules],
    })


def legacy_openvpn_mapping(config: FirewallConfig) -> dict[str, Any]:
    """Build the old semantic OpenVPN policy shape from canonical local rules."""
    cfg = normalize_config(config)
    clients: list[dict[str, Any]] = []
    for rule in cfg.rules:
        if not rule.enabled:
            continue
        if rule.kind == "vpn_ban":
            source = str(ip_network(rule.source, strict=False).network_address)
            clients.append({
                "clientName": rule.name,
                "clientIP": source,
                "type": 1,
                "banTo": rule.ban_to or None,
            })
            continue
        # Preserve the legacy "may reach VPN server but not forward elsewhere"
        # semantic imported from type=2 as a standard rule.
        if (
            rule.kind == "standard"
            and rule.direction == "forward"
            and rule.action == "deny"
            and rule.protocol == "any"
            and rule.destination_invert
            and rule.destination
            and cfg.openvpn_server_ip
            and str(ip_network(rule.destination, strict=False).network_address)
                == str(ip_network(cfg.openvpn_server_ip, strict=False).network_address)
            and (not rule.interface or rule.interface == cfg.openvpn_interface)
        ):
            source = str(ip_network(rule.source, strict=False).network_address)
            clients.append({
                "clientName": rule.name,
                "clientIP": source,
                "type": 2,
            })
    return {
        "server_name": cfg.openvpn_server_name,
        "server_ip": cfg.openvpn_server_ip,
        "server_mask": cfg.openvpn_server_mask,
        "clients": clients,
    }


def hard_source_rules(config: FirewallConfig) -> tuple[tuple[str, ...], ...]:
    """Compile standard all-port trusted INPUT rules matching legacy hard-source semantics."""
    cfg = normalize_config(config)
    result: list[tuple[str, ...]] = []
    for rule in cfg.rules:
        if not rule.enabled or rule.kind != "standard":
            continue
        if (
            rule.direction == "input"
            and rule.action == "allow"
            and rule.protocol == "any"
            and rule.source
            and not rule.destination
            and not rule.destination_invert
            and not rule.src_ports and not rule.dst_ports
            and not rule.interface
        ):
            source = rule.source
            if source.endswith("/32") or source.endswith("/128"):
                source = str(ip_network(source, strict=False).network_address)
            result.append(("-A", "ufw-before-input", "-s", source, "-j", "ACCEPT"))
    return tuple(result)


def managed_standard_rule_ids(config: FirewallConfig) -> set[str]:
    """IDs currently representable by the legacy hard-source block."""
    cfg = normalize_config(config)
    managed: set[str] = set()
    for rule in cfg.rules:
        if (
            rule.enabled and rule.kind == "standard"
            and rule.direction == "input" and rule.action == "allow"
            and rule.protocol == "any" and rule.source
            and not rule.destination and not rule.destination_invert
            and not rule.src_ports and not rule.dst_ports and not rule.interface
        ):
            managed.add(rule.rule_id)
        elif (
            rule.enabled and rule.kind == "standard"
            and rule.direction == "forward" and rule.action == "deny"
            and rule.protocol == "any" and rule.destination_invert
            and rule.destination and rule.source
            and config.openvpn_server_ip
            and str(ip_network(rule.destination, strict=False).network_address)
                == str(ip_network(config.openvpn_server_ip, strict=False).network_address)
            and (not rule.interface or rule.interface == config.openvpn_interface)
        ):
            managed.add(rule.rule_id)
    return managed
