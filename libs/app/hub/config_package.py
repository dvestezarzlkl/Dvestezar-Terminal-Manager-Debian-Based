from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .settings import HubSettings


_PACKAGE_PREFIX = "SYSHUB1E:"
_AAD = b"SysApps-Hub-settings-v1"
_MAX_PACKAGE_LENGTH = 32768


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _derive_key(password: str, salt: bytes) -> bytes:
    if not password:
        raise ValueError("Package password cannot be empty.")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(
        password.encode("utf-8")
    )


def export_encrypted_settings(settings: HubSettings, password: str) -> str:
    ok, error = settings.validate()
    if not ok:
        raise ValueError(error)

    payload = json.dumps(
        {"version": 1, "settings": settings.export_dict()},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive_key(password, salt)).encrypt(nonce, payload, _AAD)
    envelope = {
        "v": 1,
        "salt": _b64_encode(salt),
        "nonce": _b64_encode(nonce),
        "data": _b64_encode(ciphertext),
    }
    encoded = _b64_encode(
        json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return _PACKAGE_PREFIX + encoded


def import_encrypted_settings(package: str, password: str) -> dict[str, Any]:
    package = str(package or "").strip()
    if len(package) > _MAX_PACKAGE_LENGTH:
        raise ValueError("Settings package is too large.")
    if not package.startswith(_PACKAGE_PREFIX):
        raise ValueError("Unsupported SysApps Hub settings package.")

    try:
        envelope_raw = _b64_decode(package[len(_PACKAGE_PREFIX):])
        envelope = json.loads(envelope_raw.decode("utf-8"))
        if not isinstance(envelope, dict) or envelope.get("v") != 1:
            raise ValueError("Unsupported package version.")
        salt = _b64_decode(str(envelope["salt"]))
        nonce = _b64_decode(str(envelope["nonce"]))
        ciphertext = _b64_decode(str(envelope["data"]))
        if len(salt) != 16 or len(nonce) != 12:
            raise ValueError("Invalid package parameters.")
        payload = AESGCM(_derive_key(password, salt)).decrypt(
            nonce, ciphertext, _AAD
        )
        decoded = json.loads(payload.decode("utf-8"))
    except InvalidTag as exc:
        raise ValueError("Wrong package password or damaged package.") from exc
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, ValueError) and str(exc) in {
            "Unsupported package version.",
            "Invalid package parameters.",
        }:
            raise
        raise ValueError("Invalid SysApps Hub settings package.") from exc

    if not isinstance(decoded, dict) or decoded.get("version") != 1:
        raise ValueError("Unsupported settings payload version.")
    settings = decoded.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("Settings payload is missing.")
    return settings
