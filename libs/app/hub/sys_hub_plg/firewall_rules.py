"""Read-only sync of locally edited Firewall Manager rules to SysApps Hub.

Local editor rules are always host-targeted and origin=host_local in the DB.
This collector does not read or apply central group/all policies.
"""
from __future__ import annotations

from libs.app.hub.models import HubContext, HubFirewallRule, HubProviderSnapshot
from libs.app.menus.app_40_firewall.config import load_config

HUB_PROVIDER_KEY = "firewall_rules"


def hub_collect(context: HubContext) -> HubProviderSnapshot:
    cfg = load_config()
    items = tuple(
        HubFirewallRule(
            rule_uid=rule.rule_id,
            rule_type=rule.kind,
            enabled=rule.enabled,
            name=rule.name,
            direction=rule.direction,
            action=rule.action,
            protocol=rule.protocol,
            source=rule.source,
            destination=rule.destination,
            destination_invert=rule.destination_invert,
            port_from=rule.port_from,
            port_to=rule.port_to,
            interface_name=rule.interface,
            ban_to=rule.ban_to or None,
        )
        for rule in cfg.rules
    )
    return HubProviderSnapshot(
        source_key=HUB_PROVIDER_KEY,
        dataset="firewall_rules",
        items=items,
        min_schema_version=6,
    )
