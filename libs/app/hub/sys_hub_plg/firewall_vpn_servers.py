"""Host-local VPN server inventory for SysApps Hub."""
from __future__ import annotations

from libs.app.hub.models import HubContext, HubFirewallVpnServer, HubProviderSnapshot
from libs.app.menus.app_40_firewall.config import load_config

HUB_PROVIDER_KEY = "firewall_vpn_servers"


def hub_collect(context: HubContext) -> HubProviderSnapshot:
    cfg = load_config()
    return HubProviderSnapshot(
        source_key=HUB_PROVIDER_KEY,
        dataset="firewall_vpn_servers",
        items=tuple(
            HubFirewallVpnServer(
                server_uid=item.server_id,
                name=item.name,
                server_ip=item.ip,
                server_mask=item.mask,
                interface_name=item.interface,
            )
            for item in cfg.vpn_servers
        ),
        min_schema_version=8,
    )
