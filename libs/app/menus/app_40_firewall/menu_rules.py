"""Interactive local standard Firewall Manager rule editor."""
from __future__ import annotations

from dataclasses import replace

from .lng.default import *
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import (
    c_menu,
    c_menu_block_items,
    c_menu_item,
    c_menu_title_label,
    onSelReturn,
)
from libs.JBLibs.input import confirm
from libs.JBLibs.term import en_color, text_color

from .config import (
    FirewallConfig,
    FirewallConfigError,
    FirewallRule,
    append_rule,
    config_path,
    delete_rule,
    load_config,
    new_rule_id,
    normalize_port_spec,
    normalize_rule,
    replace_rule,
    save_config,
)
from .hub_sync import sync_local_rules_best_effort
from .menu_helpers import (
    _PORT_INPUT_RE,
    color_action,
    color_direction,
    color_protocol,
    pick,
    pick_interface,
    prompt,
    render_progress,
)
from .menu_vpn import VpnServersMenu

def _rule_label(rule: FirewallRule, cfg: FirewallConfig) -> str:
    state = TXT_FW_EDITOR_ENABLED if rule.enabled else TXT_FW_EDITOR_DISABLED
    source = rule.source or "*"
    destination = rule.destination or "*"
    if rule.destination_invert:
        destination = "!" + destination
    ports = ""
    if rule.src_ports:
        ports += f" src:{rule.src_ports}"
    if rule.dst_ports:
        ports += f" dst:{rule.dst_ports}"
    vpn = ""
    if rule.vpn_server_id:
        server = next(
            (
                item for item in cfg.vpn_servers
                if item.server_id == rule.vpn_server_id
            ),
            None,
        )
        vpn = f" [VPN:{server.name}]" if server is not None else " [VPN:?]"
    return (
        f"[{state}] {rule.name or 'rule'}: "
        f"{color_action(rule.action)} {color_direction(rule.direction)} "
        f"{color_protocol(rule.protocol)} {source} -> {destination}{ports}{vpn}"
    )


def _rule_context(rule: FirewallRule) -> dict[str, str]:
    return {
        TXT_FW_EDITOR_NAME.rstrip(":"): rule.name,
        TXT_FW_EDITOR_DIRECTION: color_direction(rule.direction),
        TXT_FW_EDITOR_ACTION: color_action(rule.action),
        TXT_FW_EDITOR_PROTOCOL: color_protocol(rule.protocol),
        TXT_FW_EDITOR_SOURCE_OPTIONAL.rstrip(":"): rule.source or "*",
        TXT_FW_EDITOR_DEST_OPTIONAL.rstrip(":"):
            ("!" if rule.destination_invert else "") + (rule.destination or "*"),
        TXT_FW_EDITOR_SRC_PORTS: rule.src_ports or "*",
        TXT_FW_EDITOR_DST_PORTS: rule.dst_ports or "*",
        TXT_FW_EDITOR_INTERFACE_OPTIONAL.rstrip(":"): rule.interface or "*",
    }


def _confirm_rule(rule: FirewallRule, width: int) -> bool:
    width = max(
        width,
        render_progress(TXT_FW_STANDARD_FORM, _rule_context(rule), width),
    )
    return confirm(TXT_FW_EDITOR_CONFIRM_SAVE, minMessageWidth=width)

