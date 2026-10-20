"""Read-only UFW inspection menu. Privileged Apply is not implemented."""
from __future__ import annotations

from pathlib import Path

from .lng.default import *
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import (
    c_menu, c_menu_block_items, c_menu_item, c_menu_title_label, onSelReturn,
)
from libs.JBLibs.input import anyKey, get_input
from libs.JBLibs.term import en_color, text_color

from .hub_provider import HUB_PROVIDER_KEY, hub_collect, inspect_ufw_service
from .policy import (FirewallPolicyError, inspect_before_rules,
                     plan_legacy_openvpn, read_legacy_config)

_MENU_NAME_ = TXT_FW_MENU
_HUB_PROVIDER_KEY_ = HUB_PROVIDER_KEY
_BEFORE_RULES = Path("/etc/ufw/before.rules")


class menu(c_menu):
    _VERSION_ = "0.1.0"
    ESC_is_quit = True
    minMenuWidth = 72

    def onShowMenu(self) -> None:
        title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        title.append((_MENU_NAME_, "c"))
        title.append("-")
        title.append((TXT_FW_VERSION, self._VERSION_))
        title.append((TXT_FW_FILE, str(_BEFORE_RULES)))
        self.title = title
        self.menu = [
            c_menu_title_label(text_color(TXT_FW_READ_ONLY, en_color.BRIGHT_YELLOW)),
            c_menu_item(TXT_FW_INSPECT, "i", self.inspect_rules),
            c_menu_item(TXT_FW_STATUS, "s", self.inspect_status),
            c_menu_item(TXT_FW_PREVIEW, "p", self.preview_legacy_config),
        ]

    def preview_legacy_config(self, selItem: c_menu_item) -> onSelReturn:
        """Read-only comparison against an explicitly selected old JSON/JS config."""
        selected = get_input(TXT_FW_PROMPT_PATH, minMessageWidth=self.minMenuWidth)
        if not selected:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        path = Path(str(selected).strip())
        if not path.is_absolute():
            return onSelReturn().errRet(TXT_FW_REQUIRE_ABSOLUTE)
        try:
            source = read_legacy_config(path)
            current = _BEFORE_RULES.read_text(encoding="utf-8")
            result = plan_legacy_openvpn(current, source)
        except (OSError, UnicodeError, FirewallPolicyError) as exc:
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
        print(TXT_FW_NO_RELOAD)
        anyKey()
        return onSelReturn(ok=TXT_FW_PREVIEW_STATUS.format(status=result.status))

    def inspect_status(self, selItem: c_menu_item) -> onSelReturn:
        status = inspect_ufw_service()
        detail = status.status if status.detected else TXT_FW_UNAVAILABLE
        return onSelReturn(ok=f"{TXT_FW_SERVICE}: {detail} {status.version}")

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
