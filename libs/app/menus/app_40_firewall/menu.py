"""Firewall Manager UI: desired-state editor, preview and guarded manual UFW Apply."""
from __future__ import annotations

from math import ceil
from pathlib import Path
import re
import shlex
from time import time

from .lng.default import *
from libs.JBLibs.helper import loadLng, sleep_ms
loadLng()

from libs.app import cfg as app_cfg

from libs.JBLibs.c_menu import (
    c_menu, c_menu_block_items, c_menu_item, c_menu_title_label, onSelReturn,
)
from libs.JBLibs.input import anyKey, confirm, get_input, select, select_item, selectFile
from libs.JBLibs.term import clearRow, en_color, savePos, text_color

from .ack import is_pending_acknowledged
from .apply import (
    ApplyPaths,
    FirewallApplyError,
    add_native_ufw_rule,
    apply_local_config,
    delete_numbered_ufw_rule,
    diagnose_ufw_port,
    disable_ufw,
    list_numbered_ufw_rules,
    ufw_app_info,
    ufw_app_list,
    ufw_version,
)
from .compiler import (
    CandidateResult,
    CompiledFirewall,
    build_candidate,
    compile_firewall,
)
from .config import (
    FirewallConfig, FirewallConfigError, config_path,
    import_legacy, load_config, merge_config, save_config,
)
from .hub_provider import HUB_PROVIDER_KEY, hub_collect, inspect_ufw_service
from .hub_sync import sync_local_rules_best_effort
from .menu_rules import FirewallRulesMenu
from .policy import FirewallPolicyError, inspect_before_rules
from .ufw_console import (
    UfwAddPort,
    UfwAddService,
    UfwConsoleError,
    build_ufw_add_args,
    parse_console_command,
)

_MENU_NAME_ = TXT_FW_MENU
_HUB_PROVIDER_KEY_ = HUB_PROVIDER_KEY
_BEFORE_RULES = Path("/etc/ufw/before.rules")
_BEFORE6_RULES = Path("/etc/ufw/before6.rules")


