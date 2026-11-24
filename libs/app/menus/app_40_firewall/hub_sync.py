"""Best-effort Hub notifications for Firewall Manager state changes."""
from __future__ import annotations

from libs.JBLibs.helper import getLogger

log = getLogger(__name__)


def sync_local_rules_best_effort() -> None:
    """Publish local VPN servers first, then host-local firewall rules."""
    try:
        from libs.app.hub.runtime import hub_runtime
        hub_runtime.sync_provider_best_effort("firewall_vpn_servers")
        hub_runtime.sync_provider_best_effort("firewall_rules")
    except Exception as exc:
        # Local desired-state editing remains usable when Hub is unavailable.
        log.warning("Firewall Hub synchronization skipped/failed: %s", exc)


def sync_central_policy_state_best_effort() -> None:
    """Report cached/applied central-policy state without changing UFW."""
    try:
        from libs.app.hub.runtime import hub_runtime
        hub_runtime.sync_provider_best_effort("firewall_central_policy")
    except Exception as exc:
        # A successful local guarded Apply must not become failed merely because
        # the central status report is temporarily unavailable.
        log.warning("Central firewall state synchronization skipped/failed: %s", exc)
