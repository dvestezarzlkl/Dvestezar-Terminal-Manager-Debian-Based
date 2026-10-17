"""Nonblocking process-wide lock shared by menu and hourly Hub collectors."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterator


class HubSyncBusy(RuntimeError):
    """Another collector currently owns the local inventory snapshot."""


def _lock_path() -> Path:
    # Each real installation runs as root. Keep unit tests isolated by UID.
    if os.geteuid() == 0:
        return Path("/run/lock/jb_sys_apps_hub.lock")
    return Path(tempfile.gettempdir()) / f"jb_sys_apps_hub_{os.geteuid()}.lock"


@contextmanager
def hub_sync_lock() -> Iterator[None]:
    """Serialize full and individual provider synchronizations on one host."""
    path = _lock_path()
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags, 0o600)
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
                or meta.st_nlink != 1 or meta.st_mode & 0o077):
            raise PermissionError(f"Unsafe SysApps Hub lock file: {path}")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HubSyncBusy("SysApps Hub synchronization is already running.") from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
