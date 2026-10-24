"""Read-only Firewall Manager Hub and menu integration tests."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
from types import SimpleNamespace
import io
import unittest
from unittest.mock import patch

from libs.app.hub.models import HubContext
from libs.app.menus.app_40_firewall import hub_provider
from libs.app.menus.app_40_firewall import menu as firewall_menu
from libs.app.menus.app_40_firewall.compiler import build_candidate, compile_firewall
from libs.app.menus.app_40_firewall.config import (
    FirewallConfig,
    FirewallRule,
    FirewallVpnServer,
)
from tests.test_hub_firewall_policy import before_rules, before_rules_two_servers


class HubFirewallCollectorTests(unittest.TestCase):
    def test_ufw_active_service_uses_only_readonly_cli(self):
        calls = []

        def safe_cli(path: str, flag: str):
            calls.append((path, flag))
            if flag == "status":
                return SimpleNamespace(stdout="Status: active\n", returncode=0)
            if flag == "--version":
                return SimpleNamespace(stdout="ufw 0.36.2\n", returncode=0)
            self.fail("Unexpected UFW command")

        with patch.object(
            hub_provider, "_ufw_binary", return_value="/usr/sbin/ufw"
        ), patch.object(hub_provider, "_call", side_effect=safe_cli):
            snapshot = hub_provider.hub_collect(HubContext(
                datetime.now(timezone.utc), "machine-test"
            ))
        self.assertEqual(snapshot.dataset, "service")
        self.assertEqual(snapshot.source_key, "ufw")
        svc = snapshot.items[0]
        self.assertEqual(
            (svc.detected, svc.status, svc.version),
            (True, "active", "0.36.2"),
        )
        self.assertIsNone(svc.port)
        self.assertEqual(calls, [
            ("/usr/sbin/ufw", "status"),
            ("/usr/sbin/ufw", "--version"),
        ])

    def test_ufw_absent_and_command_failure_do_not_claim_active(self):
        with patch.object(
            hub_provider, "_ufw_binary", return_value=None
        ), patch.object(
            hub_provider, "_call", side_effect=AssertionError("unexpected call")
        ):
            result = hub_provider.inspect_ufw_service()
        self.assertFalse(result.detected)
        self.assertEqual(result.status, "absent")

        with patch.object(
            hub_provider, "_ufw_binary", return_value="/usr/sbin/ufw"
        ), patch.object(hub_provider, "_call", return_value=None):
            result = hub_provider.inspect_ufw_service()
        self.assertTrue(result.detected)
        self.assertEqual(result.status, "unknown")

    def test_active_menu_prioritizes_edit_and_explicit_guarded_runtime_actions(self):
        self.assertEqual(firewall_menu._HUB_PROVIDER_KEY_, "ufw")
        self.assertTrue(callable(firewall_menu.hub_collect))
        self.assertEqual(firewall_menu.menu._VERSION_, "0.5.0")
        screen = firewall_menu.menu()
        with patch.object(
            firewall_menu,
            "inspect_ufw_service",
            return_value=SimpleNamespace(
                detected=True, status="active", version="0.36"
            ),
        ):
            screen.onShowMenu()
        actionable = [item for item in screen.menu if getattr(item, "choice", "")]
        self.assertEqual(actionable[0].choice, "e")
        self.assertEqual(
            [item.choice for item in actionable],
            ["e", "a", "d", "i", "s", "p", "l"],
        )
        self.assertTrue(hasattr(firewall_menu.menu, "apply_rules"))
        self.assertTrue(hasattr(firewall_menu.menu, "disable_runtime"))

    def test_menu_offers_only_guarded_activation_when_inactive(self):
        with patch.object(
            firewall_menu,
            "inspect_ufw_service",
            return_value=SimpleNamespace(
                detected=True, status="inactive", version="0.36"
            ),
        ):
            screen = firewall_menu.menu()
            screen.onShowMenu()
        self.assertEqual(len(screen.menu), 1)
        self.assertTrue(screen.menu[0].enabled)
        self.assertEqual(screen.menu[0].choice, "a")

    def test_menu_blocks_unknown_and_absent_states(self):
        for detected, status in (
            (False, "absent"),
            (True, "unknown"),
        ):
            with self.subTest(status=status), patch.object(
                firewall_menu,
                "inspect_ufw_service",
                return_value=SimpleNamespace(
                    detected=detected, status=status, version=""
                ),
            ):
                screen = firewall_menu.menu()
                screen.onShowMenu()
                self.assertEqual(len(screen.menu), 1)
                self.assertFalse(screen.menu[0].enabled)

    def test_local_preview_exposes_no_change_without_apply(self):
        server = FirewallVpnServer(
            "1" * 32, "vpn-jb", "10.8.88.1", 23, "tun+"
        )
        cfg = FirewallConfig(
            vpn_servers=(server,),
            rules=(
                FirewallRule(
                    "a" * 32,
                    "vpn_ban",
                    True,
                    "Alice",
                    source="10.8.89.12/32",
                    vpn_server_id=server.server_id,
                ),
            ),
        )
        current = build_candidate(
            before_rules(),
            compile_firewall(cfg).ipv4,
            allow_openvpn=True,
        ).content
        screen = firewall_menu.menu()
        with patch.object(
            firewall_menu, "load_config", return_value=cfg
        ), patch.object(
            firewall_menu._BEFORE_RULES.__class__,
            "read_text",
            return_value=current,
        ), patch.object(
            firewall_menu,
            "_BEFORE6_RULES",
            SimpleNamespace(is_file=lambda: False),
        ), patch.object(
            firewall_menu, "anyKey"
        ), redirect_stdout(io.StringIO()) as output:
            screen.preview_local_config(None)

        self.assertIn("IPv4", output.getvalue())
        self.assertIn("NO_CHANGE", output.getvalue())

    def test_preview_detects_stale_block_when_local_ban_is_disabled(self):
        server = FirewallVpnServer(
            "3" * 32, "vpn-jb", "10.8.88.1", 23, "tun+"
        )
        cfg = FirewallConfig(
            vpn_servers=(server,),
            rules=(
                FirewallRule(
                    "c" * 32,
                    "vpn_ban",
                    False,
                    "Alice",
                    source="10.8.89.12/32",
                    vpn_server_id=server.server_id,
                ),
            ),
        )
        screen = firewall_menu.menu()
        with patch.object(
            firewall_menu, "load_config", return_value=cfg
        ), patch.object(
            firewall_menu._BEFORE_RULES.__class__,
            "read_text",
            return_value=before_rules(),
        ), patch.object(
            firewall_menu,
            "_BEFORE6_RULES",
            SimpleNamespace(is_file=lambda: False),
        ), patch.object(
            firewall_menu, "anyKey"
        ), redirect_stdout(io.StringIO()) as output:
            screen.preview_local_config(None)
        self.assertIn("CHANGED", output.getvalue())

    def test_preview_compiler_preserves_each_vpn_server_interface(self):
        server = FirewallVpnServer(
            "2" * 32, "vpn-two", "10.9.88.1", 23, "tun9"
        )
        cfg = FirewallConfig(
            vpn_servers=(server,),
            rules=(
                FirewallRule(
                    "b" * 32,
                    "vpn_ban",
                    True,
                    "Carol",
                    source="10.9.89.12/32",
                    vpn_server_id=server.server_id,
                ),
            ),
        )
        compiled = compile_firewall(cfg)
        self.assertTrue(all("tun9" in rule for rule in compiled.ipv4[0].rules))

    def test_menu_inspect_lists_multiple_openvpn_blocks_readonly(self):
        screen = firewall_menu.menu()
        with patch.object(
            firewall_menu._BEFORE_RULES.__class__,
            "read_text",
            return_value=before_rules_two_servers(),
        ) as reading, patch.object(
            firewall_menu, "anyKey"
        ), redirect_stdout(io.StringIO()) as output:
            result = screen.inspect_rules(None)
        reading.assert_called_once()
        self.assertIn("vpn-jb", output.getvalue())
        self.assertIn("vpn-two", output.getvalue())
        self.assertIn("2", output.getvalue())
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
