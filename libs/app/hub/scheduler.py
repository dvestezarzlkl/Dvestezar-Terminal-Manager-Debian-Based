"""Managed systemd oneshot/timer units for local SysApps Hub synchronization."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile

from .sync_policy import SYNC_MODES

UNIT_DIR = Path("/etc/systemd/system")
SERVICE_NAME = "jb-sysapps-hub.service"
TIMER_NAME = "jb-sysapps-hub.timer"
MANAGED_MARKER = "# Managed by SysApps Hub. Edit through sys_apps, not manually.\n"
_APP_ROOT = Path(__file__).resolve().parents[3]


def _quoted_path(path: Path) -> str:
    text = str(path.resolve())
    if not text.startswith("/") or any(ch in text for ch in ("\n", "\r", '"', "%")):
        raise ValueError("SysApps Hub installation path cannot be used in a systemd unit.")
    return f'"{text}"'


def render_units(root: Path | None = None) -> tuple[str, str]:
    root = _APP_ROOT if root is None else root
    runner = root / "run.sh"
    if not runner.is_file() or not os.access(runner, os.X_OK):
        raise FileNotFoundError(f"Executable SysApps runtime wrapper not found: {runner}")
    directory = _quoted_path(root)
    command = _quoted_path(runner)
    service = (
        MANAGED_MARKER
        + "[Unit]\n"
        + "Description=SysApps Hub inventory collection\n"
        + "Wants=network-online.target\n"
        + "After=network-online.target\n\n"
        + "[Service]\n"
        + "Type=oneshot\n"
        + "User=root\n"
        + "Group=root\n"
        + f"WorkingDirectory={directory}\n"
        + f"ExecStart={command} --hub-sync\n"
        + "TimeoutStartSec=10min\n"
        + "NoNewPrivileges=true\n"
    )
    timer = (
        MANAGED_MARKER
        + "[Unit]\n"
        + "Description=Collect SysApps Hub inventory hourly\n\n"
        + "[Timer]\n"
        + "OnCalendar=hourly\n"
        + "AccuracySec=1min\n"
        + "RandomizedDelaySec=2min\n"
        + "Persistent=true\n"
        + f"Unit={SERVICE_NAME}\n\n"
        + "[Install]\n"
        + "WantedBy=timers.target\n"
    )
    return service, timer


def _read_managed(path: Path) -> bytes | None:
    if path.is_symlink():
        raise RuntimeError(f"Refusing to replace symlinked systemd unit: {path}")
    if not path.exists():
        return None
    if not path.is_file():
        raise RuntimeError(f"Not a regular systemd unit: {path}")
    content = path.read_bytes()
    if not content.startswith(MANAGED_MARKER.encode("utf-8")):
        raise RuntimeError(f"Refusing to replace unmanaged systemd unit: {path}")
    return content


def _atomic_unit_write(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".jb-sysapps-hub-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _systemctl(*args: str) -> None:
    result = subprocess.run(
        ["systemctl", *args], capture_output=True, text=True, timeout=20, check=False
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"systemctl {args[0]} failed: {detail[:500]}")


def _restore_units(backup: dict[Path, bytes | None]) -> None:
    for path, content in backup.items():
        if content is None:
            if path.exists():
                path.unlink()
        else:
            _atomic_unit_write(path, content)


def set_schedule(
    mode: str, *, root: Path | None = None, unit_dir: Path | None = None
) -> None:
    """Apply OS-side schedule, then caller may persist HUB_SYNC_MODE.

    Config is never changed here. Existing non-SysApps units are not touched.
    """
    if mode not in SYNC_MODES:
        raise ValueError(f"Invalid SysApps Hub synchronization mode: {mode}")
    if os.geteuid() != 0:
        raise PermissionError("Managing SysApps Hub systemd timer requires root.")

    directory = UNIT_DIR if unit_dir is None else unit_dir
    service_path = directory / SERVICE_NAME
    timer_path = directory / TIMER_NAME
    if mode != "timer":
        # A normal startup/manual-only installation has no timer to disable.
        if _read_managed(timer_path) is not None:
            _systemctl("disable", "--now", TIMER_NAME)
        return

    if not directory.is_dir():
        raise RuntimeError(f"systemd unit directory does not exist: {directory}")
    service, timer = render_units(root)
    backup = {
        service_path: _read_managed(service_path),
        timer_path: _read_managed(timer_path),
    }
    updated = {
        service_path: service.encode("utf-8"),
        timer_path: timer.encode("utf-8"),
    }
    try:
        for path, data in updated.items():
            if backup[path] != data:
                _atomic_unit_write(path, data)
        _systemctl("daemon-reload")
        _systemctl("enable", "--now", TIMER_NAME)
    except Exception:
        if backup[timer_path] is None:
            try:
                # Disable first while the newly installed timer file still exists.
                _systemctl("disable", "--now", TIMER_NAME)
            except Exception:
                pass
        _restore_units(backup)
        try:
            _systemctl("daemon-reload")
        except Exception:
            # Preserve original setup error while retaining a useful journal.
            pass
        raise


def timer_status() -> str:
    path = UNIT_DIR / TIMER_NAME
    if not path.is_file():
        return "not installed"
    try:
        result = subprocess.run(
            ["systemctl", "is-active", TIMER_NAME],
            capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return result.stdout.strip() or "unavailable"
