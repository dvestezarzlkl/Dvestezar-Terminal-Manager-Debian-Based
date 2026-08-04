import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from libs.app.hub.models import HubContext
from libs.app.menus.app_20_node_red import hub_provider


class FakeService:
    fullName = "node-red-userInstance@node1.service"

    def running(self):
        return True

    def enabled(self):
        return False


class FakeCfg:
    err = ""
    title = "Competition Node"
    port = 1880
    service = FakeService()
    admin_users = [
        SimpleNamespace(user="admin", permissions="*", password="$2b$secret-hash"),
        SimpleNamespace(user="viewer", permissions="read", password="$2b$other-hash"),
    ]


class NodeRedHubProviderTests(unittest.TestCase):
    def test_snapshot_contains_versions_and_never_exports_password_hashes(self):
        context = HubContext(datetime.now().astimezone(), "machine-1")
        with patch.object(hub_provider, "getSysUsers", return_value=[("a", "node1")]), patch.object(
            hub_provider, "cfg_data", return_value=FakeCfg()
        ), patch.object(
            hub_provider, "getNodeJsVersion", return_value=(22, True, "22.23.1")
        ), patch.object(
            hub_provider, "instanceVersion", return_value="4.0.9"
        ), patch.object(
            hub_provider,
            "get_active_project_info",
            return_value=SimpleNamespace(
                name="competition", remote="git@example:competition.git"
            ),
        ), patch.object(hub_provider, "getHttps", return_value=None), patch.object(
            hub_provider, "existsSelfSignedCert", return_value=False
        ), patch.object(
            hub_provider,
            "build_instance_url",
            return_value="http://node.example:1880",
        ):
            snapshot = hub_provider.collect_node_red_snapshot(context)

        self.assertEqual(snapshot.source_key, "node_red")
        self.assertEqual(snapshot.dataset, "node_red_instances")
        self.assertEqual(len(snapshot.items), 1)
        item = snapshot.items[0]
        self.assertEqual(item.node_red_version, "4.0.9")
        self.assertEqual(item.node_js_version, "22.23.1")
        self.assertEqual(
            [(user.username, user.access) for user in item.editor_users],
            [("admin", "RW"), ("viewer", "R")],
        )
        rendered = repr(snapshot)
        self.assertNotIn("secret-hash", rendered)
        self.assertNotIn("other-hash", rendered)

    def test_invalid_instance_aborts_provider_to_preserve_previous_snapshot(self):
        broken = FakeCfg()
        broken.err = "invalid config"
        context = HubContext(datetime.now().astimezone(), "machine-1")
        with patch.object(hub_provider, "getSysUsers", return_value=[("a", "node1")]), patch.object(
            hub_provider, "cfg_data", return_value=broken
        ):
            with self.assertRaisesRegex(RuntimeError, "invalid config"):
                hub_provider.collect_node_red_snapshot(context)


if __name__ == "__main__":
    unittest.main()
