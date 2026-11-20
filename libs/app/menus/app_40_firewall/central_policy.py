"""Read-only cache for firewall policy received from SysApps Hub.

This module never mutates UFW and never changes the user-owned firewall.json.
It only validates typed Hub updates and atomically stores the last successful
central policy snapshot for later preview/merge stages.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile

from libs.JBLibs.helper import getConfigPath
from libs.app import g_def as defs
from libs.app.hub.models import HubFirewallPolicyUpdate

from .config import normalize_rule, normalize_vpn_server

CACHE_NAME = "firewall_hub_policy.json"
CACHE_VERSION = 1


class FirewallCentralPolicyError(ValueError):
    pass


def cache_path(*, create_dir: bool = False) -> Path:
    return getConfigPath(
        configName=CACHE_NAME,
        appName=defs.APP_NAME,
        fromEtc=defs.CONFIG_ETC,
        createIfNotExist=create_dir,
    )


def _validate(update: HubFirewallPolicyUpdate) -> None:
    if not isinstance(update, HubFirewallPolicyUpdate):
        raise FirewallCentralPolicyError("Invalid central firewall policy update.")
    if not update.machine_id:
        raise FirewallCentralPolicyError("Central firewall policy has no machine ID.")

    rule_ids: set[str] = set()
    for rule in update.rules:
        if rule.target_kind not in {"all", "group", "host"}:
            raise FirewallCentralPolicyError("Invalid central firewall rule target.")
        if rule.position < 0:
            raise FirewallCentralPolicyError("Invalid central firewall rule position.")
        if rule.rule_uid in rule_ids:
            raise FirewallCentralPolicyError("Duplicate central firewall rule UID.")
        rule_ids.add(rule.rule_uid)
        try:
            normalize_rule({
                "rule_id": rule.rule_uid,
                "kind": rule.rule_type,
                "enabled": rule.enabled,
                "name": rule.name,
                "direction": rule.direction,
                "action": rule.action,
                "protocol": rule.protocol,
                "source": rule.source,
                "destination": rule.destination,
                "destination_invert": rule.destination_invert,
                "port_from": rule.port_from,
                "port_to": rule.port_to,
                "src_ports": rule.src_ports,
                "dst_ports": rule.dst_ports,
                "interface": rule.interface_name,
                "ban_to": rule.ban_to or "",
                "vpn_server_id": rule.vpn_server_uid,
            })
        except ValueError as exc:
            raise FirewallCentralPolicyError(
                f"Invalid central firewall rule {rule.rule_uid}."
            ) from exc

    server_keys: set[tuple[str, str]] = set()
    for server in update.vpn_servers:
        if server.target_kind not in {"all", "group", "host"}:
            raise FirewallCentralPolicyError("Invalid central VPN server target.")
        key = (server.target_kind, server.server_uid)
        if key in server_keys:
            raise FirewallCentralPolicyError("Duplicate central VPN server in one scope.")
        server_keys.add(key)
        try:
            normalize_vpn_server({
                "server_id": server.server_uid,
                "name": server.name,
                "ip": server.server_ip,
                "mask": server.server_mask,
                "interface": server.interface_name,
            })
        except ValueError as exc:
            raise FirewallCentralPolicyError(
                f"Invalid central VPN server {server.server_uid}."
            ) from exc


def save_central_policy(
    update: HubFirewallPolicyUpdate,
    path: Path | None = None,
) -> Path:
    _validate(update)
    target = path or cache_path(create_dir=True)
    if target.exists() and target.is_symlink():
        raise FirewallCentralPolicyError("Central firewall cache must not be a symlink.")
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": CACHE_VERSION,
        "machine_id": update.machine_id,
        "group_id": update.group_id,
        "generated_at": update.generated_at.isoformat(),
        "vpn_servers": [asdict(item) for item in update.vpn_servers],
        "rules": [asdict(item) for item in update.rules],
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


def load_central_policy(path: Path | None = None) -> dict:
    target = path or cache_path(create_dir=False)
    if not target.exists():
        return {
            "version": CACHE_VERSION,
            "machine_id": "",
            "group_id": None,
            "generated_at": "",
            "vpn_servers": [],
            "rules": [],
        }
    if target.is_symlink():
        raise FirewallCentralPolicyError("Central firewall cache must not be a symlink.")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise FirewallCentralPolicyError("Cannot read central firewall cache.") from exc
    if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
        raise FirewallCentralPolicyError("Unsupported central firewall cache version.")
    if not isinstance(raw.get("vpn_servers"), list) or not isinstance(raw.get("rules"), list):
        raise FirewallCentralPolicyError("Invalid central firewall cache payload.")
    return raw
