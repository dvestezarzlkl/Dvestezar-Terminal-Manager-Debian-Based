"""Read-only cache and local apply-state for central firewall policy.

Hub synchronization may validate/cache policy and report status. Only the
explicit local Firewall Manager Apply workflow may activate cached policy in
UFW; this module never invokes UFW itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from libs.JBLibs.helper import getConfigPath
from libs.app import g_def as defs
from libs.app.hub.firewall_policy import (
    firewall_policy_hash,
    valid_firewall_policy_hash,
)
from libs.app.hub.models import (
    HubCentralFirewallRule,
    HubCentralFirewallVpnServer,
    HubFirewallPolicyUpdate,
)

from .config import normalize_rule, normalize_vpn_server

CACHE_NAME = "firewall_hub_policy.json"
CACHE_VERSION = 2
APPLY_STATE_NAME = "firewall_hub_apply_state.json"
APPLY_STATE_VERSION = 1


class FirewallCentralPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class FirewallCentralApplyState:
    applied_hash: str = ""
    applied_revision: int = 0
    applied_at: str = ""
    status: str = "unknown"
    last_error: str = ""


def cache_path(*, create_dir: bool = False) -> Path:
    return getConfigPath(
        configName=CACHE_NAME,
        appName=defs.APP_NAME,
        fromEtc=defs.CONFIG_ETC,
        createIfNotExist=create_dir,
    )


def apply_state_path(*, create_dir: bool = False) -> Path:
    return getConfigPath(
        configName=APPLY_STATE_NAME,
        appName=defs.APP_NAME,
        fromEtc=defs.CONFIG_ETC,
        createIfNotExist=create_dir,
    )


def _write_json_atomic(target: Path, payload: dict, *, label: str) -> Path:
    if target.exists() and target.is_symlink():
        raise FirewallCentralPolicyError(f"{label} must not be a symlink.")
    target.parent.mkdir(parents=True, exist_ok=True)
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


def _validate(update: HubFirewallPolicyUpdate) -> None:
    if not isinstance(update, HubFirewallPolicyUpdate):
        raise FirewallCentralPolicyError("Invalid central firewall policy update.")
    if not update.machine_id:
        raise FirewallCentralPolicyError("Central firewall policy has no machine ID.")
    if isinstance(update.policy_revision, bool) or int(update.policy_revision) < 0:
        raise FirewallCentralPolicyError("Invalid central firewall policy revision.")

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

    expected_hash = firewall_policy_hash(update)
    if update.policy_hash and (
        not valid_firewall_policy_hash(update.policy_hash)
        or update.policy_hash != expected_hash
    ):
        raise FirewallCentralPolicyError("Central firewall policy hash mismatch.")


def save_central_policy(
    update: HubFirewallPolicyUpdate,
    path: Path | None = None,
) -> Path:
    _validate(update)
    policy_hash = update.policy_hash or firewall_policy_hash(update)
    target = path or cache_path(create_dir=True)
    return _write_json_atomic(
        target,
        {
            "version": CACHE_VERSION,
            "machine_id": update.machine_id,
            "group_id": update.group_id,
            "generated_at": update.generated_at.isoformat(),
            "policy_hash": policy_hash,
            "policy_revision": int(update.policy_revision),
            "vpn_servers": [asdict(item) for item in update.vpn_servers],
            "rules": [asdict(item) for item in update.rules],
        },
        label="Central firewall cache",
    )


def load_central_policy(path: Path | None = None) -> dict:
    target = path or cache_path(create_dir=False)
    if not target.exists():
        return {
            "version": CACHE_VERSION,
            "machine_id": "",
            "group_id": None,
            "generated_at": "",
            "policy_hash": "",
            "policy_revision": 0,
            "vpn_servers": [],
            "rules": [],
        }
    if target.is_symlink():
        raise FirewallCentralPolicyError("Central firewall cache must not be a symlink.")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise FirewallCentralPolicyError("Cannot read central firewall cache.") from exc
    if not isinstance(raw, dict) or raw.get("version") not in {1, CACHE_VERSION}:
        raise FirewallCentralPolicyError("Unsupported central firewall cache version.")
    if not isinstance(raw.get("vpn_servers"), list) or not isinstance(raw.get("rules"), list):
        raise FirewallCentralPolicyError("Invalid central firewall cache payload.")
    return raw


def load_central_policy_update(
    path: Path | None = None,
) -> HubFirewallPolicyUpdate | None:
    """Load and fully validate the cached central policy as typed data."""
    raw = load_central_policy(path)
    if not raw.get("machine_id"):
        return None
    try:
        generated_at = datetime.fromisoformat(str(raw.get("generated_at") or ""))
        group_id = raw.get("group_id")
        if group_id is not None:
            if isinstance(group_id, bool):
                raise ValueError("Invalid central firewall group ID.")
            group_id = int(group_id)
            if group_id <= 0:
                raise ValueError("Invalid central firewall group ID.")
        vpn_servers = tuple(
            HubCentralFirewallVpnServer(**item)
            for item in raw["vpn_servers"]
        )
        rules = tuple(
            HubCentralFirewallRule(**item)
            for item in raw["rules"]
        )
        update = HubFirewallPolicyUpdate(
            machine_id=str(raw["machine_id"]),
            group_id=group_id,
            generated_at=generated_at,
            policy_hash=str(raw.get("policy_hash") or ""),
            policy_revision=int(raw.get("policy_revision") or 0),
            vpn_servers=vpn_servers,
            rules=rules,
        )
        _validate(update)
        if not update.policy_hash:
            update = replace(update, policy_hash=firewall_policy_hash(update))
        return update
    except (TypeError, ValueError, KeyError) as exc:
        raise FirewallCentralPolicyError(
            "Invalid central firewall cache payload."
        ) from exc


def load_central_apply_state(
    path: Path | None = None,
) -> FirewallCentralApplyState:
    target = path or apply_state_path(create_dir=False)
    if not target.exists():
        return FirewallCentralApplyState()
    if target.is_symlink():
        raise FirewallCentralPolicyError(
            "Central firewall apply state must not be a symlink."
        )
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("version") != APPLY_STATE_VERSION:
            raise ValueError("Unsupported apply-state version.")
        applied_hash = str(raw.get("applied_hash") or "")
        if applied_hash and not valid_firewall_policy_hash(applied_hash):
            raise ValueError("Invalid applied policy hash.")
        applied_revision = int(raw.get("applied_revision") or 0)
        if applied_revision < 0:
            raise ValueError("Invalid applied policy revision.")
        status = str(raw.get("status") or "unknown")
        if status not in {"unknown", "applied", "failed", "rolled_back"}:
            raise ValueError("Invalid apply status.")
        return FirewallCentralApplyState(
            applied_hash=applied_hash,
            applied_revision=applied_revision,
            applied_at=str(raw.get("applied_at") or ""),
            status=status,
            last_error=str(raw.get("last_error") or "")[:512],
        )
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise FirewallCentralPolicyError(
            "Cannot read central firewall apply state."
        ) from exc


def _save_central_apply_state(
    state: FirewallCentralApplyState,
    path: Path | None = None,
) -> Path:
    target = path or apply_state_path(create_dir=True)
    return _write_json_atomic(
        target,
        {
            "version": APPLY_STATE_VERSION,
            "applied_hash": state.applied_hash,
            "applied_revision": int(state.applied_revision),
            "applied_at": state.applied_at,
            "status": state.status,
            "last_error": state.last_error[:512],
        },
        label="Central firewall apply state",
    )


def mark_central_policy_applied(
    update: HubFirewallPolicyUpdate,
    path: Path | None = None,
) -> Path:
    _validate(update)
    policy_hash = update.policy_hash or firewall_policy_hash(update)
    return _save_central_apply_state(
        FirewallCentralApplyState(
            applied_hash=policy_hash,
            applied_revision=int(update.policy_revision),
            applied_at=datetime.now().astimezone().isoformat(),
            status="applied",
            last_error="",
        ),
        path,
    )


def mark_central_policy_apply_failed(
    update: HubFirewallPolicyUpdate | None,
    error: str,
    *,
    rolled_back: bool = False,
    path: Path | None = None,
) -> Path:
    previous = load_central_apply_state(path)
    # Never advance applied hash/revision on failure or rollback.
    return _save_central_apply_state(
        FirewallCentralApplyState(
            applied_hash=previous.applied_hash,
            applied_revision=previous.applied_revision,
            applied_at=previous.applied_at,
            status="rolled_back" if rolled_back else "failed",
            last_error=str(error or "")[:512],
        ),
        path,
    )
