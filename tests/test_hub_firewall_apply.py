"""Guarded Firewall Manager compiler/apply regression tests."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from libs.app.menus.app_40_firewall import apply as firewall_apply
from libs.app.menus.app_40_firewall.apply import (
    ApplyPaths,
    FirewallApplyError,
    UfwNumberedRule,
    apply_local_config,
    build_apply_plan,
    delete_numbered_ufw_rule,
    disable_ufw,
    list_numbered_ufw_rules,
)
from libs.app.menus.app_40_firewall.compiler import (
    build_candidate,
    compile_firewall,
)
from libs.app.menus.app_40_firewall.config import (
    FirewallConfig,
    FirewallRule,
    FirewallVpnServer,
)
from libs.app.menus.app_40_firewall.policy import FirewallPolicyError
from libs.app.menus.app_40_firewall.ssh_safety import SshManagementPath


def base_before() -> str:
    return "\n".join((
        "# rules.before",
        "*filter",
        ":ufw-before-input - [0:0]",
        ":ufw-before-output - [0:0]",
        ":ufw-before-forward - [0:0]",
        "# End required lines",
        "# unmanaged custom rule",
        "-A ufw-before-input -i lo -j ACCEPT",
        "COMMIT",
        "",
    ))


def base_before6() -> str:
    return "\n".join((
        "# rules.before",
        "*filter",
        ":ufw6-before-input - [0:0]",
        ":ufw6-before-output - [0:0]",
        ":ufw6-before-forward - [0:0]",
        "# End required lines",
        "# unmanaged custom IPv6 rule",
        "-A ufw6-before-input -i lo -j ACCEPT",
        "COMMIT",
        "",
    ))


def config() -> FirewallConfig:
    server = FirewallVpnServer(
        "e099a95ebc1f4984b61cad9ffe2915b1",
        "dvestezar",
        "10.8.88.1",
        23,
        "tun0",
    )
    return FirewallConfig(
        vpn_servers=(server,),
        rules=(
            FirewallRule(
                "03f3ebf0354b4af5b568831abb6596c2",
                "standard",
                True,
                "gitea",
                direction="input",
                action="allow",
                protocol="tcp",
                dst_ports="3000",
            ),
            FirewallRule(
                "d847cadf405a406eb1a708c79caac3fd",
                "standard",
                True,
                "test",
                direction="input",
                action="allow",
                protocol="udp",
                dst_ports="50",
            ),
            FirewallRule(
                "297e5af922e54fecacbac56ed04b8520",
                "vpn_ban",
                True,
                "bendik",
                source="10.8.88.15/32",
                ban_to="2026-12-12",
                vpn_server_id=server.server_id,
            ),
        ),
    )


class FirewallCompilerTests(unittest.TestCase):
    def test_compile_user_vm_config_to_v4_v6_and_vpn_blocks(self):
        compiled = compile_firewall(config())
        self.assertEqual(
            [block.kind for block in compiled.ipv4],
            ["openvpn", "hard_sources", "standard"],
        )
        vpn = compiled.ipv4[0]
        self.assertEqual(len(vpn.rules), 2)
        self.assertTrue(all("tun0" in rule for rule in vpn.rules))
        self.assertIn("10.8.88.15", vpn.rules[0])

        standard4 = compiled.ipv4[-1].rules
        self.assertIn(
            (
                "-A", "ufw-before-input", "-p", "tcp", "-m", "tcp",
                "--dport", "3000", "-j", "ACCEPT",
            ),
            standard4,
        )
        self.assertIn(
            (
                "-A", "ufw-before-input", "-p", "udp", "-m", "udp",
                "--dport", "50", "-j", "ACCEPT",
            ),
            standard4,
        )
        # Family-neutral rules also target the real UFW IPv6 chain namespace.
        standard6 = compiled.ipv6[-1].rules
        self.assertIn(
            (
                "-A", "ufw6-before-input", "-p", "tcp", "-m", "tcp",
                "--dport", "3000", "-j", "ACCEPT",
            ),
            standard6,
        )
        self.assertIn(
            (
                "-A", "ufw6-before-input", "-p", "udp", "-m", "udp",
                "--dport", "50", "-j", "ACCEPT",
            ),
            standard6,
        )
        self.assertFalse(any(rule[1] == "ufw-before-input" for rule in standard6))

    def test_multiple_source_and_destination_ports_expand_deterministically(self):
        cfg = FirewallConfig(rules=(
            FirewallRule(
                "a" * 32,
                "standard",
                True,
                "multi",
                direction="input",
                action="allow",
                protocol="tcp",
                src_ports="1000,2000-2002",
                dst_ports="80,443",
            ),
        ))
        rules = compile_firewall(cfg).ipv4[-1].rules
        self.assertEqual(len(rules), 4)
        self.assertIn("--sport", rules[0])
        self.assertTrue(any("2000:2002" in rule for rule in rules))

    def test_candidate_preserves_unmanaged_content_and_is_idempotent(self):
        desired = compile_firewall(config()).ipv4
        first = build_candidate(base_before(), desired, allow_openvpn=True)
        self.assertTrue(first.changed)
        self.assertIn("# unmanaged custom rule", first.content)
        self.assertIn("ZLKL Standard Firewall Config", first.content)
        self.assertIn("OpenVPN JB Config - dvestezar 10.8.88.0/23", first.content)

        second = build_candidate(first.content, desired, allow_openvpn=True)
        self.assertFalse(second.changed)
        self.assertEqual(second.content, first.content)

    def test_unmanaged_executable_rule_between_owned_blocks_blocks_reorder(self):
        original_cfg = config()
        current_desired = compile_firewall(original_cfg).ipv4
        candidate = build_candidate(
            base_before(), current_desired, allow_openvpn=True
        )
        source = candidate.content.replace(
            "# *** EOF OpenVPN JB Config - dvestezar 10.8.88.0/23\n"
            "# *** BOF ZLKL Hard Source Allow Config - managed by sys_apps",
            "# *** EOF OpenVPN JB Config - dvestezar 10.8.88.0/23\n"
            "-A ufw-before-input -s 203.0.113.77 -j DROP\n"
            "# *** BOF ZLKL Hard Source Allow Config - managed by sys_apps",
        )

        # NO_CHANGE must stay a harmless no-op even with an unmanaged line
        # between owned blocks.
        noop = build_candidate(source, current_desired, allow_openvpn=True)
        self.assertFalse(noop.changed)

        changed_cfg = FirewallConfig(
            vpn_servers=original_cfg.vpn_servers,
            rules=original_cfg.rules + (
                FirewallRule(
                    "f" * 32,
                    "standard",
                    True,
                    "new ssh",
                    direction="input",
                    action="allow",
                    protocol="tcp",
                    dst_ports="22",
                ),
            ),
        )
        changed_desired = compile_firewall(changed_cfg).ipv4
        with self.assertRaisesRegex(
            FirewallPolicyError, "change its precedence"
        ):
            build_candidate(source, changed_desired, allow_openvpn=True)

    def test_unrepresented_existing_openvpn_block_blocks_takeover(self):
        source = base_before().replace(
            "# End required lines",
            "# End required lines\n"
            "# *** BOF OpenVPN JB Config - unknown 10.99.0.0/24\n"
            "# *** EOF OpenVPN JB Config - unknown 10.99.0.0/24",
        )
        with self.assertRaisesRegex(FirewallPolicyError, "not represented"):
            build_candidate(
                source,
                compile_firewall(config()).ipv4,
                allow_openvpn=True,
            )

    def test_explicit_ipv6_requires_before6_rules(self):
        cfg = FirewallConfig(rules=(
            FirewallRule(
                "b" * 32,
                "standard",
                True,
                "v6 ssh",
                source="2001:db8::1/128",
                direction="input",
                action="allow",
                protocol="tcp",
                dst_ports="22",
            ),
        ))
        with self.assertRaisesRegex(FirewallPolicyError, "before6"):
            build_apply_plan(cfg, before4=base_before(), before6=None)

    def test_ipv6_candidate_uses_ufw6_chains(self):
        plan = build_apply_plan(
            config(),
            before4=base_before(),
            before6=base_before6(),
        )
        self.assertIsNotNone(plan.ipv6)
        assert plan.ipv6 is not None
        self.assertIn(":ufw6-before-input - [0:0]", plan.ipv6.content)
        self.assertIn(":ufw6-before-output - [0:0]", plan.ipv6.content)
        self.assertIn(":ufw6-before-forward - [0:0]", plan.ipv6.content)
        self.assertIn("-A ufw6-before-input", plan.ipv6.content)
        self.assertNotIn("-A ufw-before-input", plan.ipv6.content)


class FirewallApplyTransactionTests(unittest.TestCase):
    def _paths(self, root: Path) -> ApplyPaths:
        etc = root / "etc"
        etc.mkdir()
        before4 = etc / "before.rules"
        before6 = etc / "before6.rules"
        before4.write_text(base_before(), encoding="utf-8")
        before6.write_text(base_before6(), encoding="utf-8")
        user4 = etc / "user.rules"
        user6 = etc / "user6.rules"
        user4.write_text("# user v4\n", encoding="utf-8")
        user6.write_text("# user v6\n", encoding="utf-8")
        return ApplyPaths(
            before4=before4,
            before6=before6,
            state=root / "var" / "state.json",
            backups=root / "var" / "backups",
            pending_ack=root / "run" / "pending_ack.json",
            user4=user4,
            user6=user6,
        )

    @staticmethod
    def _runner(calls: list[list[str]]):
        def run(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0, "", "")
        return run

    def test_preflight_validates_exact_full_ipv4_and_ipv6_candidates(self):
        plan = build_apply_plan(
            config(),
            before4=base_before(),
            before6=base_before6(),
        )
        payloads: list[tuple[list[str], str]] = []

        def runner(args, **kwargs):
            payloads.append((list(args), kwargs.get("input_text") or ""))
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(
            firewall_apply, "_binary", side_effect=lambda name: f"/usr/bin/{name}"
        ):
            firewall_apply._validate_candidate_files(plan, runner=runner)

        self.assertEqual(payloads[0][1], plan.ipv4.content)
        self.assertEqual(payloads[1][1], plan.ipv6.content)
        self.assertIn(":ufw6-before-input - [0:0]", payloads[1][1])
        self.assertIn("-A ufw6-before-input", payloads[1][1])

    def test_active_apply_arms_rollback_before_reload_and_saves_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            calls: list[list[str]] = []
            statuses = [
                SimpleNamespace(detected=True, status="active"),
                SimpleNamespace(detected=True, status="active"),
                SimpleNamespace(detected=True, status="active"),
            ]
            with patch.object(
                firewall_apply, "_binary", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch.object(
                firewall_apply, "inspect_ufw_service", side_effect=statuses
            ), patch.object(
                firewall_apply.os, "fchown", return_value=None
            ):
                result = apply_local_config(
                    config(),
                    acknowledge=lambda token, seconds: True,
                    paths=paths,
                    runner=self._runner(calls),
                )

            self.assertEqual(result.status, "APPLIED")
            self.assertTrue(result.changed_files)
            self.assertFalse(result.activated)
            self.assertTrue(paths.state.is_file())
            self.assertFalse(paths.pending_ack.exists())
            arm = next(
                i for i, call in enumerate(calls)
                if call and call[0].endswith("/systemd-run")
            )
            dry = next(
                i for i, call in enumerate(calls)
                if call[-3:] == ["/usr/bin/ufw", "--dry-run", "reload"]
            )
            live = next(
                i for i, call in enumerate(calls)
                if call[-2:] == ["/usr/bin/ufw", "reload"]
            )
            self.assertLess(arm, dry)
            self.assertLess(dry, live)
            self.assertTrue(any(
                call[0].endswith("/systemctl")
                and call[1] == "stop"
                and call[2].endswith(".timer")
                and call[3].endswith(".service")
                for call in calls
            ))

    def test_active_non_ssh_change_skips_fresh_ssh_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            calls: list[list[str]] = []
            acknowledgements: list[tuple[str, float]] = []
            statuses = [
                SimpleNamespace(detected=True, status="active"),
                SimpleNamespace(detected=True, status="active"),
                SimpleNamespace(detected=True, status="active"),
            ]
            with patch.object(
                firewall_apply, "_binary", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch.object(
                firewall_apply, "inspect_ufw_service", side_effect=statuses
            ), patch.object(
                firewall_apply,
                "current_ssh_path",
                return_value=SshManagementPath(
                    server_port=22,
                    client_ip="192.168.88.10",
                    client_port=51000,
                    server_ip="192.168.88.46",
                ),
            ), patch.object(
                firewall_apply.os, "fchown", return_value=None
            ):
                result = apply_local_config(
                    config(),
                    acknowledge=lambda token, expires: acknowledgements.append((token, expires)) or True,
                    paths=paths,
                    runner=self._runner(calls),
                )

            self.assertEqual(result.status, "APPLIED")
            self.assertEqual(acknowledgements, [])
            self.assertFalse(paths.pending_ack.exists())

    def test_active_ssh_port_change_requires_fresh_ssh_ack(self):
        cfg = FirewallConfig(rules=(
            FirewallRule(
                "b" * 32,
                "standard",
                True,
                "ssh deny test",
                direction="input",
                action="deny",
                protocol="tcp",
                dst_ports="22",
            ),
        ))
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            calls: list[list[str]] = []
            acknowledgements: list[tuple[str, float]] = []
            statuses = [
                SimpleNamespace(detected=True, status="active"),
                SimpleNamespace(detected=True, status="active"),
                SimpleNamespace(detected=True, status="active"),
            ]
            with patch.object(
                firewall_apply, "_binary", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch.object(
                firewall_apply, "inspect_ufw_service", side_effect=statuses
            ), patch.object(
                firewall_apply,
                "current_ssh_path",
                return_value=SshManagementPath(
                    server_port=22,
                    client_ip="192.168.88.10",
                    client_port=51000,
                    server_ip="192.168.88.46",
                ),
            ), patch.object(
                firewall_apply.os, "fchown", return_value=None
            ):
                result = apply_local_config(
                    cfg,
                    acknowledge=lambda token, expires: acknowledgements.append((token, expires)) or True,
                    paths=paths,
                    runner=self._runner(calls),
                )

            self.assertEqual(result.status, "APPLIED")
            self.assertEqual(len(acknowledgements), 1)
            self.assertTrue(acknowledgements[0][0])
            self.assertFalse(paths.pending_ack.exists())

    def test_inactive_apply_enables_and_rejected_ack_restores_original_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            original4 = paths.before4.read_text(encoding="utf-8")
            original6 = paths.before6.read_text(encoding="utf-8")
            calls: list[list[str]] = []
            statuses = [
                SimpleNamespace(detected=True, status="inactive"),
                SimpleNamespace(detected=True, status="active"),
            ]
            with patch.object(
                firewall_apply, "_binary", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch.object(
                firewall_apply, "inspect_ufw_service", side_effect=statuses
            ), patch.object(
                firewall_apply.os, "fchown", return_value=None
            ):
                result = apply_local_config(
                    config(),
                    acknowledge=lambda token, seconds: False,
                    paths=paths,
                    runner=self._runner(calls),
                )

            self.assertEqual(result.status, "ROLLED_BACK")
            self.assertEqual(paths.before4.read_text(encoding="utf-8"), original4)
            self.assertEqual(paths.before6.read_text(encoding="utf-8"), original6)
            self.assertTrue(any(
                call[-4:] == ["/usr/bin/ufw", "--dry-run", "--force", "enable"]
                for call in calls
            ))
            self.assertTrue(any(
                call[-2:] == ["--force", "enable"] for call in calls
            ))
            self.assertTrue(any(call[-1] == "disable" for call in calls))

    def test_concurrent_ufw_file_edit_aborts_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            original = paths.before4.read_text(encoding="utf-8")
            external = original + "# external administrator change\n"
            calls: list[list[str]] = []

            def runner(args, **kwargs):
                calls.append(list(args))
                if args and args[0].endswith("/systemd-run"):
                    paths.before4.write_text(external, encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, "", "")

            with patch.object(
                firewall_apply, "_binary", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch.object(
                firewall_apply,
                "inspect_ufw_service",
                return_value=SimpleNamespace(detected=True, status="active"),
            ), patch.object(
                firewall_apply.os, "fchown", return_value=None
            ):
                with self.assertRaisesRegex(
                    FirewallApplyError, "changed concurrently"
                ):
                    apply_local_config(
                        config(),
                        acknowledge=lambda token, seconds: True,
                        paths=paths,
                        runner=runner,
                    )

            self.assertEqual(
                paths.before4.read_text(encoding="utf-8"),
                external,
            )
            self.assertFalse(any(
                call[-2:] == ["/usr/bin/ufw", "reload"]
                for call in calls
            ))

    def test_active_no_change_does_not_arm_or_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            plan = build_apply_plan(
                config(),
                before4=paths.before4.read_text(encoding="utf-8"),
                before6=paths.before6.read_text(encoding="utf-8"),
            )
            paths.before4.write_text(plan.ipv4.content, encoding="utf-8")
            paths.before6.write_text(plan.ipv6.content, encoding="utf-8")
            calls: list[list[str]] = []
            with patch.object(
                firewall_apply,
                "inspect_ufw_service",
                return_value=SimpleNamespace(detected=True, status="active"),
            ):
                result = apply_local_config(
                    config(),
                    acknowledge=lambda token, seconds: True,
                    paths=paths,
                    runner=self._runner(calls),
                )
            self.assertEqual(result.status, "NO_CHANGE")
            self.assertEqual(calls, [])

    def test_numbered_ufw_rules_are_parsed_and_deleted_from_stable_snapshot(self):
        before = "\n".join((
            "Status: active",
            "",
            "     To                         Action      From",
            "[ 1] 22/tcp                     ALLOW IN    Anywhere",
            "[ 2] 22/tcp (v6)                ALLOW IN    Anywhere (v6)",
            "",
        ))
        after = "\n".join((
            "Status: active",
            "",
            "[ 1] 22/tcp (v6)                ALLOW IN    Anywhere (v6)",
            "",
        ))
        status_outputs = iter((before, before, before, after, after))
        calls: list[list[str]] = []

        def runner(args, **kwargs):
            calls.append(list(args))
            if args[-2:] == ["status", "numbered"]:
                return subprocess.CompletedProcess(
                    args, 0, next(status_outputs), ""
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            with patch.object(
                firewall_apply, "_binary", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch.object(
                firewall_apply,
                "current_ssh_path",
                return_value=SshManagementPath(
                    server_port=2222,
                    client_ip="192.168.88.10",
                    client_port=51000,
                    server_ip="192.168.88.46",
                ),
            ):
                snapshot = list_numbered_ufw_rules(runner=runner)
                self.assertEqual(snapshot, (
                    UfwNumberedRule(1, "22/tcp ALLOW IN Anywhere"),
                    UfwNumberedRule(2, "22/tcp (v6) ALLOW IN Anywhere (v6)"),
                ))
                result = delete_numbered_ufw_rule(
                    snapshot[0],
                    snapshot=snapshot,
                    acknowledge=lambda token, expires: True,
                    paths=paths,
                    runner=runner,
                )

        self.assertEqual(result.status, "DELETED")
        self.assertFalse(result.ssh_ack_required)
        self.assertEqual(
            result.remaining,
            (UfwNumberedRule(1, "22/tcp (v6) ALLOW IN Anywhere (v6)"),),
        )
        self.assertIn(
            ["/usr/sbin/ufw", "--force", "delete", "1"],
            calls,
        )

    def test_native_ssh_allow_delete_requires_ack_and_rolls_back_when_rejected(self):
        before = "\n".join((
            "Status: active",
            "[ 1] 22/tcp ALLOW IN Anywhere",
        ))
        after = "Status: active\n"
        status_outputs = iter((before, before, before, after))
        calls: list[list[str]] = []

        def runner(args, **kwargs):
            calls.append(list(args))
            if args[-2:] == ["status", "numbered"]:
                return subprocess.CompletedProcess(args, 0, next(status_outputs), "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            original4 = paths.user4.read_text(encoding="utf-8")
            with patch.object(
                firewall_apply, "_binary", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch.object(
                firewall_apply,
                "current_ssh_path",
                return_value=SshManagementPath(
                    server_port=22,
                    client_ip="192.168.88.10",
                    client_port=51000,
                    server_ip="192.168.88.46",
                ),
            ):
                snapshot = list_numbered_ufw_rules(runner=runner)
                result = delete_numbered_ufw_rule(
                    snapshot[0],
                    snapshot=snapshot,
                    acknowledge=lambda token, expires: False,
                    paths=paths,
                    runner=runner,
                )

            self.assertEqual(result.status, "ROLLED_BACK")
            self.assertTrue(result.ssh_ack_required)
            self.assertEqual(paths.user4.read_text(encoding="utf-8"), original4)
            self.assertTrue(any(call[0].endswith("/systemd-run") for call in calls))

    def test_native_ufw_delete_aborts_if_numbered_snapshot_changed(self):
        displayed = "\n".join((
            "Status: active",
            "[ 1] 22/tcp ALLOW IN Anywhere",
            "[ 2] 80/tcp ALLOW IN Anywhere",
        ))
        changed = "\n".join((
            "Status: active",
            "[ 1] 80/tcp ALLOW IN Anywhere",
        ))
        status_outputs = iter((displayed, changed))
        calls: list[list[str]] = []

        def runner(args, **kwargs):
            calls.append(list(args))
            if args[-2:] == ["status", "numbered"]:
                return subprocess.CompletedProcess(
                    args, 0, next(status_outputs), ""
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(
            firewall_apply, "_binary", return_value="/usr/sbin/ufw"
        ):
            snapshot = list_numbered_ufw_rules(runner=runner)
            with self.assertRaisesRegex(
                FirewallApplyError, "changed after selection"
            ):
                delete_numbered_ufw_rule(
                    snapshot[0],
                    snapshot=snapshot,
                    acknowledge=lambda token, expires: True,
                    runner=runner,
                )

        self.assertFalse(any("delete" in call for call in calls))

    def test_native_ufw_parser_fails_closed_on_malformed_numbered_line(self):
        def runner(args, **kwargs):
            return subprocess.CompletedProcess(
                args, 0, "Status: active\n[ xx] broken rule\n", ""
            )

        with patch.object(
            firewall_apply, "_binary", return_value="/usr/sbin/ufw"
        ):
            with self.assertRaisesRegex(
                FirewallApplyError, "Cannot safely parse"
            ):
                list_numbered_ufw_rules(runner=runner)

    def test_disable_is_explicit_and_verified(self):
        calls: list[list[str]] = []
        with patch.object(
            firewall_apply, "_binary", return_value="/usr/sbin/ufw"
        ), patch.object(
            firewall_apply,
            "inspect_ufw_service",
            side_effect=[
                SimpleNamespace(detected=True, status="active"),
                SimpleNamespace(detected=True, status="inactive"),
            ],
        ):
            disable_ufw(runner=self._runner(calls))
        self.assertEqual(calls, [["/usr/sbin/ufw", "disable"]])


if __name__ == "__main__":
    unittest.main()
