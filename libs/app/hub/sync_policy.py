"""Local SysApps Hub collection policy, independent of central DB settings."""
from __future__ import annotations

from libs.app import cfg


SYNC_MODES = ("startup", "timer", "off")


def effective_sync_mode(legacy_auto_sync: bool | None = None) -> str:
    """Preserve old HUB_AUTO_SYNC installations until a local mode is selected.

    HUB_SYNC_MODE intentionally stays outside SYSAPP1E: it controls local
    systemd units and must not be changed by a remote settings import.
    """
    mode = str(getattr(cfg, "HUB_SYNC_MODE", "") or "").strip().lower()
    if mode:
        if mode not in SYNC_MODES:
            raise ValueError("Invalid local SysApps Hub sync mode.")
        return mode
    if legacy_auto_sync is None:
        legacy_auto_sync = bool(getattr(cfg, "HUB_AUTO_SYNC", True))
    return "startup" if legacy_auto_sync else "off"
