"""Interactive local Firewall Manager rule editor using JBLibs c_menu/input."""
from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any
import re

from .lng.default import *
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu, c_menu_block_items, c_menu_item, c_menu_title_label, onSelReturn, printBlock
from libs.JBLibs.input import confirm, get_input, select, select_item
from libs.JBLibs.term import en_color, text_color

from .config import (
    FirewallConfig, FirewallConfigError, FirewallRule, append_rule, config_path,
    delete_rule, load_config, new_rule_id, normalize_config, normalize_rule,
    replace_rule, save_config, normalize_port_spec,
)
from .hub_sync import sync_local_rules_best_effort


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
    rgx: Any = None,
) -> str | None:
    note = ""
    if current not in (None, ""):
        note = TXT_FW_EDITOR_CURRENT.format(value=current)
        if not required:
            note += "\n" + TXT_FW_EDITOR_CLEAR
    value = get_input(
        message,
        accept_empty=(not required or current not in (None, "")),
        maxLen=max_len,
        rgx=rgx,
        titleNote=note,
        minMessageWidth=width,
    )
    if value is None:
        return None
    if not required and value == "-":
        return ""
    if value == "" and current not in (None, ""):
        return str(current)
    return value


def _color_direction(value: str) -> str:
    return text_color(value.upper(), {
        "input": en_color.RED, "output": en_color.GREEN,
        "forward": en_color.YELLOW,
    }.get(value, en_color.WHITE))


def _color_action(value: str) -> str:
    return text_color(("DROP" if value == "deny" else value.upper()), {
        "allow": en_color.GREEN, "deny": en_color.YELLOW,
        "reject": en_color.RED,
    }.get(value, en_color.WHITE))


def _color_protocol(value: str) -> str:
    return text_color(value.upper(), {
        "tcp": en_color.GREEN, "udp": en_color.BLUE,
    }.get(value, en_color.WHITE))


def _rule_label(rule: FirewallRule) -> str:
    state = TXT_FW_EDITOR_ENABLED if rule.enabled else TXT_FW_EDITOR_DISABLED
    if rule.kind == "vpn_ban":
        until = f" -> {rule.ban_to}" if rule.ban_to else ""
        return f"[{state}] VPN BAN: {rule.name or rule.source} ({rule.source}{until})"
    source = rule.source or "*"
    destination = rule.destination or "*"
    if rule.destination_invert:
        destination = "!" + destination
    ports = ""
    if rule.src_ports:
        ports += f" src:{rule.src_ports}"
    if rule.dst_ports:
        ports += f" dst:{rule.dst_ports}"
    return (f"[{state}] {rule.name or 'rule'}: "
            f"{_color_action(rule.action)} {_color_direction(rule.direction)} "
            f"{_color_protocol(rule.protocol)} {source} -> {destination}{ports}")


def _confirm_rule(rule: FirewallRule) -> bool:
    summary = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
    summary.append((TXT_FW_EDITOR_NAME.rstrip(":"), rule.name))
    summary.append((TXT_FW_EDITOR_ADD_TYPE, rule.kind))
    summary.append((TXT_FW_EDITOR_ENABLED if rule.enabled else TXT_FW_EDITOR_DISABLED, ""))
    if rule.kind == "vpn_ban":
        summary.append((TXT_FW_EDITOR_SOURCE.rstrip(":"), rule.source))
        summary.append((TXT_FW_EDITOR_BAN_TO.rstrip(":"), rule.ban_to or "-"))
    else:
        summary.append((TXT_FW_EDITOR_DIRECTION, _color_direction(rule.direction)))
        summary.append((TXT_FW_EDITOR_ACTION, _color_action(rule.action)))
        summary.append((TXT_FW_EDITOR_PROTOCOL, _color_protocol(rule.protocol)))
        summary.append((TXT_FW_EDITOR_SOURCE_OPTIONAL.rstrip(":"), rule.source or "*"))
        summary.append((TXT_FW_EDITOR_DEST_OPTIONAL.rstrip(":"), ("!" if rule.destination_invert else "") + (rule.destination or "*")))
        summary.append((TXT_FW_EDITOR_SRC_PORTS, rule.src_ports or "*"))
        summary.append((TXT_FW_EDITOR_DST_PORTS, rule.dst_ports or "*"))
        summary.append((TXT_FW_EDITOR_INTERFACE_OPTIONAL.rstrip(":"), rule.interface or "*"))
    printBlock(summary, c_menu_block_items(), min_width=78)
    return confirm(TXT_FW_EDITOR_CONFIRM_SAVE)


_PORT_INPUT_RE = re.compile(r"^-$|^$|^[0-9]{1,5}(?:-[0-9]{1,5})?(?:,[0-9]{1,5}(?:-[0-9]{1,5})?)*$")


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
            c_menu_title_label("-" * 30),
            c_menu_item(TXT_FW_EDITOR_ADD, "a", self.add_rule),
            c_menu_title_label("-" * 30),
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
        sync_local_rules_best_effort()
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
        if not _confirm_rule(rule):
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
        if not _confirm_rule(edited):
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

        src_ports = dst_ports = ""
        if protocol in {"tcp", "udp"}:
            src_ports = _prompt(
                TXT_FW_EDITOR_SRC_PORTS, width=self.minMenuWidth,
                current=current.src_ports if current else "",
                rgx=_PORT_INPUT_RE, max_len=1024,
            )
            if src_ports is None:
                return None
            dst_ports = _prompt(
                TXT_FW_EDITOR_DST_PORTS, width=self.minMenuWidth,
                current=current.dst_ports if current else "",
                rgx=_PORT_INPUT_RE, max_len=1024,
            )
            if dst_ports is None:
                return None
            try:
                src_ports = normalize_port_spec(src_ports, "source ports")
                dst_ports = normalize_port_spec(dst_ports, "destination ports")
            except FirewallConfigError as exc:
                self.msg = TXT_FW_FAIL.format(reason=str(exc))
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
            protocol=protocol, src_ports=src_ports, dst_ports=dst_ports,
            interface=interface,
        )
        try:
            return normalize_rule(rule)
        except FirewallConfigError as exc:
            self.msg = TXT_FW_FAIL.format(reason=str(exc))
            return None
