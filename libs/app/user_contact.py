from __future__ import annotations

import json
import os
import pwd
import secrets
import stat
from pathlib import Path
from typing import Any, Optional, Tuple

import json5

from libs.app import mail_hlp


_CONTACT_RELATIVE_PATH = Path(".config") / "jb_sys_apps" / "contact.jsonc"
_CONFIG_DIR_NAME = ".config"
_APP_DIR_NAME = "jb_sys_apps"
_CONTACT_FILE_NAME = "contact.jsonc"
_MAX_CONTACT_BYTES = 64 * 1024
_DIR_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _get_user_record(username: str):
    if not isinstance(username, str) or not username.strip():
        raise ValueError("System username is required.")
    return pwd.getpwnam(username.strip())


def get_user_contact_path(username: str) -> Path:
    """Return the XDG-style contact file for one system user."""
    record = _get_user_record(username)
    return Path(record.pw_dir) / _CONTACT_RELATIVE_PATH


def _verify_directory(fd: int, expected_uid: int, label: str) -> None:
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"{label} is not a directory.")
    if info.st_uid != expected_uid:
        raise PermissionError(f"{label} is not owned by the target user.")


def _set_owner(fd: int, uid: int, gid: int) -> None:
    if os.geteuid() == 0:
        os.fchown(fd, uid, gid)


def _open_child_dir(
    parent_fd: int,
    name: str,
    record,
    create: bool,
    label: str,
) -> Optional[int]:
    try:
        fd = os.open(name, _DIR_OPEN_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            return None
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        fd = os.open(name, _DIR_OPEN_FLAGS, dir_fd=parent_fd)
        os.fchmod(fd, 0o700)
        _set_owner(fd, record.pw_uid, record.pw_gid)

    _verify_directory(fd, record.pw_uid, label)
    return fd


def _open_contact_dir(username: str, create: bool) -> Tuple[object, Optional[int]]:
    record = _get_user_record(username)
    home_fd = os.open(record.pw_dir, _DIR_OPEN_FLAGS)
    try:
        _verify_directory(home_fd, record.pw_uid, "User home")
        config_fd = _open_child_dir(
            home_fd,
            _CONFIG_DIR_NAME,
            record,
            create,
            "User .config directory",
        )
        if config_fd is None:
            return record, None
        try:
            app_fd = _open_child_dir(
                config_fd,
                _APP_DIR_NAME,
                record,
                create,
                "jb_sys_apps config directory",
            )
            if app_fd is not None and create:
                os.fchmod(app_fd, 0o700)
            return record, app_fd
        finally:
            os.close(config_fd)
    finally:
        os.close(home_fd)


def _read_contact_bytes(app_fd: int, expected_uid: int) -> Optional[bytes]:
    try:
        file_fd = os.open(
            _CONTACT_FILE_NAME,
            os.O_RDONLY | _FILE_NOFOLLOW,
            dir_fd=app_fd,
        )
    except FileNotFoundError:
        return None

    try:
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("User contact configuration is not a regular file.")
        if info.st_uid != expected_uid:
            raise PermissionError("User contact configuration has an unexpected owner.")
        if info.st_size > _MAX_CONTACT_BYTES:
            raise ValueError("User contact configuration is too large.")

        chunks: list[bytes] = []
        remaining = _MAX_CONTACT_BYTES + 1
        while remaining > 0:
            chunk = os.read(file_fd, min(8192, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > _MAX_CONTACT_BYTES:
            raise ValueError("User contact configuration is too large.")
        return content
    finally:
        os.close(file_fd)


def load_user_contact(username: str) -> Tuple[bool, dict[str, Any], Optional[str]]:
    """Load user contact data without following user-controlled symlinks."""
    app_fd: Optional[int] = None
    try:
        record, app_fd = _open_contact_dir(username, create=False)
        if app_fd is None:
            return True, {}, None
        content = _read_contact_bytes(app_fd, record.pw_uid)
        if content is None:
            return True, {}, None
        data = json5.loads(content.decode("utf-8"))
        if not isinstance(data, dict):
            return False, {}, "User contact configuration is not an object."
        return True, data, None
    except Exception as exc:
        return False, {}, f"Cannot read user contact configuration: {exc}"
    finally:
        if app_fd is not None:
            os.close(app_fd)


def get_user_email(username: str) -> Optional[str]:
    """Return the configured recipient address, or ``None`` when unset."""
    ok, data, _ = load_user_contact(username)
    if not ok:
        return None
    value = data.get("email")
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if mail_hlp.is_valid_mail_address(value) else None


def save_user_contact(username: str, data: dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Atomically save a user-owned contact file without following symlinks."""
    if not isinstance(data, dict):
        return False, "User contact data must be an object."

    app_fd: Optional[int] = None
    temp_name: Optional[str] = None
    try:
        record, app_fd = _open_contact_dir(username, create=True)
        if app_fd is None:
            return False, "Cannot create user contact directory."

        payload = (json.dumps(data, ensure_ascii=False, indent=4) + "\n").encode("utf-8")
        if len(payload) > _MAX_CONTACT_BYTES:
            return False, "User contact configuration is too large."

        temp_name = f".{_CONTACT_FILE_NAME}.{secrets.token_hex(8)}.tmp"
        file_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW,
            0o600,
            dir_fd=app_fd,
        )
        try:
            os.fchmod(file_fd, 0o600)
            _set_owner(file_fd, record.pw_uid, record.pw_gid)
            view = memoryview(payload)
            while view:
                written = os.write(file_fd, view)
                view = view[written:]
            os.fsync(file_fd)
        finally:
            os.close(file_fd)

        os.replace(
            temp_name,
            _CONTACT_FILE_NAME,
            src_dir_fd=app_fd,
            dst_dir_fd=app_fd,
        )
        temp_name = None
        os.fsync(app_fd)
        return True, None
    except Exception as exc:
        return False, f"Cannot save user contact configuration: {exc}"
    finally:
        if temp_name and app_fd is not None:
            try:
                os.unlink(temp_name, dir_fd=app_fd)
            except OSError:
                pass
        if app_fd is not None:
            os.close(app_fd)


def set_user_email(username: str, email: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Set or clear the default delivery address for a system user."""
    normalized = str(email or "").strip().lower()
    if normalized and not mail_hlp.is_valid_mail_address(normalized):
        return False, "Invalid email address."

    ok, data, error = load_user_contact(username)
    if not ok:
        return False, error

    if normalized:
        data["email"] = normalized
    else:
        data.pop("email", None)

    return save_user_contact(username, data)
