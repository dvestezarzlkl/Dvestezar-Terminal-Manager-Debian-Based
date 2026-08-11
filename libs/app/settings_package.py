from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from libs.app import cfg
from libs.JBLibs.helper import getLogger
from libs.app.hub.config_package import import_encrypted_settings as import_legacy_hub_settings
from libs.app.hub.settings import (
    HubSettings,
    apply_settings as apply_hub_settings,
    settings_from_dict as hub_settings_from_dict,
)


log = getLogger(__name__)

PACKAGE_PREFIX = "SYSAPP1E:"
LEGACY_HUB_PREFIX = "SYSHUB1E:"
PACKAGE_FORMAT = "sysapps-settings"
FORMAT_VERSION = 1
_AAD = b"SysApps-global-settings-v1"
_MAX_PACKAGE_LENGTH = 65536
_MAX_DOWNLOAD_BYTES = 65536
_SECTION_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)


@dataclass(frozen=True)
class SettingsPolicyField:
    key: str
    label: str
    data_key: str
    config_key: str


@dataclass(frozen=True)
class SettingsImportPolicy:
    skip_sections: tuple[str, ...] = ()
    skip_fields: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def fields_for(self, section_key: str) -> tuple[str, ...]:
        key = str(section_key or "")
        for current_key, fields in self.skip_fields:
            if current_key == key:
                return fields
        return ()


@dataclass(frozen=True)
class SettingsSectionHandler:
    key: str
    label: str
    version: int
    config_keys: tuple[str, ...]
    exporter: Callable[[], dict[str, Any]]
    validator: Callable[[dict[str, Any]], dict[str, Any]]
    applier: Callable[[dict[str, Any]], None]
    previewer: Callable[[dict[str, Any]], str]
    policy_fields: tuple[SettingsPolicyField, ...] = ()


@dataclass(frozen=True)
class DecodedSettingsPackage:
    revision: int
    created_at: str
    sections: dict[str, dict[str, Any]]
    sha256: str
    legacy: bool = False


@dataclass(frozen=True)
class SettingsApplyReport:
    changed: bool
    revision: int
    applied_sections: tuple[str, ...] = ()
    skipped_sections: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SettingsUpdateResult:
    changed: bool
    revision: int
    message: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SettingsImportConflict:
    section_key: str
    field_key: str
    label: str
    current_value: str
    incoming_value: str


_SECTIONS: dict[str, SettingsSectionHandler] = {}
_LAST_EXPORTED_REVISION = 0


def register_settings_section(handler: SettingsSectionHandler) -> None:
    if not isinstance(handler, SettingsSectionHandler):
        raise TypeError("Invalid settings section handler.")
    if not _SECTION_KEY_RE.fullmatch(handler.key):
        raise ValueError(f"Invalid settings section key: {handler.key}")
    if handler.version < 1:
        raise ValueError("Settings section version must be positive.")
    current = _SECTIONS.get(handler.key)
    if current is not None and current != handler:
        raise ValueError(f"Duplicate settings section: {handler.key}")
    policy_keys: set[str] = set()
    for item in handler.policy_fields:
        if not isinstance(item, SettingsPolicyField):
            raise TypeError("Invalid settings policy field.")
        if not _SECTION_KEY_RE.fullmatch(item.key):
            raise ValueError(f"Invalid settings policy field: {item.key}")
        if not _SECTION_KEY_RE.fullmatch(item.data_key):
            raise ValueError(f"Invalid settings policy data key: {item.data_key}")
        if item.config_key not in handler.config_keys:
            raise ValueError(
                f"Settings policy field {item.key} uses unknown config key {item.config_key}."
            )
        if item.key in policy_keys:
            raise ValueError(
                f"Duplicate settings policy field {item.key} in {handler.key}."
            )
        policy_keys.add(item.key)
    _SECTIONS[handler.key] = handler


def registered_settings_sections() -> tuple[str, ...]:
    return tuple(sorted(_SECTIONS))


def settings_section_label(section_key: str) -> str:
    key = str(section_key or "")
    handler = _SECTIONS.get(key)
    return handler.label if handler is not None else key


def settings_section_policy_fields(
    section_key: str,
) -> tuple[SettingsPolicyField, ...]:
    handler = _SECTIONS.get(str(section_key or ""))
    return handler.policy_fields if handler is not None else ()


