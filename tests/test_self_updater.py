from __future__ import annotations

from pathlib import Path
import stat
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
        self.default_state_path = self.updater.plugins.state_path
        self.updater.plugins.catalog_path = self.root / "pluginy.jsonc"
        self.updater.plugins.state_path = self.root / "plugins.jsonc"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_plugin_state_path_has_no_runtime_side_effect(self) -> None:
        self.assertEqual(
            self.default_state_path,
            Path("/etc/jb_sys_apps/plugins.jsonc"),
        )

    def test_core_preflight_does_not_depend_on_optional_plugin_catalog(self) -> None:
        with patch.object(self.updater, "_capture", return_value=(0, "")), \
             patch.object(self.updater, "_is_initialized_submodule", return_value=False), \
             patch.object(
                 self.updater.plugins,
                 "load_catalog",
                 side_effect=AssertionError("optional catalog must not be read"),
             ):
            self.assertTrue(self.updater._verify_clean_worktrees())

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

    def test_registry_writes_token_with_private_permissions(self) -> None:
        self.updater.plugins.set_token("private_plugin", "tester", "secret-token")
        token_path = self.root / "assets/tokens/private_plugin.cd"
        self.assertEqual(token_path.read_text(encoding="utf-8"), "tester:secret-token\n")
        self.assertEqual(stat.S_IMODE(token_path.stat().st_mode), 0o600)

    def test_private_uninstalled_plugin_without_token_is_optional_skip(self) -> None:
        plugin = {
            "adr_name": "app_50_private",
            "private": True,
            "optional": True,
            "auto_update": True,
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

    def test_locally_disabled_plugin_is_not_touched_even_with_token(self) -> None:
        plugin = {
            "adr_name": "app_50_private",
            "private": True,
            "optional": True,
            "auto_update": True,
            "access": {"type": "token"},
        }
        self.updater.plugins.save_state(
            {"private_plugin": {"enabled": False}}
        )
        self.updater.plugins.set_token("private_plugin", "tester", "secret-token")
        with patch.object(self.updater, "_run_live") as run_live:
            self.assertTrue(self.updater._update_plugin("private_plugin", plugin))
        run_live.assert_not_called()
        self.assertIn("disabled by local plugin settings", self.updater.report.warnings[0])

    def test_catalog_auto_update_false_is_not_touched(self) -> None:
        plugin = {
            "adr_name": "app_40_public",
            "private": False,
            "optional": True,
            "auto_update": False,
        }
        with patch.object(self.updater, "_run_live") as run_live:
            self.assertTrue(self.updater._update_plugin("public_plugin", plugin))
        run_live.assert_not_called()

    def test_plugin_path_rejects_parent_directory(self) -> None:
        self.assertIsNone(
            self.updater.plugins.plugin_path({"adr_name": "../app_50_private"})
        )

    def test_update_availability_uses_only_ls_remote_for_current_main(self) -> None:
        (self.root / ".git").mkdir()
        local_head = "a" * 40
        commands = []

        def capture(cmd, **kwargs):
            commands.append(list(cmd))
            return 0, f"{local_head}\trefs/heads/main"

        with patch.object(self.updater, "_head", return_value=local_head), patch.object(
            self.updater, "_capture", side_effect=capture
        ):
            result = self.updater.check_availability(cache_ttl=0)

        self.assertEqual(result.state, "current")
        self.assertEqual(result.status_text, "up to date")
        self.assertEqual(
            commands[0][-4:],
            ["ls-remote", "--heads", "origin", "refs/heads/main"],
        )
        command_text = " ".join(commands[0])
        self.assertNotIn(" pull ", f" {command_text} ")
        self.assertNotIn(" fetch ", f" {command_text} ")
        self.assertNotIn(" submodule ", f" {command_text} ")

    def test_update_availability_reports_remote_difference(self) -> None:
        (self.root / ".git").mkdir()
        local_head = "a" * 40
        remote_head = "b" * 40
        with patch.object(self.updater, "_head", return_value=local_head), patch.object(
            self.updater,
            "_capture",
            return_value=(0, f"{remote_head}\trefs/heads/main"),
        ):
            result = self.updater.check_availability(cache_ttl=0)

        self.assertEqual(result.state, "available")
        self.assertEqual(result.status_text, "update available")
        self.assertEqual(result.remote_head, remote_head)

    def test_update_availability_failure_is_nonfatal_unknown(self) -> None:
        (self.root / ".git").mkdir()
        with patch.object(self.updater, "_head", return_value="a" * 40), patch.object(
            self.updater, "_capture", return_value=(124, "Command timed out.")
        ):
            result = self.updater.check_availability(cache_ttl=0)

        self.assertEqual(result.state, "unknown")
        self.assertEqual(result.status_text, "check unavailable")
        self.assertIn("timed out", result.detail.lower())

    def test_update_availability_cache_avoids_repeated_remote_check(self) -> None:
        (self.root / ".git").mkdir()
        local_head = "a" * 40
        remote_head = "b" * 40
        with patch.object(self.updater, "_head", return_value=local_head), patch.object(
            self.updater,
            "_capture",
            return_value=(0, f"{remote_head}\trefs/heads/main"),
        ):
            first = self.updater.check_availability(cache_ttl=300)

        with patch.object(self.updater, "_head", return_value=local_head), patch.object(
            self.updater,
            "_capture",
            side_effect=AssertionError("remote check must be served from cache"),
        ):
            second = self.updater.check_availability(cache_ttl=300)

        self.assertEqual(first.state, "available")
        self.assertEqual(second.state, "available")
        self.assertTrue(second.cached)


if __name__ == "__main__":
    unittest.main()
