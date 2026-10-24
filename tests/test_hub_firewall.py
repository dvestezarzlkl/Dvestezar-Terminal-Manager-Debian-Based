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

    def test_active_menu_prioritizes_edit_and_has_no_apply(self):
        self.assertEqual(firewall_menu._HUB_PROVIDER_KEY_, "ufw")
        self.assertTrue(callable(firewall_menu.hub_collect))
        self.assertEqual(firewall_menu.menu._VERSION_, "0.4.0")
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
            ["e", "i", "s", "p", "l"],
        )
        self.assertFalse(hasattr(firewall_menu.menu, "apply_rules"))

    def test_menu_gates_inactive_unknown_and_absent_without_mutation(self):
        for detected, status, fragment in (
            (False, "absent", "UFW"),
            (True, "inactive", "UFW"),
            (True, "unknown", "UFW"),
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
                self.assertIn(fragment, screen.menu[0].label)

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
        screen = firewall_menu.menu()
        with patch.object(
            firewall_menu, "load_config", return_value=cfg
        ), patch.object(
            firewall_menu._BEFORE_RULES.__class__,
            "read_text",
            return_value=before_rules(),
        ), patch.object(
            firewall_menu, "anyKey"
        ), redirect_stdout(io.StringIO()) as output:
            screen.preview_local_config(None)

        self.assertIn("vpn-jb", output.getvalue())
        self.assertIn("NO_CHANGE", output.getvalue())
        self.assertIn("0", output.getvalue())

    def test_preview_passes_each_vpn_server_interface_to_policy(self):
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
        result = SimpleNamespace(
            status="NO_CHANGE",
            current_rules=2,
            effective_rules=2,
            expired_bans=0,
            next_expiry=None,
            reason="",
        )
        screen = firewall_menu.menu()
        with patch.object(
            firewall_menu, "load_config", return_value=cfg
        ), patch.object(
            firewall_menu._BEFORE_RULES.__class__,
            "read_text",
            return_value=before_rules_two_servers(),
        ), patch.object(
            firewall_menu, "plan_legacy_openvpn", return_value=result
        ) as plan, patch.object(
            firewall_menu, "anyKey"
        ):
            screen.preview_local_config(None)
        self.assertEqual(plan.call_args.kwargs["interface"], "tun9")

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
