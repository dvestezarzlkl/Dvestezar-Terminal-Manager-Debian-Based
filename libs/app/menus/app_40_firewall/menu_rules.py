"""Interactive local Firewall Manager rule editor using JBLibs c_menu/input."""
from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from .lng.default import *
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu, c_menu_block_items, c_menu_item, c_menu_title_label, onSelReturn
from libs.JBLibs.input import confirm, get_input, select, select_item

from .config import (
    FirewallConfig, FirewallConfigError, FirewallRule, append_rule, config_path,
    delete_rule, load_config, new_rule_id, normalize_config, normalize_rule,
    replace_rule, save_config,
)


def _pick(message: str, options: list[tuple[str, str, Any]], width: int) -> Any | None:
    result = select(
        message,
        [select_item(label, key, data) for key, label, data in options],
        width,
    )
    if not result or result.item is None:
        return None
    return result.item.data


def _prompt(
    message: str,
    *,
    width: int,
    current: str | int | None = None,
    required: bool = False,
    max_len: int = 255,
) -> str | None:
    note = ""
    if current not in (None, ""):
        note = TXT_FW_EDITOR_CURRENT.format(value=current)
    value = get_input(
        message,
        accept_empty=(not required or current not in (None, "")),
        maxLen=max_len,
        titleNote=note,
        minMessageWidth=width,
    )
    if value is None:
        return None
    if value == "" and current not in (None, ""):
        return str(current)
    return value


def _rule_label(rule: FirewallRule) -> str:
    state = TXT_FW_EDITOR_ENABLED if rule.enabled else TXT_FW_EDITOR_DISABLED
    if rule.kind == "vpn_ban":
        until = f" -> {rule.ban_to}" if rule.ban_to else ""
        return f"[{state}] VPN BAN: {rule.name or rule.source} ({rule.source}{until})"
    port = ""
    if rule.port_from is not None:
        port = f":{rule.port_from}" if rule.port_from == rule.port_to else (
            f":{rule.port_from}-{rule.port_to}"
        )
    source = rule.source or "*"
    destination = rule.destination or "*"
    if rule.destination_invert:
        destination = "!" + destination
    return (
        f"[{state}] {rule.name or 'rule'}: {rule.action.upper()} "
        f"{rule.direction} {rule.protocol} {source} -> {destination}{port}"
    )


