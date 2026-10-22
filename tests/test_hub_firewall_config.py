"""Local Firewall Manager configuration/editor and Hub collector tests."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
import json
import os
import stat
import tempfile
import unittest
from unittest.mock import patch

from libs.app.hub.models import HubContext
from libs.app.hub.sys_hub_plg import firewall_rules as hub_firewall_rules
from libs.app.menus.app_40_firewall import menu as firewall_menu
from libs.app.menus.app_40_firewall import menu_rules as firewall_menu_rules
from libs.app.menus.app_40_firewall.config import (
    FirewallConfig, FirewallConfigError, FirewallRule, append_rule,
    hard_source_rules, import_legacy, legacy_openvpn_mapping, load_config,
    managed_standard_rule_ids, normalize_config, save_config,
)
from libs.app.menus.app_40_firewall.policy import inspect_before_rules
from tests.test_hub_firewall_policy import before_rules


def legacy_file(path: Path) -> None:
    path.write_text(
        """// BOF JSON CFG
{
  "server_name": "openvpn-jb",
  "server_ip": "10.8.88.1",
  "server_mask": 23,
  "clients": [
    {"clientName": "Alice", "clientIP": "10.8.89.12", "type": 1, "banTo": "2026-12-31"},
    {"clientName": "Bob", "clientIP": "10.8.89.8", "type": 2}
  ]
}
""",
        encoding="utf-8",
    )


class HubFirewallConfigTests(unittest.TestCase):
    def test_save_load_is_atomic_normalized_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall.json"
            cfg = FirewallConfig(
                openvpn_server_name="openvpn-jb",
                openvpn_server_ip="10.8.88.1",
                openvpn_server_mask=23,
                rules=(
                    FirewallRule(
                        "a" * 32, "vpn_ban", True, "Alice",
                        source="10.8.89.12", ban_to="2026-12-31",
                    ),
                    FirewallRule(
                        "b" * 32, "standard", True, "office",
                        source="198.51.100.44", direction="input",
                        action="allow", protocol="any",
                    ),
                ),
            )
            save_config(cfg, path)
            loaded = load_config(path)
            self.assertEqual(loaded.rules[0].source, "10.8.89.12/32")
            self.assertEqual(loaded.rules[1].source, "198.51.100.44/32")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertFalse(any(p.suffix == ".tmp" for p in path.parent.iterdir()))
            parsed = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(parsed["version"], 1)

    def test_rejects_symlink_and_invalid_ports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real.json"
            target.write_text('{"version":1,"rules":[]}\n', encoding="utf-8")
            link = root / "firewall.json"
            os.symlink(target, link)
            with self.assertRaises(FirewallConfigError):
                load_config(link)
        with self.assertRaises(FirewallConfigError):
            normalize_config({
                "version": 1,
                "rules": [{
                    "rule_id": "a" * 32, "kind": "standard",
                    "name": "bad", "enabled": True,
                    "direction": "input", "action": "allow",
                    "protocol": "tcp", "port_from": 443, "port_to": 22,
                }],
            })

    def test_import_legacy_and_existing_hard_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.js"
            legacy_file(path)
            inspection = inspect_before_rules(before_rules())
            cfg = import_legacy(path, inspection)
        kinds = [rule.kind for rule in cfg.rules]
        self.assertEqual(kinds.count("vpn_ban"), 1)
        self.assertEqual(kinds.count("standard"), 2)
        mapping = legacy_openvpn_mapping(cfg)
        self.assertEqual({item["type"] for item in mapping["clients"]}, {1, 2})
        self.assertEqual(
            hard_source_rules(cfg),
            (("-A", "ufw-before-input", "-s", "198.51.100.44", "-j", "ACCEPT"),),
        )
        self.assertEqual(len(managed_standard_rule_ids(cfg)), 2)

    def test_append_rule_keeps_host_local_rule_ids_stable(self):
        cfg = FirewallConfig()
        rule = FirewallRule(
            "f" * 32, "standard", True, "HTTPS",
            source="203.0.113.0/24", direction="input",
            action="allow", protocol="tcp", port_from=443, port_to=443,
        )
        cfg = append_rule(cfg, rule)
        self.assertEqual(cfg.rules[0].rule_id, "f" * 32)

    def test_hub_collector_is_host_local_dataset_requiring_schema_006(self):
        cfg = FirewallConfig(
            rules=(
                FirewallRule(
                    "c" * 32, "standard", True, "SSH",
                    source="203.0.113.7/32", direction="input",
                    action="allow", protocol="tcp", port_from=22, port_to=22,
                ),
            ),
        )
        with patch.object(hub_firewall_rules, "load_config", return_value=cfg):
            snapshot = hub_firewall_rules.hub_collect(
                HubContext(
                    generated_at=None,
                    machine_id="machine-firewall",
                )
            )
        self.assertEqual(snapshot.source_key, "firewall_rules")
        self.assertEqual(snapshot.dataset, "firewall_rules")
        self.assertEqual(snapshot.min_schema_version, 6)
        self.assertEqual(snapshot.items[0].rule_uid, "c" * 32)
        self.assertEqual(snapshot.items[0].port_from, 22)

    def test_optional_editor_value_can_be_cleared_explicitly(self):
        with patch.object(firewall_menu_rules, "get_input", return_value="-"):
            value = firewall_menu_rules._prompt(
                "Optional:", width=72, current="2026-12-31", required=False
            )
        self.assertEqual(value, "")

    def test_legacy_import_menu_uses_framework_file_picker_not_typed_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "old.js"
            legacy_file(legacy)
            saved = Path(tmp) / "firewall.json"
            fake = SimpleNamespace(minMenuWidth=72, menuRecycle=False)
            before_file = SimpleNamespace(
                read_text=lambda encoding="utf-8": before_rules()
            )
            with patch.object(
                firewall_menu, "selectFile", return_value=legacy
            ) as picker, patch.object(
                firewall_menu, "_BEFORE_RULES", before_file
            ), patch.object(
                firewall_menu, "config_path", return_value=saved
            ), patch.object(
                firewall_menu, "save_config", return_value=saved
            ) as save, patch.object(
                firewall_menu, "sync_local_rules_best_effort"
            ) as sync:
                result = firewall_menu.menu.import_legacy_config(fake, None)
            picker.assert_called_once()
            save.assert_called_once()
            sync.assert_called_once_with()
            self.assertTrue(bool(getattr(result, "ok", None)))
            self.assertTrue(fake.menuRecycle)


if __name__ == "__main__":
    unittest.main()
