from __future__ import annotations

from .lng.default import *
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu, c_menu_block_items, c_menu_item, c_menu_title_label, onSelReturn
from libs.JBLibs.input import anyKey, confirm, get_input, get_pwd
from libs.JBLibs.term import en_color, text_color
from libs.app import cfg
from libs.app.runtime_flags import local_settings_override_enabled
from libs.app.settings_package import (
    centrally_managed_config_keys,
    invalidate_central_settings_after_local_override,
)

from .config_package import export_encrypted_settings, import_encrypted_settings
from .models import HubState
from .runtime import hub_runtime
from .settings import HubSettings, apply_settings


class HubSettingsMenu(c_menu):
    choiceBack = None
    ESC_is_quit = True

    def _save(self, *changed_keys: str) -> None:
        invalidate_central_settings_after_local_override(*changed_keys)
        cfg.save()
        hub_runtime.refresh_status()

    def _status_color(self) -> en_color:
        if hub_runtime.status.state is HubState.READY:
            return en_color.BRIGHT_GREEN
        if hub_runtime.status.state in {HubState.DISABLED, HubState.NOT_CONFIGURED}:
            return en_color.BRIGHT_BLACK
        return en_color.BRIGHT_RED

    def onShowMenu(self) -> None:
        settings = HubSettings.from_cfg()
        managed_keys = centrally_managed_config_keys()
        hide_managed = not local_settings_override_enabled()
        self.title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        self.title.append(TXT_HUB_TITLE)
        self.subTitle = c_menu_block_items()
        self.subTitle.append((TXT_HUB_STATUS, text_color(hub_runtime.status_text(), self._status_color())))
        self.subTitle.append((TXT_HUB_TARGET, f"{settings.host}:{settings.port}/{settings.database}"))
        self.subTitle.append((TXT_HUB_PREFIX, settings.prefix))
        self.menu = [
            c_menu_title_label(text_color(TXT_HUB_TITLE, en_color.CYAN)),
            c_menu_item(
                TXT_HUB_ENABLED,
                "e",
                self.toggle_enabled,
                atRight=TXT_HUB_ON if settings.enabled else TXT_HUB_OFF,
                hidden=hide_managed and "HUB_ENABLED" in managed_keys,
            ),
            c_menu_item(
                TXT_HUB_AUTO_SYNC,
                "a",
                self.toggle_auto_sync,
                atRight=TXT_HUB_ON if settings.auto_sync else TXT_HUB_OFF,
                hidden=hide_managed and "HUB_AUTO_SYNC" in managed_keys,
            ),
            None,
            c_menu_item(
                TXT_HUB_DB_HOST,
                "h",
                self.edit_host,
                atRight=settings.host or TXT_HUB_NOT_SET,
                hidden=hide_managed and "HUB_DB_HOST" in managed_keys,
            ),
            c_menu_item(
                TXT_HUB_DB_PORT,
                "p",
                self.edit_port,
                atRight=str(settings.port),
                hidden=hide_managed and "HUB_DB_PORT" in managed_keys,
            ),
            c_menu_item(
                TXT_HUB_DB_USER,
                "u",
                self.edit_user,
                atRight=settings.user or TXT_HUB_NOT_SET,
                hidden=hide_managed and "HUB_DB_USER" in managed_keys,
            ),
            c_menu_item(
                TXT_HUB_DB_PASSWORD,
                "w",
                self.edit_password,
                atRight=TXT_HUB_SET if settings.password else TXT_HUB_NOT_SET,
                hidden=hide_managed and "HUB_DB_PASSWORD" in managed_keys,
            ),
            c_menu_item(
                TXT_HUB_DB_NAME,
                "d",
                self.edit_database,
                atRight=settings.database,
                hidden=hide_managed and "HUB_DB_NAME" in managed_keys,
            ),
            c_menu_item(
                TXT_HUB_DB_PREFIX,
                "x",
                self.edit_prefix,
                atRight=settings.prefix,
                hidden=hide_managed and "HUB_DB_PREFIX" in managed_keys,
            ),
            c_menu_item(
                TXT_HUB_TIMEOUT,
                "o",
                self.edit_timeout,
                atRight=f"{settings.connect_timeout}s",
                hidden=hide_managed and "HUB_CONNECT_TIMEOUT" in managed_keys,
            ),
            None,
            c_menu_item(text_color(TXT_HUB_TEST, en_color.BRIGHT_CYAN), "t", self.test_connection),
            c_menu_item(text_color(TXT_HUB_SCHEMA, en_color.BRIGHT_YELLOW), "i", self.initialize_schema),
            c_menu_item(
                text_color(TXT_HUB_SYNC, en_color.BRIGHT_GREEN),
                "s",
                self.sync_all,
                enabled=hub_runtime.status.state is HubState.READY,
                atRight=hub_runtime.status_text(),
            ),
        ]

    def toggle_enabled(self, selItem: c_menu_item) -> onSelReturn:
        cfg.HUB_ENABLED = not bool(cfg.HUB_ENABLED)
        self._save("HUB_ENABLED")
        return onSelReturn(ok=TXT_HUB_SAVED)

    def toggle_auto_sync(self, selItem: c_menu_item) -> onSelReturn:
        cfg.HUB_AUTO_SYNC = not bool(cfg.HUB_AUTO_SYNC)
        self._save("HUB_AUTO_SYNC")
        return onSelReturn(ok=TXT_HUB_SAVED)

    def _edit_text(self, prompt: str, attr_name: str, max_len: int = 255) -> onSelReturn:
        current = str(getattr(cfg, attr_name, "") or "")
        value = get_input(f"{prompt} [{current}]:", accept_empty=True, maxLen=max_len)
        if value is None:
            return onSelReturn().errRet(TXT_HUB_CANCELLED)
        setattr(cfg, attr_name, value.strip())
        self._save(attr_name)
        return onSelReturn(ok=TXT_HUB_SAVED)

    def edit_host(self, selItem: c_menu_item) -> onSelReturn:
        return self._edit_text(TXT_HUB_DB_HOST, "HUB_DB_HOST")

    def edit_user(self, selItem: c_menu_item) -> onSelReturn:
        return self._edit_text(TXT_HUB_DB_USER, "HUB_DB_USER")

    def edit_database(self, selItem: c_menu_item) -> onSelReturn:
        value = get_input(
            f"{TXT_HUB_DB_NAME} [{cfg.HUB_DB_NAME}]:",
            accept_empty=False,
            maxLen=64,
            rgx=r"^[A-Za-z0-9_]+$",
            errTx="Invalid database name.",
        )
        if value is None:
            return onSelReturn().errRet(TXT_HUB_CANCELLED)
        cfg.HUB_DB_NAME = value.strip()
        self._save("HUB_DB_NAME")
        return onSelReturn(ok=TXT_HUB_SAVED)

    def edit_prefix(self, selItem: c_menu_item) -> onSelReturn:
        value = get_input(
            f"{TXT_HUB_DB_PREFIX} [{cfg.HUB_DB_PREFIX}]:",
            accept_empty=False,
            maxLen=32,
            rgx=r"^[a-z][a-z0-9_]{0,31}$",
            errTx="Invalid table prefix.",
        )
        if value is None:
            return onSelReturn().errRet(TXT_HUB_CANCELLED)
        cfg.HUB_DB_PREFIX = value.strip()
        self._save("HUB_DB_PREFIX")
        return onSelReturn(ok=TXT_HUB_SAVED)

    def edit_password(self, selItem: c_menu_item) -> onSelReturn:
        value = get_pwd(TXT_HUB_DB_PASSWORD, make_cls=False, minMessageWidth=0)
        if value is None:
            return onSelReturn().errRet(TXT_HUB_CANCELLED)
        cfg.HUB_DB_PASSWORD = value
        self._save("HUB_DB_PASSWORD")
        return onSelReturn(ok=TXT_HUB_SAVED)

    def _edit_number(self, prompt: str, attr_name: str, minimum: int, maximum: int) -> onSelReturn:
        current = int(getattr(cfg, attr_name))
        value = get_input(
            f"{prompt} [{current}]:",
            accept_empty=False,
            maxLen=5,
            rgx=r"^\d+$",
            errTx="Invalid number.",
        )
        if value is None:
            return onSelReturn().errRet(TXT_HUB_CANCELLED)
        number = int(value)
        if not minimum <= number <= maximum:
            return onSelReturn().errRet(f"Value must be between {minimum} and {maximum}.")
        setattr(cfg, attr_name, number)
        self._save(attr_name)
        return onSelReturn(ok=TXT_HUB_SAVED)

    def edit_port(self, selItem: c_menu_item) -> onSelReturn:
        return self._edit_number(TXT_HUB_DB_PORT, "HUB_DB_PORT", 1, 65535)

    def edit_timeout(self, selItem: c_menu_item) -> onSelReturn:
        return self._edit_number(TXT_HUB_TIMEOUT, "HUB_CONNECT_TIMEOUT", 1, 30)

    def test_connection(self, selItem: c_menu_item) -> onSelReturn:
        status = hub_runtime.refresh_status()
        if status.ready:
            return onSelReturn(ok=hub_runtime.status_text())
        return onSelReturn().errRet(hub_runtime.status_text())

    def initialize_schema(self, selItem: c_menu_item) -> onSelReturn:
        if not confirm(TXT_HUB_SCHEMA_CONFIRM):
            return onSelReturn().errRet(TXT_HUB_CANCELLED)
        print("SysApps Hub: applying database migrations...")
        ok, message = hub_runtime.initialize_schema()
        if not ok:
            return onSelReturn().errRet(message)
        return onSelReturn(ok=message)

    def sync_all(self, selItem: c_menu_item) -> onSelReturn:
        if not confirm(TXT_HUB_SYNC_CONFIRM):
            return onSelReturn().errRet(TXT_HUB_CANCELLED)
        print("SysApps Hub: collecting and synchronizing inventory...")
        report = hub_runtime.sync_all()
        if report.error:
            return onSelReturn().errRet(report.error)
        for warning in report.warnings:
            print(f"{TXT_HUB_WARNING}: {warning}")
        if report.warnings:
            anyKey()
        total = sum(report.provider_counts.values())
        return onSelReturn(ok=f"{TXT_HUB_SYNC_CORE} Provider items: {total}.")

    def export_settings(self, selItem: c_menu_item) -> onSelReturn:
        password = get_pwd(TXT_HUB_PACKAGE_PASSWORD, make_cls=False, minMessageWidth=0)
        if not password:
            return onSelReturn().errRet(TXT_HUB_CANCELLED)
        confirmation = get_pwd(TXT_HUB_PACKAGE_PASSWORD_CONFIRM, make_cls=False, minMessageWidth=0)
        if confirmation != password:
            return onSelReturn().errRet(TXT_HUB_PACKAGE_PASSWORD_MISMATCH)
        try:
            package = export_encrypted_settings(HubSettings.from_cfg(), password)
        except ValueError as exc:
            return onSelReturn().errRet(str(exc))
        print(TXT_HUB_PACKAGE_OUTPUT)
        print(package)
        anyKey()
        return onSelReturn(ok="Package generated.")

    def import_settings(self, selItem: c_menu_item) -> onSelReturn:
        package = get_input(TXT_HUB_PACKAGE_INPUT, accept_empty=False, maxLen=32768)
        if package is None:
            return onSelReturn().errRet(TXT_HUB_CANCELLED)
        password = get_pwd(TXT_HUB_PACKAGE_PASSWORD, make_cls=False, minMessageWidth=0)
        if not password:
            return onSelReturn().errRet(TXT_HUB_CANCELLED)
        try:
            values = import_encrypted_settings(package, password)
            if not confirm(TXT_HUB_IMPORT_CONFIRM):
                return onSelReturn().errRet(TXT_HUB_CANCELLED)
            apply_settings(values)
            hub_runtime.refresh_status()
        except (TypeError, ValueError) as exc:
            return onSelReturn().errRet(str(exc))
        return onSelReturn(ok=TXT_HUB_SAVED)
