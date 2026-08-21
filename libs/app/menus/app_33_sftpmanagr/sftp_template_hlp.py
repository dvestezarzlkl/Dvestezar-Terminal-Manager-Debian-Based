from __future__ import annotations

import os
import uuid
from typing import Dict, List, Optional, Tuple

from libs.JBLibs.sftp.glob import SAFE_NAME_RGX
from libs.JBLibs.sftp.mountpoint_templates import MountpointRecord, resolve_mountpoint_records


def _safe_name(value: object) -> bool:
    return isinstance(value, str) and bool(SAFE_NAME_RGX.match(value))


def _find_user(cfg: Dict, username: str) -> Optional[Dict]:
    for user in cfg.get("users", []):
        if isinstance(user, dict) and user.get("sftpuser") == username:
            return user
    return None


def list_templates(cfg: Dict) -> List[Tuple[str, Dict]]:
    templates = cfg.get("mountpointTemplates", {})
    if not isinstance(templates, dict):
        return []
    return sorted(
        [(name, row) for name, row in templates.items() if isinstance(name, str) and isinstance(row, dict)],
        key=lambda item: item[0].lower(),
    )


def find_template(cfg: Dict, template_name: str) -> Optional[Dict]:
    templates = cfg.get("mountpointTemplates", {})
    if not isinstance(templates, dict):
        return None
    row = templates.get(template_name)
    return row if isinstance(row, dict) else None


def create_template(cfg: Dict, template_name: str) -> bool:
    if not _safe_name(template_name):
        return False
    templates = cfg.setdefault("mountpointTemplates", {})
    if not isinstance(templates, dict) or template_name in templates:
        return False
    templates[template_name] = {"mounts": {}}
    return True


def _template_mount_ids(template: Optional[Dict]) -> List[str]:
    if not isinstance(template, dict):
        return []
    mounts = template.get("mounts", {})
    if not isinstance(mounts, dict):
        return []
    return [mount_id for mount_id in mounts if isinstance(mount_id, str)]


def _prune_user_template_overrides(user: Dict, mount_ids: List[str]) -> None:
    points = user.get("templatePoints")
    if not isinstance(points, dict):
        return
    for mount_id in mount_ids:
        points.pop(mount_id, None)
    if not points:
        user.pop("templatePoints", None)


def delete_template(cfg: Dict, template_name: str) -> bool:
    templates = cfg.get("mountpointTemplates", {})
    if not isinstance(templates, dict) or template_name not in templates:
        return False
    mount_ids = _template_mount_ids(templates.get(template_name))
    del templates[template_name]
    for user in cfg.get("users", []):
        if not isinstance(user, dict):
            continue
        assigned = user.get("mountTemplates")
        if isinstance(assigned, list):
            user["mountTemplates"] = [name for name in assigned if name != template_name]
            if not user["mountTemplates"]:
                user.pop("mountTemplates", None)
        _prune_user_template_overrides(user, mount_ids)
    return True


def _all_template_mount_ids(cfg: Dict) -> set[str]:
    result: set[str] = set()
    for _, template in list_templates(cfg):
        result.update(_template_mount_ids(template))
    return result


def _new_mount_id(cfg: Dict) -> str:
    used = _all_template_mount_ids(cfg)
    while True:
        mount_id = f"mp_{uuid.uuid4().hex}"
        if mount_id not in used:
            return mount_id


def list_template_mounts(cfg: Dict, template_name: str) -> List[Tuple[str, Dict]]:
    template = find_template(cfg, template_name)
    if not template:
        return []
    mounts = template.get("mounts", {})
    if not isinstance(mounts, dict):
        return []
    rows = [
        (mount_id, row)
        for mount_id, row in mounts.items()
        if isinstance(mount_id, str) and isinstance(row, dict)
    ]
    return sorted(rows, key=lambda item: str(item[1].get("label", item[0])).lower())


def add_template_mountpoint(cfg: Dict, template_name: str, label: str, path: str) -> Optional[str]:
    template = find_template(cfg, template_name)
    if not template or not _safe_name(label) or not isinstance(path, str) or not os.path.isabs(path):
        return None
    mounts = template.setdefault("mounts", {})
    if not isinstance(mounts, dict):
        return None
    for row in mounts.values():
        if isinstance(row, dict) and row.get("label") == label:
            return None
    mount_id = _new_mount_id(cfg)
    mounts[mount_id] = {"label": label, "path": path}
    return mount_id


def set_template_mountpoint_label(cfg: Dict, template_name: str, mount_id: str, label: str) -> bool:
    if not _safe_name(label):
        return False
    template = find_template(cfg, template_name)
    mounts = template.get("mounts", {}) if template else {}
    if not isinstance(mounts, dict) or mount_id not in mounts or not isinstance(mounts[mount_id], dict):
        return False
    for other_id, row in mounts.items():
        if other_id != mount_id and isinstance(row, dict) and row.get("label") == label:
            return False
    mounts[mount_id]["label"] = label
    return True