class FirewallRulesMenu(c_menu):
    ESC_is_quit = True
    minMenuWidth = 78

    def onShowMenu(self) -> None:
        try:
            cfg = load_config()
            standard_rules = [
                rule for rule in cfg.rules if rule.kind == "standard"
            ]
            bans = sum(1 for rule in cfg.rules if rule.kind == "vpn_ban")
            self.subTitle = c_menu_block_items([
                (TXT_FW_EDITOR_CONFIG, str(config_path(create_dir=False))),
                (TXT_FW_STANDARD_COUNT, str(len(standard_rules))),
                (TXT_FW_VPN_SERVER_COUNT, str(len(cfg.vpn_servers))),
                (TXT_FW_VPN_BAN_COUNT, str(bans)),
            ])
        except FirewallConfigError as exc:
            cfg = FirewallConfig()
            standard_rules = []
            self.subTitle = c_menu_block_items([
                (TXT_FW_EDITOR_CONFIG, str(config_path(create_dir=False))),
            ])
            self.msg = TXT_FW_FAIL.format(reason=str(exc))

        self.menu = [
            c_menu_title_label(TXT_FW_STANDARD_SECTION),
            c_menu_item(
                text_color(TXT_FW_STANDARD_ADD, en_color.BRIGHT_CYAN),
                "a",
                self.add_rule,
            ),
        ]
        for idx, rule in enumerate(standard_rules, 1):
            self.menu.append(c_menu_item(
                _rule_label(rule, cfg),
                str(idx),
                self.rule_action,
                data=rule.rule_id,
            ))

        self.menu.extend([
            c_menu_title_label(TXT_FW_VPN_BAN_SECTION),
            c_menu_item(
                text_color(TXT_FW_VPN_EDIT, en_color.BRIGHT_CYAN),
                "v",
                VpnServersMenu(),
            ),
        ])

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

    def add_rule(self, selItem: c_menu_item) -> onSelReturn:
        try:
            cfg = self._load()
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        rule = self._edit_standard(None)
        if rule is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        if not _confirm_rule(rule, self.minMenuWidth):
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            return self._save(append_rule(cfg, rule))
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

    def rule_action(self, selItem: c_menu_item) -> onSelReturn:
        rule_id = str(selItem.data or "")
        try:
            cfg = self._load()
            rule = next(
                item for item in cfg.rules
                if item.rule_id == rule_id and item.kind == "standard"
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
            title=TXT_FW_STANDARD_FORM,
            context=_rule_context(rule),
        )
        if action is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        if action == "delete":
            if not confirm(TXT_FW_EDITOR_DELETE_CONFIRM.format(
                name=rule.name or rule.rule_id
            )):
                return onSelReturn().errRet(TXT_FW_CANCELLED)
            try:
                return self._save(delete_rule(cfg, rule.rule_id))
            except FirewallConfigError as exc:
                return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))
        if action == "toggle":
            try:
                return self._save(
                    replace_rule(cfg, replace(rule, enabled=not rule.enabled))
                )
            except FirewallConfigError as exc:
                return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

        edited = self._edit_standard(rule)
        if edited is None:
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        if not _confirm_rule(edited, self.minMenuWidth):
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            return self._save(replace_rule(cfg, edited))
        except FirewallConfigError as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

    def _edit_standard(self, current: FirewallRule | None) -> FirewallRule | None:
        context: dict[str, str] = {}
        name = prompt(
            TXT_FW_EDITOR_NAME,
            width=self.minMenuWidth,
            current=current.name if current else "",
            required=True,
            title=TXT_FW_STANDARD_FORM,
            context=context,
        )
        if name is None:
            return None
        context[TXT_FW_EDITOR_NAME.rstrip(":")] = name

        direction = pick(
            TXT_FW_EDITOR_DIRECTION,
            [
                ("i", text_color(TXT_FW_EDITOR_DIR_INPUT, en_color.RED), "input"),
                ("f", text_color(TXT_FW_EDITOR_DIR_FORWARD, en_color.YELLOW), "forward"),
                ("o", text_color(TXT_FW_EDITOR_DIR_OUTPUT, en_color.GREEN), "output"),
            ],
            self.minMenuWidth,
            title=TXT_FW_STANDARD_FORM,
            context=context,
        )
        if direction is None:
            return None
        context[TXT_FW_EDITOR_DIRECTION] = color_direction(direction)

        action = pick(
            TXT_FW_EDITOR_ACTION,
            [
                ("a", text_color(TXT_FW_EDITOR_ACTION_ALLOW, en_color.GREEN), "allow"),
                ("d", text_color(TXT_FW_EDITOR_ACTION_DENY, en_color.YELLOW), "deny"),
                ("r", text_color(TXT_FW_EDITOR_ACTION_REJECT, en_color.RED), "reject"),
            ],
            self.minMenuWidth,
            title=TXT_FW_STANDARD_FORM,
            context=context,
        )
        if action is None:
            return None
        context[TXT_FW_EDITOR_ACTION] = color_action(action)

        protocol = pick(
            TXT_FW_EDITOR_PROTOCOL,
            [
                ("a", TXT_FW_EDITOR_PROTO_ANY, "any"),
                ("t", text_color("TCP", en_color.GREEN), "tcp"),
                ("u", text_color("UDP", en_color.BLUE), "udp"),
                ("i", "ICMP", "icmp"),
            ],
            self.minMenuWidth,
            title=TXT_FW_STANDARD_FORM,
            context=context,
        )
        if protocol is None:
            return None
        context[TXT_FW_EDITOR_PROTOCOL] = color_protocol(protocol)

        source = prompt(
            TXT_FW_EDITOR_SOURCE_OPTIONAL,
            width=self.minMenuWidth,
            current=current.source if current else "",
            required=False,
            max_len=64,
            title=TXT_FW_STANDARD_FORM,
            context=context,
        )
        if source is None:
            return None
        context[TXT_FW_EDITOR_SOURCE_OPTIONAL.rstrip(":")] = source or "*"

        destination = prompt(
            TXT_FW_EDITOR_DEST_OPTIONAL,
            width=self.minMenuWidth,
            current=current.destination if current else "",
            required=False,
            max_len=64,
            title=TXT_FW_STANDARD_FORM,
            context=context,
        )
        if destination is None:
            return None
        context[TXT_FW_EDITOR_DEST_OPTIONAL.rstrip(":")] = destination or "*"

        invert = False
        if destination:
            choice = pick(
                TXT_FW_EDITOR_DEST_MODE,
                [
                    ("n", TXT_FW_EDITOR_DEST_NORMAL, False),
                    ("x", TXT_FW_EDITOR_DEST_INVERT, True),
                ],
                self.minMenuWidth,
                title=TXT_FW_STANDARD_FORM,
                context=context,
            )
            if choice is None:
                return None
            invert = bool(choice)
            context[TXT_FW_EDITOR_DEST_MODE] = (
                TXT_FW_EDITOR_DEST_INVERT
                if invert else TXT_FW_EDITOR_DEST_NORMAL
            )

        src_ports = dst_ports = ""
        if protocol in {"tcp", "udp"}:
            src_ports = prompt(
                TXT_FW_EDITOR_SRC_PORTS,
                width=self.minMenuWidth,
                current=current.src_ports if current else "",
                rgx=_PORT_INPUT_RE,
                max_len=1024,
                title=TXT_FW_STANDARD_FORM,
                context=context,
            )
            if src_ports is None:
                return None
            try:
                src_ports = normalize_port_spec(src_ports, "source ports")
            except FirewallConfigError as exc:
                self.msg = TXT_FW_FAIL.format(reason=str(exc))
                return None
            context[TXT_FW_EDITOR_SRC_PORTS] = src_ports or "*"

            dst_ports = prompt(
                TXT_FW_EDITOR_DST_PORTS,
                width=self.minMenuWidth,
                current=current.dst_ports if current else "",
                rgx=_PORT_INPUT_RE,
                max_len=1024,
                title=TXT_FW_STANDARD_FORM,
                context=context,
            )
            if dst_ports is None:
                return None
            try:
                dst_ports = normalize_port_spec(dst_ports, "destination ports")
            except FirewallConfigError as exc:
                self.msg = TXT_FW_FAIL.format(reason=str(exc))
                return None
            context[TXT_FW_EDITOR_DST_PORTS] = dst_ports or "*"

        interface = pick_interface(
            width=self.minMenuWidth,
            context=context,
            current=current.interface if current else "",
            allow_any=True,
            title=TXT_FW_STANDARD_FORM,
        )
        if interface is None:
            return None
        context[TXT_FW_EDITOR_INTERFACE_OPTIONAL.rstrip(":")] = interface or "*"

        try:
            return normalize_rule(FirewallRule(
                rule_id=current.rule_id if current else new_rule_id(),
                kind="standard",
                enabled=current.enabled if current else True,
                name=name,
                source=source,
                destination=destination,
                destination_invert=invert,
                direction=direction,
                action=action,
                protocol=protocol,
                src_ports=src_ports,
                dst_ports=dst_ports,
                interface=interface,
                vpn_server_id=current.vpn_server_id if current else "",
            ))
        except FirewallConfigError as exc:
            self.msg = TXT_FW_FAIL.format(reason=str(exc))
            return None
