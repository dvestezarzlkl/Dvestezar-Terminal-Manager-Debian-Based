"""Read central firewall desired state and report local policy state."""
from __future__ import annotations

from datetime import datetime

from libs.app.hub.models import (
    HubContext,
    HubFirewallPolicyStatus,
    HubProviderSnapshot,
)
from libs.app.menus.app_40_firewall.central_policy import (
    load_central_apply_state,
    load_central_policy_update,
    save_central_policy,
)

HUB_PROVIDER_KEY = "firewall_central_policy"


def hub_collect(context: HubContext) -> HubProviderSnapshot:
    del context
    cached = load_central_policy_update()
    applied = load_central_apply_state()
    applied_at = None
    if applied.applied_at:
        applied_at = datetime.fromisoformat(applied.applied_at)
    status = HubFirewallPolicyStatus(
        cached_hash=cached.policy_hash if cached is not None else "",
        cached_revision=cached.policy_revision if cached is not None else 0,
        applied_hash=applied.applied_hash,
        applied_revision=applied.applied_revision,
        apply_status=applied.status,
        applied_at=applied_at,
        last_error=applied.last_error,
    )
    return HubProviderSnapshot(
        source_key=HUB_PROVIDER_KEY,
        dataset="firewall_central_policy",
        items=(status,),
        min_schema_version=10,
    )


def hub_apply_remote(updates) -> None:
    if len(updates) != 1:
        raise ValueError("Central firewall provider expects exactly one policy update.")
    save_central_policy(updates[0])
