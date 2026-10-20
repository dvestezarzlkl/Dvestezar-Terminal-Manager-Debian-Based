"""Pure firewall reconciliation decisions; no filesystem or UFW side effects.

Existing SysApps Hub can run every hour. A configuration fetch/check is NOT
permission to write UFW rules or reload a service. Apply remains unimplemented.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .policy import FirewallPlan

Decision = Literal["NO_CHANGE", "PENDING_REVIEW", "BLOCKED", "DRIFT"]


@dataclass(frozen=True)
class ReconcileState:
    """Previously verified application metadata; never centrally writable."""
    applied_hash: str | None = None
    last_checked_at: datetime | None = None
    last_applied_at: datetime | None = None


@dataclass(frozen=True)
class ReconcileResult:
    decision: Decision
    state: ReconcileState
    reason: str = ""


def reconcile(
    plan: FirewallPlan,
    previous: ReconcileState,
    *,
    checked_at: datetime,
) -> ReconcileResult:
    """Evaluate desired/observed drift; NEVER call Apply or alter applied time.

    An unseen hash cannot be silently adopted. Even if observed rules match
    desired rules, first application/ownership needs explicit human review.
    """
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("checked_at must have a timezone")
    if previous.last_checked_at is not None and checked_at < previous.last_checked_at:
        raise ValueError("Cannot move last_checked_at backwards")

    checked = ReconcileState(
        applied_hash=previous.applied_hash,
        last_checked_at=checked_at,
        last_applied_at=previous.last_applied_at,
    )
    if plan.status in {"MISSING", "REVIEW"}:
        return ReconcileResult("BLOCKED", checked, plan.reason)
    if plan.status not in {"NO_CHANGE", "CHANGED"}:
        return ReconcileResult("BLOCKED", checked, "Unrecognized firewall policy status.")
    if previous.applied_hash is None:
        return ReconcileResult(
            "PENDING_REVIEW", checked,
            "No verified previous apply. Explicit adoption is required.",
        )
    if previous.applied_hash != plan.current_hash:
        return ReconcileResult(
            "DRIFT", checked,
            "Observed managed UFW rules differ from the last verified apply.",
        )
    if plan.status == "CHANGED":
        return ReconcileResult(
            "PENDING_REVIEW", checked,
            "Desired effective rules differ; only a separately approved Apply may change UFW.",
        )
    return ReconcileResult("NO_CHANGE", checked)
