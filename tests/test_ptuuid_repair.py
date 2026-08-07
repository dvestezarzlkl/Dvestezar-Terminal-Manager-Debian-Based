from __future__ import annotations

import inspect
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace

from libs.app.menus.app_10_disk import ptuuid_repair
from libs.app.menus.app_10_disk.menu import m_disk_oper


class PTUUIDRepairTemplateTests(unittest.TestCase):
    def test_initramfs_script_changes_only_disk_guid(self):
        script = ptuuid_repair.build_initramfs_boot_script()

        self.assertIn('sgdisk --disk-guid="$NEW_PTUUID" "$DEVICE"', script)
        self.assertIn('CURRENT_PTUUID" != "$OLD_PTUUID', script)
        self.assertIn('CURRENT_SIZE" != "$SIZE_BYTES', script)
        self.assertIn("verify_partuuids", script)
        self.assertIn('lsblk -ndo PARTUUID "$PART_DEVICE"', script)
        self.assertNotIn('blkid -p -s PARTUUID', script)
        self.assertIn("PARTUUID před změnou nesouhlasí", script)
        self.assertIn("PARTUUID se po změně liší", script)
        self.assertIn('sgdisk --verify "$DEVICE"', script)
        self.assertNotIn("--randomize-guids", script)
        self.assertNotIn("--partition-guid", script)

    def test_generated_shell_scripts_have_valid_posix_syntax(self):
        for script in (
            ptuuid_repair.build_initramfs_hook(),
            ptuuid_repair.build_initramfs_boot_script(),
        ):
            result = subprocess.run(
                ["sh", "-n"],
                input=script,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)

    def test_initramfs_hook_embeds_state_and_required_tools(self):
        hook = ptuuid_repair.build_initramfs_hook()

        self.assertIn("/conf/sysapps-ptuuid/pending.env", hook)
        self.assertIn("copy_exec", hook)
        for command in ("sgdisk", "blkid", "lsblk", "blockdev", "tr"):
            self.assertIn(command, hook)

    def test_finalize_service_uses_selected_runtime_without_network_wait(self):
        service = ptuuid_repair.build_finalize_service(
            Path("/opt/sys_apps"),
            Path("/opt/sys_apps/venv310/bin/python"),
        )

        self.assertIn('WorkingDirectory=/opt/sys_apps', service)
        self.assertNotIn('WorkingDirectory="/opt/sys_apps"', service)
        self.assertIn(
            'ExecStart="/opt/sys_apps/venv310/bin/python" -m '
            "libs.app.menus.app_10_disk.ptuuid_repair --finalize",
            service,
        )
        self.assertIn("After=local-fs.target", service)
        self.assertNotIn("network-online.target", service)
        self.assertIn("ConditionPathExists=", service)

    def test_prepare_preflights_finalize_unit_before_arming(self):
        source = inspect.getsource(ptuuid_repair.prepare_system_disk_change)
        verify = source.index("_verify_finalize_service()")
        disabled = source.index("_pending_env(state, enabled=False)")
        enabled = source.index("_pending_env(state, enabled=True)")
        self.assertLess(verify, disabled)
        self.assertLess(verify, enabled)
        self.assertIn("systemd-analyze", inspect.getsource(ptuuid_repair._verify_finalize_service))

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

    def test_pending_env_contains_partition_baseline_and_can_be_disabled(self):
        state = {
            "device": "/dev/mmcblk0",
            "old_ptuuid": "11111111-2222-3333-4444-555555555555",
            "new_ptuuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "size_bytes": 123,
            "partuuids": {
                "/dev/mmcblk0p1": "aaaa-bbbb",
                "/dev/mmcblk0p2": "cccc-dddd",
            },
        }

        enabled = ptuuid_repair._pending_env(state, enabled=True)
        disabled = ptuuid_repair._pending_env(state, enabled=False)

        self.assertIn("ENABLED=1", enabled)
        self.assertIn("ENABLED=0", disabled)
        self.assertIn("PART_COUNT=2", enabled)
        self.assertIn("PART_1_DEVICE=/dev/mmcblk0p1", enabled)
        self.assertIn("PART_1_UUID=aaaa-bbbb", enabled)
        self.assertIn("PART_2_DEVICE=/dev/mmcblk0p2", enabled)
        self.assertIn("PART_2_UUID=cccc-dddd", enabled)

    def test_prepare_uses_disabled_baseline_before_arming_payload(self):
        source = inspect.getsource(ptuuid_repair.prepare_system_disk_change)

        disabled = source.index("_pending_env(state, enabled=False)")
        baseline = source.index("_rebuild_initramfs(expect_pending=True)", disabled)
        service = source.index('"enable", FINALIZE_SERVICE_NAME', baseline)
        enabled = source.index("_pending_env(state, enabled=True)", service)
        armed = source.index("_rebuild_initramfs(expect_pending=True)", enabled)
        self.assertLess(disabled, baseline)
        self.assertLess(baseline, service)
        self.assertLess(service, enabled)
        self.assertLess(enabled, armed)
        self.assertIn("NERESTARTUJTE zařízení", source)

    def test_initramfs_payload_verification_checks_active_kernel_image(self):
        source = inspect.getsource(ptuuid_repair._verify_initramfs_payload)

        self.assertIn("lsinitramfs", source)
        self.assertIn("_sudo", source)
        self.assertIn("_INITRAMFS_SCRIPT_ENTRY", source)
        self.assertIn("_INITRAMFS_PENDING_ENTRY", source)


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
        self.assertIn("přestat bootovat", source)
        self.assertIn("nové PTUUID přesně", source)

    def test_cancel_callback_requires_confirmation(self):
        source = inspect.getsource(m_disk_oper.cancel_system_disk_ptuuid_change)

        self.assertIn("confirm(", source)
        self.assertIn("cancel_pending_change", source)


if __name__ == "__main__":
    unittest.main()
