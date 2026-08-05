from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit


_PLACEHOLDERS = {"moje.domena.fake"}
_HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _valid_hostname(host: str) -> bool:
    value = host.rstrip(".")
    if not value or len(value) > 253:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    try:
        ascii_value = value.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    return all(_HOST_LABEL_RE.fullmatch(label) for label in ascii_value.split("."))


def normalize_service_host(value: object) -> str:
    """Return a host/FQDN/IP from the historical SERVER_URL value.

    Legacy values may contain a scheme, port or path. They are reduced to the
    host only so all generated service URLs use one consistent identity.
    Invalid values and the historical placeholder are treated as not set.
    """
    raw = str(value or "").strip()
    if not raw or raw.casefold() in _PLACEHOLDERS or any(ch.isspace() for ch in raw):
        return ""
    try:
        parsed = urlsplit(raw if "://" in raw else f"//{raw}")
        if parsed.username or parsed.password:
            return ""
        host = str(parsed.hostname or "").strip().rstrip(".")
    except ValueError:
        return ""
    if not host or host.casefold() in _PLACEHOLDERS or not _valid_hostname(host):
        return ""
    return host.casefold()


def validate_service_host(value: object) -> str:
    """Validate a new interactive service host value.

    New values are deliberately stricter than legacy normalization: only a
    hostname, FQDN or IP address is accepted, without scheme, port or path.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    if any(token in raw for token in ("://", "/", "?", "#", "@")):
        raise ValueError(
            "Service host must be a hostname, FQDN or IP address without scheme, port or path."
        )
    try:
        parsed = urlsplit(f"//{raw}")
        if parsed.port is not None:
            raise ValueError
    except ValueError as exc:
        raise ValueError(
            "Service host must not contain a port; bracketed IPv6 is supported."
        ) from exc
    host = normalize_service_host(raw)
    if not host:
        raise ValueError("Service host / FQDN is invalid.")
    return host


def configured_service_host() -> str:
    from libs.app import cfg

    return normalize_service_host(getattr(cfg, "SERVER_URL", ""))
