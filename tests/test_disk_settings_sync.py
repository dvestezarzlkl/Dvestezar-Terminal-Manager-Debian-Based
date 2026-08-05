import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from libs.app.disk_hlp import c_other, disk_settings
from libs.app.hub.models import HubDiskNameUpdate


class DiskSettingsSyncTests(unittest.TestCase):
    def setUp(self):
        self.previous_names = dict(disk_settings.diskNames)
        self.previous_updates = dict(disk_settings.diskNameUpdatedAt)
        self.previous_mnt = disk_settings.MNT_DIR
        self.previous_bkp = disk_settings.BKP_DIR

    def tearDown(self):
        disk_settings.diskNames = self.previous_names
        disk_settings.diskNameUpdatedAt = self.previous_updates
        disk_settings.MNT_DIR = self.previous_mnt
        disk_settings.BKP_DIR = self.previous_bkp

    def test_legacy_disk_names_gain_timestamp_without_losing_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "disk.json"
            path.write_text(
                json.dumps(
                    {
                        "MNT_DIR": "/mnt",
                        "BKP_DIR": "/var/backups",
                        "diskNames": {"ABC-123": "backup_disk"},
                    }
                ),
                encoding="utf-8",
            )
            disk_settings.diskNames = {}
            disk_settings.diskNameUpdatedAt = {}
            with patch.object(disk_settings, "_config_path", return_value=path):
                disk_settings.load()
                saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(disk_settings.diskNames, {"abc-123": "backup_disk"})
        self.assertIn("abc-123", disk_settings.diskNameUpdatedAt)
        self.assertEqual(saved["diskNames"], {"abc-123": "backup_disk"})
        self.assertIn("abc-123", saved["diskNameUpdatedAt"])

    def test_newer_remote_name_updates_once_and_older_update_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "disk.json"
            local_time = datetime.now(timezone.utc)
            disk_settings.diskNames = {"ptuuid-1": "local"}
            disk_settings.diskNameUpdatedAt = {
                "ptuuid-1": local_time.isoformat(timespec="microseconds")
            }
            with patch.object(disk_settings, "_config_path", return_value=path):
                disk_settings.apply_remote_names(
                    (
                        HubDiskNameUpdate(
                            "ptuuid-1", "remote", local_time + timedelta(seconds=1)
                        ),
                    )
                )
                disk_settings.apply_remote_names(
                    (
                        HubDiskNameUpdate(
                            "ptuuid-1", "old", local_time - timedelta(seconds=1)
                        ),
                    )
                )

        self.assertEqual(disk_settings.diskNames["ptuuid-1"], "remote")

    def test_empty_name_is_a_timestamped_tombstone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "disk.json"
            disk_settings.diskNames = {"ptuuid-1": "old"}
            disk_settings.diskNameUpdatedAt = {}
            with patch.object(disk_settings, "_config_path", return_value=path):
                disk_settings.set_disk_name("PTUUID-1", "")

        self.assertEqual(disk_settings.diskNames["ptuuid-1"], "")
        self.assertIsNotNone(disk_settings.get_disk_name_updated_at("ptuuid-1"))

    def test_prepare_machine_id_for_first_boot_preserves_first_boot_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "etc/systemd/system").mkdir(parents=True)
            (root / "var/lib/dbus").mkdir(parents=True)
            (root / "etc/machine-id").write_text(
                "0123456789abcdef0123456789abcdef\n", encoding="ascii"
            )
            (root / "var/lib/dbus/machine-id").write_text(
                "0123456789abcdef0123456789abcdef\n", encoding="ascii"
            )
            part = SimpleNamespace(mountpoints=[str(root)])

            error = c_other.prepare_machine_id_for_first_boot(part)

            self.assertIsNone(error)
            self.assertEqual(
                (root / "etc/machine-id").read_text(encoding="ascii"), ""
            )
            self.assertFalse((root / "var/lib/dbus/machine-id").exists())
            service = (
                root
                / "etc/systemd/system/generate-machine-id-firstboot.service"
            )
            self.assertIn("ConditionFirstBoot=yes", service.read_text(encoding="utf-8"))
            self.assertIn(
                "ExecStart=/usr/bin/systemd-machine-id-setup",
                service.read_text(encoding="utf-8"),
            )
            symlink = (
                root
                / "etc/systemd/system/multi-user.target.wants"
                / "generate-machine-id-firstboot.service"
            )
            self.assertTrue(symlink.is_symlink())
            self.assertEqual(
                str(symlink.readlink()), "../generate-machine-id-firstboot.service"
            )

    def test_machine_id_menu_wording_describes_first_boot_preparation(self):
        source = Path(
            "libs/app/menus/app_10_disk/menu.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "Připravit nové Machine ID při prvním bootu", source
        )
        self.assertNotIn("Resetovat MachineID", source)


if __name__ == "__main__":
    unittest.main()
