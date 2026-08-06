from __future__ import annotations

import re

from libs.JBLibs.fs_utils import lsblkDiskInfo


_HIDDEN_DISK_NAMES = (
    re.compile(r"^zram\d+$"),
    re.compile(r"^mtdblock\d+$"),
    re.compile(r"^mmcblk\d+boot\d+$"),
    re.compile(r"^mmcblk\d+rpmb$"),
)


def is_manageable_storage_device(device: lsblkDiskInfo) -> bool:
    """Vrátí True pro úložiště, se kterými má pracovat Disk Manager.

    Disk Manager spravuje fyzické a virtuální disky, USB/eMMC/NVMe zařízení
    a loop zařízení vytvořená z image. Zram, MTD bloky a interní eMMC boot/RPMB
    oblasti nejsou běžná úložiště pro diskové operace a patří do specializovaných
    nástrojů nebo pouze do systémové diagnostiky.
    """
    if device.type == "loop":
        return True
    if device.type != "disk":
        return False
    return not any(pattern.fullmatch(device.name) for pattern in _HIDDEN_DISK_NAMES)