class FirewallRulesMenu(c_menu):
    ESC_is_quit = True
    minMenuWidth = 78

    def onShowMenu(self) -> None:
        try:
            cfg = load_config()
            self.subTitle = c_menu_block_items([
                (TXT_FW_EDITOR_CONFIG, str(config_path(create_dir=False))),
                (TXT_FW_EDITOR_COUNT, str(len(cfg.rules))),
            ])
            rules = list(cfg.rules)
        except FirewallConfigError as exc:
            self.subTitle = c_menu_block_items([
                (TXT_FW_EDITOR_CONFIG, str(config_path(create_dir=False))),
            ])
            rules = []
            self.msg = TXT_FW_FAIL.format(reason=str(exc))
        self.menu = [
            c_menu_title_label(TXT_FW_EDITOR_TITLE),
            c_menu_item(TXT_FW_EDITOR_ADD, "a", self.add_rule),
        ]
        for idx, rule in enumerate(rules, 1):
            self.menu.append(
                c_menu_item(_rule_label(rule), str(idx), self.rule_action, data=rule.rule_id)
            )

    def _load(self) -> FirewallConfig:
        return load_config()

    def _save(self, cfg: FirewallConfig) -> onSelReturn:
        try:
            path = save_config(cfg)
        except (OSError, FirewallConfigError) as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        self.menuRecycle = True
        return onSelReturn(ok=TXT_FW_EDITOR_SAVED.format(path=path))

    def _ensure_openvpn(self, cfg: FirewallConfig) -> FirewallConfig | None:
        name = _prompt(
            TXT_FW_EDITOR_VPN_NAME, width=self.minMenuWidth,
            current=cfg.openvpn_server_name, required=True,
        )
        if name is None:
            return None
        ip = _prompt(
            TXT_FW_EDITOR_VPN_IP, width=self.minMenuWidth,
            current=cfg.openvpn_server_ip, required=True, max_len=64,
        )
        if ip is None:
            return None
        mask = _prompt(
            TXT_FW_EDITOR_VPN_MASK, width=self.minMenuWidth,
            current=cfg.openvpn_server_mask if cfg.openvpn_server_mask is not None else 23,
            required=True, max_len=2,
        )
        if mask is None:
            return None
        interface = _prompt(
            TXT_FW_EDITOR_INTERFACE, width=self.minMenuWidth,
            current=cfg.openvpn_interface or "tun+", required=True, max_len=15,
        )
        if interface is None:
            return None
        try:
            return normalize_config({
                **asdict(cfg),
                "openvpn_server_name": name,
                "openvpn_server_ip": ip,
                "openvpn_server_mask": int(mask),
                "openvpn_interface": interface,
            })
        except (ValueError, FirewallConfigError) as exc:
            self.msg = TXT_FW_FAIL.format(reason=str(exc))
            return None

    def add_rule(self, selItem: c_menu_item) -> onSelReturn:
        kind = _pick(
            TXT_FW_EDITOR_ADD_TYPE,
            [
                ("b", TXT_FW_EDITOR_TYPE_VPN_BAN, "vpn_ban"),
                ("s", TXT_FW_EDITOR_TYPE_STANDARD, "standard"),
            ],
            self.minMenuWidth,
        )
        if kind is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            cfg = self._load()
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        if kind == "vpn_ban":
            cfg = self._ensure_openvpn(cfg)
            if cfg is None:
                return onSelReturn().errRet(TXT_FW_CANCELLED)
            rule = self._edit_vpn_ban(None)
        else:
            rule = self._edit_standard(None)
        if rule is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            return self._save(append_rule(cfg, rule))
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

    def rule_action(self, selItem: c_menu_item) -> onSelReturn:
        rule_id = str(selItem.data or "")
        try:
            cfg = self._load()
            rule = next(item for item in cfg.rules if item.rule_id == rule_id)
        except (FirewallConfigError, StopIteration) as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

        action = _pick(
            TXT_FW_EDITOR_RULE_ACTION,
            [
                ("e", TXT_FW_EDITOR_EDIT, "edit"),
                ("t", TXT_FW_EDITOR_TOGGLE, "toggle"),
                ("d", TXT_FW_EDITOR_DELETE, "delete"),
            ],
            self.minMenuWidth,
        )
        if action is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        if action == "delete":
            if not confirm(TXT_FW_EDITOR_DELETE_CONFIRM.format(name=rule.name or rule.rule_id)):
                return onSelReturn().errRet(TXT_FW_CANCELLED)
            try:
                return self._save(delete_rule(cfg, rule.rule_id))
            except FirewallConfigError as exc:
                return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        if action == "toggle":
            try:
                return self._save(replace_rule(cfg, replace(rule, enabled=not rule.enabled)))
            except FirewallConfigError as exc:
                return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

        edited = (
            self._edit_vpn_ban(rule)
            if rule.kind == "vpn_ban"
            else self._edit_standard(rule)
        )
        if edited is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            return self._save(replace_rule(cfg, edited))
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

    def _edit_vpn_ban(self, current: FirewallRule | None) -> FirewallRule | None:
        name = _prompt(
            TXT_FW_EDITOR_NAME, width=self.minMenuWidth,
            current=current.name if current else "", required=True,
        )
        if name is None:
            return None
        source = _prompt(
            TXT_FW_EDITOR_SOURCE, width=self.minMenuWidth,
            current=current.source if current else "", required=True, max_len=64,
        )
        if source is None:
            return None
        ban_to = _prompt(
            TXT_FW_EDITOR_BAN_TO, width=self.minMenuWidth,
            current=current.ban_to if current else "", required=False, max_len=10,
        )
        if ban_to is None:
            return None
        rule = FirewallRule(
            rule_id=current.rule_id if current else new_rule_id(),
            kind="vpn_ban",
            enabled=current.enabled if current else True,
            name=name, source=source, ban_to=ban_to,
        )
        try:
            return normalize_rule(rule)
        except FirewallConfigError as exc:
            self.msg = TXT_FW_FAIL.format(reason=str(exc))
            return None

    def _edit_standard(self, current: FirewallRule | None) -> FirewallRule | None:
        name = _prompt(
            TXT_FW_EDITOR_NAME, width=self.minMenuWidth,
            current=current.name if current else "", required=True,
        )
        if name is None:
            return None
        direction = _pick(
            TXT_FW_EDITOR_DIRECTION,
            [
                ("i", TXT_FW_EDITOR_DIR_INPUT, "input"),
                ("f", TXT_FW_EDITOR_DIR_FORWARD, "forward"),
                ("o", TXT_FW_EDITOR_DIR_OUTPUT, "output"),
            ],
            self.minMenuWidth,
        )
        if direction is None:
            return None
        action = _pick(
            TXT_FW_EDITOR_ACTION,
            [
                ("a", TXT_FW_EDITOR_ACTION_ALLOW, "allow"),
                ("d", TXT_FW_EDITOR_ACTION_DENY, "deny"),
                ("r", TXT_FW_EDITOR_ACTION_REJECT, "reject"),
            ],
            self.minMenuWidth,
        )
        if action is None:
            return None
        protocol = _pick(
            TXT_FW_EDITOR_PROTOCOL,
            [
                ("a", TXT_FW_EDITOR_PROTO_ANY, "any"),
                ("t", "TCP", "tcp"),
                ("u", "UDP", "udp"),
                ("i", "ICMP", "icmp"),
            ],
            self.minMenuWidth,
        )
        if protocol is None:
            return None
        source = _prompt(
            TXT_FW_EDITOR_SOURCE_OPTIONAL, width=self.minMenuWidth,
            current=current.source if current else "", required=False, max_len=64,
        )
        if source is None:
            return None
        destination = _prompt(
            TXT_FW_EDITOR_DEST_OPTIONAL, width=self.minMenuWidth,
            current=current.destination if current else "", required=False, max_len=64,
        )
        if destination is None:
            return None
        invert = False
        if destination:
            choice = _pick(
                TXT_FW_EDITOR_DEST_MODE,
                [
                    ("n", TXT_FW_EDITOR_DEST_NORMAL, False),
                    ("x", TXT_FW_EDITOR_DEST_INVERT, True),
                ],
                self.minMenuWidth,
            )
            if choice is None:
                return None
            invert = bool(choice)

        port_from = port_to = None
        if protocol in {"tcp", "udp"}:
            p_from = _prompt(
                TXT_FW_EDITOR_PORT_FROM, width=self.minMenuWidth,
                current=current.port_from if current else "", required=False, max_len=5,
            )
            if p_from is None:
                return None
            if p_from:
                p_to = _prompt(
                    TXT_FW_EDITOR_PORT_TO, width=self.minMenuWidth,
                    current=current.port_to if current else p_from, required=True, max_len=5,
                )
                if p_to is None:
                    return None
                try:
                    port_from, port_to = int(p_from), int(p_to)
                except ValueError:
                    self.msg = TXT_FW_FAIL.format(reason=TXT_FW_EDITOR_INVALID_PORT)
                    return None

        interface = _prompt(
            TXT_FW_EDITOR_INTERFACE_OPTIONAL, width=self.minMenuWidth,
            current=current.interface if current else "", required=False, max_len=15,
        )
        if interface is None:
            return None

        rule = FirewallRule(
            rule_id=current.rule_id if current else new_rule_id(),
            kind="standard",
            enabled=current.enabled if current else True,
            name=name, source=source, destination=destination,
            destination_invert=invert, direction=direction, action=action,
            protocol=protocol, port_from=port_from, port_to=port_to,
            interface=interface,
        )
        try:
            return normalize_rule(rule)
        except FirewallConfigError as exc:
            self.msg = TXT_FW_FAIL.format(reason=str(exc))
            return None
