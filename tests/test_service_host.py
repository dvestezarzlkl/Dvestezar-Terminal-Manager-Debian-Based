import unittest
from unittest.mock import patch

from libs.app import cfg
from libs.app.service_host import (
    configured_service_host,
    normalize_service_host,
    validate_service_host,
)


class ServiceHostTests(unittest.TestCase):
    def test_empty_and_historical_placeholder_are_not_configured(self):
        self.assertEqual(normalize_service_host(""), "")
        self.assertEqual(normalize_service_host("moje.domena.fake"), "")
        self.assertEqual(normalize_service_host("MOJE.DOMENA.FAKE"), "")

    def test_legacy_url_is_reduced_to_host_only(self):
        self.assertEqual(
            normalize_service_host("https://Vpn-Node.Example:1880/legacy/path"),
            "vpn-node.example",
        )

    def test_new_value_accepts_fqdn_ipv4_and_bracketed_ipv6(self):
        self.assertEqual(validate_service_host("node.vpn.example"), "node.vpn.example")
        self.assertEqual(validate_service_host("10.8.89.2"), "10.8.89.2")
        self.assertEqual(validate_service_host("[2001:db8::1]"), "2001:db8::1")

    def test_new_value_rejects_scheme_port_path_and_placeholder(self):
        for value in (
            "https://node.example",
            "node.example:1880",
            "node.example/path",
            "moje.domena.fake",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_service_host(value)

    def test_configured_service_host_reads_compatible_server_url_key(self):
        with patch.object(cfg, "SERVER_URL", "Node.VPN.Example"):
            self.assertEqual(configured_service_host(), "node.vpn.example")


if __name__ == "__main__":
    unittest.main()
