"""Reconciliation never reloads UFW or changes successful Apply metadata."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone, timedelta
import unittest
from unittest.mock import patch
import subprocess
from pathlib import Path

from libs.app.menus.app_40_firewall.policy import plan_legacy_openvpn
from libs.app.menus.app_40_firewall.reconcile import ReconcileState, reconcile
from tests.test_hub_firewall_policy import before_rules, policy_config


class HubFirewallReconcileTests(unittest.TestCase):
    def setUp(self):
        self.checked = datetime(2026, 10, 20, 16, tzinfo=timezone.utc)
        self.current = plan_legacy_openvpn(
            before_rules(), policy_config(), on_date=date(2026, 10, 20)
        )
        self.applied = ReconcileState(
            applied_hash=self.current.current_hash,
            last_checked_at=self.checked - timedelta(hours=1),
            last_applied_at=self.checked - timedelta(days=1),
        )

    def test_same_configuration_has_no_side_effect_and_preserves_apply_time(self):
        with patch.object(subprocess, "run", side_effect=AssertionError("no reload")), patch.object(
            Path, "write_text", side_effect=AssertionError("no file write")
        ):
            result = reconcile(self.current, self.applied, checked_at=self.checked)
        self.assertEqual(result.decision, "NO_CHANGE")
        self.assertEqual(result.state.last_checked_at, self.checked)
        self.assertEqual(result.state.last_applied_at, self.applied.last_applied_at)
        self.assertEqual(result.state.applied_hash, self.applied.applied_hash)

    def test_expired_ban_requires_review_not_automatic_reload(self):
        expired = plan_legacy_openvpn(
            before_rules(), policy_config(), on_date=date(2026, 10, 21)
        )
        self.assertEqual(expired.status, "CHANGED")
        result = reconcile(expired, self.applied, checked_at=self.checked)
        self.assertEqual(result.decision, "PENDING_REVIEW")
        self.assertEqual(result.state.applied_hash, self.applied.applied_hash)
        self.assertEqual(result.state.last_applied_at, self.applied.last_applied_at)

    def test_no_verified_apply_cannot_be_implicitly_adopted(self):
        result = reconcile(
            self.current, ReconcileState(), checked_at=self.checked
        )
        self.assertEqual(result.decision, "PENDING_REVIEW")
        self.assertIsNone(result.state.applied_hash)

    def test_manually_modified_firewall_is_drift_even_if_desired_same(self):
        previous = replace(self.applied, applied_hash="0" * 64)
        result = reconcile(self.current, previous, checked_at=self.checked)
        self.assertEqual(result.decision, "DRIFT")

    def test_ambiguous_block_is_blocked(self):
        result = reconcile(
            replace(self.current, status="REVIEW", reason="marker mismatch"),
            self.applied, checked_at=self.checked,
        )
        self.assertEqual(result.decision, "BLOCKED")
        self.assertIn("marker", result.reason)

    def test_time_validation_and_monotonic_check(self):
        with self.assertRaises(ValueError):
            reconcile(self.current, self.applied, checked_at=datetime(2026, 10, 20))
        with self.assertRaises(ValueError):
            reconcile(
                self.current, self.applied,
                checked_at=self.applied.last_checked_at - timedelta(seconds=1),
            )


if __name__ == "__main__":
    unittest.main()
