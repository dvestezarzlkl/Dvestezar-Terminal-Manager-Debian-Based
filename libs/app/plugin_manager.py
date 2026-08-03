from __future__ import annotations

"""Plugin catalog and local-state interface.

Permanent format documentation lives in docs/plugin-system.md.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, TypedDict

import json5

from libs.JBLibs.helper import getConfigPath
from libs.app import g_def as defs


CATALOG_NAME = "pluginy.jsonc"
STATE_NAME = "plugins.jsonc"
TOKENS_DIR = Path("assets/tokens")


class PluginAccessConfig(TypedDict, total=False):
    """Authentication policy stored in one pluginy.jsonc entry."""

    type: str


class PluginMaintainerConfig(TypedDict, total=False):
    """Informational maintainer metadata stored in pluginy.jsonc."""

    name: str
    email: str
    company: str


class PluginCatalogEntry(TypedDict, total=False):
    """One plugin definition from the committed pluginy.jsonc catalog."""

    adr_name: str
    git_repo_name: str
    git_repo_branch: str
    git_repo_user: str
    description: str
    private: bool
    optional: bool
    auto_update: bool
    enabled_by_default: bool
    licence: str
    access: PluginAccessConfig
    maintainer: PluginMaintainerConfig


class PluginLocalStateEntry(TypedDict, total=False):
    """One local override from /etc/jb_sys_apps/plugins.jsonc."""

    enabled: bool


PluginCatalog = dict[str, PluginCatalogEntry]
PluginLocalState = dict[str, PluginLocalStateEntry]


@dataclass(frozen=True)
class PluginStatus:
    plugin_id: str
    enabled: bool
    installed: bool
    has_token: bool
    private: bool
    optional: bool
    auto_update: bool
    path: str | None
    description: str


class PluginRegistry:
    """Combine the committed plugin catalog with local installation state."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.catalog_path = self.root / CATALOG_NAME
        self.state_path = getConfigPath(
            fromEtc=True,
            configName=STATE_NAME,
            appName=defs.APP_NAME,
            createIfNotExist=False,
        )

    def load_catalog(self) -> PluginCatalog:
        if not self.catalog_path.is_file():
            return {}
        data = json5.loads(self.catalog_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{CATALOG_NAME} must contain an object")
        return {
            str(plugin_id): value
            for plugin_id, value in data.items()
            if isinstance(value, dict)
        }

    def load_state(self) -> PluginLocalState:
        if not self.state_path.is_file():
            return {}
        try:
            data = json5.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(
                f"Cannot read local plugin state {self.state_path}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ValueError(
                f"Local plugin state {self.state_path} must contain an object"
            )
        return {
            str(plugin_id): value
            for plugin_id, value in data.items()
            if isinstance(value, dict)
        }

    @staticmethod
    def _atomic_write(path: Path, content: str, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{path.name}.",
            dir=str(path.parent),
            text=True,
        )
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(temp_path, path)
            os.chmod(path, mode)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def save_state(self, state: PluginLocalState) -> None:
        content = json.dumps(
            state,
            ensure_ascii=False,
            indent=4,
            sort_keys=True,
        ) + "\n"
        self._atomic_write(self.state_path, content, 0o644)

    @staticmethod
    def plugin_path(plugin: PluginCatalogEntry) -> str | None:
        adr_name = plugin.get("adr_name")
        if not isinstance(adr_name, str) or not adr_name.strip():
            return None
        adr_name = adr_name.strip()
        if Path(adr_name).name != adr_name or not adr_name.startswith("app_"):
            return None
        return str(Path("libs/app/menus") / adr_name)

    def token_path(self, token_id: str) -> Path:
        token_id = str(token_id).strip()
        if not token_id or Path(token_id).name != token_id:
            raise ValueError("Token ID must be a non-empty file-safe identifier")
        return self.root / TOKENS_DIR / f"{token_id}.cd"

    def has_token(self, token_id: str) -> bool:
        return self.token_path(token_id).is_file()

    def set_token(self, token_id: str, username: str, token: str) -> None:
        username = str(username)
        token = str(token)
        if not username or username.strip() != username or any(c.isspace() for c in username):
            raise ValueError("Git username must be non-empty and contain no whitespace")
        if not token or token.strip() != token or any(c.isspace() for c in token):
            raise ValueError("Git token must be non-empty and contain no whitespace")
        if ":" in username:
            raise ValueError("Git username must not contain ':'")
        self._atomic_write(
            self.token_path(token_id),
            f"{username}:{token}\n",
            0o600,
        )

    def remove_token(self, token_id: str) -> bool:
        token_path = self.token_path(token_id)
        if not token_path.exists():
            return False
        token_path.unlink()
        return True

    def is_installed(self, plugin: PluginCatalogEntry) -> bool:
        path = self.plugin_path(plugin)
        return bool(path and (self.root / path / ".git").exists())

    def is_enabled(
        self,
        plugin_id: str,
        plugin: PluginCatalogEntry,
        state: PluginLocalState | None = None,
    ) -> bool:
        local_state = state if state is not None else self.load_state()
        plugin_state = local_state.get(plugin_id, {})
        enabled = plugin_state.get("enabled")
        if isinstance(enabled, bool):
            return enabled
        return bool(plugin.get("enabled_by_default", True))

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        catalog = self.load_catalog()
        if plugin_id not in catalog:
            raise KeyError(f"Unknown plugin {plugin_id}")
        state = self.load_state()
        plugin_state = state.setdefault(plugin_id, {})
        plugin_state["enabled"] = bool(enabled)
        self.save_state(state)

    def status(self, plugin_id: str, plugin: PluginCatalogEntry) -> PluginStatus:
        path = self.plugin_path(plugin)
        return PluginStatus(
            plugin_id=plugin_id,
            enabled=self.is_enabled(plugin_id, plugin),
            installed=self.is_installed(plugin),
            has_token=self.has_token(plugin_id),
            private=bool(plugin.get("private", False)),
            optional=bool(plugin.get("optional", True)),
            auto_update=bool(plugin.get("auto_update", True)),
            path=path,
            description=str(plugin.get("description") or ""),
        )

    def statuses(self) -> list[PluginStatus]:
        catalog = self.load_catalog()
        return [
            self.status(plugin_id, plugin)
            for plugin_id, plugin in catalog.items()
        ]

    def is_app_directory_enabled(self, app_dir: str) -> bool:
        catalog = self.load_catalog()
        state = self.load_state()
        for plugin_id, plugin in catalog.items():
            path = self.plugin_path(plugin)
            if path and Path(path).name == app_dir:
                return self.is_enabled(plugin_id, plugin, state)
        return True

    def uninstall(self, plugin_id: str) -> tuple[bool, str]:
        catalog = self.load_catalog()
        plugin = catalog.get(plugin_id)
        if plugin is None:
            return False, f"Unknown plugin {plugin_id}."
        path = self.plugin_path(plugin)
        if path is None:
            return False, f"Plugin {plugin_id} has no valid path."

        self.set_enabled(plugin_id, False)
        if not self.is_installed(plugin):
            return True, f"Plugin {plugin_id} is disabled and already not installed."

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        proc = subprocess.run(
            ["git", "submodule", "deinit", "-f", "--", path],
            cwd=str(self.root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return False, (
                f"Plugin {plugin_id} was disabled, but local uninstall failed: "
                f"{proc.stdout.strip()}"
            )
        return True, (
            f"Plugin {plugin_id} was disabled and uninstalled locally. "
            "Its token was preserved. Restart sys_apps to unload it."
        )
