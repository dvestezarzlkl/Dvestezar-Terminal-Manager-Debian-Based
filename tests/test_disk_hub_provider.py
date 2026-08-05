import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from libs.JBLibs.fs_utils import lsblkDiskInfo
from libs.app.disk_hlp import disk_settings
from libs.app.hub.models import HubContext, HubDiskNameUpdate
from libs.app.menus.app_10_disk.hub_provider import (
    apply_disk_updates,
    collect_disk_snapshot,
)


def disk(name: str, ptuuid: str, size: int = 1000) -> lsblkDiskInfo:
    return lsblkDiskInfo(
        name=name,
        label="",
        size=size,
        fstype="",
        type="disk",
        uuid="",
        partuuid="",
        mountpoints=[],
        children=[],
        ptuuid=ptuuid,
    )


class DiskHubProviderTests(unittest.TestCase):
    def setUp(self):
        self.context = HubContext(datetime.now(timezone.utc), "machine-1")
        self.previous_names = disk_settings.diskNames
        self.previous_updates = disk_settings.diskNameUpdatedAt
        disk_settings.diskNames = {}
        disk_settings.diskNameUpdatedAt = {}

    def tearDown(self):
        disk_settings.diskNames = self.previous_names
        disk_settings.diskNameUpdatedAt = self.previous_updates

    def test_collects_physical_disks_and_local_names(self):
        updated = datetime.now(timezone.utc)
        with patch(
            "libs.app.menus.app_10_disk.hub_provider.lsblk_list_disks",
            return_value={"sda": disk("sda", "ABC-123", 4096)},
        ), patch(
            "libs.app.menus.app_10_disk.hub_provider.disk_settings.init"
        ), patch(
            "libs.app.menus.app_10_disk.hub_provider.disk_settings.find_disk_name",
            return_value="system_disk",
        ), patch(
            "libs.app.menus.app_10_disk.hub_provider.disk_settings.get_disk_name_updated_at",
            return_value=updated,
        ):
            snapshot = collect_disk_snapshot(self.context)

        self.assertEqual(snapshot.source_key, "disks")
        self.assertEqual(snapshot.dataset, "disks")
        self.assertEqual(len(snapshot.items), 1)
        item = snapshot.items[0]
        self.assertEqual(item.ptuuid, "abc-123")
        self.assertEqual(item.device_name, "sda")
        self.assertEqual(item.display_name, "system_disk")
        self.assertEqual(item.name_updated_at, updated)
        self.assertEqual(item.size_bytes, 4096)

    def test_collects_disconnected_named_disks_as_catalog_only_items(self):
        updated = datetime.now(timezone.utc)
        disk_settings.diskNames = {"offline-id": "archive_disk"}
        disk_settings.diskNameUpdatedAt = {
            "offline-id": updated.isoformat(timespec="microseconds")
        }
        with patch(
            "libs.app.menus.app_10_disk.hub_provider.lsblk_list_disks",
            return_value={},
        ), patch(
            "libs.app.menus.app_10_disk.hub_provider.disk_settings.init"
        ):
            snapshot = collect_disk_snapshot(self.context)

        self.assertEqual(len(snapshot.items), 1)
        item = snapshot.items[0]
        self.assertEqual(item.ptuuid, "offline-id")
        self.assertEqual(item.display_name, "archive_disk")
        self.assertEqual(item.name_updated_at, updated)
        self.assertFalse(item.attached)
        self.assertEqual(item.device_name, "")
        self.assertEqual(item.device_path, "")

    def test_duplicate_ptuuid_is_rejected_before_database_write(self):
        with patch(
            "libs.app.menus.app_10_disk.hub_provider.lsblk_list_disks",
            return_value={
                "sda": disk("sda", "clone-id"),
                "sdb": disk("sdb", "CLONE-ID"),
            },
        ), patch(
            "libs.app.menus.app_10_disk.hub_provider.disk_settings.init"
        ):
            with self.assertRaisesRegex(ValueError, "Duplicate PTUUID"):
                collect_disk_snapshot(self.context)

    def test_remote_names_are_delegated_to_disk_settings(self):
        update = HubDiskNameUpdate(
            "ptuuid-1", "backup_disk", datetime.now(timezone.utc)
        )
        with patch(
            "libs.app.menus.app_10_disk.hub_provider.disk_settings.apply_remote_names"
        ) as apply_remote:
            apply_disk_updates((update,))
        apply_remote.assert_called_once_with((update,))


if __name__ == "__main__":
    unittest.main()
