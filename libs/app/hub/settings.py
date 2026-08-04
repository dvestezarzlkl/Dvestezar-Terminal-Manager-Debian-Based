from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from libs.app import cfg


_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_DATABASE_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


@dataclass(frozen=True)
class HubSettings:
    enabled: bool
    host: str
    port: int
    user: str
    password: str
    database: str
    prefix: str
    connect_timeout: int
    auto_sync: bool

    @classmethod
    def from_cfg(cls) -> "HubSettings":
        return cls(
            enabled=bool(getattr(cfg, "HUB_ENABLED", False)),
            host=str(getattr(cfg, "HUB_DB_HOST", "") or "").strip(),
            port=int(getattr(cfg, "HUB_DB_PORT", 3306) or 3306),
            user=str(getattr(cfg, "HUB_DB_USER", "") or "").strip(),
            password=str(getattr(cfg, "HUB_DB_PASSWORD", "") or ""),
            database=str(getattr(cfg, "HUB_DB_NAME", "sys_apps") or "sys_apps").strip(),
            prefix=str(getattr(cfg, "HUB_DB_PREFIX", "sysapps_") or "sysapps_").strip(),
            connect_timeout=int(getattr(cfg, "HUB_CONNECT_TIMEOUT", 3) or 3),
            auto_sync=bool(getattr(cfg, "HUB_AUTO_SYNC", True)),
        )

    def validate(self, require_enabled: bool = False) -> tuple[bool, str]:
        if require_enabled and not self.enabled:
            return False, "SysApps Hub is disabled."
        if not self.host:
            return False, "Database host is not configured."
        if not self.user:
            return False, "Database user is not configured."
        if not 1 <= self.port <= 65535:
            return False, "Database port must be between 1 and 65535."
        if not _DATABASE_RE.fullmatch(self.database):
            return False, "Database name may contain only letters, digits and underscore."
        if not _IDENTIFIER_RE.fullmatch(self.prefix):
            return False, "Table prefix must start with a lowercase letter and contain only lowercase letters, digits and underscore."
        if not 1 <= self.connect_timeout <= 30:
            return False, "Connect timeout must be between 1 and 30 seconds."
        return True, ""

    def export_dict(self) -> dict[str, Any]:
        return asdict(self)


def apply_settings(values: dict[str, Any]) -> HubSettings:
    candidate = HubSettings(
        enabled=bool(values.get("enabled", True)),
        host=str(values.get("host", "") or "").strip(),
        port=int(values.get("port", 3306)),
        user=str(values.get("user", "") or "").strip(),
        password=str(values.get("password", "") or ""),
        database=str(values.get("database", "sys_apps") or "sys_apps").strip(),
        prefix=str(values.get("prefix", "sysapps_") or "sysapps_").strip(),
        connect_timeout=int(values.get("connect_timeout", 3)),
        auto_sync=bool(values.get("auto_sync", True)),
    )
    ok, error = candidate.validate()
    if not ok:
        raise ValueError(error)

    cfg.HUB_ENABLED = candidate.enabled
    cfg.HUB_DB_HOST = candidate.host
    cfg.HUB_DB_PORT = candidate.port
    cfg.HUB_DB_USER = candidate.user
    cfg.HUB_DB_PASSWORD = candidate.password
    cfg.HUB_DB_NAME = candidate.database
    cfg.HUB_DB_PREFIX = candidate.prefix
    cfg.HUB_CONNECT_TIMEOUT = candidate.connect_timeout
    cfg.HUB_AUTO_SYNC = candidate.auto_sync
    cfg.save()
    return candidate
