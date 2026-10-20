"""Read-only Bacula File Daemon inventory collector for SysApps Hub.

One self-contained collector file, no DB/SQL access, no Bacula credentials.
The reported status does not imply that backups are running or restorable.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from libs.app.hub.models import HubContext, HubProviderSnapshot, HubService

HUB_PROVIDER_KEY = "bacula_fd"

_BIN_PATHS = (Path("/usr/sbin/bacula-fd"), Path("/usr/local/sbin/bacula-fd"))
_SERVICE_NAME = "bacula-fd.service"


def _run(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args, capture_output=True, text=True,
            check=False, timeout=4,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _unit_properties() -> dict[str, str]:
    result = _run([
        "systemctl", "show", _SERVICE_NAME,
        "--property=LoadState", "--property=ActiveState",
    ])
    if result is None or result.returncode != 0:
        return {}
    return dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if "=" in line
    )


def _package_version() -> str:
    result = _run(["dpkg-query", "-W", "-f=${Version}", "bacula-fd"])
    if result is None or result.returncode != 0:
        return ""
    # Only a plain version string, never dump Bacula config or secrets.
    return result.stdout.strip().splitlines()[0][:128] if result.stdout.strip() else ""


def hub_collect(context: HubContext) -> HubProviderSnapshot:
    """Read package/unit metadata without reading bacula-fd.conf."""
    unit = _unit_properties()
    version = _package_version()
    binary = bool(shutil.which("bacula-fd")) or any(
        path.is_file() for path in _BIN_PATHS
    )
    detected = binary or bool(version) or unit.get("LoadState") == "loaded"
    state = unit.get("ActiveState", "unknown") if detected else "absent"
    if state not in {
        "active", "inactive", "failed", "activating", "deactivating",
        "unknown", "absent"
    }:
        state = "unknown"

    return HubProviderSnapshot(
        source_key=HUB_PROVIDER_KEY,
        dataset="service",
        items=(HubService(
            service_key=HUB_PROVIDER_KEY,
            detected=detected,
            port=None,  # Do not assume default FDPort=9102: can be overridden.
            status=state,
            version=version,
        ),),
    )
