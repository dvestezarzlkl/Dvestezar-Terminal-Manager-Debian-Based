from __future__ import annotations

import json
import os
import pwd
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple

import json5

from libs.app import mail_hlp


_CONTACT_RELATIVE_PATH = Path(".config") / "jb_sys_apps" / "contact.jsonc"


def _get_user_record(username: str):
    if not isinstance(username, str) or not username.strip():
        raise ValueError("System username is required.")
    return pwd.getpwnam(username.strip())


def get_user_contact_path(username: str) -> Path:
    """Return the XDG-style contact file for one system user."""
    record = _get_user_record(username)
    return Path(record.pw_dir) / _CONTACT_RELATIVE_PATH


def load_user_contact(username: str) -> Tuple[bool, dict[str, Any], Optional[str]]:
    """Load a user's contact data without creating files as a side effect."""
    try:
        path = get_user_contact_path(username)
    except Exception as exc:
        return False, {}, str(exc)

    if not path.is_file():
        return True, {}, None

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json5.load(handle)
        if not isinstance(data, dict):
            return False, {}, f"User contact configuration is not an object: {path}"
        return True, data, None
    except Exception as exc:
        return False, {}, f"Cannot read user contact configuration {path}: {exc}"


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


def _ensure_config_dir(record, path: Path) -> None:
    xdg_dir = path.parent.parent
    app_dir = path.parent

    if not xdg_dir.exists():
        xdg_dir.mkdir(mode=0o700)
        os.chown(xdg_dir, record.pw_uid, record.pw_gid)

    app_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(app_dir, 0o700)
    os.chown(app_dir, record.pw_uid, record.pw_gid)


def save_user_contact(username: str, data: dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Atomically save user-owned contact data with mode ``0600``."""
    if not isinstance(data, dict):
        return False, "User contact data must be an object."

    temp_path: Optional[str] = None
    try:
        record = _get_user_record(username)
        path = Path(record.pw_dir) / _CONTACT_RELATIVE_PATH
        _ensure_config_dir(record, path)

        fd, temp_path = tempfile.mkstemp(
            prefix=f".{path.name}.",
            dir=str(path.parent),
            text=True,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=4)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.chmod(temp_path, 0o600)
        os.chown(temp_path, record.pw_uid, record.pw_gid)
        os.replace(temp_path, path)
        temp_path = None
        return True, None
    except Exception as exc:
        return False, f"Cannot save user contact configuration: {exc}"
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


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
