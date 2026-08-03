from __future__ import annotations

from libs.JBLibs.c_menu import (
    c_menu,
    c_menu_block_items,
    c_menu_item,
    c_menu_title_label,
    onSelReturn,
)
from libs.JBLibs.helper import getMainScriptDir
from libs.JBLibs.input import confirm, get_input, get_pwd
from libs.JBLibs.term import en_color, text_color
from libs.app.plugin_manager import PluginRegistry


CORE_TOKEN_ID = "sys_apps"
JBLIBS_TOKEN_ID = "JBLibs-python"


def _fit(value: str, width: int) -> str:
    value = str(value)
    if len(value) > width:
        return value[: max(1, width - 1)] + "~"
    return f"{value:<{width}}"


def _flag(value: bool, width: int, true_text: str = "yes", false_text: str = "no") -> str:
    plain = f"{true_text if value else false_text:^{width}}"
    color = en_color.BRIGHT_GREEN if value else en_color.BRIGHT_YELLOW
    return text_color(plain, color)


def _token_state(registry: PluginRegistry, token_id: str, fallback_id: str | None = None) -> str:
    if registry.has_token(token_id):
        return "configured"
    if fallback_id and registry.has_token(fallback_id):
        return f"fallback: {fallback_id}"
    return "not configured"


class PluginSettingsMenu(c_menu):
    """Display catalog plugins in a disk-manager style status table."""

    choiceBack = None
    ESC_is_quit = True
    minMenuWidth = 100

    def onEnterMenu(self) -> None:
        self.registry = PluginRegistry(getMainScriptDir())

    def onShowMenu(self) -> None:
        self.title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        self.title.append(("Plugin settings", "c"))
        self.subTitle = c_menu_block_items()
        self.subTitle.append(("Catalog", str(self.registry.catalog_path)))
        self.subTitle.append(("Local state", str(self.registry.state_path)))

        self.menu = [
            c_menu_title_label(text_color("Repository access", en_color.CYAN)),
            c_menu_item(
                "Core sys_apps Git token",
                "g",
                TokenSettingsMenu(CORE_TOKEN_ID, "Core sys_apps repository"),
                atRight=_token_state(self.registry, CORE_TOKEN_ID),
            ),
            c_menu_item(
                "JBLibs Git token",
                "j",
                TokenSettingsMenu(
                    JBLIBS_TOKEN_ID,
                    "Mandatory JBLibs repository",
                    fallback_id=CORE_TOKEN_ID,
                ),
                atRight=_token_state(
                    self.registry,
                    JBLIBS_TOKEN_ID,
                    fallback_id=CORE_TOKEN_ID,
                ),
            ),
            c_menu_title_label(text_color("Plugin catalog", en_color.CYAN)),
        ]

        try:
            catalog = self.registry.load_catalog()
            statuses = [
                self.registry.status(plugin_id, plugin)
                for plugin_id, plugin in catalog.items()
            ]
        except Exception as exc:
            self.menu.append(
                c_menu_title_label(text_color(str(exc), en_color.BRIGHT_RED))
            )
            return

        title = (
            f"{'Plugin':<32} | {'Enabled':^7} | {'Installed':^9} | "
            f"{'Token':^7} | {'Auto':^5}"
        )
        self.menu.append(c_menu_item(text_color(title, en_color.BRIGHT_BLACK)))
        self.menu.append(
            c_menu_item(text_color("-" * len(title), en_color.BRIGHT_BLACK))
        )

        for index, status in enumerate(statuses):
            row = (
                f"{_fit(status.plugin_id, 32)} | "
                f"{_flag(status.enabled, 7)} | "
                f"{_flag(status.installed, 9)} | "
                f"{_flag(status.has_token, 7)} | "
                f"{_flag(status.auto_update, 5)}"
            )
            self.menu.append(
                c_menu_item(
                    row,
                    f"{index:02}",
                    PluginDetailMenu(status.plugin_id),
                )
            )

        if not statuses:
            self.menu.append(c_menu_item("No plugins in catalog."))


