"""Read-only UFW presence/state collector for the existing Hub service dataset."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from libs.app.hub.models import HubContext, HubProviderSnapshot, HubService

HUB_PROVIDER_KEY = "ufw"
_BINARY_LOCATIONS = (Path("/usr/sbin/ufw"), Path("/sbin/ufw"))


def _ufw_binary() -> str | None:
    command = shutil.which("ufw")
    if command:
        return command
    return next((str(path) for path in _BINARY_LOCATIONS if path.is_file()), None)


def _call(binary: str, argument: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            [binary, argument],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def inspect_ufw_service() -> HubService:
    """Read UFW state and version; never execute enable/reload/reset/apply."""
    binary = _ufw_binary()
    if binary is None:
        return HubService(HUB_PROVIDER_KEY, False, status="absent")
    result = _call(binary, "status")
    status = "unknown"
    if result is not None and result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.lower().startswith("status:"):
                state = line.partition(":")[2].strip().lower()
                if state in {"active", "inactive"}:
                    status = state
                break
    version = ""
    response = _call(binary, "--version")
    if response is not None and response.returncode == 0:
        lines = response.stdout.strip().splitlines()
        if lines:
            line = lines[0].strip()
            if line.lower().startswith("ufw "):
                version = line[4:][:128]
    return HubService(HUB_PROVIDER_KEY, True, status=status, version=version)


def hub_collect(context: HubContext) -> HubProviderSnapshot:
    return HubProviderSnapshot(
        source_key=HUB_PROVIDER_KEY,
        dataset="service",
        items=(inspect_ufw_service(),),
    )
