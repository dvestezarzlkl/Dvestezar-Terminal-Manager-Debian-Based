"""OpenVPN server catalog and per-server BAN editor for Firewall Manager."""
from __future__ import annotations

from dataclasses import replace
import re

from .lng.default import *
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import (
    c_menu,
    c_menu_block_items,
    c_menu_item,
    c_menu_title_label,
    onSelReturn,
    printBlock,
)
from libs.JBLibs.input import confirm
from libs.JBLibs.term import en_color, text_color

from .config import (
    FirewallConfig,
    FirewallConfigError,
    FirewallRule,
    FirewallVpnServer,
    append_rule,
    append_vpn_server,
    delete_rule,
    delete_vpn_server,
    load_config,
    new_rule_id,
    new_server_id,
    normalize_rule,
    normalize_vpn_server,
    replace_rule,
    replace_vpn_server,
    save_config,
    vpn_server,
)
from .hub_sync import sync_local_rules_best_effort
from .menu_helpers import pick, pick_interface, progress_block, prompt


def _save(menu: c_menu, cfg: FirewallConfig) -> onSelReturn:
    try:
        path = save_config(cfg)
    except (OSError, FirewallConfigError) as exc:
        return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
    sync_local_rules_best_effort()
    menu.menuRecycle = True
    return onSelReturn(ok=TXT_FW_EDITOR_SAVED.format(path=path))


def _server_context(server: FirewallVpnServer) -> dict[str, str]:
    return {
        TXT_FW_EDITOR_VPN_NAME.rstrip(":"): server.name,
        TXT_FW_EDITOR_VPN_IP.rstrip(":"): server.ip,
        TXT_FW_EDITOR_VPN_MASK.rstrip(":"): str(server.mask),
        TXT_FW_EDITOR_INTERFACE.rstrip(":"): server.interface,
    }


def _confirm_server(server: FirewallVpnServer, width: int) -> bool:
    printBlock(
        progress_block(TXT_FW_VPN_SERVER_FORM, _server_context(server)),
        c_menu_block_items(),
        min_width=width,
    )
    return confirm(TXT_FW_VPN_SERVER_CONFIRM)


def _confirm_ban(
    server: FirewallVpnServer,
    rule: FirewallRule,
    width: int,
) -> bool:
    context = _server_context(server)
    context[TXT_FW_EDITOR_NAME.rstrip(":")] = rule.name
    context[TXT_FW_EDITOR_SOURCE.rstrip(":")] = rule.source
    context[TXT_FW_EDITOR_BAN_TO.rstrip(":")] = rule.ban_to or "-"
    printBlock(
        progress_block(TXT_FW_VPN_BAN_FORM, context),
        c_menu_block_items(),
        min_width=width,
    )
    return confirm(TXT_FW_EDITOR_CONFIRM_SAVE)


def _edit_server(
    width: int,
    current: FirewallVpnServer | None,
) -> FirewallVpnServer | None:
    context: dict[str, str] = {}
    name = prompt(
        TXT_FW_EDITOR_VPN_NAME,
        width=width,
        current=current.name if current else "",
        required=True,
        title=TXT_FW_VPN_SERVER_FORM,
        context=context,
    )
    if name is None:
        return None
    context[TXT_FW_EDITOR_VPN_NAME.rstrip(":")] = name

    ip = prompt(
        TXT_FW_EDITOR_VPN_IP,
        width=width,
        current=current.ip if current else "",
        required=True,
        max_len=64,
        title=TXT_FW_VPN_SERVER_FORM,
        context=context,
    )
    if ip is None:
        return None
    context[TXT_FW_EDITOR_VPN_IP.rstrip(":")] = ip

    mask = prompt(
        TXT_FW_EDITOR_VPN_MASK,
        width=width,
        current=current.mask if current else 23,
        required=True,
        max_len=2,
        rgx=re.compile(r"^[0-9]{1,2}$"),
        title=TXT_FW_VPN_SERVER_FORM,
        context=context,
    )
    if mask is None:
        return None
    context[TXT_FW_EDITOR_VPN_MASK.rstrip(":")] = mask

    interface = pick_interface(
        width=width,
        context=context,
        current=current.interface if current else "tun+",
        allow_any=False,
        title=TXT_FW_VPN_SERVER_FORM,
    )
    if interface is None:
        return None
    context[TXT_FW_EDITOR_INTERFACE.rstrip(":")] = interface

    try:
        return normalize_vpn_server(FirewallVpnServer(
            server_id=current.server_id if current else new_server_id(),
            name=name,
            ip=ip,
            mask=int(mask),
            interface=interface,
        ))
    except (ValueError, FirewallConfigError):
        return None


