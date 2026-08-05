from __future__ import annotations

from libs.JBLibs.fs_utils import lsblkDiskInfo, lsblk_list_disks, normalizeDiskPath
from libs.app.disk_hlp import disk_settings
from libs.app.hub.models import (
    HubContext,
    HubDisk,
    HubDiskNameUpdate,
    HubProviderSnapshot,
)


SOURCE_KEY = "disks"
DATASET = "disks"


def _mountpoint_count(disk: lsblkDiskInfo) -> int:
    count = len(disk.mountpoints)
    for child in disk.children:
        count += len(child.mountpoints)
    return count


def _is_system_disk(disk: lsblkDiskInfo) -> bool:
    if disk.isSystemDisk:
        return True
    return any(child.isSystemDisk for child in disk.children)


def collect_disk_snapshot(context: HubContext) -> HubProviderSnapshot:
    del context
    disk_settings.init()
    discovered = lsblk_list_disks(True) or {}
    seen: dict[str, str] = {}
    items: list[HubDisk] = []

    for disk in discovered.values():
        if disk.type != "disk":
            continue
        ptuuid = disk_settings.normalize_ptuuid(disk.ptuuid)
        if not ptuuid:
            continue
        if ptuuid in seen:
            raise ValueError(
                f"Duplicate PTUUID {ptuuid} detected on {seen[ptuuid]} and {disk.name}. "
                "The disks may have been cloned without generating a new disk ID."
            )
        seen[ptuuid] = disk.name
        items.append(
            HubDisk(
                ptuuid=ptuuid,
                device_name=disk.name,
                device_path=normalizeDiskPath(disk.name, False),
                display_name=disk_settings.find_disk_name(ptuuid) or "",
                name_updated_at=disk_settings.get_disk_name_updated_at(ptuuid),
                size_bytes=max(0, int(disk.size)),
                device_type=disk.type,
                partition_count=len(disk.children),
                mountpoint_count=_mountpoint_count(disk),
                is_system_disk=_is_system_disk(disk),
                attached=True,
            )
        )

    catalog_ptuuids = {
        disk_settings.normalize_ptuuid(raw_ptuuid)
        for raw_ptuuid in (
            set(disk_settings.diskNames)
            | set(disk_settings.diskNameUpdatedAt)
        )
    }
    for ptuuid in sorted(
        item for item in catalog_ptuuids if item and item not in seen
    ):
        items.append(
            HubDisk(
                ptuuid=ptuuid,
                device_name="",
                device_path="",
                display_name=disk_settings.find_disk_name(ptuuid) or "",
                name_updated_at=disk_settings.get_disk_name_updated_at(ptuuid),
                size_bytes=0,
                device_type="disk",
                partition_count=0,
                mountpoint_count=0,
                is_system_disk=False,
                attached=False,
            )
        )

    return HubProviderSnapshot(SOURCE_KEY, DATASET, tuple(items))


def apply_disk_updates(updates: tuple[HubDiskNameUpdate, ...]) -> None:
    disk_settings.apply_remote_names(updates)
