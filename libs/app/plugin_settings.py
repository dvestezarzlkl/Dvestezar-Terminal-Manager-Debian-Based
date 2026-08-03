from __future__ import annotations

import string

from libs.JBLibs.c_menu import (
    c_menu,
    c_menu_block_items,
    c_menu_item,
    c_menu_title_label,
    onSelReturn,
)
from libs.JBLibs.helper import getMainScriptDir
from libs.JBLibs.input import confirm
from libs.JBLibs.term import en_color, text_color
from libs.app.plugin_manager import PluginRegistry


def _state_text(enabled: bool, installed: bool, has_token: bool) -> str:
    state = "enabled" if enabled else "disabled"
    install = "installed" if installed else "not installed"
    token = "token" if has_token else "no token"
    return f"{state}, {install}, {token}"


class PluginSettingsMenu(c_menu):
    """List catalog plugins and open their local settings."""

    choiceBack = None
    ESC_is_quit = True

    def onEnterMenu(self) -> None:
        self.registry = PluginRegistry(getMainScriptDir())

    def onShowMenu(self) -> None:
        self.title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        self.title.append(("Plugin settings", "c"))
        self.subTitle = c_menu_block_items()
        self.subTitle.append(("Local state", str(self.registry.state_path)))

        try:
            catalog = self.registry.load_catalog()
            statuses = [
                self.registry.status(plugin_id, plugin)
                for plugin_id, plugin in catalog.items()
            ]
        except Exception as exc:
            self.menu = [c_menu_title_label(text_color(str(exc), en_color.BRIGHT_RED))]
            return

        self.menu = [
            c_menu_title_label(text_color("Configured plugins", en_color.CYAN))
        ]
        for index, status in enumerate(statuses):
            choice = string.ascii_lowercase[index] if index < 26 else str(index - 25)
            label = status.plugin_id
            if status.description:
                label = f"{status.plugin_id} - {status.description}"
            self.menu.append(
                c_menu_item(
                    label,
                    choice,
                    PluginDetailMenu(status.plugin_id),
                    atRight=_state_text(
                        status.enabled,
                        status.installed,
                        status.has_token,
                    ),
                )
            )

        if not statuses:
            self.menu.append(c_menu_title_label("No plugins in catalog."))


class PluginDetailMenu(c_menu):
    """Manage one plugin's local enabled/install state."""

    choiceBack = None
    ESC_is_quit = True

    def __init__(self, plugin_id: str):
        super().__init__()
        self.plugin_id = plugin_id

    def onEnterMenu(self) -> None:
        self.registry = PluginRegistry(getMainScriptDir())

    def _load(self):
        catalog = self.registry.load_catalog()
        plugin = catalog.get(self.plugin_id)
        if plugin is None:
            raise KeyError(f"Plugin {self.plugin_id} is no longer in the catalog.")
        return plugin, self.registry.status(self.plugin_id, plugin)

    def onShowMenu(self) -> None:
        try:
            plugin, status = self._load()
        except Exception as exc:
            self.menu = [c_menu_title_label(text_color(str(exc), en_color.BRIGHT_RED))]
            return

        self.title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        self.title.append((self.plugin_id, "c"))
        self.subTitle = c_menu_block_items()
        self.subTitle.append(("Enabled", "yes" if status.enabled else "no"))
        self.subTitle.append(("Installed", "yes" if status.installed else "no"))
        self.subTitle.append(("Token", "present" if status.has_token else "missing"))
        self.subTitle.append(("Private", "yes" if status.private else "no"))
        self.subTitle.append(("Optional", "yes" if status.optional else "no"))
        self.subTitle.append(("Auto update", "yes" if status.auto_update else "no"))
        self.subTitle.append(("Path", status.path or "invalid"))

        self.menu = [
            c_menu_item(
                text_color("Enable", en_color.BRIGHT_GREEN),
                "e",
                self.enable,
                enabled=not status.enabled,
            ),
            c_menu_item(
                text_color("Disable", en_color.BRIGHT_YELLOW),
                "d",
                self.disable,
                enabled=status.enabled,
            ),
            c_menu_item(
                text_color("Uninstall local plugin", en_color.BRIGHT_RED),
                "u",
                self.uninstall,
                enabled=status.installed,
            ),
        ]

    def enable(self, sel_item: c_menu_item) -> onSelReturn:
        try:
            self.registry.set_enabled(self.plugin_id, True)
        except Exception as exc:
            return onSelReturn().errRet(str(exc))
        return onSelReturn(
            ok=(
                f"Plugin {self.plugin_id} enabled. Run Update me to install/update it, "
                "then restart sys_apps."
            )
        )

    def disable(self, sel_item: c_menu_item) -> onSelReturn:
        try:
            self.registry.set_enabled(self.plugin_id, False)
        except Exception as exc:
            return onSelReturn().errRet(str(exc))
        return onSelReturn(
            ok=(
                f"Plugin {self.plugin_id} disabled. It will be skipped by the updater "
                "and hidden after sys_apps restart."
            )
        )

    def uninstall(self, sel_item: c_menu_item) -> onSelReturn:
        if not confirm(
            f"Disable and uninstall local files for plugin {self.plugin_id}? (y/n): "
        ):
            return onSelReturn().errRet("Cancelled.")
        try:
            ok, message = self.registry.uninstall(self.plugin_id)
        except Exception as exc:
            return onSelReturn().errRet(str(exc))
        if not ok:
            return onSelReturn().errRet(message)
        return onSelReturn(ok=message)
