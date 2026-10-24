"""Local user-owned Firewall Manager configuration.

The canonical file is /etc/jb_sys_apps/firewall.json. This module never applies
UFW. It only validates, normalizes, imports legacy policy and atomically stores
local desired rules for this host.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from hashlib import sha256
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
CONFIG_VERSION = 2
_LEGACY_CONFIG_VERSION = 1
_RULE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SERVER_ID_RE = _RULE_ID_RE
_IFACE_RE = re.compile(r"^[a-zA-Z0-9_.+-]{1,15}$")
_ALLOWED_DIRECTIONS = {"input", "forward", "output"}
_ALLOWED_ACTIONS = {"allow", "deny", "reject"}
_ALLOWED_PROTOCOLS = {"any", "tcp", "udp", "icmp"}
_ALLOWED_KINDS = {"vpn_ban", "standard"}
_MAX_RULES = 5000


class FirewallConfigError(ValueError):
    pass


@dataclass(frozen=True)
class FirewallVpnServer:
    server_id: str
    name: str
    ip: str
    mask: int
    interface: str = "tun+"


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
    vpn_server_id: str = ""


@dataclass(frozen=True)
class FirewallConfig:
    version: int = CONFIG_VERSION
    vpn_servers: tuple[FirewallVpnServer, ...] = field(default_factory=tuple)
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


def new_server_id() -> str:
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

    vpn_server_id = str(raw.get("vpn_server_id") or "").strip().lower()
    if vpn_server_id and not _SERVER_ID_RE.fullmatch(vpn_server_id):
        raise FirewallConfigError("Invalid VPN server ID.")

    if kind == "vpn_ban":
        if not vpn_server_id:
            raise FirewallConfigError("VPN BAN rule requires vpn_server_id.")
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
            protocol="any", ban_to=ban_to, vpn_server_id=vpn_server_id,
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
        vpn_server_id=vpn_server_id,
    )


def normalize_vpn_server(
    data: Mapping[str, Any] | FirewallVpnServer,
) -> FirewallVpnServer:
    raw = asdict(data) if isinstance(data, FirewallVpnServer) else dict(data)
    server_id = str(raw.get("server_id") or "").strip().lower()
    if not _SERVER_ID_RE.fullmatch(server_id):
        raise FirewallConfigError("Invalid VPN server ID.")
    name = str(raw.get("name") or "").strip()
    if not name or len(name) > 128 or "\n" in name or "\r" in name:
        raise FirewallConfigError("Invalid OpenVPN server name.")
    try:
        parsed_ip = ip_address(str(raw.get("ip") or "").strip())
    except ValueError as exc:
        raise FirewallConfigError("Invalid OpenVPN server IP.") from exc
    if not isinstance(parsed_ip, IPv4Address):
        raise FirewallConfigError("OpenVPN server IP must be IPv4.")
    mask = raw.get("mask")
    if type(mask) is not int or not 0 <= mask <= 32:
        raise FirewallConfigError("OpenVPN server mask must be 0..32.")
    interface = str(raw.get("interface") or "tun+").strip()
    if not _IFACE_RE.fullmatch(interface):
        raise FirewallConfigError("Invalid OpenVPN interface.")
    return FirewallVpnServer(
        server_id=server_id,
        name=name,
        ip=str(parsed_ip),
        mask=mask,
        interface=interface,
    )


def _legacy_server_id(name: str, ip: str, mask: object, interface: str) -> str:
    seed = f"legacy-vpn\0{name}\0{ip}\0{mask}\0{interface}"
    return sha256(seed.encode("utf-8")).hexdigest()[:32]


def _legacy_standard_isolation(
    raw_rule: Mapping[str, Any],
    server_ip: str,
    interface: str,
) -> bool:
    if (
        str(raw_rule.get("kind") or "").lower() != "standard"
        or str(raw_rule.get("direction") or "").lower() != "forward"
        or str(raw_rule.get("action") or "").lower() != "deny"
        or str(raw_rule.get("protocol") or "").lower() != "any"
        or raw_rule.get("destination_invert") is not True
    ):
        return False
    destination = str(raw_rule.get("destination") or "").strip()
    if not destination:
        return False
    try:
        same_destination = (
            str(ip_network(destination, strict=False).network_address)
            == str(ip_address(server_ip))
        )
    except ValueError:
        return False
    rule_interface = str(raw_rule.get("interface") or "").strip()
    return same_destination and (
        not rule_interface or rule_interface == interface
    )


def _migrate_v1(raw: Mapping[str, Any]) -> dict[str, Any]:
    rules_raw = raw.get("rules", ())
    if not isinstance(rules_raw, (list, tuple)):
        raise FirewallConfigError("Invalid firewall rules list.")
    name = str(raw.get("openvpn_server_name") or "").strip()
    ip = str(raw.get("openvpn_server_ip") or "").strip()
    mask = raw.get("openvpn_server_mask")
    interface = str(raw.get("openvpn_interface") or "tun+").strip()
    needs_server = any(
        isinstance(item, Mapping)
        and str(item.get("kind") or "").strip().lower() == "vpn_ban"
        for item in rules_raw
    ) or any(
        isinstance(item, Mapping)
        and ip
        and _legacy_standard_isolation(item, ip, interface)
        for item in rules_raw
    )

    server: dict[str, Any] | None = None
    server_id = ""
    if needs_server:
        server_id = _legacy_server_id(name, ip, mask, interface)
        server = {
            "server_id": server_id,
            "name": name,
            "ip": ip,
            "mask": mask,
            "interface": interface,
        }

    migrated_rules: list[dict[str, Any]] = []
    for item in rules_raw:
        if not isinstance(item, Mapping):
            raise FirewallConfigError("Invalid firewall rule.")
        converted = dict(item)
        kind = str(converted.get("kind") or "").strip().lower()
        if server_id and (
            kind == "vpn_ban"
            or _legacy_standard_isolation(converted, ip, interface)
        ):
            converted["vpn_server_id"] = server_id
        migrated_rules.append(converted)

    return {
        "version": CONFIG_VERSION,
        "vpn_servers": [server] if server is not None else [],
        "rules": migrated_rules,
    }


def normalize_config(data: Mapping[str, Any] | FirewallConfig) -> FirewallConfig:
    raw = asdict(data) if isinstance(data, FirewallConfig) else dict(data)
    version = raw.get("version", _LEGACY_CONFIG_VERSION)
    if version == _LEGACY_CONFIG_VERSION:
        raw = _migrate_v1(raw)
    elif version != CONFIG_VERSION:
        raise FirewallConfigError("Unsupported firewall config version.")

    servers_raw = raw.get("vpn_servers", ())
    if not isinstance(servers_raw, (list, tuple)):
        raise FirewallConfigError("Invalid VPN server list.")
    servers = tuple(normalize_vpn_server(item) for item in servers_raw)
    server_ids = [item.server_id for item in servers]
    if len(server_ids) != len(set(server_ids)):
        raise FirewallConfigError("Duplicate VPN server ID.")
    marker_ids = [
        (
            item.name,
            str(ip_network(f"{item.ip}/{item.mask}", strict=False)),
        )
        for item in servers
    ]
    if len(marker_ids) != len(set(marker_ids)):
        raise FirewallConfigError(
            "Duplicate VPN server marker identity (name + network)."
        )
    server_map = {item.server_id: item for item in servers}

    rules_raw = raw.get("rules", ())
    if not isinstance(rules_raw, (list, tuple)) or len(rules_raw) > _MAX_RULES:
        raise FirewallConfigError("Invalid firewall rules list.")
    rules = tuple(normalize_rule(item) for item in rules_raw)
    rule_ids = [item.rule_id for item in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise FirewallConfigError("Duplicate firewall rule_id.")

    for rule in rules:
        if rule.vpn_server_id and rule.vpn_server_id not in server_map:
            raise FirewallConfigError(
                f"Firewall rule references unknown VPN server: {rule.vpn_server_id}."
            )
        if rule.kind == "vpn_ban" and not rule.vpn_server_id:
            raise FirewallConfigError("VPN BAN rule requires a VPN server.")

    return FirewallConfig(
        version=CONFIG_VERSION,
        vpn_servers=servers,
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


def append_vpn_server(
    config: FirewallConfig,
    server: FirewallVpnServer,
) -> FirewallConfig:
    normalized = normalize_vpn_server(server)
    if any(item.server_id == normalized.server_id for item in config.vpn_servers):
        raise FirewallConfigError("Duplicate VPN server ID.")
    return normalize_config({
        **asdict(config),
        "vpn_servers": [
            *(asdict(item) for item in config.vpn_servers),
            asdict(normalized),
        ],
    })


def replace_vpn_server(
    config: FirewallConfig,
    server: FirewallVpnServer,
) -> FirewallConfig:
    normalized = normalize_vpn_server(server)
    existing = next(
        (item for item in config.vpn_servers if item.server_id == normalized.server_id),
        None,
    )
    if existing is None:
        raise FirewallConfigError("VPN server was not found.")

    servers = [
        normalized if item.server_id == normalized.server_id else item
        for item in config.vpn_servers
    ]
    rules: list[FirewallRule] = []
    for rule in config.rules:
        if rule.vpn_server_id != normalized.server_id or rule.kind != "standard":
            rules.append(rule)
            continue
        if (
            rule.direction == "forward"
            and rule.action == "deny"
            and rule.protocol == "any"
            and rule.destination_invert
        ):
            rules.append(FirewallRule(
                **{
                    **asdict(rule),
                    "destination": normalized.ip,
                    "interface": normalized.interface,
                }
            ))
        else:
            rules.append(rule)
    return normalize_config({
        **asdict(config),
        "vpn_servers": [asdict(item) for item in servers],
        "rules": [asdict(item) for item in rules],
    })


def delete_vpn_server(config: FirewallConfig, server_id: str) -> FirewallConfig:
    server_id = str(server_id or "").strip().lower()
    if any(rule.vpn_server_id == server_id for rule in config.rules):
        raise FirewallConfigError(
            "VPN server still has firewall rules; delete or move them first."
        )
    servers = [item for item in config.vpn_servers if item.server_id != server_id]
    if len(servers) == len(config.vpn_servers):
        raise FirewallConfigError("VPN server was not found.")
    return normalize_config({
        **asdict(config),
        "vpn_servers": [asdict(item) for item in servers],
    })


def vpn_server(config: FirewallConfig, server_id: str) -> FirewallVpnServer:
    try:
        return next(
            item for item in config.vpn_servers if item.server_id == server_id
        )
    except StopIteration as exc:
        raise FirewallConfigError("VPN server was not found.") from exc

def merge_config(base: FirewallConfig, incoming: FirewallConfig) -> FirewallConfig:
    """Merge normalized local configs while preserving stable IDs."""
    left = normalize_config(base)
    right = normalize_config(incoming)
    server_ids = {item.server_id for item in left.vpn_servers}
    rule_ids = {item.rule_id for item in left.rules}
    if any(item.server_id in server_ids for item in right.vpn_servers):
        raise FirewallConfigError("Duplicate VPN server ID during import.")
    if any(item.rule_id in rule_ids for item in right.rules):
        raise FirewallConfigError("Duplicate firewall rule ID during import.")
    return normalize_config({
        "version": CONFIG_VERSION,
        "vpn_servers": [
            *(asdict(item) for item in left.vpn_servers),
            *(asdict(item) for item in right.vpn_servers),
        ],
        "rules": [
            *(asdict(item) for item in left.rules),
            *(asdict(item) for item in right.rules),
        ],
    })


def import_legacy(path: Path, inspection: UfwInspection | None = None) -> FirewallConfig:
    """Convert one old OpenVPN JSON/JS policy into config v2."""
    legacy = read_legacy_config(path)
    server = normalize_vpn_server({
        "server_id": new_server_id(),
        "name": legacy.get("server_name", ""),
        "ip": legacy.get("server_ip", ""),
        "mask": legacy.get("server_mask"),
        "interface": "tun+",
    })
    rules: list[FirewallRule] = []
    for client in legacy.get("clients", []):
        kind = client.get("type")
        if kind == 1:
            rules.append(FirewallRule(
                new_rule_id(), "vpn_ban", True,
                str(client.get("clientName") or "").strip(),
                source=str(client.get("clientIP") or "").strip(),
                ban_to=str(client.get("banTo") or "").strip(),
                vpn_server_id=server.server_id,
            ))
        elif kind == 2:
            rules.append(FirewallRule(
                new_rule_id(), "standard", True,
                str(client.get("clientName") or "").strip() + " - VPN isolation",
                source=str(client.get("clientIP") or "").strip(),
                destination=server.ip,
                destination_invert=True, direction="forward", action="deny",
                protocol="any", interface=server.interface,
                vpn_server_id=server.server_id,
            ))
    if inspection is not None and inspection.hard_sources is not None:
        for action in inspection.hard_sources.rules:
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
        "vpn_servers": [asdict(server)],
        "rules": [asdict(rule) for rule in rules],
    })

def legacy_openvpn_mapping(
    config: FirewallConfig,
    server_id: str,
) -> dict[str, Any]:
    """Build legacy OpenVPN policy shape for one stable VPN server."""
    cfg = normalize_config(config)
    server = vpn_server(cfg, server_id)
    clients: list[dict[str, Any]] = []
    for rule in cfg.rules:
        if not rule.enabled or rule.vpn_server_id != server.server_id:
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
        if (
            rule.kind == "standard"
            and rule.direction == "forward"
            and rule.action == "deny"
            and rule.protocol == "any"
            and rule.destination_invert
            and rule.destination
            and str(ip_network(rule.destination, strict=False).network_address)
                == str(ip_address(server.ip))
            and (not rule.interface or rule.interface == server.interface)
        ):
            source = str(ip_network(rule.source, strict=False).network_address)
            clients.append({
                "clientName": rule.name,
                "clientIP": source,
                "type": 2,
            })
    return {
        "server_name": server.name,
        "server_ip": server.ip,
        "server_mask": server.mask,
        "interface": server.interface,
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
            and not rule.vpn_server_id
        ):
            source = rule.source
            if source.endswith("/32") or source.endswith("/128"):
                source = str(ip_network(source, strict=False).network_address)
            result.append(("-A", "ufw-before-input", "-s", source, "-j", "ACCEPT"))
    return tuple(result)


def managed_standard_rule_ids(config: FirewallConfig) -> set[str]:
    """IDs currently representable by legacy hard-source or VPN isolation blocks."""
    cfg = normalize_config(config)
    servers = {item.server_id: item for item in cfg.vpn_servers}
    managed: set[str] = set()
    for rule in cfg.rules:
        if (
            rule.enabled and rule.kind == "standard"
            and rule.direction == "input" and rule.action == "allow"
            and rule.protocol == "any" and rule.source
            and not rule.destination and not rule.destination_invert
            and not rule.src_ports and not rule.dst_ports and not rule.interface
            and not rule.vpn_server_id
        ):
            managed.add(rule.rule_id)
            continue
        server = servers.get(rule.vpn_server_id)
        if (
            server is not None
            and rule.enabled and rule.kind == "standard"
            and rule.direction == "forward" and rule.action == "deny"
            and rule.protocol == "any" and rule.destination_invert
            and rule.destination and rule.source
            and str(ip_network(rule.destination, strict=False).network_address)
                == str(ip_address(server.ip))
            and (not rule.interface or rule.interface == server.interface)
        ):
            managed.add(rule.rule_id)
    return managed
