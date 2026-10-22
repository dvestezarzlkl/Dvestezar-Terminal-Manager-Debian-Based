"""Read-only Firewall Manager Hub and menu integration tests."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from libs.app.hub.models import HubContext
from libs.app.menus.app_40_firewall import hub_provider
from libs.app.menus.app_40_firewall import menu as firewall_menu


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
        with patch.object(hub_provider, "_ufw_binary", return_value="/usr/sbin/ufw"), patch.object(
            hub_provider, "_call", side_effect=safe_cli
        ):
            snapshot = hub_provider.hub_collect(HubContext(
                datetime.now(timezone.utc), "machine-test"
            ))
        self.assertEqual(snapshot.dataset, "service")
        self.assertEqual(snapshot.source_key, "ufw")
        self.assertEqual(len(snapshot.items), 1)
        svc = snapshot.items[0]
        self.assertEqual((svc.detected, svc.status, svc.version), (True, "active", "0.36.2"))
        self.assertIsNone(svc.port)
        self.assertEqual(calls, [
            ("/usr/sbin/ufw", "status"), ("/usr/sbin/ufw", "--version"),
        ])

    def test_ufw_absent_and_command_failure_do_not_claim_active(self):
        with patch.object(hub_provider, "_ufw_binary", return_value=None), patch.object(
            hub_provider, "_call", side_effect=AssertionError("unexpected call")
        ):
            result = hub_provider.inspect_ufw_service()
        self.assertFalse(result.detected)
        self.assertEqual(result.status, "absent")

        with patch.object(hub_provider, "_ufw_binary", return_value="/usr/sbin/ufw"), patch.object(
            hub_provider, "_call", return_value=None
        ):
            result = hub_provider.inspect_ufw_service()
        self.assertTrue(result.detected)
        self.assertEqual(result.status, "unknown")

    def test_menu_edits_only_local_desired_state_and_has_hub_provider_contract(self):
        self.assertEqual(firewall_menu._HUB_PROVIDER_KEY_, "ufw")
        self.assertTrue(callable(firewall_menu.hub_collect))
        self.assertEqual(firewall_menu.menu._VERSION_, "0.2.0")
        screen = firewall_menu.menu()
        screen.onShowMenu()
        self.assertEqual(len(screen.menu), 6)
        self.assertFalse(hasattr(firewall_menu.menu, "apply_rules"))

    def test_local_preview_exposes_no_change_without_apply(self):
        from libs.app.menus.app_40_firewall.config import FirewallConfig, FirewallRule
        from tests.test_hub_firewall_policy import before_rules

        cfg = FirewallConfig(
            openvpn_server_name="vpn-jb",
            openvpn_server_ip="10.8.88.1",
            openvpn_server_mask=23,
            rules=(
                FirewallRule(
                    "a" * 32, "vpn_ban", True, "Alice",
                    source="10.8.89.12/32", ban_to="2099-12-31",
                ),
            ),
        )
        screen = firewall_menu.menu()
        with patch.object(
            firewall_menu, "load_config", return_value=cfg
        ), patch.object(
            firewall_menu._BEFORE_RULES.__class__, "read_text",
            return_value=before_rules(),
        ), patch.object(
            firewall_menu, "anyKey"
        ), patch.object(
            hub_provider, "_call", side_effect=AssertionError("no UFW command")
        ), redirect_stdout(io.StringIO()) as output:
            screen.preview_local_config(None)

        self.assertIn("NO_CHANGE", output.getvalue())
        self.assertIn("0", output.getvalue())

    def test_menu_inspect_only_reads_before_rules(self):
        source = "\n".join([
            "*filter",
            "# *** BOF OpenVPN JB Config - test 10.8.88.0/23",
            "-A ufw-before-input -i tun+ -s 10.8.89.12 -j DROP",
            "# *** EOF OpenVPN JB Config - test 10.8.88.0/23",
            "# *** BOF ZLKL Hard Source Allow Config - managed by sys_apps",
            "-A ufw-before-input -s 198.51.100.23 -j ACCEPT",
            "# *** EOF ZLKL Hard Source Allow Config - managed by sys_apps",
            "COMMIT",
        ])
        screen = firewall_menu.menu()
        with patch.object(
            firewall_menu._BEFORE_RULES.__class__, "read_text",
            return_value=source,
        ) as reading, patch.object(
            firewall_menu, "anyKey"
        ), patch.object(
            hub_provider, "_call", side_effect=AssertionError("no UFW exec")
        ), redirect_stdout(io.StringIO()) as output:
            result = screen.inspect_rules(None)
        reading.assert_called_once()
        self.assertIn("OpenVPN", output.getvalue())
        self.assertIn("1", output.getvalue())
        self.assertIsNotNone(result)
