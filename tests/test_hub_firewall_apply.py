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
    apply_local_config,
    build_apply_plan,
    disable_ufw,
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
        # Family-neutral standard rules apply to IPv6 too when before6.rules exists.
        self.assertEqual(compiled.ipv6[-1].rules, standard4)

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


class FirewallApplyTransactionTests(unittest.TestCase):
    def _paths(self, root: Path) -> ApplyPaths:
        etc = root / "etc"
        etc.mkdir()
        before4 = etc / "before.rules"
        before6 = etc / "before6.rules"
        before4.write_text(base_before(), encoding="utf-8")
        before6.write_text(base_before(), encoding="utf-8")
        return ApplyPaths(
            before4=before4,
            before6=before6,
            state=root / "var" / "state.json",
            backups=root / "var" / "backups",
        )

    @staticmethod
    def _runner(calls: list[list[str]]):
        def run(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0, "", "")
        return run

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
                    acknowledge=lambda seconds: True,
                    paths=paths,
                    runner=self._runner(calls),
                )

            self.assertEqual(result.status, "APPLIED")
            self.assertTrue(result.changed_files)
            self.assertFalse(result.activated)
            self.assertTrue(paths.state.is_file())
            flat = [" ".join(call) for call in calls]
            arm = next(i for i, call in enumerate(flat) if "systemd-run" in call)
            dry = next(i for i, call in enumerate(flat) if "--dry-run reload" in call)
            live = next(
                i for i, call in enumerate(flat)
                if call.endswith("/ufw reload") and "--dry-run" not in call
            )
            self.assertLess(arm, dry)
            self.assertLess(dry, live)

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
                    acknowledge=lambda seconds: False,
                    paths=paths,
                    runner=self._runner(calls),
                )

            self.assertEqual(result.status, "ROLLED_BACK")
            self.assertEqual(paths.before4.read_text(encoding="utf-8"), original4)
            self.assertEqual(paths.before6.read_text(encoding="utf-8"), original6)
            self.assertTrue(any(
                call[-2:] == ["--force", "enable"] for call in calls
            ))
            self.assertTrue(any(call[-1] == "disable" for call in calls))

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
                    acknowledge=lambda seconds: True,
                    paths=paths,
                    runner=self._runner(calls),
                )
            self.assertEqual(result.status, "NO_CHANGE")
            self.assertEqual(calls, [])

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
