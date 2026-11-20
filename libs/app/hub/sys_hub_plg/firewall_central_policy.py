"""Read central firewall desired state from Hub through the typed provider API."""
from __future__ import annotations

from libs.app.hub.models import HubContext, HubProviderSnapshot
from libs.app.menus.app_40_firewall.central_policy import save_central_policy

HUB_PROVIDER_KEY = "firewall_central_policy"


def hub_collect(context: HubContext) -> HubProviderSnapshot:
    del context
    return HubProviderSnapshot(
        source_key=HUB_PROVIDER_KEY,
        dataset="firewall_central_policy",
        items=(),
        min_schema_version=9,
    )


def hub_apply_remote(updates) -> None:
    if len(updates) != 1:
        raise ValueError("Central firewall provider expects exactly one policy update.")
    save_central_policy(updates[0])