class TokenSettingsMenu(c_menu):
    """Manage one local Git access token without ever displaying its value."""

    choiceBack = None
    ESC_is_quit = True

    def __init__(
        self,
        token_id: str,
        title: str,
        fallback_id: str | None = None,
    ):
        super().__init__()
        self.token_id = token_id
        self.menu_title = title
        self.fallback_id = fallback_id

    def onEnterMenu(self) -> None:
        self.registry = PluginRegistry(getMainScriptDir())

    def onShowMenu(self) -> None:
        configured = self.registry.has_token(self.token_id)
        self.title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        self.title.append((self.menu_title, "c"))
        self.subTitle = c_menu_block_items()
        self.subTitle.append(("Token ID", self.token_id))
        self.subTitle.append(
            (
                "Status",
                _token_state(self.registry, self.token_id, self.fallback_id),
            )
        )
        self.subTitle.append(("File", str(self.registry.token_path(self.token_id))))
        self.menu = [
            c_menu_item(
                text_color("Set or replace token", en_color.BRIGHT_GREEN),
                "s",
                self.set_token,
            ),
            c_menu_item(
                text_color("Remove token", en_color.BRIGHT_RED),
                "d",
                self.remove_token,
                enabled=configured,
            ),
        ]

    def set_token(self, sel_item: c_menu_item) -> onSelReturn:
        username = get_input(
            "GitHub username (q cancels):",
            accept_empty=False,
            maxLen=255,
            rgx=r"^[^:\s]+$",
            errTx="Username must not contain spaces or ':'.",
        )
        if username is None:
            return onSelReturn().errRet("Cancelled.")
        token = get_pwd(
            action="Git access token",
            minLen=4,
            maxLen=255,
            regExpStr=r"^\S+$",
            errTx="Token must contain 4-255 non-whitespace characters.",
        )
        if token is None:
            return onSelReturn().errRet("Cancelled.")
        try:
            self.registry.set_token(self.token_id, username, token)
        except Exception as exc:
            return onSelReturn().errRet(str(exc))
        return onSelReturn(ok=f"Token {self.token_id}.cd saved with mode 0600.")

    def remove_token(self, sel_item: c_menu_item) -> onSelReturn:
        if not confirm(f"Remove token {self.token_id}.cd? (y/n): "):
            return onSelReturn().errRet("Cancelled.")
        try:
            removed = self.registry.remove_token(self.token_id)
        except Exception as exc:
            return onSelReturn().errRet(str(exc))
        if not removed:
            return onSelReturn().errRet("Token file does not exist.")
        return onSelReturn(ok=f"Token {self.token_id}.cd removed.")


class PluginDetailMenu(c_menu):
    """Manage one plugin's local enabled, install and token state."""

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
            self.menu = [
                c_menu_title_label(text_color(str(exc), en_color.BRIGHT_RED))
            ]
            return

        self.title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        self.title.append((self.plugin_id, "c"))
        self.subTitle = c_menu_block_items()
        self.subTitle.append(("Description", status.description or "-"))
        self.subTitle.append(("Enabled", "yes" if status.enabled else "no"))
        self.subTitle.append(("Installed", "yes" if status.installed else "no"))
        self.subTitle.append(("Token", "present" if status.has_token else "missing"))
        self.subTitle.append(("Private", "yes" if status.private else "no"))
        self.subTitle.append(("Optional", "yes" if status.optional else "no"))
        self.subTitle.append(("Auto update", "yes" if status.auto_update else "no"))
        self.subTitle.append(("Path", status.path or "invalid"))

        requires_token = bool(status.private)
        access = plugin.get("access")
        if isinstance(access, dict):
            requires_token = requires_token or access.get("type") == "token"

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
        if requires_token:
            self.menu.extend(
                [
                    c_menu_title_label(text_color("Plugin access", en_color.CYAN)),
                    c_menu_item(
                        "Set or replace plugin token",
                        "t",
                        TokenSettingsMenu(
                            self.plugin_id,
                            f"Access token for {self.plugin_id}",
                        ),
                    ),
                ]
            )

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
