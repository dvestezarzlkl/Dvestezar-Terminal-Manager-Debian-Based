from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StartupDiagnosticsContractTests(unittest.TestCase):
    def test_venv_runner_logs_bootstrap_boundaries(self) -> None:
        source = (ROOT / "venv_run.py").read_text(encoding="utf-8")
        for marker in (
            "Startup bootstrap cfg module import: done",
            "Startup bootstrap cfg load: done",
            "Startup bootstrap logger initialization: done",
            "Startup bootstrap language setup: done",
            "Startup bootstrap terminal import: done",
            "Startup bootstrap menuBoss import: done",
            "Startup bootstrap runtime preflight: done",
            "Startup splash delay: start",
            "Startup splash delay: done",
            "Startup bootstrap: ready for menu initialization",
            "Startup menuBoss init/run call: start",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_menu_boss_logs_startup_phases(self) -> None:
        source = (ROOT / "libs/app/menus/menuBoss.py").read_text(encoding="utf-8")
        for marker in (
            "Startup menu discovery/filter: start",
            "Startup menu discovery/filter: done",
            "Startup menu module %s import: start",
            "Startup menu module %s import: done",
            "Startup dynamic menu registration: done",
            "Startup update availability check: start",
            "Startup update availability check: done",
            "Startup central settings phase: start",
            "Startup central settings phase: done",
            "Startup SysApps Hub phase: start",
            "Startup SysApps Hub phase: done",
            "Startup main menu handoff: ready",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
