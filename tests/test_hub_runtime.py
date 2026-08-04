import unittest
from datetime import datetime
from unittest.mock import patch

from libs.app.hub.models import (
    HubHostSnapshot,
    HubNodeRedInstance,
    HubProviderSnapshot,
    HubState,
    HubStatus,
)
from libs.app.hub.runtime import HubRuntime


class FakeDatabase:
    instances = []

    def __init__(self, settings):
        self.settings = settings
        self.core = []
        self.providers = []
        self.errors = []
        FakeDatabase.instances.append(self)

    def check_status(self):
        return HubStatus(HubState.READY, "ready", datetime.now().astimezone(), "8.0", 1)

    def sync_core(self, host):
        self.core.append(host)
        return 1

    def sync_provider(self, machine_id, snapshot):
        self.providers.append((machine_id, snapshot))
        return len(snapshot.items)

    def record_source_error(self, machine_id, key, error):
        self.errors.append((machine_id, key, error))


class HubRuntimeTests(unittest.TestCase):
    def setUp(self):
        FakeDatabase.instances.clear()
        self.host = HubHostSnapshot(
            machine_id="machine-1",
            hostname="host",
            fqdn="host.example",
            operating_system="Ubuntu",
            kernel="Linux",
            architecture="x86_64",
            hardware_vendor="",
            hardware_model="",
            sys_apps_version="2.0.0",
            jblibs_version="1.2.16",
        )

    def test_provider_key_must_be_a_stable_lowercase_identifier(self):
        runtime = HubRuntime()
        collector = lambda context: None
        runtime.register_provider("node_red", collector)

        for invalid in ("", "NodeRed", "node-red", "../node", "node red"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "Invalid SysApps Hub provider"):
                    runtime.register_provider(invalid, collector)

    def test_provider_failure_does_not_block_other_provider(self):
        runtime = HubRuntime()
        item = HubNodeRedInstance(
            system_user="node1",
            title="Node 1",
            service_name="node-red@node1.service",
            port=1880,
            url="http://host:1880",
            node_red_version="4.0.9",
            node_js_version="22.23.1",
            node_js_global=True,
            project_name="project",
            git_remote="git@example:project.git",
            service_running=True,
            service_enabled=True,
        )
        runtime.register_provider(
            "node_red",
            lambda context: HubProviderSnapshot(
                "node_red", "node_red_instances", (item,)
            ),
        )

        def broken_provider(context):
            raise RuntimeError("broken provider")

        runtime.register_provider("broken", broken_provider)

        with patch("libs.app.hub.runtime.HubDatabase", FakeDatabase), patch(
            "libs.app.hub.runtime.collect_host_snapshot", return_value=self.host
        ):
            report = runtime.sync_all()

        self.assertTrue(report.core_synced)
        self.assertEqual(report.provider_counts, {"node_red": 1})
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("broken provider", report.warnings[0])

        sync_database = next(db for db in FakeDatabase.instances if db.providers)
        error_database = next(db for db in FakeDatabase.instances if db.errors)
        self.assertEqual(len(sync_database.providers), 1)
        self.assertEqual(error_database.errors[0][1], "broken")


if __name__ == "__main__":
    unittest.main()
