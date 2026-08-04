from __future__ import annotations

from typing import Any, Optional

from libs.app import cfg as app_cfg
from libs.app.appHelper import getSysUsers
from libs.app.c_cfg import cfg_data
from libs.app.hub.models import (
    HubContext,
    HubNodeRedEditorUser,
    HubNodeRedInstance,
    HubProviderSnapshot,
)
from libs.app.instanceHelper import (
    existsSelfSignedCert,
    getHttps,
    getNodeJsVersion,
    instanceVersion,
)

from .handover_mail import build_instance_url, get_active_project_info


PROVIDER_KEY = "node_red"
DATASET = "node_red_instances"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_bool(value: Any, method_name: str) -> Optional[bool]:
    try:
        return bool(getattr(value, method_name)())
    except Exception:
        return None


def collect_node_red_snapshot(context: HubContext) -> HubProviderSnapshot:
    items: list[HubNodeRedInstance] = []
    for _, username in getSysUsers():
        node_cfg = cfg_data(username)
        if node_cfg.err:
            raise RuntimeError(f"Node-RED instance {username}: {node_cfg.err}")

        node_major, node_global, node_js_version = getNodeJsVersion(username)
        node_js_global: Optional[bool]
        if node_major <= 0:
            node_js_version = ""
            node_js_global = None
        else:
            node_js_global = bool(node_global)

        project = get_active_project_info(username)
        use_https = bool(getHttps(username) or existsSelfSignedCert(username))
        editor_users = tuple(
            HubNodeRedEditorUser(
                username=_text(user.user),
                access="RW" if _text(user.permissions) == "*" else "R",
            )
            for user in node_cfg.admin_users
            if _text(user.user)
        )

        items.append(
            HubNodeRedInstance(
                system_user=username,
                title=_text(node_cfg.title) or username,
                service_name=_text(getattr(node_cfg.service, "fullName", "")),
                port=int(node_cfg.port),
                url=build_instance_url(app_cfg.SERVER_URL, int(node_cfg.port), use_https),
                node_red_version=_text(instanceVersion(username)),
                node_js_version=_text(node_js_version),
                node_js_global=node_js_global,
                project_name=_text(project.name),
                git_remote=_text(project.remote),
                service_running=_safe_bool(node_cfg.service, "running"),
                service_enabled=_safe_bool(node_cfg.service, "enabled"),
                editor_users=editor_users,
            )
        )

    return HubProviderSnapshot(
        source_key=PROVIDER_KEY,
        dataset=DATASET,
        items=tuple(items),
    )
