"""Firewall local config, editor, and Hub collector regression tests."""
from __future__ import annotations

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
from libs.app.hub.sys_hub_plg import firewall_vpn_servers as hub_vpn_servers
from libs.app.menus.app_40_firewall import menu as firewall_menu
from libs.app.menus.app_40_firewall import menu_helpers
from libs.app.menus.app_40_firewall import menu_rules as firewall_menu_rules
from libs.app.menus.app_40_firewall.config import (
    FirewallConfig,
    FirewallConfigError,
    FirewallRule,
    FirewallVpnServer,
    append_rule,
    hard_source_rules,
    import_legacy,
    legacy_openvpn_mapping,
    load_config,
    managed_standard_rule_ids,
    merge_config,
    normalize_config,
    normalize_port_spec,
    save_config,
)
from libs.app.menus.app_40_firewall.policy import inspect_before_rules
from tests.test_hub_firewall_policy import before_rules


def legacy_file(path: Path, *, name: str = "openvpn-jb", ip: str = "10.8.88.1") -> None:
    path.write_text(
        """// BOF JSON CFG
{
  "server_name": "%s",
  "server_ip": "%s",
  "server_mask": 23,
  "clients": [
    {"clientName": "Alice", "clientIP": "10.8.89.12", "type": 1, "banTo": "2026-12-31"},
    {"clientName": "Bob", "clientIP": "10.8.89.8", "type": 2}
  ]
}
""" % (name, ip),
        encoding="utf-8",
    )


