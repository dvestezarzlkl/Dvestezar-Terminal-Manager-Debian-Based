from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import stat
import tempfile
import unittest
from unittest.mock import patch

from libs.app.hub.models import (
    HubCentralFirewallRule,
    HubCentralFirewallVpnServer,
    HubContext,
    HubFirewallPolicyUpdate,
)
from libs.app.hub.sys_hub_plg import firewall_central_policy as provider
from libs.app.menus.app_40_firewall.central_policy import (
    load_central_policy,
    save_central_policy,
)


class HubFirewallCentralPolicyTests(unittest.TestCase):
    @staticmethod
    def _update() -> HubFirewallPolicyUpdate:
        return HubFirewallPolicyUpdate(
            machine_id="machine-a",
            group_id=7,
            generated_at=datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc),
            vpn_servers=(
                HubCentralFirewallVpnServer(
                    server_uid="1" * 32,
                    target_kind="group",
                    name="vpn",
                    server_ip="10.8.88.1",
                    server_mask=23,
                    interface_name="tun0",
                ),
            ),
            rules=(
                HubCentralFirewallRule(
                    rule_uid="a" * 32,
                    target_kind="all",
                    position=10,
                    rule_type="standard",
                    enabled=True,
                    name="https",
                    direction="input",
                    action="allow",
                    protocol="tcp",
                    dst_ports="443",
                ),
            ),
        )

    def test_provider_is_read_only_schema_009_contract(self):
        snapshot = provider.hub_collect(
            HubContext(datetime.now(timezone.utc), "machine-a")
        )
        self.assertEqual(snapshot.source_key, "firewall_central_policy")
        self.assertEqual(snapshot.dataset, "firewall_central_policy")
        self.assertEqual(snapshot.items, ())
        self.assertEqual(snapshot.min_schema_version, 9)

    def test_central_policy_cache_is_private_atomic_and_preserves_scope_order(self):
        update = self._update()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall_hub_policy.json"
            save_central_policy(update, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertFalse(any(p.suffix == ".tmp" for p in path.parent.iterdir()))
            raw = load_central_policy(path)
            self.assertEqual(raw["version"], 1)
            self.assertEqual(raw["machine_id"], "machine-a")
            self.assertEqual(raw["group_id"], 7)
            self.assertEqual(raw["rules"][0]["target_kind"], "all")
            self.assertEqual(raw["rules"][0]["position"], 10)
            self.assertEqual(raw["vpn_servers"][0]["target_kind"], "group")

    def test_cache_rejects_invalid_central_rule_before_write(self):
        update = self._update()
        bad_rule = HubCentralFirewallRule(
            rule_uid="b" * 32,
            target_kind="all",
            position=1,
            rule_type="standard",
            enabled=True,
            name="invalid-port-protocol",
            direction="input",
            action="allow",
            protocol="icmp",
            dst_ports="443",
        )
        invalid = HubFirewallPolicyUpdate(
            machine_id=update.machine_id,
            group_id=update.group_id,
            generated_at=update.generated_at,
            vpn_servers=update.vpn_servers,
            rules=(bad_rule,),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall_hub_policy.json"
            with self.assertRaises(ValueError):
                save_central_policy(invalid, path)
            self.assertFalse(path.exists())

    def test_provider_applier_accepts_exactly_one_typed_update(self):
        update = self._update()
        with patch.object(provider, "save_central_policy") as save:
            provider.hub_apply_remote((update,))
            save.assert_called_once_with(update)
        with self.assertRaises(ValueError):
            provider.hub_apply_remote(())


if __name__ == "__main__":
    unittest.main()