class menu(c_menu):
    _VERSION_ = "0.8.0"
    ESC_is_quit = True
    minMenuWidth = 78

    def onShowMenu(self) -> None:
        title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        title.append((_MENU_NAME_, "c"))
        title.append("-")
        title.append((TXT_FW_VERSION, self._VERSION_))
        title.append((TXT_FW_FILE, str(_BEFORE_RULES)))
        if _BEFORE6_RULES.exists():
            title.append((TXT_FW_FILE6, str(_BEFORE6_RULES)))
        title.append((TXT_FW_LOCAL_CONFIG, str(config_path(create_dir=False))))
        self.title = title

        service = inspect_ufw_service()
        if not service.detected:
            self.menu = [
                c_menu_item(
                    text_color(TXT_FW_NOT_INSTALLED, en_color.BRIGHT_BLACK),
                    enabled=False,
                ),
            ]
            return
        if service.status == "inactive":
            self.menu = [
                c_menu_item(
                    text_color(TXT_FW_ACTIVATE, en_color.BRIGHT_RED),
                    "a",
                    self.apply_rules,
                ),
            ]
            return
        if service.status != "active":
            self.menu = [
                c_menu_item(
                    text_color(TXT_FW_UNKNOWN_STATUS, en_color.BRIGHT_RED),
                    enabled=False,
                ),
            ]
            return

        self.menu = [
            c_menu_title_label(
                text_color(TXT_FW_SECTION_MANAGE, en_color.BRIGHT_CYAN)
            ),
            c_menu_item(
                text_color(TXT_FW_EDIT_RULES, en_color.BRIGHT_CYAN),
                "e",
                FirewallRulesMenu(),
            ),
            c_menu_title_label(
                text_color(TXT_FW_RUNTIME_SECTION, en_color.BRIGHT_YELLOW)
            ),
            c_menu_item(
                text_color(TXT_FW_APPLY, en_color.BRIGHT_YELLOW),
                "a",
                self.apply_rules,
            ),
            c_menu_item(
                text_color(TXT_FW_DISABLE, en_color.BRIGHT_RED),
                "d",
                self.disable_runtime,
            ),
            c_menu_item(
                TXT_FW_NATIVE_RULES,
                "u",
                self.manage_native_ufw_rules,
            ),
            c_menu_title_label(TXT_FW_SECTION_INSPECT),
            c_menu_item(TXT_FW_INSPECT, "i", self.inspect_rules),
            c_menu_item(TXT_FW_STATUS, "s", self.inspect_status),
            c_menu_item(TXT_FW_PREVIEW, "p", self.preview_local_config),
            c_menu_title_label(TXT_FW_SECTION_IMPORT),
            c_menu_item(TXT_FW_IMPORT_LEGACY, "l", self.import_legacy_config),
        ]

    def _acknowledge_live_apply(self, token: str, expires_at: float) -> bool:
        initial_seconds = max(0, ceil(expires_at - time()))
        print(TXT_FW_APPLY_ACK.format(token=token, seconds=initial_seconds))
        last_remaining: int | None = None
        savePos()
        while True:
            if is_pending_acknowledged(
                token,
                path=ApplyPaths().pending_ack,
            ):
                clearRow(1)
                print(TXT_FW_APPLY_ACK_RECEIVED)
                return True

            remaining = max(0, ceil(expires_at - time()))
            if remaining <= 0:
                clearRow(1)
                print(TXT_FW_APPLY_ACK_TIMEOUT)
                return False

            if remaining != last_remaining:
                clearRow(1)
                print(
                    TXT_FW_APPLY_ACK_WAIT.format(seconds=remaining),
                    end="",
                    flush=True,
                )
                last_remaining = remaining
            sleep_ms(100)

    def _build_preview(
        self,
    ) -> tuple[
        FirewallConfig,
        CompiledFirewall,
        CandidateResult,
        CandidateResult | None,
    ]:
        cfg = load_config()
        compiled = compile_firewall(cfg)
        result4 = build_candidate(
            _BEFORE_RULES.read_text(encoding="utf-8"),
            compiled.ipv4,
            allow_openvpn=True,
        )
        result6: CandidateResult | None = None
        if _BEFORE6_RULES.is_file():
            result6 = build_candidate(
                _BEFORE6_RULES.read_text(encoding="utf-8"),
                compiled.ipv6,
                allow_openvpn=False,
            )
        elif compiled.explicit_ipv6:
            raise FirewallPolicyError(
                "IPv6 rule exists but before6.rules is unavailable."
            )
        return cfg, compiled, result4, result6

    def _print_preview(
        self,
        compiled: CompiledFirewall,
        result4: CandidateResult,
        result6: CandidateResult | None,
    ) -> None:
        print(TXT_FW_PREVIEW_FAMILY.format(
            family="IPv4",
            status="CHANGED" if result4.changed else "NO_CHANGE",
            current=result4.current_rules,
            desired=result4.desired_rules,
        ))
        if result6 is not None:
            print(TXT_FW_PREVIEW_FAMILY.format(
                family="IPv6",
                status="CHANGED" if result6.changed else "NO_CHANGE",
                current=result6.current_rules,
                desired=result6.desired_rules,
            ))
        if compiled.expired_bans:
            print(TXT_FW_PREVIEW_EXPIRED.format(count=compiled.expired_bans))
        if compiled.next_expiry:
            print(TXT_FW_NEXT_EXPIRY.format(
                day=compiled.next_expiry.isoformat()
            ))
        print(TXT_FW_PREVIEW_SAFE)

    def apply_rules(self, selItem: c_menu_item) -> onSelReturn:
        service = inspect_ufw_service()
        if not service.detected or service.status not in {"active", "inactive"}:
            return onSelReturn().errRet(TXT_FW_APPLY_UNSAFE_STATUS)

        try:
            cfg, compiled, result4, result6 = self._build_preview()
        except (OSError, UnicodeError, FirewallPolicyError, FirewallConfigError) as exc:
            return onSelReturn().errRet(TXT_FW_APPLY_FAIL.format(reason=str(exc)))

        # Even when inactive, keep the menu itself reduced to one activation
        # action, but show the exact read-only candidate before confirmation.
        self._print_preview(compiled, result4, result6)

        changed = result4.changed or bool(result6 and result6.changed)
        if service.status == "active" and not changed:
            return onSelReturn(ok=TXT_FW_APPLY_NO_CHANGE)

        confirm_text = (
            TXT_FW_ACTIVATE_CONFIRM
            if service.status == "inactive"
            else TXT_FW_APPLY_CONFIRM
        )
        if not confirm(confirm_text, minMessageWidth=self.minMenuWidth):
            return onSelReturn().errRet(TXT_FW_CANCELLED)

        try:
            # The configuration the operator confirmed must be exactly the
            # configuration that is applied.
            if load_config() != cfg:
                return onSelReturn().errRet(TXT_FW_APPLY_CONFIG_CHANGED)
            result = apply_local_config(
                cfg,
                acknowledge=self._acknowledge_live_apply,
            )
        except (FirewallConfigError, FirewallPolicyError, FirewallApplyError) as exc:
            return onSelReturn().errRet(TXT_FW_APPLY_FAIL.format(reason=str(exc)))

        self.menuRecycle = True
        if result.status == "NO_CHANGE":
            return onSelReturn(ok=TXT_FW_APPLY_NO_CHANGE)
        if result.status == "ROLLED_BACK":
            return onSelReturn(ok=TXT_FW_APPLY_ROLLED_BACK.format(
                backup=result.backup_dir
            ))
        return onSelReturn(ok=TXT_FW_APPLY_OK.format(
            backup=result.backup_dir
        ))

    def disable_runtime(self, selItem: c_menu_item) -> onSelReturn:
        if not confirm(TXT_FW_DISABLE_CONFIRM, minMessageWidth=self.minMenuWidth):
            return onSelReturn().errRet(TXT_FW_CANCELLED)
        try:
            disable_ufw()
        except FirewallApplyError as exc:
            return onSelReturn().errRet(TXT_FW_APPLY_FAIL.format(reason=str(exc)))
        self.menuRecycle = True
        return onSelReturn(ok=TXT_FW_DISABLE_OK)

    @staticmethod
    def _format_native_rules(rules) -> str:
        if not rules:
            return TXT_FW_NATIVE_RULES_EMPTY
        return "\n".join(
            f"[{rule.number:>2}] {rule.text}" for rule in rules
        )

    @staticmethod
    def _format_port_diagnostics(diag) -> str:
        specs = ", ".join(
            (
                f"{spec.start}/{spec.protocol}"
                if spec.start == spec.end
                else f"{spec.start}:{spec.end}/{spec.protocol}"
            )
            for spec in diag.specs
        ) or "-"
        lines = [
            TXT_FW_CONSOLE_DIAG_QUERY.format(query=diag.query),
            TXT_FW_CONSOLE_DIAG_PORTS.format(ports=specs),
        ]
        if diag.profile_info:
            lines.extend(("", TXT_FW_CONSOLE_DIAG_PROFILE, diag.profile_info))
        lines.extend(("", TXT_FW_CONSOLE_DIAG_LISTEN))
        lines.extend(diag.listeners or ("-",))
        lines.extend(("", TXT_FW_CONSOLE_DIAG_NATIVE))
        lines.extend(
            (f"[{rule.number}] {rule.text}" for rule in diag.native_rules)
            if diag.native_rules else ("-",)
        )
        lines.extend(("", TXT_FW_CONSOLE_DIAG_IPV4))
        lines.extend(diag.ipv4_rules or ("-",))
        lines.extend(("", TXT_FW_CONSOLE_DIAG_IPV6))
        lines.extend(diag.ipv6_rules or ("-",))
        return "\n".join(lines)

    def manage_native_ufw_rules(self, selItem: c_menu_item) -> onSelReturn:
        message = TXT_FW_NATIVE_CONSOLE_READY
        while True:
            try:
                rules = list_numbered_ufw_rules()
            except FirewallApplyError as exc:
                return onSelReturn().errRet(
                    TXT_FW_NATIVE_RULES_FAIL.format(reason=str(exc))
                )

            action = TXT_FW_NATIVE_CONSOLE_PROMPT.format(
                rules=self._format_native_rules(rules),
                message=message,
            )
            raw = get_input(
                action,
                False,
                maxLen=512,
                minMessageWidth=self.minMenuWidth,
            )
            if raw is None:
                return onSelReturn()

            try:
                command = parse_console_command(raw)
            except UfwConsoleError as exc:
                message = TXT_FW_CONSOLE_ERROR.format(reason=str(exc))
                continue

            if command.kind == "help":
                message = TXT_FW_CONSOLE_HELP
                continue
            if command.kind == "list":
                message = TXT_FW_CONSOLE_LIST_REFRESHED
                continue

            try:
                if command.kind == "services":
                    message = ufw_app_list() or TXT_FW_CONSOLE_EMPTY_OUTPUT
                    continue
                if command.kind == "info":
                    message = ufw_app_info(str(command.value)) or TXT_FW_CONSOLE_EMPTY_OUTPUT
                    continue
                if command.kind == "version":
                    message = TXT_FW_CONSOLE_VERSION.format(
                        sysapps=app_cfg.VERSION,
                        firewall=self._VERSION_,
                        ufw=ufw_version() or "-",
                    )
                    continue
                if command.kind == "list-port":
                    message = self._format_port_diagnostics(
                        diagnose_ufw_port(str(command.value))
                    )
                    continue

                if command.kind == "delete":
                    number = int(command.value)
                    rule = next(
                        (item for item in rules if item.number == number),
                        None,
                    )
                    if rule is None:
                        message = TXT_FW_CONSOLE_RULE_NOT_FOUND.format(number=number)
                        continue
                    if not confirm(
                        TXT_FW_NATIVE_RULE_DELETE_CONFIRM.format(
                            number=rule.number,
                            rule=rule.text,
                        ),
                        minMessageWidth=self.minMenuWidth,
                    ):
                        message = TXT_FW_CANCELLED
                        continue
                    delete_result = delete_numbered_ufw_rule(
                        rule,
                        snapshot=rules,
                        acknowledge=self._acknowledge_live_apply,
                    )
                    self.menuRecycle = True
                    if delete_result.status == "ROLLED_BACK":
                        message = TXT_FW_NATIVE_RULE_DELETE_ROLLED_BACK.format(
                            backup=delete_result.backup_dir
                        )
                    else:
                        message = TXT_FW_NATIVE_RULE_DELETED.format(rule=rule.text)
                    continue

                if command.kind in {"add-port", "add-service"}:
                    spec = command.value
                    args = build_ufw_add_args(spec)
                    if isinstance(spec, UfwAddPort):
                        summary = TXT_FW_CONSOLE_ADD_PORT_SUMMARY.format(
                            port=spec.port,
                            proto=spec.protocol,
                            source=spec.source or "*",
                            destination=spec.destination or "*",
                        )
                    elif isinstance(spec, UfwAddService):
                        summary = TXT_FW_CONSOLE_ADD_SERVICE_SUMMARY.format(
                            profile=spec.profile,
                        )
                    else:
                        raise UfwConsoleError("Unsupported add command.")

                    preview = shlex.join(["ufw", *args])
                    if not confirm(
                        TXT_FW_CONSOLE_ADD_CONFIRM.format(
                            summary=summary,
                            command=preview,
                        ),
                        minMessageWidth=self.minMenuWidth,
                    ):
                        message = TXT_FW_CANCELLED
                        continue
                    add_result = add_native_ufw_rule(spec)
                    self.menuRecycle = True
                    if add_result.status == "NO_CHANGE":
                        message = TXT_FW_CONSOLE_ADD_NO_CHANGE.format(
                            output=add_result.output or "-",
                        )
                    else:
                        message = TXT_FW_CONSOLE_ADD_OK.format(
                            output=add_result.output or "-",
                        )
                    continue

                message = TXT_FW_CONSOLE_ERROR.format(reason="Unknown command.")
            except (FirewallApplyError, UfwConsoleError) as exc:
                message = TXT_FW_NATIVE_RULES_FAIL.format(reason=str(exc))

    def import_legacy_config(self, selItem: c_menu_item) -> onSelReturn:
        """Import one legacy VPN policy; merge with an existing v2 config."""
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
            target = config_path(create_dir=False)
            existing = load_config(target) if target.is_file() else FirewallConfig()
            has_existing = bool(existing.rules or existing.vpn_servers)
            if has_existing and not confirm(TXT_FW_IMPORT_MERGE):
                return onSelReturn().errRet(TXT_FW_CANCELLED)

            imported = import_legacy(
                selected,
                None if has_existing else inspection,
            )
            result = merge_config(existing, imported) if has_existing else imported
            saved = save_config(result)
            sync_local_rules_best_effort()
        except (OSError, UnicodeError, FirewallPolicyError, FirewallConfigError) as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

        self.menuRecycle = True
        return onSelReturn(
            ok=TXT_FW_IMPORT_OK.format(
                path=saved,
                count=len(imported.rules),
            )
        )

    def preview_local_config(self, selItem: c_menu_item) -> onSelReturn:
        """Compare local desired state with the exact candidates Apply would use."""
        try:
            _, compiled, result4, result6 = self._build_preview()
        except (OSError, UnicodeError, FirewallPolicyError, FirewallConfigError) as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

        self._print_preview(compiled, result4, result6)
        anyKey()
        return onSelReturn(ok=TXT_FW_PREVIEW_DONE)

    def inspect_status(self, selItem: c_menu_item) -> onSelReturn:
        status = inspect_ufw_service()
        detail = status.status if status.detected else TXT_FW_UNAVAILABLE
        if not status.detected:
            return onSelReturn(ok=text_color(
                f"{TXT_FW_SERVICE}: {TXT_FW_NOT_INSTALLED}",
                en_color.BRIGHT_BLACK,
            ))
        color = (
            en_color.BRIGHT_GREEN
            if status.status == "active"
            else en_color.BRIGHT_RED
        )
        return onSelReturn(ok=text_color(
            f"{TXT_FW_SERVICE}: {detail} {status.version}",
            color,
        ))

    def inspect_rules(self, selItem: c_menu_item) -> onSelReturn:
        try:
            inspection = inspect_before_rules(
                _BEFORE_RULES.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, FirewallPolicyError) as exc:
            return onSelReturn().errRet(TXT_FW_FAIL.format(reason=str(exc)))

        if inspection.openvpn:
            print(
                f"{TXT_FW_OPENVPN}: {TXT_FW_PRESENT} "
                f"({len(inspection.openvpn)} {TXT_FW_BLOCK_COUNT})"
            )
            for block in inspection.openvpn:
                print(
                    f"  {block.label}: "
                    f"{len(block.rules)} {TXT_FW_RULE_COUNT}"
                )
        else:
            print(f"{TXT_FW_OPENVPN}: {TXT_FW_ABSENT}")

        block = inspection.hard_sources
        print(
            f"{TXT_FW_HARD_SOURCES}: {TXT_FW_PRESENT} "
            f"({len(block.rules)} {TXT_FW_RULE_COUNT})"
            if block is not None
            else f"{TXT_FW_HARD_SOURCES}: {TXT_FW_ABSENT}"
        )

        standard = inspection.standard
        print(
            f"{TXT_FW_STANDARD_BLOCK}: {TXT_FW_PRESENT} "
            f"({len(standard.rules)} {TXT_FW_RULE_COUNT})"
            if standard is not None
            else f"{TXT_FW_STANDARD_BLOCK}: {TXT_FW_ABSENT}"
        )

        print(TXT_FW_INSPECT_DONE)
        anyKey()
        return onSelReturn(ok=TXT_FW_INSPECT_DONE)