class HubFirewallConfigTests(unittest.TestCase):
    def test_save_load_is_atomic_v2_normalized_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall.json"
            server = FirewallVpnServer(
                "1" * 32, "openvpn-jb", "10.8.88.1", 23, "tun+"
            )
            cfg = FirewallConfig(
                vpn_servers=(server,),
                rules=(
                    FirewallRule(
                        "a" * 32,
                        "vpn_ban",
                        True,
                        "Alice",
                        source="10.8.89.12",
                        ban_to="2026-12-31",
                        vpn_server_id=server.server_id,
                    ),
                    FirewallRule(
                        "b" * 32,
                        "standard",
                        True,
                        "office",
                        source="198.51.100.44",
                        direction="input",
                        action="allow",
                        protocol="any",
                    ),
                ),
            )
            save_config(cfg, path)
            loaded = load_config(path)
            self.assertEqual(loaded.version, 2)
            self.assertEqual(loaded.vpn_servers[0], server)
            self.assertEqual(loaded.rules[0].source, "10.8.89.12/32")
            self.assertEqual(loaded.rules[0].vpn_server_id, server.server_id)
            self.assertEqual(loaded.rules[1].source, "198.51.100.44/32")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertFalse(any(p.suffix == ".tmp" for p in path.parent.iterdir()))
            parsed = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(parsed["version"], 2)
            self.assertIn("vpn_servers", parsed)
            self.assertNotIn("openvpn_server_name", parsed)

    def test_v1_migration_preserves_ports_and_assigns_vpn_server(self):
        cfg = normalize_config({
            "version": 1,
            "openvpn_server_name": "vpn-old",
            "openvpn_server_ip": "10.8.88.1",
            "openvpn_server_mask": 23,
            "openvpn_interface": "tun9",
            "rules": [
                {
                    "rule_id": "a" * 32,
                    "kind": "vpn_ban",
                    "enabled": True,
                    "name": "Alice",
                    "source": "10.8.89.12",
                    "ban_to": "2026-12-31",
                },
                {
                    "rule_id": "b" * 32,
                    "kind": "standard",
                    "enabled": True,
                    "name": "web",
                    "direction": "input",
                    "action": "allow",
                    "protocol": "tcp",
                    "src_ports": "40000-40100",
                    "dst_ports": "80,443,8080-8090",
                },
            ],
        })
        self.assertEqual(cfg.version, 2)
        self.assertEqual(len(cfg.vpn_servers), 1)
        server = cfg.vpn_servers[0]
        self.assertEqual((server.name, server.ip, server.mask, server.interface),
                         ("vpn-old", "10.8.88.1", 23, "tun9"))
        self.assertEqual(cfg.rules[0].vpn_server_id, server.server_id)
        self.assertEqual(cfg.rules[1].src_ports, "40000-40100")
        self.assertEqual(cfg.rules[1].dst_ports, "80,443,8080-8090")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firewall.json"
            save_config(cfg, path)
            parsed = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(parsed["version"], 2)
            self.assertEqual(parsed["rules"][1]["dst_ports"], "80,443,8080-8090")

    def test_rejects_symlink_invalid_ports_and_unknown_config_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real.json"
            target.write_text('{"version":2,"vpn_servers":[],"rules":[]}\n', encoding="utf-8")
            link = root / "firewall.json"
            os.symlink(target, link)
            with self.assertRaises(FirewallConfigError):
                load_config(link)

        with self.assertRaises(FirewallConfigError):
            normalize_config({
                "version": 2,
                "vpn_servers": [],
                "rules": [{
                    "rule_id": "a" * 32,
                    "kind": "standard",
                    "name": "bad",
                    "enabled": True,
                    "direction": "input",
                    "action": "allow",
                    "protocol": "tcp",
                    "port_from": 443,
                    "port_to": 22,
                }],
            })
        with self.assertRaises(FirewallConfigError):
            normalize_config({"version": 99, "rules": []})

    def test_legacy_vpn_ban_rejects_ipv6_source(self):
        with self.assertRaises(FirewallConfigError):
            normalize_config({
                "version": 1,
                "openvpn_server_name": "vpn",
                "openvpn_server_ip": "10.8.88.1",
                "openvpn_server_mask": 23,
                "rules": [{
                    "rule_id": "e" * 32,
                    "kind": "vpn_ban",
                    "enabled": True,
                    "name": "IPv6 not supported by legacy block",
                    "source": "2001:db8::1/128",
                }],
            })

    def test_import_legacy_and_existing_hard_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.js"
            legacy_file(path)
            inspection = inspect_before_rules(before_rules())
            cfg = import_legacy(path, inspection)
        self.assertEqual(cfg.version, 2)
        self.assertEqual(len(cfg.vpn_servers), 1)
        server = cfg.vpn_servers[0]
        kinds = [rule.kind for rule in cfg.rules]
        self.assertEqual(kinds.count("vpn_ban"), 1)
        self.assertEqual(kinds.count("standard"), 2)
        mapping = legacy_openvpn_mapping(cfg, server.server_id)
        self.assertEqual(mapping["interface"], "tun+")
        self.assertEqual({item["type"] for item in mapping["clients"]}, {1, 2})
        self.assertTrue(all(
            rule.vpn_server_id == server.server_id
            for rule in cfg.rules
            if rule.kind == "vpn_ban" or "VPN isolation" in rule.name
        ))
        self.assertEqual(
            hard_source_rules(cfg),
            (("-A", "ufw-before-input", "-s", "198.51.100.44", "-j", "ACCEPT"),),
        )
        self.assertEqual(len(managed_standard_rule_ids(cfg)), 2)

    def test_multiple_legacy_imports_merge_as_separate_vpn_servers(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = Path(tmp) / "one.js"
            two = Path(tmp) / "two.js"
            legacy_file(one, name="vpn-one", ip="10.8.88.1")
            legacy_file(two, name="vpn-two", ip="10.9.88.1")
            first = import_legacy(one)
            second = import_legacy(two)
            merged = merge_config(first, second)
        self.assertEqual(len(merged.vpn_servers), 2)
        self.assertEqual({item.name for item in merged.vpn_servers}, {"vpn-one", "vpn-two"})
        for server in merged.vpn_servers:
            bans = [
                rule for rule in merged.rules
                if rule.kind == "vpn_ban" and rule.vpn_server_id == server.server_id
            ]
            self.assertEqual(len(bans), 1)

    def test_append_rule_keeps_host_local_rule_ids_stable(self):
        cfg = FirewallConfig()
        rule = FirewallRule(
            "f" * 32,
            "standard",
            True,
            "HTTPS",
            source="203.0.113.0/24",
            direction="input",
            action="allow",
            protocol="tcp",
            port_from=443,
            port_to=443,
        )
        cfg = append_rule(cfg, rule)
        self.assertEqual(cfg.rules[0].rule_id, "f" * 32)

    def test_hub_collectors_require_schema_008_and_preserve_association(self):
        server = FirewallVpnServer(
            "1" * 32, "vpn-one", "10.8.88.1", 23, "tun9"
        )
        cfg = normalize_config({
            "version": 2,
            "vpn_servers": [{
                "server_id": server.server_id,
                "name": server.name,
                "ip": server.ip,
                "mask": server.mask,
                "interface": server.interface,
            }],
            "rules": [{
                "rule_id": "c" * 32,
                "kind": "vpn_ban",
                "name": "Alice",
                "source": "10.8.89.12",
                "vpn_server_id": server.server_id,
            }],
        })
        with patch.object(hub_firewall_rules, "load_config", return_value=cfg):
            rules = hub_firewall_rules.hub_collect(
                HubContext(generated_at=None, machine_id="machine-firewall")
            )
        with patch.object(hub_vpn_servers, "load_config", return_value=cfg):
            servers = hub_vpn_servers.hub_collect(
                HubContext(generated_at=None, machine_id="machine-firewall")
            )
        self.assertEqual(rules.min_schema_version, 8)
        self.assertEqual(rules.items[0].vpn_server_uid, server.server_id)
        self.assertEqual(servers.min_schema_version, 8)
        self.assertEqual(servers.items[0].server_uid, server.server_id)
        self.assertEqual(servers.items[0].interface_name, "tun9")

    def test_port_specs_preserve_both_directions_and_reject_overlap(self):
        cfg = normalize_config({"version": 1, "rules": [{
            "rule_id": "f" * 32,
            "kind": "standard",
            "name": "web",
            "direction": "input",
            "action": "allow",
            "protocol": "tcp",
            "src_ports": "40000-40100,22",
            "dst_ports": "8080-8090,443,80",
        }]})
        rule = cfg.rules[0]
        self.assertEqual(rule.src_ports, "22,40000-40100")
        self.assertEqual(rule.dst_ports, "80,443,8080-8090")
        self.assertEqual((rule.port_from, rule.port_to), (None, None))
        for invalid in ("0", "65536", "4-3", "80,80", "80-90,90-100", "80,,443"):
            with self.subTest(invalid=invalid), self.assertRaises(FirewallConfigError):
                normalize_port_spec(invalid, "port")
        self.assertEqual(normalize_port_spec("", "ports"), "")

    def test_legacy_range_becomes_destination_ports(self):
        cfg = normalize_config({"version": 1, "rules": [{
            "rule_id": "d" * 32,
            "kind": "standard",
            "name": "legacy",
            "direction": "input",
            "action": "allow",
            "protocol": "tcp",
            "port_from": 3000,
            "port_to": 3010,
        }]})
        self.assertEqual(cfg.rules[0].dst_ports, "3000-3010")
        self.assertIsNone(cfg.rules[0].port_from)

    def test_scoped_port_rules_cannot_become_legacy_hard_source(self):
        cfg = normalize_config({"version": 2, "vpn_servers": [], "rules": [{
            "rule_id": "c" * 32,
            "kind": "standard",
            "name": "ssh",
            "direction": "input",
            "action": "allow",
            "protocol": "tcp",
            "source": "203.0.113.4",
            "dst_ports": "22",
        }]})
        self.assertEqual(hard_source_rules(cfg), ())
        self.assertEqual(managed_standard_rule_ids(cfg), set())

    def test_reject_save_before_confirmation(self):
        rule = FirewallRule("f" * 32, "standard", name="test")
        with patch.object(
            firewall_menu_rules, "render_progress", return_value=78
        ) as redraw, patch.object(
            firewall_menu_rules, "confirm", return_value=False
        ):
            self.assertFalse(firewall_menu_rules._confirm_rule(rule, 78))
        redraw.assert_called_once()

    def test_protocol_colors_keep_tcp_green_and_udp_cyan(self):
        self.assertEqual(
            menu_helpers.color_protocol("tcp"),
            menu_helpers.text_color("TCP", menu_helpers.en_color.GREEN),
        )
        self.assertEqual(
            menu_helpers.color_protocol("udp"),
            menu_helpers.text_color("UDP", menu_helpers.en_color.CYAN),
        )
        self.assertNotEqual(
            menu_helpers.color_protocol("udp"),
            menu_helpers.text_color("UDP", menu_helpers.en_color.BLUE),
        )

    def test_optional_editor_value_can_be_cleared_explicitly(self):
        with patch.object(menu_helpers, "get_input", return_value="-"):
            value = menu_helpers.prompt(
                "Optional:",
                width=72,
                current="2026-12-31",
                required=False,
                context={},
            )
        self.assertEqual(value, "")

    def test_existing_rule_action_no_longer_uses_undefined_context(self):
        rule = FirewallRule("f" * 32, "standard", name="test")
        cfg = FirewallConfig(rules=(rule,))
        screen = firewall_menu_rules.FirewallRulesMenu()
        with patch.object(screen, "_load", return_value=cfg), patch.object(
            firewall_menu_rules, "pick", return_value=None
        ) as choose:
            result = screen.rule_action(SimpleNamespace(data=rule.rule_id))
        choose.assert_called_once()
        self.assertIsNotNone(result)

    def test_interface_choices_are_short_unique_and_keep_full_names_as_data(self):
        interfaces = [
            SimpleNamespace(
                name="verylongif01",
                ipv4="192.0.2.10",
                ipv6="2001:db8::10",
            ),
            SimpleNamespace(
                name="verylongif02",
                ipv4="192.0.2.11",
                ipv6="2001:db8::11",
            ),
        ]
        with patch.object(menu_helpers, "getInterfaces", return_value=interfaces):
            options = menu_helpers.host_interface_options()
        self.assertEqual([item[0] for item in options], ["1", "2"])
        self.assertEqual([item[2] for item in options], ["verylongif01", "verylongif02"])
        self.assertTrue(all(len(item[0]) <= 8 for item in options))

    def test_editor_save_publishes_host_rules_best_effort(self):
        fake = SimpleNamespace(menuRecycle=False)
        cfg = FirewallConfig()
        saved = Path("/etc/jb_sys_apps/firewall.json")
        with patch.object(
            firewall_menu_rules, "save_config", return_value=saved
        ) as save, patch.object(
            firewall_menu_rules, "sync_local_rules_best_effort"
        ) as sync:
            result = firewall_menu_rules.FirewallRulesMenu._save(fake, cfg)
        save.assert_called_once_with(cfg)
        sync.assert_called_once_with()
        self.assertTrue(fake.menuRecycle)
        self.assertTrue(bool(getattr(result, "ok", None)))

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
