from __future__ import annotations

from libs.JBLibs.c_menu import (
    c_menu,
    c_menu_block_items,
    c_menu_item,
    c_menu_title_label,
    onSelReturn,
)
from libs.JBLibs.input import anyKey, confirm, get_input, get_pwd
from libs.JBLibs.term import en_color, text_color
from libs.app import cfg
from libs.app.hub.runtime import hub_runtime
from libs.app.settings_package import (
    DecodedSettingsPackage,
    apply_decoded_settings,
    decode_encrypted_settings,
    detect_import_conflicts,
    download_settings_package,
    export_encrypted_settings,
    preview_decoded_settings,
    registered_settings_sections,
    validate_settings_url,
)


class SettingsPackageMenu(c_menu):
    choiceBack = None
    ESC_is_quit = True

    def _save(self) -> None:
        cfg.save()

    def onShowMenu(self) -> None:
        url = str(cfg.SETTINGS_URL or "").strip()
        password_set = bool(cfg.SETTINGS_PASSWORD)
        auth_user = str(cfg.SETTINGS_AUTH_USER or "")
        auth_password_set = bool(cfg.SETTINGS_AUTH_PASSWORD)
        auth_valid = bool(auth_user) == auth_password_set
        if auth_user and auth_password_set:
            auth_state = f"{auth_user} / password set"
        elif auth_user or auth_password_set:
            auth_state = "incomplete"
        else:
            auth_state = "off"
        last_hash = str(cfg.SETTINGS_LAST_SHA256 or "")
        self.title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        self.title.append(("Centralized settings", "c"))
        self.subTitle = c_menu_block_items()
        self.subTitle.append(("URL", url or "not set"))
        self.subTitle.append(("HTTP Basic Auth", auth_state))
        self.subTitle.append(("Automatic update", "on" if cfg.SETTINGS_AUTO_UPDATE else "off"))
        self.subTitle.append(("Last revision", str(cfg.SETTINGS_LAST_REVISION or 0)))
        self.subTitle.append(("Last SHA-256", last_hash[:16] if last_hash else "not set"))
        self.menu = [
            c_menu_title_label(text_color("Bootstrap settings", en_color.CYAN)),
            c_menu_item(
                text_color("Settings URL", en_color.BRIGHT_CYAN),
                "u",
                self.edit_url,
                atRight=url or "not set",
            ),
            c_menu_item(
                text_color("Settings password", en_color.BRIGHT_CYAN),
                "p",
                self.edit_password,
                atRight="set" if password_set else "not set",
            ),
            c_menu_item(
                text_color("Clear settings password", en_color.BRIGHT_YELLOW),
                "cp",
                self.clear_password,
                enabled=password_set,
            ),
            c_menu_item(
                text_color("HTTP Basic Auth user", en_color.BRIGHT_CYAN),
                "bu",
                self.edit_auth_user,
                atRight=auth_user or "not set",
            ),
            c_menu_item(
                text_color("HTTP Basic Auth password", en_color.BRIGHT_CYAN),
                "bp",
                self.edit_auth_password,
                atRight="set" if auth_password_set else "not set",
                enabled=bool(auth_user),
            ),
            c_menu_item(
                text_color("Clear HTTP Basic Auth", en_color.BRIGHT_YELLOW),
                "bc",
                self.clear_http_auth,
                enabled=bool(auth_user or auth_password_set),
            ),
            c_menu_item(
                "Automatic update at startup",
                "a",
                self.toggle_auto_update,
                atRight="on" if cfg.SETTINGS_AUTO_UPDATE else "off",
            ),
            c_menu_item(
                "Download timeout",
                "t",
                self.edit_timeout,
                atRight=f"{cfg.SETTINGS_CONNECT_TIMEOUT}s",
            ),
            c_menu_item(
                text_color("Allow insecure HTTP", en_color.BRIGHT_YELLOW),
                "h",
                self.toggle_allow_http,
                atRight="on" if cfg.SETTINGS_ALLOW_HTTP else "off",
            ),
            None,
            c_menu_title_label(text_color("Settings package", en_color.CYAN)),
            c_menu_item(
                text_color("Export encrypted settings", en_color.BRIGHT_CYAN),
                "exp",
                self.export_package,
            ),
            c_menu_item(
                text_color("Import encrypted settings", en_color.BRIGHT_YELLOW),
                "imp",
                self.import_package,
            ),
            c_menu_item(
                text_color("Import settings from URL", en_color.BRIGHT_GREEN),
                "url",
                self.import_from_url,
                atRight=url or "URL not set",
                enabled=bool(url and password_set and auth_valid),
            ),
        ]

    def edit_url(self, selItem: c_menu_item) -> onSelReturn:
        current = str(cfg.SETTINGS_URL or "").strip()
        value = get_input(
            f"Central settings URL [{current}]:",
            accept_empty=True,
            maxLen=2048,
            titleNote=(
                "Use an HTTPS URL containing one encrypted SYSAPP1E package.\n"
                "Empty value clears the URL. Credentials must not be embedded in it."
            ),
        )
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        value = value.strip()
        if value:
            try:
                value = validate_settings_url(value, bool(cfg.SETTINGS_ALLOW_HTTP))
            except ValueError as exc:
                return onSelReturn().errRet(str(exc))
        cfg.SETTINGS_URL = value
        self._save()
        return onSelReturn(ok="Central settings URL updated.")

    def edit_password(self, selItem: c_menu_item) -> onSelReturn:
        value = get_pwd(
            "Central settings password",
            make_cls=False,
            minMessageWidth=0,
        )
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        confirmation = get_pwd(
            "Confirm central settings password",
            make_cls=False,
            minMessageWidth=0,
        )
        if confirmation != value:
            return onSelReturn().errRet("Passwords do not match.")
        cfg.SETTINGS_PASSWORD = value
        self._save()
        return onSelReturn(ok="Central settings password updated.")

    def clear_password(self, selItem: c_menu_item) -> onSelReturn:
        if not cfg.SETTINGS_PASSWORD:
            return onSelReturn(ok="Central settings password is already empty.")
        if not confirm("Clear the configured central settings password?"):
            return onSelReturn().errRet("Cancelled.")
        cfg.SETTINGS_PASSWORD = ""
        self._save()
        return onSelReturn(ok="Central settings password cleared.")

    def edit_auth_user(self, selItem: c_menu_item) -> onSelReturn:
        current = str(cfg.SETTINGS_AUTH_USER or "")
        value = get_input(
            f"HTTP Basic Auth user [{current}]:",
            accept_empty=True,
            maxLen=255,
            titleNote=(
                "Optional web-server username sent in the Authorization header.\n"
                "It is local bootstrap data and is never exported in SYSAPP1E."
            ),
        )
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        value = value.strip()
        if ":" in value or "\r" in value or "\n" in value:
            return onSelReturn().errRet(
                "HTTP Basic Auth user contains invalid characters."
            )
        if not value and cfg.SETTINGS_AUTH_PASSWORD:
            if not confirm(
                "Clearing the HTTP Basic Auth user also clears its password. Continue?"
            ):
                return onSelReturn().errRet("Cancelled.")
            cfg.SETTINGS_AUTH_PASSWORD = ""
        cfg.SETTINGS_AUTH_USER = value
        self._save()
        return onSelReturn(ok="HTTP Basic Auth user updated.")

    def edit_auth_password(self, selItem: c_menu_item) -> onSelReturn:
        if not cfg.SETTINGS_AUTH_USER:
            return onSelReturn().errRet(
                "Configure the HTTP Basic Auth user first."
            )
        value = get_pwd(
            "HTTP Basic Auth password",
            make_cls=False,
            minMessageWidth=0,
        )
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        confirmation = get_pwd(
            "Confirm HTTP Basic Auth password",
            make_cls=False,
            minMessageWidth=0,
        )
        if confirmation != value:
            return onSelReturn().errRet("Passwords do not match.")
        cfg.SETTINGS_AUTH_PASSWORD = value
        self._save()
        return onSelReturn(ok="HTTP Basic Auth password updated.")

    def clear_http_auth(self, selItem: c_menu_item) -> onSelReturn:
        if not cfg.SETTINGS_AUTH_USER and not cfg.SETTINGS_AUTH_PASSWORD:
            return onSelReturn(ok="HTTP Basic Auth is already empty.")
        if not confirm("Clear the configured HTTP Basic Auth credentials?"):
            return onSelReturn().errRet("Cancelled.")
        cfg.SETTINGS_AUTH_USER = ""
        cfg.SETTINGS_AUTH_PASSWORD = ""
        self._save()
        return onSelReturn(ok="HTTP Basic Auth credentials cleared.")

    def toggle_auto_update(self, selItem: c_menu_item) -> onSelReturn:
        cfg.SETTINGS_AUTO_UPDATE = not bool(cfg.SETTINGS_AUTO_UPDATE)
        self._save()
        return onSelReturn(ok="Automatic settings update changed.")

    def edit_timeout(self, selItem: c_menu_item) -> onSelReturn:
        value = get_input(
            f"Download timeout [{cfg.SETTINGS_CONNECT_TIMEOUT}]:",
            accept_empty=False,
            maxLen=2,
            rgx=r"^\d+$",
            errTx="Timeout must be a number from 1 to 30.",
        )
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        timeout = int(value)
        if not 1 <= timeout <= 30:
            return onSelReturn().errRet("Timeout must be between 1 and 30 seconds.")
        cfg.SETTINGS_CONNECT_TIMEOUT = timeout
        self._save()
        return onSelReturn(ok="Central settings timeout updated.")

    def toggle_allow_http(self, selItem: c_menu_item) -> onSelReturn:
        if not cfg.SETTINGS_ALLOW_HTTP:
            if not confirm(
                "HTTP does not protect the encrypted package against replacement or traffic analysis. Enable it anyway?"
            ):
                return onSelReturn().errRet("Cancelled.")
        cfg.SETTINGS_ALLOW_HTTP = not bool(cfg.SETTINGS_ALLOW_HTTP)
        self._save()
        return onSelReturn(ok="HTTP policy updated.")

    def _package_password(self) -> tuple[str | None, bool]:
        if cfg.SETTINGS_PASSWORD and confirm(
            "Use the configured central settings password for this package?"
        ):
            return str(cfg.SETTINGS_PASSWORD), True
        value = get_pwd(
            "Package password", make_cls=False, minMessageWidth=0
        )
        return value, False

    def _print_preview(self, decoded: DecodedSettingsPackage) -> None:
        print(text_color("Settings package preview", en_color.BRIGHT_CYAN, bold=True))
        for line in preview_decoded_settings(decoded):
            print(f" - {line}")

    def _resolve_import_conflicts(
        self, decoded: DecodedSettingsPackage
    ) -> tuple[str, ...]:
        skipped: set[str] = set()
        for conflict in detect_import_conflicts(decoded):
            current = conflict.current_value or "not set"
            incoming = conflict.incoming_value or "not set"
            replace = confirm(
                f"{conflict.label} is currently '{current}'. Replace it with '{incoming}'?"
            )
            if not replace:
                skipped.add(conflict.section_key)
                break
        return tuple(sorted(skipped))

    def _confirm_import(
        self,
        decoded: DecodedSettingsPackage,
        skip_sections: tuple[str, ...] = (),
    ) -> tuple[bool, bool]:
        remaining = set(decoded.sections).intersection(
            registered_settings_sections()
        ).difference(skip_sections)
        if not remaining:
            return True, False
        current = int(cfg.SETTINGS_LAST_REVISION or 0)
        downgrade = decoded.revision > 0 and decoded.revision < current
        scope = "remaining supported" if skip_sections else "supported"
        if downgrade:
            ok = confirm(
                f"Package revision {decoded.revision} is older than local revision {current}. Apply this manual downgrade to the {scope} settings sections?"
            )
            return ok, True
        return confirm(f"Apply the {scope} settings sections shown above?"), False

    def _apply_import(
        self,
        decoded: DecodedSettingsPackage,
        allow_downgrade: bool,
        skip_sections: tuple[str, ...] = (),
    ) -> onSelReturn:
        try:
            report = apply_decoded_settings(
                decoded,
                allow_downgrade=allow_downgrade,
                force=True,
                skip_sections=skip_sections,
            )
            hub_runtime.refresh_status()
        except (TypeError, ValueError) as exc:
            return onSelReturn().errRet(str(exc))
        for warning in report.warnings:
            print(text_color(f"Warning: {warning}", en_color.BRIGHT_YELLOW))
        if report.warnings:
            anyKey()
        revision = decoded.revision if decoded.revision else "legacy"
        if not report.applied_sections:
            skipped = ", ".join(report.skipped_sections) or "none"
            return onSelReturn(
                ok=f"No settings applied from revision {revision}; skipped sections: {skipped}."
            )
        sections = ", ".join(report.applied_sections)
        return onSelReturn(ok=f"Imported revision {revision}; sections: {sections}.")

    def export_package(self, selItem: c_menu_item) -> onSelReturn:
        password, configured = self._package_password()
        if not password:
            return onSelReturn().errRet("Package password is required.")
        if not configured:
            confirmation = get_pwd(
                "Confirm package password",
                make_cls=False,
                minMessageWidth=0,
            )
            if confirmation != password:
                return onSelReturn().errRet("Package passwords do not match.")
        try:
            package = export_encrypted_settings(password)
            decoded = decode_encrypted_settings(package, password)
        except (TypeError, ValueError) as exc:
            return onSelReturn().errRet(str(exc))
        print(f"Encrypted settings package, revision {decoded.revision}:")
        print(package)
        anyKey()
        return onSelReturn(ok=f"Settings package revision {decoded.revision} generated.")

    def import_package(self, selItem: c_menu_item) -> onSelReturn:
        package = get_input(
            "Paste the encrypted settings package:",
            accept_empty=False,
            maxLen=65536,
        )
        if package is None:
            return onSelReturn().errRet("Cancelled.")
        password, _ = self._package_password()
        if not password:
            return onSelReturn().errRet("Package password is required.")
        try:
            decoded = decode_encrypted_settings(package, password)
            self._print_preview(decoded)
        except (TypeError, ValueError) as exc:
            return onSelReturn().errRet(str(exc))
        skip_sections = self._resolve_import_conflicts(decoded)
        confirmed, downgrade = self._confirm_import(decoded, skip_sections)
        if not confirmed:
            return onSelReturn().errRet("Cancelled.")
        return self._apply_import(decoded, downgrade, skip_sections)

    def import_from_url(self, selItem: c_menu_item) -> onSelReturn:
        if not cfg.SETTINGS_URL or not cfg.SETTINGS_PASSWORD:
            return onSelReturn().errRet(
                "Central settings URL and password must be configured first."
            )
        try:
            package = download_settings_package(
                cfg.SETTINGS_URL,
                int(cfg.SETTINGS_CONNECT_TIMEOUT),
                bool(cfg.SETTINGS_ALLOW_HTTP),
                str(cfg.SETTINGS_AUTH_USER or ""),
                str(cfg.SETTINGS_AUTH_PASSWORD or ""),
            )
            decoded = decode_encrypted_settings(package, cfg.SETTINGS_PASSWORD)
            self._print_preview(decoded)
        except Exception as exc:
            return onSelReturn().errRet(str(exc))
        skip_sections = self._resolve_import_conflicts(decoded)
        confirmed, downgrade = self._confirm_import(decoded, skip_sections)
        if not confirmed:
            return onSelReturn().errRet("Cancelled.")
        return self._apply_import(decoded, downgrade, skip_sections)