def load_settings_import_policy() -> SettingsImportPolicy:
    raw = str(getattr(cfg, "SETTINGS_IMPORT_POLICY", "") or "").strip()
    if not raw:
        return SettingsImportPolicy()
    if len(raw) > 8192:
        raise ValueError("Local centralized import policy is too large.")
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Local centralized import policy is invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Local centralized import policy must be an object.")

    raw_sections = decoded.get("skip_sections", [])
    raw_fields = decoded.get("skip_fields", {})
    if not isinstance(raw_sections, list) or not isinstance(raw_fields, dict):
        raise ValueError("Local centralized import policy has invalid structure.")
    if len(raw_sections) > 128 or len(raw_fields) > 128:
        raise ValueError("Local centralized import policy is too large.")

    sections: set[str] = set()
    for raw_key in raw_sections:
        key = str(raw_key or "")
        if not _SECTION_KEY_RE.fullmatch(key):
            raise ValueError(f"Invalid import policy section key: {key}")
        sections.add(key)

    field_entries: list[tuple[str, tuple[str, ...]]] = []
    for raw_section, raw_keys in raw_fields.items():
        section_key = str(raw_section or "")
        if not _SECTION_KEY_RE.fullmatch(section_key) or not isinstance(raw_keys, list):
            raise ValueError("Local centralized field policy is invalid.")
        if len(raw_keys) > 128:
            raise ValueError("Local centralized field policy is too large.")
        keys: set[str] = set()
        for raw_key in raw_keys:
            key = str(raw_key or "")
            if not _SECTION_KEY_RE.fullmatch(key):
                raise ValueError(f"Invalid import policy field key: {key}")
            keys.add(key)
        if keys:
            field_entries.append((section_key, tuple(sorted(keys))))

    return SettingsImportPolicy(
        tuple(sorted(sections)), tuple(sorted(field_entries))
    )


