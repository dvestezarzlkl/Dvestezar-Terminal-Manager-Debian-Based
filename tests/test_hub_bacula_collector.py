"""Bacula FD single-file Hub service collector contract tests."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from libs.app.hub.models import HubContext, HubProviderSnapshot, HubService
from libs.app.hub.sys_hub_plg import bacula_fd


class HubBaculaServiceTests(unittest.TestCase):
    def test_available_bacula_fd_is_reported_without_credentials(self):
        def fake_run(args):
            if args[0] == "systemctl":
                return SimpleNamespace(
                    returncode=0, stdout="LoadState=loaded\nActiveState=active\n"
                )
            if args[0] == "dpkg-query":
                return SimpleNamespace(returncode=0, stdout="9.6.7-3ubuntu2")
            self.fail("Unexpected command")

        with patch.object(bacula_fd, "_run", side_effect=fake_run), patch.object(
            bacula_fd.shutil, "which", return_value="/usr/sbin/bacula-fd"
        ), patch.object(Path, "is_file", return_value=False):
            report = bacula_fd.hub_collect(HubContext(
                generated_at=None, machine_id="machine-a"
            ))
        self.assertIsInstance(report, HubProviderSnapshot)
        self.assertEqual(report.source_key, "bacula_fd")
        self.assertEqual(report.dataset, "service")
        self.assertEqual(report.items, (
            HubService("bacula_fd", True, None, "", "active", "9.6.7-3ubuntu2"),
        ))
        self.assertIsNone(report.items[0].port)

    def test_absent_daemon_is_reported_not_silently_removed(self):
        with patch.object(bacula_fd, "_run", return_value=None), patch.object(
            bacula_fd.shutil, "which", return_value=None
        ), patch.object(Path, "is_file", return_value=False):
            report = bacula_fd.hub_collect(HubContext(
                generated_at=None, machine_id="machine-b"
            ))
        self.assertEqual(len(report.items), 1)
        self.assertEqual(report.items[0].detected, False)
        self.assertEqual(report.items[0].status, "absent")
        self.assertFalse(report.items[0].version)

    def test_error_from_systemd_does_not_invent_service_running(self):
        def fake_run(args):
            if args[0] == "dpkg-query":
                return SimpleNamespace(returncode=0, stdout="13.0.1")
            return None

        with patch.object(bacula_fd, "_run", side_effect=fake_run), patch.object(
            bacula_fd.shutil, "which", return_value=None
        ), patch.object(Path, "is_file", return_value=False):
            report = bacula_fd.hub_collect(HubContext(
                generated_at=None, machine_id="machine-c"
            ))
        self.assertTrue(report.items[0].detected)
        self.assertEqual(report.items[0].status, "unknown")

    def test_collection_does_not_run_bacula_or_read_config(self):
        calls = []
        def fake_run(args):
            calls.append(args)
            return None

        with patch.object(bacula_fd, "_run", side_effect=fake_run), patch.object(
            bacula_fd.shutil, "which", return_value=None
        ), patch.object(Path, "is_file", return_value=False):
            bacula_fd.hub_collect(HubContext(
                generated_at=None, machine_id="machine-x"
            ))
        self.assertEqual(
            [args[0] for args in calls], ["systemctl", "dpkg-query"]
        )
        self.assertFalse(any("bacula-fd.conf" in str(args) for args in calls))


if __name__ == "__main__":
    unittest.main()
