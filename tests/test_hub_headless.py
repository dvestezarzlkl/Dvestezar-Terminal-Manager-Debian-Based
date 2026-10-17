from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from libs.app import cfg
from libs.app.hub import provider_discovery, headless
from libs.app.hub.models import HubSyncReport
from libs.app.hub.runtime import HubRuntime


class HubHeadlessTests(unittest.TestCase):
    def test_discovery_uses_plugin_enable_policy_and_standalone_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            menus = path / "menus"
            plug = path / "sys_hub_plg"
            plug.mkdir()
            for app in ("app_10_disk", "app_20_node_red"):
                folder = menus / app
                folder.mkdir(parents=True)
                (folder / "menu.py").write_text("# fake menu\n")
                (folder / "hub_provider.py").write_text("# fake provider\n")
            (plug / "web_services.py").write_text("# fake collector\n")
            mock_registry = MagicMock()
            mock_registry.is_app_directory_enabled.side_effect = (
                lambda app: app == "app_10_disk"
            )
            with patch.object(provider_discovery, "_ROOT", path), patch.object(
                provider_discovery, "_MENU_ROOT", menus
            ), patch.object(provider_discovery, "_COLLECTOR_ROOT", plug), patch.object(
                provider_discovery, "PluginRegistry", return_value=mock_registry
            ), patch.object(provider_discovery, "_register_module") as register:
                warnings = provider_discovery.register_collectors(HubRuntime())
            self.assertEqual(warnings, [])
            self.assertEqual(
                [call.args[1] for call in register.call_args_list],
                [
                    "libs.app.menus.app_10_disk.hub_provider",
                    "libs.app.hub.sys_hub_plg.web_services",
                ],
            )

    def test_headless_disabled_does_not_access_database(self):
        with patch.object(headless.os, "geteuid", return_value=0), patch.object(
            cfg, "load"
        ), patch.object(cfg, "HUB_ENABLED", False), patch(
            "libs.JBLibs.helper.setLng"
        ), patch("libs.app.hub.runtime.hub_runtime.sync_all_locked") as collector:
            self.assertEqual(headless.main(), 0)
            collector.assert_not_called()

    def test_headless_returns_nonzero_when_provider_fails(self):
        with patch.object(headless.os, "geteuid", return_value=0), patch.object(
            cfg, "load"
        ), patch.object(cfg, "HUB_ENABLED", True), patch(
            "libs.JBLibs.helper.setLng"
        ), patch.object(provider_discovery, "register_collectors", return_value=[]), patch(
            "libs.app.hub.runtime.hub_runtime.sync_all_locked",
            return_value=HubSyncReport(core_synced=True, warnings=["broken provider"]),
        ):
            self.assertEqual(headless.main(), 2)

    def test_headless_requires_privilege(self):
        with patch.object(headless.os, "geteuid", return_value=1000):
            self.assertEqual(headless.main(), 77)

    def test_entrypoint_separates_headless_from_interactive_bootstrap(self):
        path = Path(__file__).resolve().parents[1] / "venv_run.py"
        code = path.read_text(encoding="utf-8")
        self.assertIn('"--hub-sync"', code)
        self.assertLess(code.index('"--hub-sync"'), code.index("import libs.app.menus.menuBoss"))


if __name__ == "__main__":
    unittest.main()
