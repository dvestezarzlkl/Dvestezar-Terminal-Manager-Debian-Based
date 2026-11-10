"""Cross-session acknowledgement for guarded Firewall Manager Apply."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from typing import Mapping


_TOKEN_RE = re.compile(r"^[A-F0-9]{8}$")
_MIN_FINALIZE_SECONDS = 5.0


class FirewallAckError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionInfo:
    ssh_connection: str = ""
    ssh_tty: str = ""


@dataclass(frozen=True)
class AckResult:
    already_acknowledged: bool
    remaining_seconds: int


def current_session_info(
    env: Mapping[str, str] | None = None,
) -> SessionInfo:
    source = os.environ if env is None else env
    return SessionInfo(
        ssh_connection=str(source.get("SSH_CONNECTION", "")).strip(),
        ssh_tty=str(source.get("SSH_TTY", "")).strip(),
    )


def _normalize_token(token: str) -> str:
    value = str(token).strip().upper()
    if not _TOKEN_RE.fullmatch(value):
        raise FirewallAckError("Invalid firewall acknowledgement token.")
    return value


def _token_digest(token: str) -> str:
    return sha256(_normalize_token(token).encode("ascii")).hexdigest()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise FirewallAckError(
            f"Firewall acknowledgement directory is unsafe: {path.parent}"
        )
    os.chmod(path.parent, 0o700)


def _read_pending(path: Path) -> dict:
    if not path.exists():
        raise FirewallAckError("No firewall acknowledgement is pending.")
    if path.is_symlink() or not path.is_file():
        raise FirewallAckError("Firewall acknowledgement state is unsafe.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FirewallAckError(
            "Firewall acknowledgement state cannot be read."
        ) from exc
    if not isinstance(data, dict) or data.get("version") != 1:
        raise FirewallAckError("Unsupported firewall acknowledgement state.")
    return data


def _write_pending(path: Path, data: dict) -> None:
    _ensure_parent(path)
    if path.exists() and path.is_symlink():
        raise FirewallAckError("Firewall acknowledgement state is unsafe.")
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if tmp.exists():
            tmp.unlink()


def create_pending_ack(
    path: Path,
    *,
    seconds: int,
    rollback_unit: str,
    env: Mapping[str, str] | None = None,
    now: float | None = None,
) -> str:
    if not 15 <= seconds <= 600:
        raise FirewallAckError("Firewall acknowledgement timeout must be 15..600 seconds.")

    created = time.time() if now is None else float(now)
    if path.exists():
        existing = _read_pending(path)
        expires = float(existing.get("expires_at", 0.0))
        if expires > created:
            raise FirewallAckError(
                "Another firewall acknowledgement is already pending."
            )
        try:
            path.unlink()
        except OSError as exc:
            raise FirewallAckError(
                "Expired firewall acknowledgement state cannot be removed."
            ) from exc

    token = secrets.token_hex(4).upper()
    origin = current_session_info(env)
    _write_pending(
        path,
        {
            "version": 1,
            "created_at": created,
            "expires_at": created + float(seconds),
            "token_hash": _token_digest(token),
            "rollback_unit": str(rollback_unit),
            "origin_session": asdict(origin),
            "acknowledged": False,
            "acknowledged_at": None,
            "ack_session": None,
        },
    )
    return token


def acknowledge_pending(
    token: str,
    *,
    path: Path = Path("/run/jb_sys_apps/firewall/pending_ack.json"),
    env: Mapping[str, str] | None = None,
    now: float | None = None,
) -> AckResult:
    if os.geteuid() != 0:
        raise FirewallAckError("Root privileges are required.")

    normalized = _normalize_token(token)
    data = _read_pending(path)
    expected = str(data.get("token_hash", ""))
    if not expected or not hmac.compare_digest(
        expected,
        _token_digest(normalized),
    ):
        raise FirewallAckError("Firewall acknowledgement token does not match.")

    current_time = time.time() if now is None else float(now)
    expires = float(data.get("expires_at", 0.0))
    remaining = expires - current_time
    if remaining <= _MIN_FINALIZE_SECONDS:
        raise FirewallAckError(
            "Firewall acknowledgement token has expired or is too close to rollback."
        )

    current = current_session_info(env)
    if not current.ssh_connection:
        raise FirewallAckError(
            "Run this command from the newly opened SSH session."
        )

    origin_raw = data.get("origin_session") or {}
    origin = SessionInfo(
        ssh_connection=str(origin_raw.get("ssh_connection", "")).strip(),
        ssh_tty=str(origin_raw.get("ssh_tty", "")).strip(),
    )
    if origin.ssh_connection and current.ssh_connection == origin.ssh_connection:
        raise FirewallAckError(
            "This is the original SSH transport; open a new SSH connection."
        )

    already = bool(data.get("acknowledged"))
    if not already:
        data["acknowledged"] = True
        data["acknowledged_at"] = current_time
        data["ack_session"] = asdict(current)
        _write_pending(path, data)

    return AckResult(
        already_acknowledged=already,
        remaining_seconds=max(0, int(remaining)),
    )


def is_pending_acknowledged(token: str, *, path: Path) -> bool:
    try:
        normalized = _normalize_token(token)
        data = _read_pending(path)
    except FirewallAckError:
        return False

    expected = str(data.get("token_hash", ""))
    if not expected or not hmac.compare_digest(
        expected,
        _token_digest(normalized),
    ):
        return False
    return bool(data.get("acknowledged"))


def clear_pending_ack(token: str, *, path: Path) -> None:
    try:
        normalized = _normalize_token(token)
        data = _read_pending(path)
        expected = str(data.get("token_hash", ""))
        if not expected or not hmac.compare_digest(
            expected,
            _token_digest(normalized),
        ):
            return
        path.unlink()
    except (FirewallAckError, OSError):
        return
