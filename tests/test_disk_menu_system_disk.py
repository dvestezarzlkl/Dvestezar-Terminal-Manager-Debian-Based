import inspect
import unittest
from unittest.mock import patch

from libs.JBLibs.fs_utils import lsblkDiskInfo
from libs.app.menus.app_10_disk.device_policy import is_manageable_storage_device
from libs.app.menus.app_10_disk.menu import (
    _can_write_whole_disk,
    _collect_mountpoints,
    _format_disk_display_name,
    _format_mountpoints,
    m_disk_oper,
    menu,
)


def device(
    name: str,
    *,
    type_: str = "disk",
    mountpoints: list[str] | None = None,
    children: list[lsblkDiskInfo] | None = None,
    ptuuid: str = "disk-id",
) -> lsblkDiskInfo:
    return lsblkDiskInfo(
        name=name,
        label="",
        size=1024,
        fstype="ext4" if type_ == "part" else "",
        type=type_,
        uuid="",
        partuuid="",
        mountpoints=mountpoints or [],
        children=children or [],
        ptuuid=ptuuid,
    )


class DiskMenuSystemDiskTests(unittest.TestCase):
    def system_disk(self) -> lsblkDiskInfo:
        bios = device("sda1", type_="part")
        root = device("sda2", type_="part", mountpoints=["/"])
        return device("sda", children=[bios, root])

    def test_system_parent_is_read_only(self):
        disk = self.system_disk()

        self.assertTrue(disk.isSystemDisk)
        self.assertFalse(_can_write_whole_disk(disk))

    def test_regular_disk_allows_whole_disk_operations(self):
        data = device("sdb1", type_="part", mountpoints=["/mnt/data"])
        disk = device("sdb", children=[data])

        self.assertTrue(_can_write_whole_disk(disk))

    def test_mountpoints_are_collected_from_children_and_rendered_as_paths(self):
        disk = self.system_disk()

        self.assertEqual(_collect_mountpoints(disk), ["/"])
        self.assertEqual(_format_mountpoints(disk), "/")
        self.assertEqual(_format_mountpoints(device("sdc")), "-")

    def test_long_mountpoint_text_is_truncated_without_losing_column_width(self):
        part = device(
            "sdb1",
            type_="part",
            mountpoints=["/mnt/very-long-production-mountpoint"],
        )

        rendered = _format_mountpoints(part, width=16)

        self.assertEqual(len(rendered), 16)
        self.assertTrue(rendered.endswith("..."))

    def test_colored_disk_name_padding_uses_visible_text_length(self):
        disk = device("sda", ptuuid="disk-id")
        with patch(
            "libs.app.menus.app_10_disk.menu.disk_settings.find_disk_name",
            return_value="root_workstation_pc",
        ), patch(
            "libs.app.menus.app_10_disk.menu.c_other.getDiskDisplayName",
            return_value="<colored-name>",
        ):
            rendered = _format_disk_display_name(disk, width=30)

        visible_length = len("sda root_workstation_pc")
        self.assertEqual(rendered, "<colored-name>" + " " * (30 - visible_length))

    def test_backup_and_restore_callbacks_reject_live_system_disk(self):
        operation = m_disk_oper()
        operation.diskInfo = self.system_disk()

        backup = operation.backup_disk(None)
        restore = operation.restore_disk(None)

        self.assertFalse(backup.ok)
        self.assertIn("živého systémového disku", backup.err)
        self.assertFalse(restore.ok)
        self.assertIn("živém systémovém disku", restore.err)

    def test_main_menu_loads_complete_disk_tree(self):
        source = inspect.getsource(menu.onShowMenu)

        self.assertIn("lsblk_list_disks(False)", source)
        self.assertNotIn("lsblk_list_disks(True)", source)

    def test_disk_detail_header_shows_ptuuid_after_disk_name(self):
        source = inspect.getsource(m_disk_oper.onShowMenu)

        disk_pos = source.index('("Disk"')
        ptuuid_pos = source.index('("PTUUID"')
        size_pos = source.index('("Size"')
        self.assertLess(disk_pos, ptuuid_pos)
        self.assertLess(ptuuid_pos, size_pos)
        self.assertIn("disk.ptuuid or '-'", source)

    def test_device_policy_keeps_storage_and_hides_internal_devices(self):
        for storage in (
            device("sda"),
            device("nvme0n1"),
            device("mmcblk0"),
            device("loop0", type_="loop"),
        ):
            self.assertTrue(is_manageable_storage_device(storage), storage.name)

        for internal in (
            device("zram0"),
            device("mtdblock0"),
            device("mmcblk0boot0"),
            device("mmcblk0boot1"),
            device("mmcblk0rpmb"),
        ):
            self.assertFalse(is_manageable_storage_device(internal), internal.name)

    def test_swap_menu_lists_all_swaps_but_edits_only_files(self):
        from libs.app.menus.app_12_swap.menu import menu as swap_menu

        source = inspect.getsource(swap_menu.onShowMenu)
        self.assertIn("getListOfActiveSwaps(False)", source)
        self.assertIn('if s.type == "file"', source)
        self.assertIn('itm.atRight="informativní"', source)
        self.assertIn("{'Type':>10}", source)
        self.assertIn("{s.type:>10}", source)


if __name__ == "__main__":
    unittest.main()
