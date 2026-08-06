from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from libs.app.menus.app_10_disk import ptuuid_repair
from libs.app.menus.app_10_disk.menu import m_disk_oper


class PTUUIDRepairTemplateTests(unittest.TestCase):
    def test_initramfs_script_changes_only_disk_guid(self):
        script = ptuuid_repair.build_initramfs_boot_script()

        self.assertIn('sgdisk --disk-guid="$NEW_PTUUID" "$DEVICE"', script)
        self.assertIn('CURRENT_PTUUID" != "$OLD_PTUUID', script)
        self.assertIn('CURRENT_SIZE" != "$SIZE_BYTES', script)
        self.assertIn('sgdisk --verify "$DEVICE"', script)
        self.assertNotIn("--randomize-guids", script)
        self.assertNotIn("--partition-guid", script)

    def test_initramfs_hook_embeds_state_and_required_tools(self):
        hook = ptuuid_repair.build_initramfs_hook()

        self.assertIn("/conf/sysapps-ptuuid/pending.env", hook)
        self.assertIn("copy_exec", hook)
        for command in ("sgdisk", "blkid", "blockdev", "tr"):
            self.assertIn(command, hook)

    def test_finalize_service_uses_selected_runtime(self):
        service = ptuuid_repair.build_finalize_service(
            Path("/opt/sys_apps"),
            Path("/opt/sys_apps/venv310/bin/python"),
        )

        self.assertIn('WorkingDirectory="/opt/sys_apps"', service)
        self.assertIn(
            'ExecStart="/opt/sys_apps/venv310/bin/python" -m '
            "libs.app.menus.app_10_disk.ptuuid_repair --finalize",
            service,
        )
        self.assertIn("ConditionPathExists=", service)

    def test_prepare_rejects_non_system_disk_before_commands(self):
        disk = SimpleNamespace(
            name="sdb",
            type="disk",
            ptuuid="11111111-2222-3333-4444-555555555555",
            isSystemDisk=False,
        )

        with self.assertRaisesRegex(ValueError, "pouze pro systémový disk"):
            ptuuid_repair.prepare_system_disk_change(
                disk,
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            )

    def test_pending_env_can_be_disabled_for_safe_cancel(self):
        state = {
            "device": "/dev/mmcblk0",
            "old_ptuuid": "11111111-2222-3333-4444-555555555555",
            "new_ptuuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "size_bytes": 123,
        }

        enabled = ptuuid_repair._pending_env(state, enabled=True)
        disabled = ptuuid_repair._pending_env(state, enabled=False)

        self.assertIn("ENABLED=1", enabled)
        self.assertIn("ENABLED=0", disabled)


class PTUUIDRepairMenuContractTests(unittest.TestCase):
    def test_system_disk_menu_offers_staged_change(self):
        source = inspect.getsource(m_disk_oper.onShowMenu)

        self.assertIn("Připravit nové PTUUID při restartu", source)
        self.assertIn("Zrušit připravenou změnu PTUUID", source)
        self.assertIn("prepare_system_disk_ptuuid_change", source)

    def test_prepare_callback_has_two_distinct_confirmations(self):
        source = inspect.getsource(m_disk_oper.prepare_system_disk_ptuuid_change)

        self.assertIn("confirm(", source)
        self.assertIn("get_input(", source)
        self.assertIn("KRITICKÁ OPERACE", source)
        self.assertIn("může přestat bootovat", source)
        self.assertIn("nové PTUUID přesně", source)

    def test_cancel_callback_requires_confirmation(self):
        source = inspect.getsource(m_disk_oper.cancel_system_disk_ptuuid_change)

        self.assertIn("confirm(", source)
        self.assertIn("cancel_pending_change", source)


if __name__ == "__main__":
    unittest.main()
