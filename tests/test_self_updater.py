from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from libs.app.self_updater import ApplicationUpdater, UpdateReport


class SelfUpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "assets/tokens").mkdir(parents=True)
        self.updater = ApplicationUpdater(self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_update_report_changed_state(self) -> None:
        report = UpdateReport()
        self.assertFalse(report.changed)
        report.mandatory_changed = True
        self.assertTrue(report.changed)

    def test_read_token_accepts_one_line_with_final_newline(self) -> None:
        token_path = self.root / "assets/tokens/private_plugin.cd"
        token_path.write_text("tester:secret-token\n", encoding="utf-8")
        self.assertEqual(
            self.updater._read_token("private_plugin"),
            ("tester", "secret-token"),
        )

    def test_read_token_rejects_multiple_lines(self) -> None:
        token_path = self.root / "assets/tokens/private_plugin.cd"
        token_path.write_text("tester:secret\nsecond:value\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.updater._read_token("private_plugin")

    def test_private_uninstalled_plugin_without_token_is_optional_skip(self) -> None:
        plugin = {
            "adr_name": "app_50_private",
            "private": True,
            "optional": True,
            "auto_update": True,
            "access": {"type": "token"},
        }
        path = "libs/app/menus/app_50_private"
        with patch.object(self.updater, "_configured_submodule_paths", return_value={path}), \
             patch.object(self.updater, "_run_live") as run_live:
            self.assertTrue(self.updater._update_plugin("private_plugin", plugin))
        run_live.assert_not_called()
        self.assertIn("has no private_plugin.cd token", self.updater.report.warnings[0])

    def test_required_private_plugin_without_token_fails(self) -> None:
        plugin = {
            "adr_name": "app_50_private",
            "private": True,
            "optional": False,
            "auto_update": True,
            "access": {"type": "token"},
        }
        path = "libs/app/menus/app_50_private"
        with patch.object(self.updater, "_configured_submodule_paths", return_value={path}):
            self.assertFalse(self.updater._update_plugin("private_plugin", plugin))
        self.assertIsNotNone(self.updater.report.error)

    def test_public_auto_update_plugin_installs_without_token(self) -> None:
        plugin = {
            "adr_name": "app_40_public",
            "private": False,
            "optional": True,
            "auto_update": True,
        }
        path = "libs/app/menus/app_40_public"
        with patch.object(self.updater, "_configured_submodule_paths", return_value={path}), \
             patch.object(self.updater, "_run_live", return_value=True) as run_live, \
             patch.object(self.updater, "_verify_submodule", return_value=(True, "a" * 40)), \
             patch.object(self.updater, "_head", return_value=None):
            self.assertTrue(self.updater._update_plugin("public_plugin", plugin))
        self.assertEqual(run_live.call_count, 2)

    def test_disabled_plugin_is_not_touched(self) -> None:
        plugin = {
            "adr_name": "app_40_public",
            "private": False,
            "optional": True,
            "auto_update": False,
        }
        with patch.object(self.updater, "_run_live") as run_live:
            self.assertTrue(self.updater._update_plugin("public_plugin", plugin))
        run_live.assert_not_called()


if __name__ == "__main__":
    unittest.main()
