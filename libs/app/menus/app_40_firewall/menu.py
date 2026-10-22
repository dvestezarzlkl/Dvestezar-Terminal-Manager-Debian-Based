"""Read-only UFW inspection menu. Privileged Apply is not implemented."""
from __future__ import annotations

from pathlib import Path
import re

from .lng.default import *
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import (
    c_menu, c_menu_block_items, c_menu_item, c_menu_title_label, onSelReturn,
)
from libs.JBLibs.input import anyKey, confirm, selectFile
from libs.JBLibs.term import en_color, text_color

from .config import (
    FirewallConfigError, config_path, hard_source_rules, import_legacy,
    legacy_openvpn_mapping, load_config, managed_standard_rule_ids, save_config,
)
from .hub_provider import HUB_PROVIDER_KEY, hub_collect, inspect_ufw_service
from .hub_sync import sync_local_rules_best_effort
from .menu_rules import FirewallRulesMenu
from .policy import (
    FirewallPolicyError, inspect_before_rules, plan_legacy_openvpn, rules_digest,
)

_MENU_NAME_ = TXT_FW_MENU
_HUB_PROVIDER_KEY_ = HUB_PROVIDER_KEY
_BEFORE_RULES = Path("/etc/ufw/before.rules")


class menu(c_menu):
    _VERSION_ = "0.3.1"
    ESC_is_quit = True
    minMenuWidth = 72

    def onShowMenu(self) -> None:
        title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        title.append((_MENU_NAME_, "c"))
        title.append("-")
        title.append((TXT_FW_VERSION, self._VERSION_))
        title.append((TXT_FW_FILE, str(_BEFORE_RULES)))
        title.append((TXT_FW_LOCAL_CONFIG, str(config_path(create_dir=False))))
        self.title = title
        service = inspect_ufw_service()
        if not service.detected:
            self.menu = [
                c_menu_item(text_color(TXT_FW_NOT_INSTALLED, en_color.BRIGHT_BLACK),
                            enabled=False),
            ]
            return
        if service.status != "active":
            label = (TXT_FW_INACTIVE if service.status == "inactive"
                     else TXT_FW_UNKNOWN_STATUS)
            self.menu = [
                c_menu_item(text_color(label, en_color.BRIGHT_RED), enabled=False),
            ]
            return
        self.menu = [
            c_menu_title_label(text_color(TXT_FW_READ_ONLY, en_color.BRIGHT_YELLOW)),
            c_menu_item(TXT_FW_INSPECT, "i", self.inspect_rules),
            c_menu_item(TXT_FW_STATUS, "s", self.inspect_status),
            c_menu_item(TXT_FW_PREVIEW, "p", self.preview_local_config),
            c_menu_item(TXT_FW_EDIT_RULES, "e", FirewallRulesMenu()),
            c_menu_item(TXT_FW_IMPORT_LEGACY, "l", self.import_legacy_config),
        ]

    def import_legacy_config(self, selItem: c_menu_item) -> onSelReturn:
        """One-time legacy file adoption through the shared JBLibs file picker."""
        start = Path("/etc/jb_sys_apps")
        if not start.is_dir():
            start = Path("/etc")
        selected = selectFile(
            str(start),
            message=TXT_FW_IMPORT_PICK,
            minMenuWidth=self.minMenuWidth,
            filterList=re.compile(r".*\.(?:json|jsonc|js)$", re.IGNORECASE),
        )
        if selected is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            current_rules = _BEFORE_RULES.read_text(encoding="utf-8")
            inspection = inspect_before_rules(current_rules)
            imported = import_legacy(selected, inspection)
            target = config_path(create_dir=False)
            if target.is_file():
                existing = load_config(target)
                if existing.rules and not confirm(TXT_FW_IMPORT_REPLACE):
                    return onSelReturn().errRet(TXT_FW_CANCELLED)
            saved = save_config(imported)
            sync_local_rules_best_effort()
        except (OSError, UnicodeError, FirewallPolicyError, FirewallConfigError) as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        self.menuRecycle = True
        return onSelReturn(ok=TXT_FW_IMPORT_OK.format(path=saved, count=len(imported.rules)))

    def preview_local_config(self, selItem: c_menu_item) -> onSelReturn:
        """Compare canonical local desired rules with currently managed UFW blocks."""
        try:
            cfg = load_config()
            current = _BEFORE_RULES.read_text(encoding="utf-8")
            inspection = inspect_before_rules(current)
        except (OSError, UnicodeError, FirewallPolicyError, FirewallConfigError) as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

        vpn_map = legacy_openvpn_mapping(cfg)
        vpn_clients = vpn_map["clients"]
        if vpn_clients:
            try:
                result = plan_legacy_openvpn(current, vpn_map)
            except FirewallPolicyError as exc:
                return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
            print(TXT_FW_PREVIEW_STATUS.format(status=result.status))
            print(TXT_FW_PREVIEW_RULES.format(
                current=result.current_rules,
                desired=result.effective_rules,
                expired=result.expired_bans,
            ))
            if result.next_expiry:
                print(TXT_FW_NEXT_EXPIRY.format(day=result.next_expiry.isoformat()))
            if result.reason:
                print(result.reason)
        else:
            print(TXT_FW_PREVIEW_NO_VPN)

        expected_hard = hard_source_rules(cfg)
        actual_hard = inspection.hard_sources.rules if inspection.hard_sources else ()
        hard_state = "NO_CHANGE" if rules_digest(expected_hard) == rules_digest(actual_hard) else "CHANGED"
        print(TXT_FW_PREVIEW_HARD.format(
            status=hard_state, current=len(actual_hard), desired=len(expected_hard)
        ))

        managed_ids = managed_standard_rule_ids(cfg)
        other = sum(
            1 for rule in cfg.rules
            if rule.enabled and rule.kind == "standard" and rule.rule_id not in managed_ids
        )
        if other:
            print(TXT_FW_PREVIEW_GENERIC_PENDING.format(count=other))
        print(TXT_FW_NO_RELOAD)
        anyKey()
        return onSelReturn(ok=TXT_FW_PREVIEW_DONE)

    def inspect_status(self, selItem: c_menu_item) -> onSelReturn:
        status = inspect_ufw_service()
        detail = status.status if status.detected else TXT_FW_UNAVAILABLE
        if not status.detected:
            return onSelReturn(ok=text_color(
                f"{TXT_FW_SERVICE}: {TXT_FW_NOT_INSTALLED}", en_color.BRIGHT_BLACK))
        if status.status == "active":
            color = en_color.BRIGHT_GREEN
        else:
            color = en_color.BRIGHT_RED
        return onSelReturn(ok=text_color(
            f"{TXT_FW_SERVICE}: {detail} {status.version}", color))

    def inspect_rules(self, selItem: c_menu_item) -> onSelReturn:
        try:
            inspection = inspect_before_rules(_BEFORE_RULES.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, FirewallPolicyError) as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        for label, block in (
            (TXT_FW_OPENVPN, inspection.openvpn),
            (TXT_FW_HARD_SOURCES, inspection.hard_sources),
        ):
            message = (
                f"{label}: {TXT_FW_PRESENT} ({len(block.rules)} {TXT_FW_RULE_COUNT})"
                if block is not None else f"{label}: {TXT_FW_ABSENT}"
            )
            print(message)
        if inspection.openvpn and inspection.hard_sources:
            print(TXT_FW_ORDER_OK)
        print(TXT_FW_NO_RELOAD)
        anyKey()
        return onSelReturn(ok=TXT_FW_NO_RELOAD)
