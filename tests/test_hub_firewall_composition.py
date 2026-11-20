from __future__ import annotations

from datetime import datetime, timezone
import unittest

from libs.app.hub.models import (
    HubCentralFirewallRule,
    HubCentralFirewallVpnServer,
    HubFirewallPolicyUpdate,
)
from libs.app.menus.app_40_firewall.compiler import compile_firewall
from libs.app.menus.app_40_firewall.composition import (
    FirewallCompositionError,
    compose_firewall_policy,
)
from libs.app.menus.app_40_firewall.config import (
    FirewallConfig,
    FirewallRule,
    FirewallVpnServer,
)


class FirewallCompositionTests(unittest.TestCase):
    @staticmethod
    def _central(*, rules=(), servers=(), machine_id="machine-a"):
        return HubFirewallPolicyUpdate(
            machine_id=machine_id,
            group_id=7,
            generated_at=datetime(2026, 11, 20, 13, 0, tzinfo=timezone.utc),
            vpn_servers=tuple(servers),
            rules=tuple(rules),
        )

    def test_local_only_preview_needs_no_machine_identity(self):
        local = FirewallConfig(rules=(
            FirewallRule(
                "0" * 32, "standard", True, "local-only",
                direction="input", action="allow", protocol="tcp",
                dst_ports="443",
            ),
        ))
        result = compose_firewall_policy(local, None)
        self.assertEqual([item.name for item in result.config.rules], ["local-only"])
        self.assertEqual([item.key for item in result.rule_sources], ["host_local"])

    def test_specificity_order_is_local_host_group_all(self):
        local = FirewallConfig(rules=(
            FirewallRule(
                "f" * 32, "standard", True, "local",
                direction="input", action="deny", protocol="tcp",
                dst_ports="22",
            ),
        ))
        central = self._central(rules=(
            HubCentralFirewallRule(
                "1" * 32, "all", 20, "standard", True, "all-20",
                protocol="tcp", dst_ports="80",
            ),
            HubCentralFirewallRule(
                "2" * 32, "all", 10, "standard", True, "all-10",
                protocol="tcp", dst_ports="443",
            ),
            HubCentralFirewallRule(
                "3" * 32, "group", 5, "standard", True, "group-5",
                protocol="tcp", dst_ports="8080",
            ),
            HubCentralFirewallRule(
                "4" * 32, "host", 1, "standard", True, "host-1",
                protocol="tcp", dst_ports="8443",
            ),
        ))

        result = compose_firewall_policy(local, central, machine_id="machine-a")

        self.assertEqual(
            [item.name for item in result.config.rules],
            ["local", "host-1", "group-5", "all-10", "all-20"],
        )
        self.assertEqual(
            [item.key for item in result.rule_sources],
            [
                "host_local",
                "central_host",
                "central_group",
                "central_all",
                "central_all",
            ],
        )
        self.assertEqual(result.rule_count("central_all"), 2)

    def test_more_specific_central_vpn_server_wins_and_ban_stays_first(self):
        uid = "a" * 32
        central = self._central(
            servers=(
                HubCentralFirewallVpnServer(
                    uid, "all", "vpn", "10.8.0.1", 24, "tun8"
                ),
                HubCentralFirewallVpnServer(
                    uid, "host", "vpn", "10.9.0.1", 24, "tun9"
                ),
            ),
            rules=(
                HubCentralFirewallRule(
                    "b" * 32, "host", 1, "vpn_ban", True, "blocked",
                    source="10.9.0.5/32", vpn_server_uid=uid,
                ),
                HubCentralFirewallRule(
                    "c" * 32, "all", 1, "standard", True, "trusted",
                    source="198.51.100.10/32",
                ),
            ),
        )
        result = compose_firewall_policy(
            FirewallConfig(), central, machine_id="machine-a"
        )

        self.assertEqual(len(result.config.vpn_servers), 1)
        self.assertEqual(result.config.vpn_servers[0].ip, "10.9.0.1")
        self.assertEqual(result.vpn_sources[0].key, "central_host")

        compiled = compile_firewall(result.config)
        self.assertEqual(compiled.ipv4[0].kind, "openvpn")
        self.assertEqual(compiled.ipv4[1].kind, "hard_sources")
        self.assertTrue(any("tun9" in token for rule in compiled.ipv4[0].rules for token in rule))

    def test_local_and_central_ids_never_silently_override(self):
        uid = "d" * 32
        local = FirewallConfig(rules=(
            FirewallRule(uid, "standard", True, "local"),
        ))
        central = self._central(rules=(
            HubCentralFirewallRule(
                uid, "host", 1, "standard", True, "central"
            ),
        ))
        with self.assertRaisesRegex(
            FirewallCompositionError, "Local/central firewall rule ID collision"
        ):
            compose_firewall_policy(local, central, machine_id="machine-a")

    def test_machine_mismatch_and_unknown_central_vpn_reference_fail_closed(self):
        with self.assertRaisesRegex(FirewallCompositionError, "another machine"):
            compose_firewall_policy(
                FirewallConfig(),
                self._central(machine_id="machine-b"),
                machine_id="machine-a",
            )

        central = self._central(rules=(
            HubCentralFirewallRule(
                "e" * 32, "host", 1, "vpn_ban", True, "broken",
                source="10.9.0.5/32",
                vpn_server_uid="9" * 32,
            ),
        ))
        with self.assertRaisesRegex(
            FirewallCompositionError, "unknown central VPN server"
        ):
            compose_firewall_policy(
                FirewallConfig(), central, machine_id="machine-a"
            )


if __name__ == "__main__":
    unittest.main()
