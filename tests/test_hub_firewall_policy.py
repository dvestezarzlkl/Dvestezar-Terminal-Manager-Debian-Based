"""UFW legacy read-only reconcile regression tests, including cooldowns."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from libs.app.menus.app_40_firewall.policy import (
    FirewallPolicyError, compile_legacy_openvpn, inspect_before_rules,
    plan_legacy_openvpn, read_legacy_config, rules_digest,
)

VPN_BO = "# *** BOF OpenVPN JB Config - vpn-jb 10.8.88.0/23"
VPN_EO = "# *** EOF OpenVPN JB Config - vpn-jb 10.8.88.0/23"
HARD_BO = "# *** BOF ZLKL Hard Source Allow Config - managed by sys_apps"
HARD_EO = "# *** EOF ZLKL Hard Source Allow Config - managed by sys_apps"
FWD = '-A ufw-before-forward -i tun+ -s 10.8.89.12 -m comment --comment "Alice - BAN" -j DROP'
INP = '-A ufw-before-input -i tun+ -s 10.8.89.12 -m comment --comment "Alice - BAN" -j DROP'
TRUST = '-A ufw-before-input -s 198.51.100.44 -m comment --comment "Trusted office" -j ACCEPT'


def before_rules(*, generated="2025-09-29 11:51:47", vpn=(FWD, INP),
                 trusted=(TRUST,)) -> str:
    return "\n".join((
        "# rules.before", "*filter", ":ufw-before-input - [0:0]",
        ":ufw-before-forward - [0:0]", "# End required lines",
        VPN_BO, "# Generated on " + generated, *vpn, VPN_EO,
        HARD_BO, *trusted, HARD_EO,
        "# Custom unmanaged rule remains untouched",
        "-A ufw-before-input -i lo -j ACCEPT",
        "COMMIT", "",
    ))


def policy_config(ban_to="2026-10-20") -> dict:
    return {
        "server_name": "vpn-jb", "server_ip": "10.8.88.1",
        "server_mask": 23,
        "clients": [
            {"clientName": "Alice", "clientIP": "10.8.89.12",
             "type": 1, "banTo": ban_to},
        ],
    }


class HubFirewallPolicyTests(unittest.TestCase):
    def test_parse_owned_blocks_with_other_rules_and_order(self):
        parsed = inspect_before_rules(before_rules())
        self.assertEqual(len(parsed.openvpn.rules), 2)
        self.assertEqual(len(parsed.hard_sources.rules), 1)
        self.assertLess(parsed.openvpn.last_line, parsed.hard_sources.first_line)
        self.assertEqual(
            parsed.openvpn.rules[0],
            ("-A", "ufw-before-forward", "-i", "tun+", "-s", "10.8.89.12",
             "-j", "DROP"),
        )
        self.assertEqual(
            parsed.hard_sources.rules[0][-2:],
            ("-j", "ACCEPT"),
        )

    def test_same_rules_ignore_timestamp_whitespace_and_display_comment(self):
        a = plan_legacy_openvpn(
            before_rules(), policy_config(), on_date=date(2026, 10, 20)
        )
        updated = before_rules(generated="2026-10-20 23:50:00").replace(
            "Alice - BAN", "Different audit label"
        )
        b = plan_legacy_openvpn(
            updated, policy_config(), on_date=date(2026, 10, 20)
        )
        self.assertEqual(a.status, "NO_CHANGE")
        self.assertEqual(b.status, "NO_CHANGE")
        self.assertEqual(a.effective_hash, b.effective_hash)
        self.assertEqual(a.current_hash, b.current_hash)
        self.assertEqual(a.next_expiry, date(2026, 10, 21))
        self.assertEqual(a.expired_bans, 0)

    def test_ban_expires_after_whole_last_day_even_if_json_did_not_change(self):
        cfg = policy_config()
        last_day = plan_legacy_openvpn(
            before_rules(), cfg, on_date=date(2026, 10, 20)
        )
        next_day = plan_legacy_openvpn(
            before_rules(), cfg, on_date=date(2026, 10, 21)
        )
        self.assertEqual(last_day.status, "NO_CHANGE")
        self.assertEqual(next_day.status, "CHANGED")
        self.assertEqual(next_day.expired_bans, 1)
        self.assertEqual(next_day.effective_rules, 0)
        self.assertNotEqual(next_day.current_hash, next_day.effective_hash)
        self.assertIsNone(next_day.next_expiry)
        # Following checks remain idempotent once real rules have been updated.
        empty = plan_legacy_openvpn(
            before_rules(vpn=()), cfg, on_date=date(2026, 10, 22)
        )
        self.assertEqual(empty.status, "NO_CHANGE")

    def test_static_ban_and_isolation_without_cooldown(self):
        cfg = policy_config(None)
        cfg["clients"].append({
            "clientName": "Bob", "clientIP": "10.8.89.8", "type": 2,
        })
        actions, expired, next_expiry, label = compile_legacy_openvpn(
            cfg, on_date=date(2026, 12, 1)
        )
        self.assertEqual((len(actions), expired, next_expiry), (3, 0, None))
        self.assertIn("10.8.88.0/23", label)
        self.assertEqual(
            actions[-1],
            ("-A", "ufw-before-forward", "-i", "tun+", "-s", "10.8.89.8",
             "!", "-d", "10.8.88.1", "-j", "DROP"),
        )

    def test_managed_source_allow_is_kept_separate(self):
        old = before_rules()
        a = plan_legacy_openvpn(old, policy_config(), on_date=date(2026, 10, 20))
        changed_sources = old.replace("198.51.100.44", "198.51.100.45")
        b = plan_legacy_openvpn(
            changed_sources, policy_config(), on_date=date(2026, 10, 20)
        )
        self.assertEqual(a.status, "NO_CHANGE")
        self.assertEqual(b.status, "NO_CHANGE")
        self.assertNotEqual(
            inspect_before_rules(old).hard_sources.rules,
            inspect_before_rules(changed_sources).hard_sources.rules,
        )

    def test_missing_and_changed_identity_require_explicit_adoption(self):
        source = before_rules()
        missing = source.replace(VPN_BO, "# old BOF").replace(VPN_EO, "# old EOF")
        self.assertEqual(
            plan_legacy_openvpn(
                missing, policy_config(), on_date=date(2026, 10, 20)
            ).status, "MISSING",
        )
        renamed = source.replace("vpn-jb 10.8.88.0/23", "changed 10.8.88.0/23")
        self.assertEqual(
            plan_legacy_openvpn(
                renamed, policy_config(), on_date=date(2026, 10, 20)
            ).status, "REVIEW",
        )

    def test_reject_duplicate_nested_unmatched_and_reversed_blocks(self):
        source = before_rules()
        invalid = (
            source + VPN_BO + "\n" + VPN_EO + "\n",
            source.replace(VPN_EO, ""),
            source.replace(VPN_EO, "# *** EOF OpenVPN JB Config - altered"),
            source.replace(VPN_EO, VPN_BO + "\n" + VPN_EO),
            source.replace(VPN_BO, VPN_EO),
        )
        for candidate in invalid:
            with self.subTest(case=candidate[-65:]):
                with self.assertRaises(FirewallPolicyError):
                    inspect_before_rules(candidate)
        reversed_blocks = "\n".join((
            HARD_BO, TRUST, HARD_EO, VPN_BO, FWD, VPN_EO,
        ))
        with self.assertRaisesRegex(FirewallPolicyError, "precede"):
            inspect_before_rules(reversed_blocks)

    def test_reject_unknown_executable_directive_inside_managed_block(self):
        candidate = before_rules().replace(
            FWD, "-F ufw-before-forward"
        )
        with self.assertRaises(FirewallPolicyError):
            inspect_before_rules(candidate)

    def test_invalid_inputs_rejected_not_silently_skipped(self):
        cfg = policy_config()
        variations = [
            {"server_mask": 50},
            {"server_ip": "not an ip"},
            {"clients": [{"clientIP": "10.8.89.12", "type": 66}]},
            {"clients": [{"clientIP": "10.8.89.12", "type": True}]},
            {"clients": [{"clientIP": "10.8.89.12", "type": 1, "banTo": "BAD"}]},
            {"clients": [{"clientIP": "10.8.89.12", "type": 1},
                         {"clientIP": "10.8.89.12", "type": 2}]},
        ]
        for override in variations:
            with self.subTest(override=override):
                with self.assertRaises(FirewallPolicyError):
                    compile_legacy_openvpn({**cfg, **override})

    def test_load_legacy_config_is_data_only_no_exec_or_shell(self):
        cfg = policy_config()
        data = "/** Type hints **/\n// BOF JSON CFG\n" + json.dumps(cfg)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "old.js"
            source.write_text(data, encoding="utf-8")
            with patch.object(subprocess, "run", side_effect=AssertionError("no shell")):
                self.assertEqual(read_legacy_config(source), cfg)
            source.write_text("const x = {};\n", encoding="utf-8")
            with self.assertRaises(FirewallPolicyError):
                read_legacy_config(source)

    def test_plan_is_pure_even_when_rule_expired(self):
        with patch.object(subprocess, "run", side_effect=AssertionError("no commands")), patch.object(
            Path, "write_text", side_effect=AssertionError("no file write")
        ):
            result = plan_legacy_openvpn(
                before_rules(), policy_config(), on_date=date(2026, 10, 21)
            )
        self.assertEqual(result.status, "CHANGED")
        self.assertEqual(len(rules_digest(((),))), 64)
