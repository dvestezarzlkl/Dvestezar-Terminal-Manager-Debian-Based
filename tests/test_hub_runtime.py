import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from libs.app.hub import core_provider
from libs.app.hub.models import (
    HubDiskNameUpdate,
    HubHostSnapshot,
    HubNodeRedInstance,
    HubProviderSnapshot,
    HubProviderSyncResult,
    HubState,
    HubStatus,
    HubSyncReport,
)
from libs.app.hub.runtime import HubRuntime
from libs.app.hub.settings import HubSettings


class FakeDatabase:
    instances = []
    remote_updates = ()

    def __init__(self, settings):
        self.settings = settings
        self.core = []
        self.providers = []
        self.errors = []
        FakeDatabase.instances.append(self)

    def check_status(self):
        return HubStatus(HubState.READY, "ready", datetime.now().astimezone(), "8.0", 2)

    def sync_core(self, host):
        self.core.append(host)
        return 1

    def sync_provider(self, machine_id, snapshot):
        self.providers.append((machine_id, snapshot))
        return HubProviderSyncResult(len(snapshot.items), FakeDatabase.remote_updates)

    def record_source_error(self, machine_id, key, error):
        self.errors.append((machine_id, key, error))


class HubRuntimeTests(unittest.TestCase):
    def setUp(self):
        FakeDatabase.instances.clear()
        FakeDatabase.remote_updates = ()
        self.host = HubHostSnapshot(
            machine_id="machine-1",
            hostname="host",
            fqdn="host.example",
            operating_system="Ubuntu",
            kernel="Linux",
            architecture="x86_64",
            hardware_vendor="",
            hardware_model="",
            sys_apps_version="2.1.0",
            jblibs_version="1.2.17",
        )

    def test_core_snapshot_keeps_service_host_separate_from_system_fqdn(self):
        machine = SimpleNamespace(
            machine_id="machine-1",
            static_hostname="system-host",
            hostname_full="system-host.internal",
            operating_system="Ubuntu",
            kernel="Linux",
            architecture="x86_64",
            hardware_vendor="CI",
            hardware_model="Test",
        )
        with patch.object(core_provider.cfg, "machineInfo", machine), patch(
            "libs.app.hub.core_provider.configured_service_host",
            return_value="vpn-host.example.test",
        ), patch(
            "libs.app.hub.core_provider.collect_addresses", return_value=()
        ), patch(
            "libs.app.hub.core_provider.collect_services", return_value=()
        ):
            snapshot = core_provider.collect_host_snapshot()

        self.assertEqual(snapshot.hostname, "system-host")
        self.assertEqual(snapshot.fqdn, "system-host.internal")
        self.assertEqual(snapshot.service_host, "vpn-host.example.test")

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
        ), patch(
            "libs.app.hub.runtime.configured_service_host", return_value="host.example"
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

    def test_sync_all_logs_phase_boundaries(self):
        runtime = HubRuntime()
        runtime.register_provider(
            "disks",
            lambda context: HubProviderSnapshot("disks", "disks", ()),
        )

        with patch("libs.app.hub.runtime.HubDatabase", FakeDatabase), patch(
            "libs.app.hub.runtime.collect_host_snapshot", return_value=self.host
        ), patch(
            "libs.app.hub.runtime.configured_service_host", return_value="host.example"
        ), patch("libs.app.hub.runtime.log.info") as info_log:
            report = runtime.sync_all()

        self.assertTrue(report.core_synced)
        messages = [call.args[0] for call in info_log.call_args_list]
        self.assertIn("SysApps Hub database readiness check: start", messages)
        self.assertIn("SysApps Hub core inventory collection: start", messages)
        self.assertIn("SysApps Hub core database sync: start", messages)
        self.assertIn("SysApps Hub provider %s collection: start", messages)
        self.assertIn("SysApps Hub provider %s database sync: start", messages)
        self.assertIn("SysApps Hub final status refresh: start", messages)
        provider_calls = [
            call for call in info_log.call_args_list
            if call.args and call.args[0] == "SysApps Hub provider %s collection: start"
        ]
        self.assertEqual(provider_calls[0].args[1], "disks")

    def test_sync_all_reports_dynamic_progress(self):
        runtime = HubRuntime()
        runtime.register_provider(
            "node_red",
            lambda context: HubProviderSnapshot("node_red", "node_red_instances", ()),
        )
        runtime.register_provider(
            "disks",
            lambda context: HubProviderSnapshot("disks", "disks", ()),
        )
        progress = []

        with patch("libs.app.hub.runtime.HubDatabase", FakeDatabase), patch(
            "libs.app.hub.runtime.collect_host_snapshot", return_value=self.host
        ), patch(
            "libs.app.hub.runtime.configured_service_host", return_value="host.example"
        ):
            report = runtime.sync_all(lambda step, total, label: progress.append((step, total, label)))

        self.assertTrue(report.core_synced)
        self.assertEqual(
            progress,
            [
                (1, 4, "core inventory"),
                (2, 4, "disks"),
                (3, 4, "node red"),
                (4, 4, "finalization"),
            ],
        )

    def test_startup_prints_progress_callback(self):
        runtime = HubRuntime()
        settings = HubSettings(
            enabled=True,
            host="db.example",
            port=3306,
            user="sysapps",
            password="secret",
            database="sys_apps",
            prefix="sysapps_",
            connect_timeout=3,
            auto_sync=True,
        )
        ready = HubStatus(HubState.READY, "ready", datetime.now().astimezone())

        def fake_sync(progress=None):
            progress(1, 2, "core inventory")
            progress(2, 2, "finalization")
            return HubSyncReport(core_synced=True)

        with patch.object(runtime, "refresh_status", return_value=ready), patch(
            "libs.app.hub.runtime.HubSettings.from_cfg", return_value=settings
        ), patch.object(runtime, "sync_all", side_effect=fake_sync), patch(
            "builtins.print"
        ) as print_mock:
            runtime.startup()

        printed = [call.args[0] for call in print_mock.call_args_list]
        self.assertIn("SysApps Hub: synchronization 1/2 - core inventory...", printed)
        self.assertIn("SysApps Hub: synchronization 2/2 - finalization...", printed)

    def test_remote_updates_are_applied_after_database_commit(self):
        runtime = HubRuntime()
        applied = []
        update = HubDiskNameUpdate(
            "ptuuid-1", "backup_disk", datetime.now(timezone.utc)
        )
        FakeDatabase.remote_updates = (update,)
        runtime.register_provider(
            "disks",
            lambda context: HubProviderSnapshot("disks", "disks", ()),
            lambda updates: applied.extend(updates),
        )

        with patch("libs.app.hub.runtime.HubDatabase", FakeDatabase), patch(
            "libs.app.hub.runtime.collect_host_snapshot", return_value=self.host
        ), patch(
            "libs.app.hub.runtime.configured_service_host", return_value="host.example"
        ):
            report = runtime.sync_all()

        self.assertEqual(report.provider_counts, {"disks": 0})
        self.assertEqual(applied, [update])

    def test_missing_service_host_blocks_status_and_sync_before_database_access(self):
        runtime = HubRuntime()
        local_settings = HubSettings(
            enabled=True,
            host="db.example",
            port=3306,
            user="sysapps",
            password="secret",
            database="sys_apps",
            prefix="sysapps_",
            connect_timeout=3,
            auto_sync=True,
        )
        with patch(
            "libs.app.hub.runtime.HubSettings.from_cfg", return_value=local_settings
        ), patch(
            "libs.app.hub.runtime.configured_service_host", return_value=""
        ):
            status = runtime.refresh_status()
            report = runtime.sync_all()

        self.assertEqual(status.state, HubState.NOT_CONFIGURED)
        self.assertIn("Service host / FQDN", status.message)
        self.assertIn("Service host / FQDN", report.error)


if __name__ == "__main__":
    unittest.main()
