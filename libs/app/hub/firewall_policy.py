"""Pure helpers for SysApps Hub central firewall policy identity.

The policy hash is the authority for pending/delivered/applied comparison.
Revision is audit/display metadata and must never be used as the sole equality
check because one global edit can affect hosts differently.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import re

from .models import HubFirewallPolicyUpdate

_POLICY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SCOPE_RANK = {"all": 0, "group": 1, "host": 2}


def valid_firewall_policy_hash(value: str) -> bool:
    return bool(_POLICY_HASH_RE.fullmatch(str(value or "")))


def canonical_firewall_policy_payload(update: HubFirewallPolicyUpdate) -> dict:
    if not isinstance(update, HubFirewallPolicyUpdate):
        raise TypeError("Expected HubFirewallPolicyUpdate.")

    vpn_servers = sorted(
        (asdict(item) for item in update.vpn_servers),
        key=lambda item: (
            _SCOPE_RANK.get(str(item.get("target_kind") or ""), 99),
            str(item.get("server_uid") or ""),
            json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        ),
    )
    rules = sorted(
        (asdict(item) for item in update.rules),
        key=lambda item: (
            _SCOPE_RANK.get(str(item.get("target_kind") or ""), 99),
            int(item.get("position") or 0),
            str(item.get("rule_uid") or ""),
            json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        ),
    )
    return {
        "vpn_servers": vpn_servers,
        "rules": rules,
    }


def firewall_policy_hash(update: HubFirewallPolicyUpdate) -> str:
    payload = canonical_firewall_policy_payload(update)
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(serialized.encode("utf-8")).hexdigest()
