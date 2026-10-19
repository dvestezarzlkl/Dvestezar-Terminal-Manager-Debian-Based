"""Host metadata ownership and systemd timer inventory regressions."""
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from libs.app import cfg
from libs.app.hub import core_provider


class HubHostMetadataTests(unittest.TestCase):
    def test_timer_state_is_read_from_systemd_not_legacy_auto_sync(self):
        scenarios = [
            ("enabled", 0, True),
            ("enabled-runtime", 0, True),
            ("disabled", 1, False),
            ("masked", 1, False),
            ("not-found", 1, False),
            ("unknown", 1, None),
        ]
        for state, rc, expected in scenarios:
            with self.subTest(state=state), patch.object(
                cfg, "HUB_AUTO_SYNC", True
            ), patch.object(
                core_provider, "_run",
                return_value=SimpleNamespace(stdout=state + "\n", returncode=rc)
            ) as run:
                self.assertIs(core_provider._timer_is_enabled(), expected)
                run.assert_called_once_with([
                    "systemctl", "is-enabled", "jb-sysapps-hub.timer"
                ])
        with patch.object(core_provider, "_run", return_value=None):
            self.assertIsNone(core_provider._timer_is_enabled())

    def test_mode_change_requests_core_only_best_effort_sync(self):
        from libs.app.hub import menu as hub_menu
        from libs.app.hub.menu import HubSettingsMenu
        with patch.object(cfg, "HUB_SYNC_MODE", "timer"), patch.object(
            cfg, "HUB_ENABLED", True
        ), patch.object(
            hub_menu, "select",
            return_value=SimpleNamespace(item=SimpleNamespace(data="off"))
        ), patch.object(hub_menu, "set_schedule"), patch.object(
            cfg, "save"
        ), patch.object(
            hub_menu.hub_runtime, "refresh_status"
        ), patch.object(
            hub_menu.hub_runtime, "sync_core_best_effort"
        ) as sync:
            result = HubSettingsMenu().choose_sync_mode(None)
            self.assertTrue(bool(getattr(result, "ok", None)))
            sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
