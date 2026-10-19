from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from libs.app import cfg
from libs.app.hub import systemd_diagnostics as diagnostics


def _health(*, trigger_age=600, completion_age=590, due=2600, managed=True,
            enabled=True, active=True, result="success", status="0"):
    return diagnostics.HubTimerCheck(
        managed=managed, timer_loaded=True, timer_enabled=enabled,
        timer_active=active, service_loaded=True, service_state="inactive",
        last_trigger="Mon 2026-10-19 11:00:00 CEST",
        last_start="Mon 2026-10-19 11:00:01 CEST",
        last_completion="Mon 2026-10-19 11:00:10 CEST",
        next_run="Mon 2026-10-19 12:00:00 CEST",
        result=result, exit_status=status,
        trigger_age_seconds=trigger_age,
        start_age_seconds=None if trigger_age is None else trigger_age - 1,
        completion_age_seconds=completion_age,
        next_due_seconds=due,
    )


class HubSystemdDiagnosticsTests(unittest.TestCase):
    def test_healthy_requires_real_timer_history_and_successful_service(self):
        self.assertTrue(_health().healthy)
        # A manual service run must not pass as proof that the timer fired.
        self.assertFalse(_health(trigger_age=None).healthy)
        self.assertFalse(_health(trigger_age=80 * 60).healthy)
        self.assertFalse(replace(_health(), start_age_seconds=60).healthy)
        self.assertFalse(_health(completion_age=80 * 60).healthy)
        self.assertFalse(_health(due=None).healthy)
        self.assertFalse(_health(result="exit-code", status="2").healthy)
        self.assertFalse(_health(managed=False).healthy)
        self.assertFalse(_health(enabled=False).can_test)
        self.assertFalse(_health(active=False).can_test)
        self.assertFalse(replace(_health(), service_state="activating").can_test)

    def test_inspection_reads_systemd_properties_not_generic_hub_cache(self):
        now = time.time()
        def formatted(ts):
            return datetime.fromtimestamp(ts).strftime("%a %Y-%m-%d %H:%M:%S UTC")
        timer = {
            "LoadState": "loaded", "UnitFileState": "enabled",
            "ActiveState": "active",
            "LastTriggerUSec": formatted(now - 14 * 60),
            "NextElapseUSecRealtime": formatted(now + 45 * 60),
        }
        service = {
            "LoadState": "loaded", "ActiveState": "inactive",
            "Result": "success", "ExecMainStatus": "0",
            "ExecMainStartTimestamp": formatted(now - 14 * 60 + 1),
            "ExecMainExitTimestamp": formatted(now - 13 * 60),
        }
        with patch.object(diagnostics, "render_units", return_value=("service", "timer")), patch.object(
            diagnostics, "_read_managed", side_effect=[b"service", b"timer"]
        ) as files, patch.object(
            diagnostics, "_show_properties", side_effect=[timer, service]
        ) as systemctl:
            status = diagnostics.inspect_timer_sync()
        self.assertTrue(status.healthy)
        self.assertEqual(files.call_count, 2)
        self.assertEqual(systemctl.call_count, 2)
        self.assertEqual(systemctl.call_args_list[0].args[0], diagnostics.TIMER_NAME)
        self.assertEqual(systemctl.call_args_list[1].args[0], diagnostics.SERVICE_NAME)

    def test_untrusted_unit_cannot_be_invoked(self):
        with patch.object(diagnostics, "render_units", return_value=("service", "timer")), patch.object(
            diagnostics, "_read_managed", return_value=b"unexpected content"
        ), patch.object(diagnostics, "_show_properties") as show:
            show.side_effect = [
                {"LoadState": "loaded", "UnitFileState": "enabled", "ActiveState": "active"},
                {"LoadState": "loaded", "ActiveState": "inactive", "Result": "success", "ExecMainStatus": "0"},
            ]
            status = diagnostics.inspect_timer_sync()
        self.assertFalse(status.managed)
        self.assertFalse(status.can_test)

    def test_confirmed_oneshot_uses_systemctl_start_without_timer_changes(self):
        with patch.object(diagnostics.os, "geteuid", return_value=0), patch.object(
            diagnostics, "inspect_timer_sync", side_effect=[
                _health(trigger_age=None), _health(trigger_age=None, completion_age=3)
            ]
        ), patch.object(diagnostics.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            ok, message = diagnostics.run_systemd_sync()
        self.assertTrue(ok, message)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], [
            "systemctl", "start", "--no-ask-password", diagnostics.SERVICE_NAME
        ])
        self.assertEqual(run.call_args.kwargs["timeout"], 660)

    def test_oneshot_failure_and_not_ready_never_report_success(self):
        with patch.object(diagnostics.os, "geteuid", return_value=0), patch.object(
            diagnostics, "inspect_timer_sync", return_value=_health(active=False)
        ), patch.object(diagnostics.subprocess, "run") as run:
            ok, message = diagnostics.run_systemd_sync()
        self.assertFalse(ok)
        run.assert_not_called()

        with patch.object(diagnostics.os, "geteuid", return_value=0), patch.object(
            diagnostics, "inspect_timer_sync", return_value=_health()
        ), patch.object(diagnostics.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            ok, message = diagnostics.run_systemd_sync()
        self.assertFalse(ok)

    def test_menu_item_is_present_only_in_timer_mode(self):
        from libs.app.hub import menu as hub_menu
        for mode, expected in (("startup", False), ("timer", True), ("off", False)):
            with self.subTest(mode=mode), patch.object(cfg, "HUB_SYNC_MODE", mode), patch.object(
                hub_menu, "timer_status", return_value="active"
            ):
                menu = hub_menu.HubSettingsMenu()
                menu.onShowMenu()
                choices = [
                    getattr(item, "choice", None) for item in menu.menu if item is not None
                ]
            self.assertEqual("z" in choices, expected)

    def test_menu_confirmation_controls_invocation(self):
        from libs.app.hub import menu as hub_menu
        check = _health(trigger_age=None)
        with patch.object(cfg, "HUB_SYNC_MODE", "timer"), patch.object(
            cfg, "HUB_ENABLED", True
        ), patch.object(hub_menu, "inspect_timer_sync", return_value=check), patch.object(
            hub_menu, "confirm", return_value=False
        ) as confirm, patch.object(
            hub_menu, "run_systemd_sync"
        ) as run, patch("builtins.print"):
            hub_menu.HubSettingsMenu().test_systemd_sync(None)
        confirm.assert_called_once()
        self.assertIn(hub_menu.TXT_HUB_SYSTEMD_WARNING, confirm.call_args.args[0])
        run.assert_not_called()

        with patch.object(cfg, "HUB_SYNC_MODE", "timer"), patch.object(
            cfg, "HUB_ENABLED", True
        ), patch.object(hub_menu, "inspect_timer_sync", return_value=_health()), patch.object(
            hub_menu, "confirm", return_value=True
        ) as confirm, patch.object(
            hub_menu, "run_systemd_sync", return_value=(True, "success")
        ) as run, patch("builtins.print"):
            outcome = hub_menu.HubSettingsMenu().test_systemd_sync(None)
        confirm.assert_called_once()
        self.assertIn(hub_menu.TXT_HUB_SYSTEMD_HEALTHY, confirm.call_args.args[0])
        run.assert_called_once()
        self.assertTrue(bool(outcome.ok))

    def test_menu_refuses_unready_timer_without_confirmation(self):
        from libs.app.hub import menu as hub_menu
        with patch.object(cfg, "HUB_SYNC_MODE", "timer"), patch.object(
            cfg, "HUB_ENABLED", True
        ), patch.object(
            hub_menu, "inspect_timer_sync", return_value=_health(enabled=False)
        ), patch.object(hub_menu, "confirm") as confirm, patch.object(
            hub_menu, "run_systemd_sync"
        ) as run, patch("builtins.print"):
            outcome = hub_menu.HubSettingsMenu().test_systemd_sync(None)
        self.assertTrue(bool(outcome.err))
        confirm.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
