from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
import json
import os
from pathlib import Path
import socket
import subprocess
from typing import Any, Optional, Sequence
from urllib.parse import urlsplit, urlunsplit

from .lng.default import *
from libs.JBLibs.helper import getLogger, getUserHome, loadLng

loadLng()

from libs.app import cfg as app_cfg
from libs.app import mail_hlp, user_contact
from libs.app.service_host import normalize_service_host
from libs.app.instanceHelper import (
    existsSelfSignedCert,
    getHttps,
    getNodeJsVersion,
    instanceVersion,
)

log = getLogger(__name__)

_MAX_PROJECT_CONFIG_BYTES = 256 * 1024
_COMMAND_TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class NodeRedUserAccess:
    username: str
    access: str


@dataclass(frozen=True)
class NodeRedProjectInfo:
    name: str = ""
    remote: str = ""


@dataclass(frozen=True)
class NodeRedDiskIdentity:
    device: str = ""
    ptuuid: str = ""
    display_name: str = ""


@dataclass(frozen=True)
class NodeRedHandoverData:
    generated_at: datetime
    instance_title: str
    instance_url: str
    system_user: str
    service_name: str
    service_running: Optional[bool]
    service_enabled: Optional[bool]
    node_red_version: str
    node_js_version: str
    node_js_global: Optional[bool]
    editor_users: tuple[NodeRedUserAccess, ...]
    project: NodeRedProjectInfo
    hostname: str
    fqdn: str
    machine_id: str
    disk: NodeRedDiskIdentity


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def _run_as_user(username: str, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run a non-interactive command as the instance owner without a shell."""
    command = ["runuser", "-u", username, "--", *[str(arg) for arg in args]]
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=_COMMAND_TIMEOUT_SECONDS,
    )


def sanitize_git_remote(remote: str) -> str:
    """Remove URL credentials, query parameters and fragments from a Git remote."""
    remote = _text(remote)
    if not remote:
        return ""

    if "://" not in remote:
        # SCP-like SSH remotes such as git@host:group/project.git do not contain
        # a password and are useful as-is for identifying the project.
        return remote.split("?", 1)[0].split("#", 1)[0]

    try:
        parsed = urlsplit(remote)
        hostname = parsed.hostname or ""
        if not hostname:
            return ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        port = f":{parsed.port}" if parsed.port else ""
        return urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, "", ""))
    except (TypeError, ValueError):
        return ""


def build_instance_url(server_url: str, port: int, use_https: bool) -> str:
    """Build the presented instance URL from the configured service host."""
    host = normalize_service_host(server_url)
    if not host:
        return ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    scheme = "https" if use_https else "http"
    return urlunsplit((scheme, f"{host}:{int(port)}", "", "", ""))


def _valid_project_name(name: str) -> bool:
    if not name or name in {".", ".."}:
        return False
    if os.path.isabs(name) or "/" in name or "\\" in name:
        return False
    return Path(name).name == name


def get_active_project_info(username: str) -> NodeRedProjectInfo:
    """Read the active Node-RED project and its sanitized origin remote."""
    home = getUserHome(username)
    if not home:
        return NodeRedProjectInfo()

    user_dir = os.path.join(home, ".node-red")
    config_path = os.path.join(user_dir, ".config.projects.json")
    try:
        result = _run_as_user(username, ["cat", "--", config_path])
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return NodeRedProjectInfo()
    if result.returncode != 0 or not result.stdout:
        return NodeRedProjectInfo()
    if len(result.stdout.encode("utf-8", errors="ignore")) > _MAX_PROJECT_CONFIG_BYTES:
        log.warning("Node-RED project config is too large for user %s", username)
        return NodeRedProjectInfo()

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        log.warning("Node-RED project config is invalid for user %s", username)
        return NodeRedProjectInfo()
    if not isinstance(data, dict):
        return NodeRedProjectInfo()

    project_name = _text(data.get("activeProject"))
    if not _valid_project_name(project_name):
        return NodeRedProjectInfo()

    project_path = os.path.join(user_dir, "projects", project_name)
    try:
        result = _run_as_user(
            username,
            ["git", "-C", project_path, "config", "--get", "remote.origin.url"],
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        result = None

    remote = ""
    if result is not None and result.returncode == 0:
        remote = sanitize_git_remote(result.stdout.strip())
    return NodeRedProjectInfo(name=project_name, remote=remote)


def get_system_disk_identity() -> NodeRedDiskIdentity:
    """Return the system disk identity using the same PUUID/name map as Disk Manager."""
    try:
        from libs.JBLibs.fs_utils import lsblk_list_disks
        from libs.app.disk_hlp import disk_settings

        disks = lsblk_list_disks(ignoreSysDisks=False)
        system_disk = None
        for disk in disks.values():
            if "/" in disk.mountpoints:
                system_disk = disk
                break
            if any("/" in child.mountpoints for child in disk.children):
                system_disk = disk
                break
        if system_disk is None:
            return NodeRedDiskIdentity()

        disk_settings.init()
        ptuuid = _text(system_disk.ptuuid)
        display_name = disk_settings.find_disk_name(ptuuid) if ptuuid else None
        return NodeRedDiskIdentity(
            device=f"/dev/{system_disk.name}",
            ptuuid=ptuuid,
            display_name=_text(display_name),
        )
    except Exception as exc:
        log.warning("Cannot determine system disk identity: %s", exc)
        return NodeRedDiskIdentity()


def _safe_service_bool(service: Any, method_name: str) -> Optional[bool]:
    try:
        method = getattr(service, method_name)
        return bool(method())
    except Exception:
        return None


def _editor_users(node_cfg: Any) -> tuple[NodeRedUserAccess, ...]:
    result: list[NodeRedUserAccess] = []
    for user in getattr(node_cfg, "admin_users", []) or []:
        username = _text(getattr(user, "user", ""))
        if not username:
            continue
        permissions = _text(getattr(user, "permissions", ""))
        access = "RW" if permissions == "*" else "R"
        result.append(NodeRedUserAccess(username=username, access=access))
    return tuple(result)


def collect_handover_data(
    username: str,
    node_cfg: Any,
    generated_at: Optional[datetime] = None,
) -> NodeRedHandoverData:
    """Collect non-secret operational information for one Node-RED instance."""
    generated_at = generated_at or datetime.now().astimezone()
    service = getattr(node_cfg, "service", None)
    node_major, node_global, node_version = getNodeJsVersion(username)
    if node_major <= 0:
        node_version = "N/A"
        node_global_value: Optional[bool] = None
    else:
        node_global_value = bool(node_global)

    machine = app_cfg.machineInfo
    hostname = _text(getattr(machine, "static_hostname", ""), socket.gethostname())
    fqdn = _text(getattr(machine, "hostname_full", ""), socket.getfqdn())
    machine_id = _text(getattr(machine, "machine_id", ""))

    use_https = bool(getHttps(username) or existsSelfSignedCert(username))
    return NodeRedHandoverData(
        generated_at=generated_at,
        instance_title=_text(getattr(node_cfg, "title", ""), username),
        instance_url=build_instance_url(
            getattr(app_cfg, "SERVER_URL", ""),
            int(getattr(node_cfg, "port", 0)),
            use_https,
        ),
        system_user=username,
        service_name=_text(getattr(service, "fullName", "")),
        service_running=_safe_service_bool(service, "running"),
        service_enabled=_safe_service_bool(service, "enabled"),
        node_red_version=instanceVersion(username),
        node_js_version=node_version,
        node_js_global=node_global_value,
        editor_users=_editor_users(node_cfg),
        project=get_active_project_info(username),
        hostname=hostname,
        fqdn=fqdn,
        machine_id=machine_id,
        disk=get_system_disk_identity(),
    )


def _value(value: str) -> str:
    return value if value else TXT_HANDOVER_NOT_AVAILABLE


def _service_state(data: NodeRedHandoverData) -> str:
    if data.service_running is True:
        running = TXT_HANDOVER_RUNNING
    elif data.service_running is False:
        running = TXT_HANDOVER_STOPPED
    else:
        running = TXT_HANDOVER_UNKNOWN

    if data.service_enabled is True:
        enabled = TXT_HANDOVER_ENABLED
    elif data.service_enabled is False:
        enabled = TXT_HANDOVER_DISABLED
    else:
        enabled = TXT_HANDOVER_UNKNOWN
    return f"{running}, {enabled}"


def _node_js_value(data: NodeRedHandoverData) -> str:
    if data.node_js_global is True:
        scope = TXT_HANDOVER_NODE_GLOBAL
    elif data.node_js_global is False:
        scope = TXT_HANDOVER_NODE_USER
    else:
        return _value(data.node_js_version)
    return f"{_value(data.node_js_version)} ({scope})"


def render_handover_mail(
    data: NodeRedHandoverData,
    recipient: str,
) -> tuple[str, str, str]:
    """Render subject, plain text and HTML without any passwords or hashes."""
    subject = TXT_HANDOVER_SUBJECT.format(
        title=data.instance_title,
        hostname=data.hostname,
    )

    users = [f"- {user.username}: {user.access}" for user in data.editor_users]
    if not users:
        users = [f"- {TXT_HANDOVER_NOT_AVAILABLE}"]

    text_lines = [
        TXT_HANDOVER_DOCUMENT_TITLE,
        "",
        TXT_HANDOVER_SECRET_NOTICE,
        "",
        TXT_HANDOVER_SECTION_DEVICE,
        f"{TXT_HANDOVER_HOSTNAME}: {_value(data.hostname)}",
        f"{TXT_HANDOVER_FQDN}: {_value(data.fqdn)}",
        f"{TXT_HANDOVER_MACHINE_ID}: {_value(data.machine_id)}",
        f"{TXT_HANDOVER_DISK}: {_value(data.disk.device)}",
        f"{TXT_HANDOVER_DISK_PUUID}: {_value(data.disk.ptuuid)}",
        f"{TXT_HANDOVER_DISK_NAME}: {_value(data.disk.display_name)}",
        "",
        TXT_HANDOVER_SECTION_INSTANCE,
        f"{TXT_HANDOVER_INSTANCE_NAME}: {_value(data.instance_title)}",
        f"{TXT_HANDOVER_INSTANCE_URL}: {_value(data.instance_url)}",
        f"{TXT_HANDOVER_SYSTEM_USER}: {_value(data.system_user)}",
        f"{TXT_HANDOVER_SERVICE}: {_value(data.service_name)}",
        f"{TXT_HANDOVER_SERVICE_STATE}: {_service_state(data)}",
        f"{TXT_HANDOVER_NODE_RED_VERSION}: {_value(data.node_red_version)}",
        f"{TXT_HANDOVER_NODE_JS_VERSION}: {_node_js_value(data)}",
        "",
        TXT_HANDOVER_SECTION_USERS,
        *users,
        "",
        TXT_HANDOVER_SECTION_PROJECT,
        f"{TXT_HANDOVER_PROJECT_NAME}: {_value(data.project.name)}",
        f"{TXT_HANDOVER_PROJECT_REMOTE}: {_value(data.project.remote)}",
        "",
        f"{TXT_HANDOVER_RECIPIENT}: {recipient}",
        f"{TXT_HANDOVER_GENERATED_AT}: {data.generated_at.isoformat(timespec='seconds')}",
        f"{TXT_HANDOVER_GENERATOR}: {getattr(app_cfg, 'SITE_NAME', 'SysApp')} v{getattr(app_cfg, 'VERSION', '')}",
    ]
    text_body = "\n".join(text_lines)

    def row(label: str, value: str) -> str:
        return (
            "<tr><th style=\"text-align:left;padding:4px 12px 4px 0\">"
            f"{html.escape(label)}</th><td>{html.escape(_value(value))}</td></tr>"
        )

    user_items = "".join(
        f"<li>{html.escape(user.username)}: {html.escape(user.access)}</li>"
        for user in data.editor_users
    ) or f"<li>{html.escape(TXT_HANDOVER_NOT_AVAILABLE)}</li>"

    html_body = "".join([
        "<html><body>",
        f"<h2>{html.escape(TXT_HANDOVER_DOCUMENT_TITLE)}</h2>",
        f"<p><strong>{html.escape(TXT_HANDOVER_SECRET_NOTICE)}</strong></p>",
        f"<h3>{html.escape(TXT_HANDOVER_SECTION_DEVICE)}</h3><table>",
        row(TXT_HANDOVER_HOSTNAME, data.hostname),
        row(TXT_HANDOVER_FQDN, data.fqdn),
        row(TXT_HANDOVER_MACHINE_ID, data.machine_id),
        row(TXT_HANDOVER_DISK, data.disk.device),
        row(TXT_HANDOVER_DISK_PUUID, data.disk.ptuuid),
        row(TXT_HANDOVER_DISK_NAME, data.disk.display_name),
        "</table>",
        f"<h3>{html.escape(TXT_HANDOVER_SECTION_INSTANCE)}</h3><table>",
        row(TXT_HANDOVER_INSTANCE_NAME, data.instance_title),
        row(TXT_HANDOVER_INSTANCE_URL, data.instance_url),
        row(TXT_HANDOVER_SYSTEM_USER, data.system_user),
        row(TXT_HANDOVER_SERVICE, data.service_name),
        row(TXT_HANDOVER_SERVICE_STATE, _service_state(data)),
        row(TXT_HANDOVER_NODE_RED_VERSION, data.node_red_version),
        row(TXT_HANDOVER_NODE_JS_VERSION, _node_js_value(data)),
        "</table>",
        f"<h3>{html.escape(TXT_HANDOVER_SECTION_USERS)}</h3><ul>{user_items}</ul>",
        f"<h3>{html.escape(TXT_HANDOVER_SECTION_PROJECT)}</h3><table>",
        row(TXT_HANDOVER_PROJECT_NAME, data.project.name),
        row(TXT_HANDOVER_PROJECT_REMOTE, data.project.remote),
        "</table>",
        "<hr><table>",
        row(TXT_HANDOVER_RECIPIENT, recipient),
        row(TXT_HANDOVER_GENERATED_AT, data.generated_at.isoformat(timespec="seconds")),
        row(
            TXT_HANDOVER_GENERATOR,
            f"{getattr(app_cfg, 'SITE_NAME', 'SysApp')} v{getattr(app_cfg, 'VERSION', '')}",
        ),
        "</table></body></html>",
    ])
    return subject, text_body, html_body


def get_handover_recipient(username: str) -> Optional[str]:
    return user_contact.get_user_email(username)


def set_handover_recipient(username: str, email: Optional[str]) -> tuple[bool, Optional[str]]:
    return user_contact.set_user_email(username, email)


def send_handover_mail(
    username: str,
    node_cfg: Any,
    recipient: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    recipient = recipient or get_handover_recipient(username)
    if not recipient:
        return False, TXT_HANDOVER_RECIPIENT_MISSING
    if not mail_hlp.is_valid_mail_address(recipient):
        return False, TXT_HANDOVER_RECIPIENT_INVALID

    print(TXT_HANDOVER_GENERATING, flush=True)
    data = collect_handover_data(username, node_cfg)
    subject, text_body, html_body = render_handover_mail(data, recipient)
    return mail_hlp.send_mail(
        recipients=[recipient],
        subject=subject,
        body=text_body,
        html_body=html_body,
    )
