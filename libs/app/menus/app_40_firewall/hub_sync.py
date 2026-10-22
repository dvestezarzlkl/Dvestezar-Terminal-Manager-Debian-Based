"""Best-effort Hub notification after a successful local firewall config save."""
from __future__ import annotations

from libs.JBLibs.helper import getLogger

log = getLogger(__name__)


def sync_local_rules_best_effort() -> None:
    """Publish host-local desired rules without making local Save depend on Hub."""
    try:
        from libs.app.hub.runtime import hub_runtime
        hub_runtime.sync_provider_best_effort("firewall_rules")
    except Exception as exc:
        # Local desired-state editing remains usable when Hub is unavailable.
        log.warning("Firewall rules Hub synchronization skipped/failed: %s", exc)
