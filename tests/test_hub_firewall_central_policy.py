from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import json
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from libs.app.hub.firewall_policy import firewall_policy_hash
from libs.app.hub.models import (
    HubCentralFirewallRule,
    HubCentralFirewallVpnServer,
    HubContext,
    HubFirewallPolicyUpdate,
)
from libs.app.hub.sys_hub_plg import firewall_central_policy as provider
from libs.app.menus.app_40_firewall.central_policy import (
    load_central_apply_state,
    load_central_policy,
    load_central_policy_update,
    mark_central_policy_applied,
    mark_central_policy_apply_failed,
    save_central_policy,
)


class HubFirewallCentralPolicyTests(unittest.TestCase):
    @staticmethod
    def _update() -> HubFirewallPolicyUpdate:
        return HubFirewallPolicyUpdate(
            machine_id="machine-a",
            group_id=7,
            generated_at=datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc),
            policy_revision=7,
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

    def test_policy_hash_ignores_delivery_metadata_but_tracks_policy_content(self):
        update = self._update()
        first = firewall_policy_hash(update)
        self.assertEqual(
            first,
            firewall_policy_hash(replace(
                update,
                generated_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
                policy_revision=999,
                policy_hash="f" * 64,
            )),
        )
        changed = replace(
            update,
            rules=(replace(update.rules[0], dst_ports="8443"),),
        )
        self.assertNotEqual(first, firewall_policy_hash(changed))

    def test_provider_reports_cache_and_applied_state_schema_010(self):
        update = replace(
            self._update(),
            policy_hash=firewall_policy_hash(self._update()),
        )
        with patch.object(
            provider, "load_central_policy_update", return_value=update
        ), patch.object(
            provider,
            "load_central_apply_state",
            return_value=SimpleNamespace(
                applied_hash=update.policy_hash,
                applied_revision=update.policy_revision,
                applied_at="2026-11-24T08:05:00+00:00",
                status="applied",
                last_error="",
            ),
        ):
            snapshot = provider.hub_collect(
                HubContext(datetime.now(timezone.utc), "machine-a")
            )
        self.assertEqual(snapshot.source_key, "firewall_central_policy")
        self.assertEqual(snapshot.dataset, "firewall_central_policy")
        self.assertEqual(snapshot.min_schema_version, 10)
        self.assertEqual(len(snapshot.items), 1)
        status = snapshot.items[0]
        self.assertEqual(status.cached_hash, update.policy_hash)
        self.assertEqual(status.cached_revision, 7)
        self.assertEqual(status.applied_hash, update.policy_hash)
        self.assertEqual(status.apply_status, "applied")
        self.assertEqual(status.applied_at.tzinfo, timezone.utc)

    def test_central_policy_cache_v2_is_private_atomic_and_hashed(self):
        update = self._update()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall_hub_policy.json"
            save_central_policy(update, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertFalse(any(p.suffix == ".tmp" for p in path.parent.iterdir()))
            raw = load_central_policy(path)
            self.assertEqual(raw["version"], 2)
            self.assertEqual(raw["machine_id"], "machine-a")
            self.assertEqual(raw["group_id"], 7)
            self.assertEqual(raw["policy_revision"], 7)
            self.assertEqual(raw["policy_hash"], firewall_policy_hash(update))
            typed = load_central_policy_update(path)
            self.assertEqual(typed.policy_hash, raw["policy_hash"])
            self.assertEqual(typed.policy_revision, 7)

    def test_cache_v1_remains_readable_and_derives_hash(self):
        update = self._update()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall_hub_policy.json"
            path.write_text(json.dumps({
                "version": 1,
                "machine_id": update.machine_id,
                "group_id": update.group_id,
                "generated_at": update.generated_at.isoformat(),
                "vpn_servers": [
                    {
                        "server_uid": x.server_uid,
                        "target_kind": x.target_kind,
                        "name": x.name,
                        "server_ip": x.server_ip,
                        "server_mask": x.server_mask,
                        "interface_name": x.interface_name,
                    }
                    for x in update.vpn_servers
                ],
                "rules": [
                    {
                        "rule_uid": x.rule_uid,
                        "target_kind": x.target_kind,
                        "position": x.position,
                        "rule_type": x.rule_type,
                        "enabled": x.enabled,
                        "name": x.name,
                        "direction": x.direction,
                        "action": x.action,
                        "protocol": x.protocol,
                        "source": x.source,
                        "destination": x.destination,
                        "destination_invert": x.destination_invert,
                        "port_from": x.port_from,
                        "port_to": x.port_to,
                        "src_ports": x.src_ports,
                        "dst_ports": x.dst_ports,
                        "interface_name": x.interface_name,
                        "ban_to": x.ban_to,
                        "vpn_server_uid": x.vpn_server_uid,
                    }
                    for x in update.rules
                ],
            }), encoding="utf-8")
            typed = load_central_policy_update(path)
            self.assertEqual(typed.policy_revision, 0)
            self.assertEqual(len(typed.policy_hash), 64)

    def test_applied_state_advances_only_on_success(self):
        update = replace(
            self._update(),
            policy_hash=firewall_policy_hash(self._update()),
        )
        newer = replace(
            update,
            policy_revision=8,
            rules=(replace(update.rules[0], dst_ports="8443"),),
            policy_hash="",
        )
        newer = replace(newer, policy_hash=firewall_policy_hash(newer))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall_hub_apply_state.json"
            mark_central_policy_applied(update, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            state = load_central_apply_state(path)
            self.assertEqual(state.applied_hash, update.policy_hash)
            self.assertEqual(state.status, "applied")

            mark_central_policy_apply_failed(
                newer,
                "simulated failure",
                path=path,
            )
            failed = load_central_apply_state(path)
            self.assertEqual(failed.applied_hash, update.policy_hash)
            self.assertEqual(failed.applied_revision, 7)
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.last_error, "simulated failure")

            mark_central_policy_apply_failed(
                newer,
                "rolled back",
                rolled_back=True,
                path=path,
            )
            rolled = load_central_apply_state(path)
            self.assertEqual(rolled.applied_hash, update.policy_hash)
            self.assertEqual(rolled.status, "rolled_back")

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
        invalid = replace(update, rules=(bad_rule,))
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
