from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from libs.app import cfg
from libs.app.hub import scheduler, sync_lock
from libs.app.hub.sync_policy import effective_sync_mode


class HubScheduleTests(unittest.TestCase):
    def test_legacy_policy_is_preserved_until_explicit_selection(self):
        with patch.object(cfg, "HUB_SYNC_MODE", ""), patch.object(cfg, "HUB_AUTO_SYNC", True):
            self.assertEqual(effective_sync_mode(), "startup")
            self.assertEqual(effective_sync_mode(False), "off")
        with patch.object(cfg, "HUB_SYNC_MODE", "timer"):
            self.assertEqual(effective_sync_mode(False), "timer")
        with patch.object(cfg, "HUB_SYNC_MODE", "invalid"):
            with self.assertRaises(ValueError):
                effective_sync_mode()

    def test_timer_is_created_idempotently_and_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sys_apps"
            unit_dir = Path(tmp) / "units"
            root.mkdir()
            unit_dir.mkdir()
            (root / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (root / "run.sh").chmod(0o755)
            commands = []
            with patch.object(scheduler.os, "geteuid", return_value=0), patch.object(
                scheduler, "_systemctl", side_effect=lambda *args: commands.append(args)
            ):
                scheduler.set_schedule("timer", root=root, unit_dir=unit_dir)
                self.assertIn("OnCalendar=hourly", (unit_dir / scheduler.TIMER_NAME).read_text())
                service_text = (unit_dir / scheduler.SERVICE_NAME).read_text()
                self.assertIn("--hub-sync", service_text)
                self.assertIn(f"WorkingDirectory={root.resolve()}\n", service_text)
                self.assertNotIn('WorkingDirectory="', service_text)
                before = (unit_dir / scheduler.TIMER_NAME).read_bytes()
                scheduler.set_schedule("timer", root=root, unit_dir=unit_dir)
                self.assertEqual((unit_dir / scheduler.TIMER_NAME).read_bytes(), before)
                scheduler.set_schedule("off", root=root, unit_dir=unit_dir)
            self.assertEqual(commands[-1], ("disable", "--now", scheduler.TIMER_NAME))
            self.assertEqual(commands.count(("enable", "--now", scheduler.TIMER_NAME)), 2)

    def test_unmanaged_systemd_unit_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, units = Path(tmp) / "sys_apps", Path(tmp) / "units"
            root.mkdir()
            units.mkdir()
            (root / "run.sh").write_text("#!/bin/sh\n")
            (root / "run.sh").chmod(0o755)
            (units / scheduler.TIMER_NAME).write_text("[Timer]\nOnCalendar=weekly\n")
            with patch.object(scheduler.os, "geteuid", return_value=0), patch.object(
                scheduler, "_systemctl"
            ) as call:
                with self.assertRaisesRegex(RuntimeError, "unmanaged"):
                    scheduler.set_schedule("timer", root=root, unit_dir=units)
                call.assert_not_called()

    def test_enable_failure_rolls_back_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, units = Path(tmp) / "sys_apps", Path(tmp) / "units"
            root.mkdir()
            units.mkdir()
            (root / "run.sh").write_text("#!/bin/sh\n")
            (root / "run.sh").chmod(0o755)
            def fail_enable(*args):
                if args[:2] == ("enable", "--now"):
                    raise RuntimeError("simulated systemctl failure")
            with patch.object(scheduler.os, "geteuid", return_value=0), patch.object(
                scheduler, "_systemctl", side_effect=fail_enable
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated"):
                    scheduler.set_schedule("timer", root=root, unit_dir=units)
            self.assertFalse((units / scheduler.SERVICE_NAME).exists())
            self.assertFalse((units / scheduler.TIMER_NAME).exists())

    def test_menu_mode_selection_installs_timer_before_saving(self):
        from libs.app.hub import menu as hub_menu
        from libs.app.hub.menu import HubSettingsMenu

        with patch.object(cfg, "HUB_SYNC_MODE", ""), patch.object(
            cfg, "HUB_AUTO_SYNC", True
        ), patch.object(cfg, "HUB_ENABLED", True), patch.object(
            hub_menu, "select", return_value=SimpleNamespace(
                item=SimpleNamespace(data="timer")
            )
        ) as chooser, patch.object(hub_menu, "set_schedule") as schedule, patch.object(
            cfg, "save"
        ) as save, patch.object(hub_menu.hub_runtime, "refresh_status"):
            def require_install_first():
                schedule.assert_called_once_with("timer")
            save.side_effect = require_install_first
            result = HubSettingsMenu().choose_sync_mode(None)
            chooser.assert_called_once()
            self.assertEqual(
                [option.data for option in chooser.call_args.args[1]],
                ["startup", "timer", "off"],
            )
            self.assertEqual(
                [option.choice for option in chooser.call_args.args[1]],
                ["S", "T", "O"],
            )
            self.assertEqual(chooser.call_args.kwargs["title"], hub_menu.TXT_HUB_SYNC_MODE)
            self.assertEqual(cfg.HUB_SYNC_MODE, "timer")
            self.assertTrue(bool(getattr(result, "ok", None)))

    def test_menu_mode_selection_rolls_back_on_systemd_failure(self):
        from libs.app.hub import menu as hub_menu
        from libs.app.hub.menu import HubSettingsMenu

        with patch.object(cfg, "HUB_SYNC_MODE", ""), patch.object(
            cfg, "HUB_AUTO_SYNC", True
        ), patch.object(cfg, "HUB_ENABLED", True), patch.object(
            hub_menu, "select", return_value=SimpleNamespace(
                item=SimpleNamespace(data="timer")
            )
        ), patch.object(
            hub_menu, "set_schedule", side_effect=[RuntimeError("systemctl failed"), None]
        ) as schedule, patch.object(cfg, "save") as save:
            result = HubSettingsMenu().choose_sync_mode(None)
            self.assertEqual(cfg.HUB_SYNC_MODE, "")
            self.assertIsNotNone(result.err)
            self.assertEqual(schedule.call_count, 2)
            schedule.assert_any_call("timer")
            schedule.assert_any_call("startup")
            save.assert_not_called()

    def test_menu_mode_esc_does_not_change_configuration_or_systemd(self):
        from libs.app.hub import menu as hub_menu
        from libs.app.hub.menu import HubSettingsMenu

        with patch.object(cfg, "HUB_SYNC_MODE", "startup"), patch.object(
            hub_menu, "select", return_value=SimpleNamespace(item=None)
        ) as chooser, patch.object(hub_menu, "set_schedule") as schedule, patch.object(
            cfg, "save"
        ) as save:
            result = HubSettingsMenu().choose_sync_mode(None)
        chooser.assert_called_once()
        schedule.assert_not_called()
        save.assert_not_called()
        self.assertFalse(getattr(result, "err", None))

    def test_menu_mode_selection_startup_and_off(self):
        from libs.app.hub import menu as hub_menu
        from libs.app.hub.menu import HubSettingsMenu

        for initial, selected in (("timer", "startup"), ("startup", "off")):
            with self.subTest(selected=selected), patch.object(
                cfg, "HUB_SYNC_MODE", initial
            ), patch.object(cfg, "HUB_ENABLED", True), patch.object(
                hub_menu, "select", return_value=SimpleNamespace(
                    item=SimpleNamespace(data=selected)
                )
            ), patch.object(hub_menu, "set_schedule") as schedule, patch.object(
                cfg, "save"
            ) as save, patch.object(hub_menu.hub_runtime, "refresh_status"):
                result = HubSettingsMenu().choose_sync_mode(None)
                schedule.assert_called_once_with(selected)
                save.assert_called_once()
                self.assertEqual(cfg.HUB_SYNC_MODE, selected)
                self.assertTrue(bool(getattr(result, "ok", None)))

    def test_menu_mode_invalid_framework_data_is_rejected(self):
        from libs.app.hub import menu as hub_menu
        from libs.app.hub.menu import HubSettingsMenu

        with patch.object(cfg, "HUB_SYNC_MODE", "startup"), patch.object(
            hub_menu, "select", return_value=SimpleNamespace(
                item=SimpleNamespace(data="unsupported")
            )
        ), patch.object(hub_menu, "set_schedule") as schedule, patch.object(
            cfg, "save"
        ) as save:
            result = HubSettingsMenu().choose_sync_mode(None)
        schedule.assert_not_called()
        save.assert_not_called()
        self.assertIsNotNone(result.err)

    def test_process_lock_detects_overlapping_collections(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            sync_lock, "_lock_path", return_value=Path(tmp) / "collection.lock"
        ):
            with sync_lock.hub_sync_lock():
                with self.assertRaises(sync_lock.HubSyncBusy):
                    with sync_lock.hub_sync_lock():
                        pass


if __name__ == "__main__":
    unittest.main()