def set_template_mountpoint_path(cfg: Dict, template_name: str, mount_id: str, path: str) -> bool:
    if not isinstance(path, str) or not os.path.isabs(path):
        return False
    template = find_template(cfg, template_name)
    mounts = template.get("mounts", {}) if template else {}
    if not isinstance(mounts, dict) or mount_id not in mounts or not isinstance(mounts[mount_id], dict):
        return False
    mounts[mount_id]["path"] = path
    return True


def delete_template_mountpoint(cfg: Dict, template_name: str, mount_id: str) -> bool:
    template = find_template(cfg, template_name)
    mounts = template.get("mounts", {}) if template else {}
    if not isinstance(mounts, dict) or mount_id not in mounts:
        return False
    del mounts[mount_id]
    for user in cfg.get("users", []):
        if isinstance(user, dict):
            _prune_user_template_overrides(user, [mount_id])
    return True


def create_template_from_user(cfg: Dict, template_name: str, username: str) -> Tuple[bool, int]:
    user = _find_user(cfg, username)
    if not user or find_template(cfg, template_name) is not None or not _safe_name(template_name):
        return False, 0
    local_mounts = user.get("sftpmounts", {})
    if not isinstance(local_mounts, dict) or not local_mounts:
        return False, 0
    if not create_template(cfg, template_name):
        return False, 0
    count = 0
    for label, path in local_mounts.items():
        mount_id = add_template_mountpoint(cfg, template_name, label, path)
        if mount_id is None:
            delete_template(cfg, template_name)
            return False, 0
        count += 1
    return True, count


def assigned_templates(cfg: Dict, username: str) -> List[str]:
    user = _find_user(cfg, username)
    if not user:
        return []
    assigned = user.get("mountTemplates", [])
    if not isinstance(assigned, list):
        return []
    return [name for name in assigned if isinstance(name, str)]


def assign_template(cfg: Dict, username: str, template_name: str) -> bool:
    user = _find_user(cfg, username)
    if not user or find_template(cfg, template_name) is None:
        return False
    assigned = user.setdefault("mountTemplates", [])
    if not isinstance(assigned, list):
        return False
    if template_name not in assigned:
        assigned.append(template_name)
    return True


def unassign_template(cfg: Dict, username: str, template_name: str) -> bool:
    user = _find_user(cfg, username)
    template = find_template(cfg, template_name)
    if not user or not template:
        return False
    assigned = user.get("mountTemplates", [])
    if not isinstance(assigned, list) or template_name not in assigned:
        return False
    user["mountTemplates"] = [name for name in assigned if name != template_name]
    if not user["mountTemplates"]:
        user.pop("mountTemplates", None)
    _prune_user_template_overrides(user, _template_mount_ids(template))
    return True


def list_user_mountpoint_records(cfg: Dict, username: str) -> Tuple[List[MountpointRecord], List[str]]:
    user = _find_user(cfg, username)
    if not user:
        return [], [f"SFTP user '{username}' was not found."]
    return resolve_mountpoint_records(cfg, user)


def find_user_mountpoint_label(cfg: Dict, username: str, label: str) -> Optional[MountpointRecord]:
    records, _ = list_user_mountpoint_records(cfg, username)
    for record in records:
        if record.label == label:
            return record
    return None


def find_user_mountpoint_path(cfg: Dict, username: str, path: str) -> Optional[MountpointRecord]:
    records, _ = list_user_mountpoint_records(cfg, username)
    for record in records:
        if record.path == path:
            return record
    return None


def set_local_mountpoint_enabled(cfg: Dict, username: str, label: str, enabled: bool) -> bool:
    user = _find_user(cfg, username)
    if not user:
        return False
    mounts = user.get("sftpmounts", {})
    if not isinstance(mounts, dict) or label not in mounts:
        return False
    points = user.setdefault("pointsSet", {})
    if not isinstance(points, dict):
        return False
    row = points.setdefault(label, {})
    if not isinstance(row, dict):
        return False
    row["enabled"] = bool(enabled)
    return True


def _template_mount_is_assigned(cfg: Dict, user: Dict, mount_id: str) -> bool:
    assigned = user.get("mountTemplates", [])
    if not isinstance(assigned, list):
        return False
    for template_name in assigned:
        template = find_template(cfg, template_name)
        if mount_id in _template_mount_ids(template):
            return True
    return False


def set_template_mountpoint_enabled(cfg: Dict, username: str, mount_id: str, enabled: bool) -> bool:
    user = _find_user(cfg, username)
    if not user or not _template_mount_is_assigned(cfg, user, mount_id):
        return False
    points = user.setdefault("templatePoints", {})
    if not isinstance(points, dict):
        return False
    row = points.setdefault(mount_id, {})
    if not isinstance(row, dict):
        return False
    row["enabled"] = bool(enabled)
    row.setdefault("rw", False)
    return True


def set_template_mountpoint_readonly(cfg: Dict, username: str, mount_id: str, read_only: bool) -> bool:
    user = _find_user(cfg, username)
    if not user or not _template_mount_is_assigned(cfg, user, mount_id):
        return False
    points = user.setdefault("templatePoints", {})
    if not isinstance(points, dict):
        return False
    row = points.setdefault(mount_id, {})
    if not isinstance(row, dict):
        return False
    row["rw"] = not bool(read_only)
    row.setdefault("enabled", False)
    return True
