"""Regression tests for the Hub menu's conditional systemd last-run header."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from libs.app import cfg
from libs.app.hub import systemd_diagnostics as diagnostics


class HubLastServiceRunTests(unittest.TestCase):
    def test_last_start_is_read_from_service_not_timer(self):
        properties = {
            "LoadState": "loaded",
            "ActiveState": "inactive",
            "Result": "success",
            "ExecMainStatus": "0",
            "ExecMainStartTimestamp": "Mon 2026-10-19 11:36:05 CEST",
        }
        with patch.object(diagnostics, "_show_properties", return_value=properties) as query:
            start, state, result, code = diagnostics.last_service_run()
        self.assertEqual(start, "2026-10-19 11:36:05")
        self.assertEqual((state, result, code), ("inactive", "success", "0"))
        query.assert_called_once()
        self.assertEqual(query.call_args.args[0], diagnostics.SERVICE_NAME)
        self.assertNotIn(diagnostics.TIMER_NAME, str(query.call_args))

    def test_no_history_and_unavailable_service(self):
        with patch.object(diagnostics, "_show_properties", return_value={
            "LoadState": "loaded", "Result": "success", "ExecMainStatus": "0"
        }):
            start, *_ = diagnostics.last_service_run()
        self.assertIsNone(start)
        with patch.object(diagnostics, "_show_properties", return_value={
            "LoadState": "not-found"
        }):
            with self.assertRaises(RuntimeError):
                diagnostics.last_service_run()

    def test_header_reads_service_only_when_hourly_timer_mode_is_selected(self):
        from libs.app.hub import menu as hub_menu
        sample = ("2026-10-19 11:36:05", "inactive", "success", "0")
        for mode in ("startup", "timer", "off"):
            with self.subTest(mode=mode), patch.object(
                cfg, "HUB_SYNC_MODE", mode
            ), patch.object(
                hub_menu, "timer_status", return_value="active"
            ), patch.object(
                hub_menu, "last_service_run", return_value=sample
            ) as query:
                view = hub_menu.HubSettingsMenu()
                view.onShowMenu()
                header = dict(view.subTitle)
                if mode == "timer":
                    self.assertEqual(
                        header[hub_menu.TXT_HUB_LAST_RUN],
                        "2026-10-19 11:36:05 (OK)"
                    )
                    query.assert_called_once()
                else:
                    self.assertNotIn(hub_menu.TXT_HUB_LAST_RUN, header)
                    query.assert_not_called()

    def test_header_handles_systemctl_timeout_without_blocking_menu(self):
        from subprocess import TimeoutExpired
        from libs.app.hub import menu as hub_menu

        with patch.object(cfg, "HUB_SYNC_MODE", "timer"), patch.object(
            hub_menu, "timer_status", return_value="active"
        ), patch.object(
            hub_menu, "last_service_run",
            side_effect=TimeoutExpired(cmd="systemctl show", timeout=8)
        ):
            view = hub_menu.HubSettingsMenu()
            view.onShowMenu()
            self.assertEqual(
                dict(view.subTitle)[hub_menu.TXT_HUB_LAST_RUN],
                hub_menu.TXT_HUB_LAST_RUN_UNAVAILABLE
            )

    def test_header_shows_missing_running_error_and_unavailable_states(self):
        from libs.app.hub import menu as hub_menu
        variants = [
            ((None, "inactive", "success", "0"), hub_menu.TXT_HUB_LAST_RUN_NEVER),
            (("2026-10-19 11:36:05", "activating", "success", "0"),
             "2026-10-19 11:36:05 (" + hub_menu.TXT_HUB_LAST_RUN_RUNNING + ")"),
            (("2026-10-19 11:36:05", "inactive", "exit-code", "2"),
             "2026-10-19 11:36:05 (" + hub_menu.TXT_HUB_LAST_RUN_FAILED.format(code="2") + ")"),
        ]
        for response, expected in variants:
            with self.subTest(response=response), patch.object(
                cfg, "HUB_SYNC_MODE", "timer"
            ), patch.object(hub_menu, "timer_status", return_value="active"), patch.object(
                hub_menu, "last_service_run", return_value=response
            ):
                view = hub_menu.HubSettingsMenu()
                view.onShowMenu()
                self.assertEqual(dict(view.subTitle)[hub_menu.TXT_HUB_LAST_RUN], expected)

        with patch.object(cfg, "HUB_SYNC_MODE", "timer"), patch.object(
            hub_menu, "timer_status", return_value="active"
        ), patch.object(hub_menu, "last_service_run", side_effect=RuntimeError("systemctl offline")):
            view = hub_menu.HubSettingsMenu()
            view.onShowMenu()
            self.assertEqual(
                dict(view.subTitle)[hub_menu.TXT_HUB_LAST_RUN],
                hub_menu.TXT_HUB_LAST_RUN_UNAVAILABLE
            )


if __name__ == "__main__":
    unittest.main()