def serialize_settings_import_policy(policy: SettingsImportPolicy) -> str:
    if not isinstance(policy, SettingsImportPolicy):
        raise TypeError("Invalid centralized import policy.")
    fields = {
        section_key: list(keys)
        for section_key, keys in policy.skip_fields
        if keys
    }
    if not policy.skip_sections and not fields:
        return "{}"
    return json.dumps(
        {
            "skip_sections": list(policy.skip_sections),
            "skip_fields": fields,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def set_settings_import_policy(policy: SettingsImportPolicy) -> None:
    cfg.SETTINGS_IMPORT_POLICY = serialize_settings_import_policy(policy)


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


def _package_sha256(package: str) -> str:
    return hashlib.sha256(package.encode("utf-8")).hexdigest()


def _next_revision() -> int:
    global _LAST_EXPORTED_REVISION
    current = int(getattr(cfg, "SETTINGS_LAST_REVISION", 0) or 0)
    revision = max(time.time_ns() // 1_000, current + 1, _LAST_EXPORTED_REVISION + 1)
    _LAST_EXPORTED_REVISION = revision
    return revision


def _hub_export() -> dict[str, Any]:
    return HubSettings.from_cfg().export_dict()


def _hub_validate(data: dict[str, Any]) -> dict[str, Any]:
    return hub_settings_from_dict(data).export_dict()


def _hub_apply(data: dict[str, Any]) -> None:
    apply_hub_settings(data, save=False)


def _hub_preview(data: dict[str, Any]) -> str:
    item = hub_settings_from_dict(data)
    target = f"{item.host}:{item.port}/{item.database}" if item.host else "not configured"
    return (
        f"enabled={'yes' if item.enabled else 'no'}, target={target}, "
        f"user={item.user or 'not set'}, prefix={item.prefix}, "
        f"auto sync={'yes' if item.auto_sync else 'no'}, "
        f"password={'set' if item.password else 'not set'}"
    )


def _smtp_export() -> dict[str, Any]:
    return {
        "host": str(getattr(cfg, "MAIL_SMTP_HOST", "") or ""),
        "port": int(getattr(cfg, "MAIL_SMTP_PORT", 587) or 587),
        "user": str(getattr(cfg, "MAIL_SMTP_USER", "") or ""),
        "password": str(getattr(cfg, "MAIL_SMTP_PASSWORD", "") or ""),
        "mode": str(getattr(cfg, "MAIL_SMTP_MODE", "starttls") or "starttls"),
        "from_address": str(getattr(cfg, "MAIL_FROM", "") or ""),
        "fallback_admin": str(getattr(cfg, "MAIL_FALLBACK_ADMIN", "") or ""),
        "timeout": int(getattr(cfg, "MAIL_TIMEOUT", 20) or 20),
    }


def _smtp_validate(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise TypeError("SMTP settings must be an object.")
    mode = str(data.get("mode", "starttls") or "starttls").strip().lower()
    if mode not in {"plain", "starttls", "ssl"}:
        raise ValueError("SMTP mode must be plain, starttls or ssl.")
    port = int(data.get("port", 587))
    timeout = int(data.get("timeout", 20))
    if not 1 <= port <= 65535:
        raise ValueError("SMTP port must be between 1 and 65535.")
    if not 1 <= timeout <= 120:
        raise ValueError("SMTP timeout must be between 1 and 120 seconds.")
    from_address = str(data.get("from_address", "") or "").strip().lower()
    fallback_admin = str(data.get("fallback_admin", "") or "").strip().lower()
    for label, value in (
        ("From address", from_address),
        ("Fallback admin address", fallback_admin),
    ):
        if value and not _EMAIL_RE.fullmatch(value):
            raise ValueError(f"{label} is invalid.")
    return {
        "host": str(data.get("host", "") or "").strip(),
        "port": port,
        "user": str(data.get("user", "") or "").strip(),
        "password": str(data.get("password", "") or ""),
        "mode": mode,
        "from_address": from_address,
        "fallback_admin": fallback_admin,
        "timeout": timeout,
    }


def _smtp_apply(data: dict[str, Any]) -> None:
    item = _smtp_validate(data)
    cfg.MAIL_SMTP_HOST = item["host"]
    cfg.MAIL_SMTP_PORT = item["port"]
    cfg.MAIL_SMTP_USER = item["user"]
    cfg.MAIL_SMTP_PASSWORD = item["password"]
    cfg.MAIL_SMTP_MODE = item["mode"]
    cfg.MAIL_FROM = item["from_address"]
    cfg.MAIL_FALLBACK_ADMIN = item["fallback_admin"]
    cfg.MAIL_TIMEOUT = item["timeout"]


def _smtp_preview(data: dict[str, Any]) -> str:
    item = _smtp_validate(data)
    target = f"{item['host']}:{item['port']}" if item["host"] else "not configured"
    return (
        f"target={target}, mode={item['mode']}, user={item['user'] or 'not set'}, "
        f"from={item['from_address'] or item['user'] or 'not set'}, "
        f"fallback={item['fallback_admin'] or 'not set'}, "
        f"password={'set' if item['password'] else 'not set'}"
    )


def detect_import_conflicts(
    decoded: DecodedSettingsPackage,
    import_policy: SettingsImportPolicy | None = None,
) -> tuple[SettingsImportConflict, ...]:
    policy = import_policy or load_settings_import_policy()
    if "smtp" in policy.skip_sections:
        return ()
    skipped_fields = set(policy.fields_for("smtp"))
    section = decoded.sections.get("smtp")
    if not isinstance(section, dict) or int(section.get("version", 0)) != 1:
        return ()
    incoming = _smtp_validate(section.get("data", {}))
    conflicts: list[SettingsImportConflict] = []

    current_host = str(getattr(cfg, "MAIL_SMTP_HOST", "") or "").strip()
    incoming_host = incoming["host"]
    if current_host and current_host.casefold() != incoming_host.casefold():
        conflicts.append(
            SettingsImportConflict(
                "smtp", "host", "SMTP host", current_host, incoming_host
            )
        )

    current_from = str(getattr(cfg, "MAIL_FROM", "") or "").strip().lower()
    incoming_from = incoming["from_address"]
    if (
        "from_address" not in skipped_fields
        and current_from
        and current_from != incoming_from
    ):
        conflicts.append(
            SettingsImportConflict(
                "smtp",
                "from_address",
                "From address",
                current_from,
                incoming_from,
            )
        )
    return tuple(conflicts)


def _automatic_conflict_warning(
    conflicts: tuple[SettingsImportConflict, ...],
) -> str:
    details = "; ".join(
        f"{item.label} {item.current_value or 'not set'} -> {item.incoming_value or 'not set'}"
        for item in conflicts
    )
    return (
        "SMTP section skipped because it would replace existing local identity "
        f"({details}). Use manual import to confirm the change."
    )


register_settings_section(
    SettingsSectionHandler(
        key="hub",
        label="SysApps Hub",
        version=1,
        config_keys=(
            "HUB_ENABLED",
            "HUB_DB_HOST",
            "HUB_DB_PORT",
            "HUB_DB_USER",
            "HUB_DB_PASSWORD",
            "HUB_DB_NAME",
            "HUB_DB_PREFIX",
            "HUB_CONNECT_TIMEOUT",
            "HUB_AUTO_SYNC",
        ),
        exporter=_hub_export,
        validator=_hub_validate,
        applier=_hub_apply,
        previewer=_hub_preview,
    )
)
register_settings_section(
    SettingsSectionHandler(
        key="smtp",
        label="SMTP",
        version=1,
        config_keys=(
            "MAIL_SMTP_HOST",
            "MAIL_SMTP_PORT",
            "MAIL_SMTP_USER",
            "MAIL_SMTP_PASSWORD",
            "MAIL_SMTP_MODE",
            "MAIL_FROM",
            "MAIL_FALLBACK_ADMIN",
            "MAIL_TIMEOUT",
        ),
        exporter=_smtp_export,
        validator=_smtp_validate,
        applier=_smtp_apply,
        previewer=_smtp_preview,
        policy_fields=(
            SettingsPolicyField(
                key="from_address",
                label="SMTP From address",
                data_key="from_address",
                config_key="MAIL_FROM",
            ),
        ),
    )
)


def export_encrypted_settings(
    password: str,
    revision: int | None = None,
    section_keys: tuple[str, ...] | None = None,
) -> str:
    revision = _next_revision() if revision is None else int(revision)
    if revision < 1:
        raise ValueError("Settings revision must be positive.")
    keys = tuple(sorted(section_keys or registered_settings_sections()))
    sections: dict[str, dict[str, Any]] = {}
    for key in keys:
        handler = _SECTIONS.get(key)
        if handler is None:
            raise ValueError(f"Unknown settings section: {key}")
        data = handler.validator(handler.exporter())
        sections[key] = {"version": handler.version, "data": data}
    if not sections:
        raise ValueError("Settings package has no sections.")

    payload = json.dumps(
        {
            "format": PACKAGE_FORMAT,
            "format_version": FORMAT_VERSION,
            "revision": revision,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sections": sections,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive_key(password, salt)).encrypt(nonce, payload, _AAD)
    envelope = {
        "v": FORMAT_VERSION,
        "salt": _b64_encode(salt),
        "nonce": _b64_encode(nonce),
        "data": _b64_encode(ciphertext),
    }
    encoded = _b64_encode(
        json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    package = PACKAGE_PREFIX + encoded
    if len(package) > _MAX_PACKAGE_LENGTH:
        raise ValueError("Settings package is too large.")
    return package


def decode_encrypted_settings(package: str, password: str) -> DecodedSettingsPackage:
    package = str(package or "").strip()
    if len(package) > _MAX_PACKAGE_LENGTH:
        raise ValueError("Settings package is too large.")
    package_hash = _package_sha256(package)

    if package.startswith(LEGACY_HUB_PREFIX):
        try:
            values = import_legacy_hub_settings(package, password)
            normalized = _hub_validate(values)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Invalid legacy SysApps Hub settings package.") from exc
        return DecodedSettingsPackage(
            revision=0,
            created_at="",
            sections={"hub": {"version": 1, "data": normalized}},
            sha256=package_hash,
            legacy=True,
        )
    if not package.startswith(PACKAGE_PREFIX):
        raise ValueError("Unsupported SysApps settings package.")

    try:
        envelope_raw = _b64_decode(package[len(PACKAGE_PREFIX):])
        envelope = json.loads(envelope_raw.decode("utf-8"))
        if not isinstance(envelope, dict) or envelope.get("v") != FORMAT_VERSION:
            raise ValueError("Unsupported package version.")
        salt = _b64_decode(str(envelope["salt"]))
        nonce = _b64_decode(str(envelope["nonce"]))
        ciphertext = _b64_decode(str(envelope["data"]))
        if len(salt) != 16 or len(nonce) != 12:
            raise ValueError("Invalid package parameters.")
        payload = AESGCM(_derive_key(password, salt)).decrypt(nonce, ciphertext, _AAD)
        decoded = json.loads(payload.decode("utf-8"))
    except InvalidTag as exc:
        raise ValueError("Wrong package password or damaged package.") from exc
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        binascii.Error,
        UnicodeDecodeError,
    ) as exc:
        if isinstance(exc, ValueError) and str(exc) in {
            "Unsupported package version.",
            "Invalid package parameters.",
        }:
            raise
        raise ValueError("Invalid SysApps settings package.") from exc

    if not isinstance(decoded, dict):
        raise ValueError("Settings payload must be an object.")
    if decoded.get("format") != PACKAGE_FORMAT:
        raise ValueError("Unsupported settings payload format.")
    if decoded.get("format_version") != FORMAT_VERSION:
        raise ValueError("Unsupported settings payload version.")
    revision = int(decoded.get("revision", 0))
    if revision < 1:
        raise ValueError("Settings payload revision must be positive.")
    created_at = str(decoded.get("created_at", "") or "")
    raw_sections = decoded.get("sections")
    if not isinstance(raw_sections, dict) or not raw_sections:
        raise ValueError("Settings payload has no sections.")

    sections: dict[str, dict[str, Any]] = {}
    for raw_key, raw_section in raw_sections.items():
        key = str(raw_key or "")
        if not _SECTION_KEY_RE.fullmatch(key):
            raise ValueError(f"Invalid settings section key: {key}")
        if not isinstance(raw_section, dict):
            raise ValueError(f"Settings section {key} must be an object.")
        section_version = int(raw_section.get("version", 0))
        data = raw_section.get("data")
        if section_version < 1 or not isinstance(data, dict):
            raise ValueError(f"Settings section {key} is invalid.")
        sections[key] = {"version": section_version, "data": data}

    return DecodedSettingsPackage(
        revision=revision,
        created_at=created_at,
        sections=sections,
        sha256=package_hash,
    )


def _preserve_policy_fields(
    handler: SettingsSectionHandler,
    data: dict[str, Any],
    import_policy: SettingsImportPolicy,
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    requested = set(import_policy.fields_for(handler.key))
    if not requested:
        return data, (), ()
    available = {item.key: item for item in handler.policy_fields}
    merged = dict(data)
    preserved: list[str] = []
    warnings: list[str] = []
    for key in sorted(requested):
        field = available.get(key)
        if field is None:
            warnings.append(
                f"Unknown local import policy field ignored for {handler.key}: {key}"
            )
            continue
        merged[field.data_key] = getattr(cfg, field.config_key)
        preserved.append(key)
    return handler.validator(merged), tuple(preserved), tuple(warnings)


def _prepare_sections(
    decoded: DecodedSettingsPackage,
    skip_sections: tuple[str, ...] = (),
    import_policy: SettingsImportPolicy | None = None,
) -> tuple[
    list[tuple[SettingsSectionHandler, dict[str, Any], tuple[str, ...]]],
    tuple[str, ...],
    tuple[str, ...],
]:
    policy = import_policy or load_settings_import_policy()
    prepared: list[
        tuple[SettingsSectionHandler, dict[str, Any], tuple[str, ...]]
    ] = []
    skipped: list[str] = []
    warnings: list[str] = []
    explicit_skip = {str(key) for key in skip_sections}
    policy_skip = set(policy.skip_sections)
    skip_set = explicit_skip.union(policy_skip)
    for key, section in sorted(decoded.sections.items()):
        if key in skip_set:
            skipped.append(key)
            if key in policy_skip:
                warnings.append(
                    f"Settings section skipped by local centralized policy: {settings_section_label(key)}"
                )
            else:
                warnings.append(
                    f"Settings section skipped for this import: {settings_section_label(key)}"
                )
            continue
        handler = _SECTIONS.get(key)
        if handler is None:
            skipped.append(key)
            warnings.append(f"Unknown settings section skipped: {key}")
            continue
        version = int(section["version"])
        if version != handler.version:
            skipped.append(key)
            warnings.append(
                f"Unsupported {key} section version {version}; expected {handler.version}."
            )
            continue
        data = handler.validator(section["data"])
        data, preserved_fields, field_warnings = _preserve_policy_fields(
            handler, data, policy
        )
        warnings.extend(field_warnings)
        prepared.append((handler, data, preserved_fields))
    return prepared, tuple(skipped), tuple(warnings)


def _section_signature(
    prepared: list[
        tuple[SettingsSectionHandler, dict[str, Any], tuple[str, ...]]
    ],
    policy_skipped: tuple[str, ...] = (),
) -> str:
    parts: list[str] = []
    for handler, _, preserved_fields in prepared:
        suffix = (
            f"[keep={'+'.join(preserved_fields)}]"
            if preserved_fields
            else ""
        )
        parts.append(f"{handler.key}:{handler.version}{suffix}")
    parts.extend(f"{key}:skip" for key in policy_skipped)
    return ",".join(sorted(parts))


def preview_decoded_settings(
    decoded: DecodedSettingsPackage,
    import_policy: SettingsImportPolicy | None = None,
) -> tuple[str, ...]:
    policy = import_policy or load_settings_import_policy()
    prepared, skipped, warnings = _prepare_sections(
        decoded, import_policy=policy
    )
    if not prepared and not set(policy.skip_sections).intersection(decoded.sections):
        raise ValueError("Package contains no supported settings sections.")
    lines = [
        f"Revision: {decoded.revision if decoded.revision else 'legacy'}",
        f"Created: {decoded.created_at or 'not available'}",
    ]
    for handler, data, preserved_fields in prepared:
        line = f"{handler.label}: {handler.previewer(data)}"
        if preserved_fields:
            labels = {item.key: item.label for item in handler.policy_fields}
            kept = ", ".join(labels.get(key, key) for key in preserved_fields)
            line += f"; local policy keeps {kept}"
        lines.append(line)
    for key in skipped:
        lines.append(f"Skipped section: {settings_section_label(key)}")
    lines.extend(f"Warning: {warning}" for warning in warnings)
    return tuple(lines)


def apply_decoded_settings(
    decoded: DecodedSettingsPackage,
    allow_downgrade: bool = False,
    force: bool = False,
    skip_sections: tuple[str, ...] = (),
    extra_warnings: tuple[str, ...] = (),
    import_policy: SettingsImportPolicy | None = None,
) -> SettingsApplyReport:
    policy = import_policy or load_settings_import_policy()
    prepared, skipped, warnings = _prepare_sections(
        decoded, skip_sections, policy
    )
    warnings = tuple(warnings) + tuple(extra_warnings)
    transient_skip = set(skip_sections).intersection(decoded.sections)
    policy_skipped = tuple(
        sorted(set(policy.skip_sections).intersection(decoded.sections))
    )
    if not prepared and not policy_skipped:
        if transient_skip:
            return SettingsApplyReport(
                False, decoded.revision, (), skipped, warnings
            )
        raise ValueError("Package contains no supported settings sections.")
    signature = _section_signature(prepared, policy_skipped)
    current_revision = int(getattr(cfg, "SETTINGS_LAST_REVISION", 0) or 0)
    current_hash = str(getattr(cfg, "SETTINGS_LAST_SHA256", "") or "")
    current_applied = str(getattr(cfg, "SETTINGS_LAST_APPLIED", "") or "")
    if decoded.revision > 0:
        if decoded.revision < current_revision and not allow_downgrade:
            raise ValueError(
                f"Settings revision {decoded.revision} is older than local revision {current_revision}."
            )
        if decoded.revision == current_revision:
            if current_hash and current_hash != decoded.sha256:
                raise ValueError(
                    "The same settings revision has different content (SHA-256 mismatch)."
                )
            if (
                current_hash == decoded.sha256
                and current_applied == signature
                and not force
            ):
                return SettingsApplyReport(
                    False, decoded.revision, (), skipped, warnings
                )

    config_keys = {
        key
        for handler, _, _ in prepared
        for key in handler.config_keys
    }
    config_keys.update({
        "SETTINGS_LAST_REVISION",
        "SETTINGS_LAST_SHA256",
        "SETTINGS_LAST_APPLIED",
    })
    previous = {key: getattr(cfg, key) for key in config_keys}

    try:
        for handler, data, _ in prepared:
            handler.applier(data)
        if decoded.revision > 0:
            cfg.SETTINGS_LAST_REVISION = decoded.revision
            cfg.SETTINGS_LAST_SHA256 = decoded.sha256
            cfg.SETTINGS_LAST_APPLIED = signature
        elif decoded.legacy:
            # A legacy Hub-only import changes one centrally managed section.
            # Keep the anti-rollback revision, but force the current central
            # package to be applied again on the next startup.
            cfg.SETTINGS_LAST_SHA256 = ""
        cfg.save()
    except Exception:
        for key, value in previous.items():
            setattr(cfg, key, value)
        raise

    return SettingsApplyReport(
        True,
        decoded.revision,
        tuple(handler.key for handler, _, _ in prepared),
        skipped,
        warnings,
    )


def _url_origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Central settings URL has an invalid port.") from exc
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else -1
    return scheme, host, port


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target_url = urljoin(req.full_url, newurl)
        if _url_origin(req.full_url) != _url_origin(target_url):
            raise ValueError(
                "Central settings redirect to a different origin is blocked."
            )
        redirected = super().redirect_request(
            req, fp, code, msg, headers, target_url
        )
        if redirected is not None:
            authorization = req.get_header("Authorization")
            if authorization:
                redirected.add_unredirected_header(
                    "Authorization", authorization
                )
        return redirected


def _basic_authorization(user: str, password: str) -> str:
    user = str(user or "")
    password = str(password or "")
    if bool(user) != bool(password):
        raise ValueError(
            "HTTP Basic Auth user and password must both be configured."
        )
    if not user:
        return ""
    if ":" in user:
        raise ValueError("HTTP Basic Auth user must not contain ':'.")
    if "\r" in user or "\n" in user or "\r" in password or "\n" in password:
        raise ValueError("HTTP Basic Auth credentials contain invalid characters.")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode(
        "ascii"
    )
    return f"Basic {token}"


def validate_settings_url(url: str, allow_http: bool = False) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    allowed_schemes = {"https"}
    if allow_http:
        allowed_schemes.add("http")
    if parsed.scheme.lower() not in allowed_schemes:
        raise ValueError("Central settings URL must use HTTPS.")
    if not parsed.hostname:
        raise ValueError("Central settings URL has no host.")
    _url_origin(value)
    if parsed.username or parsed.password:
        raise ValueError("Credentials must not be embedded in the settings URL.")
    return value


def download_settings_package(
    url: str,
    timeout: int = 5,
    allow_http: bool = False,
    auth_user: str = "",
    auth_password: str = "",
) -> str:
    url = validate_settings_url(url, allow_http=allow_http)
    authorization = _basic_authorization(auth_user, auth_password)
    timeout = int(timeout)
    if not 1 <= timeout <= 30:
        raise ValueError("Central settings timeout must be between 1 and 30 seconds.")
    started = time.perf_counter()
    scheme, host, port = _url_origin(url)
    log.info(
        "Central settings download: start (%s://%s:%d, timeout=%ds, auth=%s)",
        scheme,
        host,
        port,
        timeout,
        "yes" if authorization else "no",
    )
    request = Request(
        url,
        headers={
            "Accept": "text/plain, application/octet-stream",
            "User-Agent": "sys_apps-settings/1.1",
        },
    )
    if authorization:
        request.add_unredirected_header("Authorization", authorization)
    opener = build_opener(_SameOriginRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = str(response.geturl() or url)
            validate_settings_url(final_url, allow_http=allow_http)
            if _url_origin(final_url) != _url_origin(url):
                raise ValueError(
                    "Central settings redirect to a different origin is blocked."
                )
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > _MAX_DOWNLOAD_BYTES:
                raise ValueError("Remote settings package is too large.")
            raw = response.read(_MAX_DOWNLOAD_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 401:
            if authorization:
                raise ValueError(
                    "Central settings HTTP Basic authentication failed (401)."
                ) from exc
            raise ValueError(
                "Central settings endpoint requires HTTP Basic authentication (401)."
            ) from exc
        raise ValueError(
            f"Central settings server returned HTTP {exc.code}."
        ) from exc
    except URLError as exc:
        reason = str(exc.reason or "connection failed")
        raise ValueError(f"Central settings download failed: {reason}") from exc
    log.info(
        "Central settings download: received %d byte(s) in %.3fs",
        len(raw),
        time.perf_counter() - started,
    )
    if len(raw) > _MAX_DOWNLOAD_BYTES:
        raise ValueError("Remote settings package is too large.")
    try:
        package = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("Remote settings package is not UTF-8 text.") from exc
    if not package:
        raise ValueError("Remote settings package is empty.")
    log.info(
        "Central settings download: validated text package in %.3fs",
        time.perf_counter() - started,
    )
    return package


def update_from_central_url(force: bool = False) -> SettingsUpdateResult:
    url = str(getattr(cfg, "SETTINGS_URL", "") or "").strip()
    password = str(getattr(cfg, "SETTINGS_PASSWORD", "") or "")
    timeout = int(getattr(cfg, "SETTINGS_CONNECT_TIMEOUT", 5) or 5)
    allow_http = bool(getattr(cfg, "SETTINGS_ALLOW_HTTP", False))
    auth_user = str(getattr(cfg, "SETTINGS_AUTH_USER", "") or "")
    auth_password = str(getattr(cfg, "SETTINGS_AUTH_PASSWORD", "") or "")
    if not url:
        raise ValueError("Central settings URL is not configured.")
    if not password:
        raise ValueError("Central settings password is not configured.")

    started = time.perf_counter()
    log.info("Central settings update: start (force=%s)", force)
    package = download_settings_package(
        url, timeout, allow_http, auth_user, auth_password
    )
    decode_started = time.perf_counter()
    log.info("Central settings decode: start")
    decoded = decode_encrypted_settings(package, password)
    log.info(
        "Central settings decode: done in %.3fs (revision=%d, sections=%s)",
        time.perf_counter() - decode_started,
        decoded.revision,
        ",".join(sorted(decoded.sections)),
    )
    if decoded.legacy:
        raise ValueError("Legacy Hub packages cannot be applied automatically from URL.")

    current_revision = int(getattr(cfg, "SETTINGS_LAST_REVISION", 0) or 0)
    current_hash = str(getattr(cfg, "SETTINGS_LAST_SHA256", "") or "")
    if decoded.revision < current_revision and not force:
        return SettingsUpdateResult(
            False,
            decoded.revision,
            f"Remote revision {decoded.revision} is older than local revision {current_revision}.",
        )
    if decoded.revision == current_revision and not force:
        if current_hash and current_hash != decoded.sha256:
            raise ValueError(
                "The remote package reuses the current revision with different content."
            )

    policy_started = time.perf_counter()
    log.info("Central settings policy/conflict evaluation: start")
    import_policy = load_settings_import_policy()
    conflicts = detect_import_conflicts(decoded, import_policy)
    skip_sections = tuple(sorted({item.section_key for item in conflicts}))
    log.info(
        "Central settings policy/conflict evaluation: done in %.3fs (conflicts=%d, skip_sections=%s)",
        time.perf_counter() - policy_started,
        len(conflicts),
        ",".join(skip_sections) or "none",
    )
    conflict_warnings = (
        (_automatic_conflict_warning(conflicts),) if conflicts else ()
    )
    apply_started = time.perf_counter()
    log.info("Central settings apply: start")
    report = apply_decoded_settings(
        decoded,
        allow_downgrade=force,
        force=force,
        skip_sections=skip_sections,
        extra_warnings=conflict_warnings,
        import_policy=import_policy,
    )
    log.info(
        "Central settings apply: done in %.3fs (changed=%s, applied=%s, skipped=%s)",
        time.perf_counter() - apply_started,
        report.changed,
        ",".join(report.applied_sections) or "none",
        ",".join(report.skipped_sections) or "none",
    )
    if not report.changed:
        if report.skipped_sections:
            message = (
                f"Central settings revision {decoded.revision} was not applied; "
                "sections were skipped by local policy."
            )
        else:
            message = "Central settings are already current."
        return SettingsUpdateResult(
            False, decoded.revision, message, report.warnings
        )
    message = (
        f"Applied central settings revision {decoded.revision}."
        if report.applied_sections
        else f"Recorded central settings revision {decoded.revision}; all supported sections are skipped by local policy."
    )
    result = SettingsUpdateResult(
        True,
        decoded.revision,
        message,
        report.warnings,
    )
    log.info(
        "Central settings update: done in %.3fs (changed=%s, revision=%d, warnings=%d)",
        time.perf_counter() - started,
        result.changed,
        result.revision,
        len(result.warnings),
    )
    return result


def startup_settings_update() -> SettingsUpdateResult | None:
    if not bool(getattr(cfg, "SETTINGS_AUTO_UPDATE", False)):
        return None
    if not str(getattr(cfg, "SETTINGS_URL", "") or "").strip():
        return None
    if not str(getattr(cfg, "SETTINGS_PASSWORD", "") or ""):
        return None
    startup_started = time.perf_counter()
    log.info("Central settings startup update: start")
    try:
        result = update_from_central_url()
    except Exception as exc:
        message = str(exc)
        secrets = (
            str(getattr(cfg, "SETTINGS_PASSWORD", "") or ""),
            str(getattr(cfg, "SETTINGS_AUTH_PASSWORD", "") or ""),
        )
        for secret in secrets:
            if secret:
                message = message.replace(secret, "***")
        log.warning(
            "Central settings startup update: failed after %.3fs: %s",
            time.perf_counter() - startup_started,
            message,
        )
        print(f"Central settings update warning: {message}")
        return SettingsUpdateResult(False, 0, message)
    log.info(
        "Central settings startup update: done in %.3fs (changed=%s, revision=%d, warnings=%d)",
        time.perf_counter() - startup_started,
        result.changed,
        result.revision,
        len(result.warnings),
    )
    if result.changed:
        print(result.message)
    for warning in result.warnings:
        print(f"Central settings warning: {warning}")
    return result