def _edit_ban(
    width: int,
    server: FirewallVpnServer,
    current: FirewallRule | None,
) -> FirewallRule | None:
    context = _server_context(server)
    name = prompt(
        TXT_FW_EDITOR_NAME,
        width=width,
        current=current.name if current else "",
        required=True,
        title=TXT_FW_VPN_BAN_FORM,
        context=context,
    )
    if name is None:
        return None
    context[TXT_FW_EDITOR_NAME.rstrip(":")] = name

    source = prompt(
        TXT_FW_EDITOR_SOURCE,
        width=width,
        current=current.source if current else "",
        required=True,
        max_len=64,
        title=TXT_FW_VPN_BAN_FORM,
        context=context,
    )
    if source is None:
        return None
    context[TXT_FW_EDITOR_SOURCE.rstrip(":")] = source

    ban_to = prompt(
        TXT_FW_EDITOR_BAN_TO,
        width=width,
        current=current.ban_to if current else "",
        required=False,
        max_len=10,
        title=TXT_FW_VPN_BAN_FORM,
        context=context,
    )
    if ban_to is None:
        return None

    try:
        return normalize_rule(FirewallRule(
            rule_id=current.rule_id if current else new_rule_id(),
            kind="vpn_ban",
            enabled=current.enabled if current else True,
            name=name,
            source=source,
            ban_to=ban_to,
            vpn_server_id=server.server_id,
        ))
    except FirewallConfigError:
        return None


class VpnServersMenu(c_menu):
    ESC_is_quit = True
    minMenuWidth = 78

    def onShowMenu(self) -> None:
        try:
            cfg = load_config()
        except FirewallConfigError as exc:
            self.menu = [c_menu_title_label(TXT_FW_VPN_SERVERS_TITLE)]
            self.msg = TXT_FW_FAIL.format(reason=str(exc))
            return

        self.subTitle = c_menu_block_items([
            (TXT_FW_VPN_SERVER_COUNT, str(len(cfg.vpn_servers))),
        ])
        self.menu = [
            c_menu_title_label(TXT_FW_VPN_SERVERS_TITLE),
            c_menu_item(
                text_color(TXT_FW_VPN_SERVER_ADD, en_color.BRIGHT_CYAN),
                "a",
                self.add_server,
            ),
            c_menu_title_label("-" * 30),
        ]
        for index, server in enumerate(cfg.vpn_servers, start=1):
            bans = sum(
                1 for rule in cfg.rules
                if rule.kind == "vpn_ban"
                and rule.vpn_server_id == server.server_id
            )
            label = TXT_FW_VPN_SERVER_ITEM.format(
                name=server.name,
                ip=server.ip,
                mask=server.mask,
                interface=server.interface,
                bans=bans,
            )
            self.menu.append(
                c_menu_item(
                    label,
                    str(index),
                    VpnServerRulesMenu(server.server_id),
                )
            )

    def add_server(self, selItem: c_menu_item) -> onSelReturn:
        try:
            cfg = load_config()
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        server = _edit_server(self.minMenuWidth, None)
        if server is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        if not _confirm_server(server, self.minMenuWidth):
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            return _save(self, append_vpn_server(cfg, server))
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))


