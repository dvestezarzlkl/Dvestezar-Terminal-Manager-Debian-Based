from __future__ import annotations

import ipaddress
from pathlib import Path
import re
import shutil
import socket
import subprocess
from typing import Iterable, Optional

import psutil

from libs.JBLibs import __version__ as jblibs_version
from libs.app import cfg

from .models import HubAddress, HubHostSnapshot, HubService


_COMMAND_TIMEOUT = 5


def _text(value: object) -> str:
    return str(value or "").strip()


def _run(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _prefix_length(family: str, netmask: str) -> Optional[int]:
    if not netmask:
        return None
    try:
        base = "0.0.0.0" if family == "ipv4" else "::"
        return int(ipaddress.ip_network(f"{base}/{netmask}", strict=False).prefixlen)
    except ValueError:
        return None


def _address_scope(address: str) -> str:
    try:
        value = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return "unknown"
    if value.is_loopback:
        return "loopback"
    if value.is_link_local:
        return "link_local"
    if value.is_private:
        return "private"
    if value.is_multicast:
        return "multicast"
    if value.is_unspecified:
        return "unspecified"
    if value.is_reserved:
        return "reserved"
    return "global"


def collect_addresses() -> tuple[HubAddress, ...]:
    result: list[HubAddress] = []
    for interface_name, values in sorted(psutil.net_if_addrs().items()):
        mac = ""
        for value in values:
            if value.family == getattr(psutil, "AF_LINK", object()):
                mac = _text(value.address)
                break
        for value in values:
            if value.family == socket.AF_INET:
                family = "ipv4"
            elif value.family == socket.AF_INET6:
                family = "ipv6"
            else:
                continue
            address = _text(value.address).split("%", 1)[0]
            if not address or _address_scope(address) == "loopback":
                continue
            netmask = _text(value.netmask)
            result.append(
                HubAddress(
                    interface_name=interface_name,
                    family=family,
                    address=address,
                    netmask=netmask,
                    prefix_length=_prefix_length(family, netmask),
                    mac=mac,
                    scope=_address_scope(address),
                )
            )
    return tuple(result)


def _systemctl_status(names: Iterable[str]) -> str:
    for name in names:
        result = _run(["systemctl", "is-active", name])
        if result is not None and result.returncode == 0:
            return "active"
        if result is not None and result.stdout.strip() in {
            "inactive",
            "failed",
            "activating",
            "deactivating",
        }:
            return result.stdout.strip()
    return "unknown"


def _service_url(port: Optional[int], use_https: bool) -> str:
    host = _text(getattr(cfg, "SERVER_URL", "")).rstrip("/")
    if not host or port is None:
        return ""
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    scheme = "https" if use_https else "http"
    return f"{scheme}://{host}:{port}"


def _detect_ssh() -> HubService:
    executable = shutil.which("sshd")
    if not executable and Path("/usr/sbin/sshd").exists():
        executable = "/usr/sbin/sshd"
    if not executable:
        return HubService("ssh", False)

    port: Optional[int] = None
    result = _run([executable, "-T"])
    if result is not None and result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.startswith("port "):
                try:
                    port = int(line.split(None, 1)[1])
                except (IndexError, ValueError):
                    pass
                break

    version = ""
    version_result = _run([executable, "-V"])
    if version_result is not None:
        version = _text(version_result.stderr or version_result.stdout).splitlines()[0:1]
        version = version[0] if version else ""
    return HubService(
        "ssh",
        True,
        port=port,
        status=_systemctl_status(("ssh.service", "sshd.service")),
        version=version,
    )


def _parse_key_value(path: Path, key: str) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    except OSError:
        return ""
    return ""


def _detect_webmin() -> HubService:
    config = Path("/etc/webmin/miniserv.conf")
    if not config.exists():
        return HubService("webmin", False)
    try:
        port = int(_parse_key_value(config, "port"))
    except ValueError:
        port = None
    use_https = _parse_key_value(config, "ssl") == "1"
    return HubService(
        "webmin",
        True,
        port=port,
        url=_service_url(port, use_https),
        status=_systemctl_status(("webmin.service",)),
    )


def _first_listen_port(paths: Iterable[Path]) -> Optional[int]:
    patterns = (
        re.compile(r"<VirtualHost\s+[^>]*:(\d+)>", re.IGNORECASE),
        re.compile(r"^\s*Listen\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^\s*listen\s+(\d+)(?:\s|;)", re.IGNORECASE | re.MULTILINE),
    )
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in patterns:
            match = pattern.search(content)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
    return None


def _detect_ispconfig() -> HubService:
    install_dir = Path("/usr/local/ispconfig")
    if not install_dir.exists():
        return HubService("ispconfig", False)
    port = _first_listen_port(
        (
            Path("/etc/apache2/sites-enabled/000-ispconfig.vhost"),
            Path("/etc/apache2/sites-available/ispconfig.vhost"),
            Path("/etc/nginx/sites-enabled/ispconfig.vhost"),
            Path("/etc/nginx/sites-available/ispconfig.vhost"),
        )
    )
    status = _systemctl_status(("apache2.service", "nginx.service"))
    return HubService(
        "ispconfig",
        True,
        port=port,
        url=_service_url(port, True),
        status=status,
    )


def collect_services() -> tuple[HubService, ...]:
    return (_detect_ssh(), _detect_webmin(), _detect_ispconfig())


def _machine_id() -> str:
    value = _text(getattr(cfg.machineInfo, "machine_id", ""))
    if value:
        return value
    try:
        return Path("/etc/machine-id").read_text(encoding="ascii").strip()
    except OSError:
        return ""


def collect_host_snapshot() -> HubHostSnapshot:
    machine = cfg.machineInfo
    hostname = _text(getattr(machine, "static_hostname", "")) or socket.gethostname()
    fqdn = _text(getattr(machine, "hostname_full", "")) or socket.getfqdn()
    return HubHostSnapshot(
        machine_id=_machine_id(),
        hostname=hostname,
        fqdn=fqdn,
        operating_system=_text(getattr(machine, "operating_system", "")),
        kernel=_text(getattr(machine, "kernel", "")),
        architecture=_text(getattr(machine, "architecture", "")),
        hardware_vendor=_text(getattr(machine, "hardware_vendor", "")),
        hardware_model=_text(getattr(machine, "hardware_model", "")),
        sys_apps_version=_text(getattr(cfg, "VERSION", "")),
        jblibs_version=_text(jblibs_version),
        addresses=collect_addresses(),
        services=collect_services(),
    )
