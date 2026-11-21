"""Conservative read-only PHP CLI discovery.

The inventory deliberately separates CLI observations from PHP-FPM state.
PHP-FPM module inventories, ISPConfig assignments and managed ownership must
be discovered independently in later phases.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable

PHP_NAME = re.compile(r"^php(?:[0-9]+(?:\.[0-9]+)?)?$")
VERSION = re.compile(r"PHP\s+(\d+\.\d+\.\d+)")
DEFAULT_DIRS = ("/usr/bin", "/usr/local/bin", "/opt/phpsys/current")


def candidate_binaries(search_dirs: Iterable[str] = DEFAULT_DIRS) -> list[str]:
    """Find PHP CLI binaries, without invoking shell or modifying the host."""
    candidates: set[str] = set()
    default = shutil.which("php")
    if default:
        candidates.add(default)
    for root in map(Path, search_dirs):
        if not root.is_dir():
            continue
        # Do not recursively inspect arbitrary /opt content.
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for entry in children:
            if entry.is_file() and PHP_NAME.fullmatch(entry.name):
                candidates.add(str(entry))
            if root.name == "current" and entry.is_dir():
                binary = entry / "bin" / "php"
                if binary.is_file():
                    candidates.add(str(binary))
    return sorted(candidates)


def _run(binary: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [binary, *args], capture_output=True, text=True,
        timeout=6, check=False, env={**os.environ, "LC_ALL": "C"},
    )


def _sections(output: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in output.splitlines():
        value = line.strip()
        if value.startswith("[") and value.endswith("]"):
            current = value[1:-1]
            sections.setdefault(current, [])
        elif current and value:
            sections[current].append(value)
    return sections


def inspect_cli(binary: str) -> dict[str, Any]:
    """Observe one PHP CLI binary. A failure is reported, not silently hidden."""
    result: dict[str, Any] = {"binary": binary, "sapi": "cli"}
    try:
        version = _run(binary, "-v")
        if version.returncode:
            raise RuntimeError((version.stderr or version.stdout).strip() or "php -v failed")
        match = VERSION.search(version.stdout)
        if not match:
            raise RuntimeError("Cannot parse PHP version")
        result["version"] = match.group(1)
        for key, arguments in (
            ("modules", ("-m",)),
            ("ini_raw", ("--ini",)),
        ):
            output = _run(binary, *arguments)
            if output.returncode:
                raise RuntimeError((output.stderr or output.stdout).strip() or f"{arguments} failed")
            if key == "modules":
                result["modules"] = _sections(output.stdout)
            else:
                ini: dict[str, str] = {}
                for line in output.stdout.splitlines():
                    if ":" in line:
                        label, value = line.split(":", 1)
                        ini[label.strip()] = value.strip()
                result["ini"] = ini
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        result["error"] = str(exc)
    return result


def discover_php(search_dirs: Iterable[str] = DEFAULT_DIRS) -> dict[str, Any]:
    """Read-only inventory; never infer FPM from CLI results."""
    binaries = candidate_binaries(search_dirs)
    return {
        "schema": "phpsys-inventory/v1",
        "read_only": True,
        "scope": "cli",
        "installations": [inspect_cli(binary) for binary in binaries],
    }


def as_json(inventory: dict[str, Any]) -> str:
    return json.dumps(inventory, indent=2, ensure_ascii=False)