class VpnServerRulesMenu(c_menu):
    ESC_is_quit = True
    minMenuWidth = 78

    def __init__(self, server_id: str):
        super().__init__()
        self.server_id = server_id

    def onShowMenu(self) -> None:
        try:
            cfg = load_config()
            server = vpn_server(cfg, self.server_id)
        except FirewallConfigError as exc:
            self.menu = [c_menu_title_label(TXT_FW_VPN_BANS_TITLE)]
            self.msg = TXT_FW_FAIL.format(reason=str(exc))
            return

        self.title = progress_block(
            TXT_FW_VPN_BANS_TITLE,
            _server_context(server),
        )
        bans = [
            rule for rule in cfg.rules
            if rule.kind == "vpn_ban"
            and rule.vpn_server_id == self.server_id
        ]
        self.menu = [
            c_menu_title_label(TXT_FW_VPN_BAN_SECTION),
            c_menu_item(
                text_color(TXT_FW_VPN_BAN_ADD, en_color.BRIGHT_CYAN),
                "a",
                self.add_ban,
            ),
        ]
        for index, rule in enumerate(bans, start=1):
            state = TXT_FW_EDITOR_ENABLED if rule.enabled else TXT_FW_EDITOR_DISABLED
            until = rule.ban_to or TXT_FW_VPN_BAN_PERMANENT
            self.menu.append(c_menu_item(
                f"[{state}] {rule.name}: {rule.source} -> {until}",
                str(index),
                self.ban_action,
                data=rule.rule_id,
            ))
        self.menu.extend([
            c_menu_title_label(TXT_FW_VPN_SERVER_SECTION),
            c_menu_item(TXT_FW_VPN_SERVER_EDIT, "e", self.edit_server),
            c_menu_item(
                text_color(TXT_FW_VPN_SERVER_DELETE, en_color.BRIGHT_RED),
                "d",
                self.delete_server,
            ),
        ])

    def add_ban(self, selItem: c_menu_item) -> onSelReturn:
        try:
            cfg = load_config()
            server = vpn_server(cfg, self.server_id)
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        rule = _edit_ban(self.minMenuWidth, server, None)
        if rule is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        if not _confirm_ban(server, rule, self.minMenuWidth):
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            return _save(self, append_rule(cfg, rule))
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

    def ban_action(self, selItem: c_menu_item) -> onSelReturn:
        try:
            cfg = load_config()
            server = vpn_server(cfg, self.server_id)
            rule = next(
                item for item in cfg.rules
                if item.rule_id == str(selItem.data or "")
                and item.kind == "vpn_ban"
                and item.vpn_server_id == self.server_id
            )
        except (FirewallConfigError, StopIteration) as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

        action = pick(
            TXT_FW_EDITOR_RULE_ACTION,
            [
                ("e", TXT_FW_EDITOR_EDIT, "edit"),
                ("t", TXT_FW_EDITOR_TOGGLE, "toggle"),
                ("d", TXT_FW_EDITOR_DELETE, "delete"),
            ],
            self.minMenuWidth,
            title=TXT_FW_VPN_BAN_FORM,
            context=_server_context(server),
        )
        if action is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        if action == "delete":
            if not confirm(TXT_FW_EDITOR_DELETE_CONFIRM.format(
                name=rule.name or rule.rule_id
            )):
                return onSelReturn().errRet(TXT_FW_CANCELLED)
            try:
                return _save(self, delete_rule(cfg, rule.rule_id))
            except FirewallConfigError as exc:
                return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        if action == "toggle":
            try:
                return _save(
                    self,
                    replace_rule(cfg, replace(rule, enabled=not rule.enabled)),
                )
            except FirewallConfigError as exc:
                return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

        edited = _edit_ban(self.minMenuWidth, server, rule)
        if edited is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        if not _confirm_ban(server, edited, self.minMenuWidth):
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            return _save(self, replace_rule(cfg, edited))
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

    def edit_server(self, selItem: c_menu_item) -> onSelReturn:
        try:
            cfg = load_config()
            current = vpn_server(cfg, self.server_id)
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        edited = _edit_server(self.minMenuWidth, current)
        if edited is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        if not _confirm_server(edited, self.minMenuWidth):
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            return _save(self, replace_vpn_server(cfg, edited))
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

    def delete_server(self, selItem: c_menu_item) -> onSelReturn:
        try:
            cfg = load_config()
            server = vpn_server(cfg, self.server_id)
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        if not confirm(TXT_FW_VPN_SERVER_DELETE_CONFIRM.format(name=server.name)):
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            return _save(self, delete_vpn_server(cfg, self.server_id))
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
