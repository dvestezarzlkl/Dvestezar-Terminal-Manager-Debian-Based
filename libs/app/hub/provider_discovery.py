"""Discover trusted Hub collectors without importing interactive menu modules."""
from __future__ import annotations

import importlib
from pathlib import Path

from libs.JBLibs.helper import getLogger
from libs.app.plugin_manager import PluginRegistry

from .runtime import HubRuntime

log = getLogger(__name__)
_ROOT = Path(__file__).resolve().parents[3]
_MENU_ROOT = _ROOT / "libs" / "app" / "menus"
_COLLECTOR_ROOT = Path(__file__).resolve().with_name("sys_hub_plg")


def _register_module(runtime: HubRuntime, module_name: str) -> None:
    module = importlib.import_module(module_name)
    key = str(getattr(module, "HUB_PROVIDER_KEY", "") or "").strip()
    collector = getattr(module, "hub_collect", None)
    applier = getattr(module, "hub_apply_remote", None)
    if not key or not callable(collector):
        raise ValueError(f"Hub collector {module_name} has no valid provider contract.")
    runtime.register_provider(key, collector, applier)


def register_collectors(
    runtime: HubRuntime, *, include_apps: bool = True
) -> list[str]:
    """Register stand-alone collectors and optional app_* Hub providers.

    The interactive menu still registers legacy menu.py-only providers. Headless
    runs use app_*/hub_provider.py so UI classes are never imported.
    """
    warnings: list[str] = []
    if include_apps:
        registry = PluginRegistry(_ROOT)
        for app in sorted(_MENU_ROOT.glob("app_*")):
            if not app.is_dir() or not (app / "menu.py").is_file():
                continue
            # The existing plugin registry is the single authority for enabled
            # app submodules, including local explicit disables.
            if not registry.is_app_directory_enabled(app.name):
                continue
            provider_file = app / "hub_provider.py"
            if not provider_file.is_file() or provider_file.is_symlink():
                continue
            module_name = f"libs.app.menus.{app.name}.hub_provider"
            try:
                _register_module(runtime, module_name)
            except Exception as exc:
                warning = f"Hub app collector {app.name}: {type(exc).__name__}: {exc}"
                log.warning("%s", warning)
                warnings.append(warning)

    for module_file in sorted(_COLLECTOR_ROOT.glob("*.py")):
        if (module_file.name == "__init__.py" or module_file.name.startswith("_")
                or module_file.is_symlink()):
            continue
        module_name = f"libs.app.hub.sys_hub_plg.{module_file.stem}"
        try:
            _register_module(runtime, module_name)
        except Exception as exc:
            warning = f"Hub collector {module_file.stem}: {type(exc).__name__}: {exc}"
            log.warning("%s", warning)
            warnings.append(warning)
    return warnings
