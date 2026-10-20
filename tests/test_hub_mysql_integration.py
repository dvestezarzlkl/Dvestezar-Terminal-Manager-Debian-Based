from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
import unittest

from libs.app.hub.database import HubDatabase
from libs.app.hub.models import (
    HubDisk,
    HubHostSnapshot,
    HubProviderSnapshot,
    HubService,
)
from libs.app.hub.schema import HubSchemaManager, table_identifier
from libs.app.hub.settings import HubSettings


@unittest.skipUnless(
    os.environ.get("SYSAPPS_TEST_MYSQL") == "1",
    "MariaDB integration environment is not enabled.",
)
class HubMySqlIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = HubSettings(
            enabled=True,
            host=os.environ.get("SYSAPPS_TEST_MYSQL_HOST", "127.0.0.1"),
            port=int(os.environ.get("SYSAPPS_TEST_MYSQL_PORT", "3306")),
            user=os.environ.get("SYSAPPS_TEST_MYSQL_USER", "root"),
            password=os.environ.get("SYSAPPS_TEST_MYSQL_PASSWORD", "root"),
            database=os.environ.get("SYSAPPS_TEST_MYSQL_DATABASE", "sys_apps_ci"),
            prefix="ci_",
            connect_timeout=5,
            auto_sync=True,
        )
        cls.database = HubDatabase(cls.settings)
        with cls.database.connect(include_database=False) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{cls.settings.database}`")
            connection.commit()
        version = cls.database.initialize_or_upgrade_schema()
        if version != 4:
            raise AssertionError(f"Expected schema version 4, got {version}")

    @classmethod
    def tearDownClass(cls) -> None:
        with cls.database.connect(include_database=False) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{cls.settings.database}`")
            connection.commit()

    @staticmethod
    def _host(machine_id: str, hostname: str) -> HubHostSnapshot:
        return HubHostSnapshot(
            machine_id=machine_id,
            hostname=hostname,
            fqdn=f"{hostname}.example.test",
            operating_system="Ubuntu",
            kernel="Linux",
            architecture="x86_64",
            hardware_vendor="CI",
            hardware_model="MariaDB",
            sys_apps_version="2.1.0",
            jblibs_version="1.2.17",
            service_host=f"service.{hostname}.example.test",
        )

    @staticmethod
    def _disk(name: str, updated_at: datetime | None) -> HubDisk:
        return HubDisk(
            ptuuid="abcd-1234",
            device_name="sdb",
            device_path="/dev/sdb",
            display_name=name,
            name_updated_at=updated_at,
            size_bytes=1_000_000,
            device_type="disk",
            partition_count=1,
            mountpoint_count=0,
            is_system_disk=False,
        )

    @staticmethod
    def _catalog_disk(
        ptuuid: str, name: str, updated_at: datetime | None
    ) -> HubDisk:
        return HubDisk(
            ptuuid=ptuuid,
            device_name="",
            device_path="",
            display_name=name,
            name_updated_at=updated_at,
            size_bytes=0,
            device_type="disk",
            partition_count=0,
            mountpoint_count=0,
            is_system_disk=False,
            attached=False,
        )

    def test_schema_disk_names_and_physical_move_between_hosts(self) -> None:
        first_time = datetime.now(timezone.utc).replace(microsecond=100000)
        second_time = first_time + timedelta(seconds=1)

        self.database.sync_core(self._host("machine-a", "host-a"))
        first = self.database.sync_provider(
            "machine-a",
            HubProviderSnapshot(
                "disks",
                "disks",
                (self._disk("backup_disk", first_time),),
            ),
        )
        self.assertEqual(first.item_count, 1)
        self.assertEqual(first.remote_updates, ())

        self.database.sync_core(self._host("machine-b", "host-b"))
        moved = self.database.sync_provider(
            "machine-b",
            HubProviderSnapshot(
                "disks",
                "disks",
                (self._disk("", None),),
            ),
        )
        self.assertEqual(len(moved.remote_updates), 1)
        self.assertEqual(moved.remote_updates[0].display_name, "backup_disk")

        updated = self.database.sync_provider(
            "machine-b",
            HubProviderSnapshot(
                "disks",
                "disks",
                (self._disk("archive_disk", second_time),),
            ),
        )
        self.assertEqual(updated.remote_updates, ())

        stale = self.database.sync_provider(
            "machine-a",
            HubProviderSnapshot(
                "disks",
                "disks",
                (self._disk("backup_disk", first_time),),
            ),
        )
        self.assertEqual(len(stale.remote_updates), 1)
        self.assertEqual(stale.remote_updates[0].display_name, "archive_disk")

        disks = table_identifier(self.settings, "disks")
        host_disks = table_identifier(self.settings, "host_disks")
        hosts = table_identifier(self.settings, "hosts")
        migrations = table_identifier(self.settings, "schema_migrations")
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT display_name FROM {disks} WHERE ptuuid=%s",
                    ("abcd-1234",),
                )
                self.assertEqual(cursor.fetchone()[0], "archive_disk")
                cursor.execute(f"SELECT COUNT(*) FROM {host_disks}")
                self.assertEqual(cursor.fetchone()[0], 1)
                cursor.execute(
                    f"SELECT h.machine_id FROM {host_disks} hd "
                    f"JOIN {hosts} h ON h.id=hd.host_id"
                )
                self.assertEqual(cursor.fetchone()[0], "machine-a")
                cursor.execute(
                    f"SELECT fqdn, service_host FROM {hosts} WHERE machine_id=%s",
                    ("machine-a",),
                )
                self.assertEqual(
                    cursor.fetchone(),
                    ("host-a.example.test", "service.host-a.example.test"),
                )
                cursor.execute(f"SELECT MAX(version) FROM {migrations}")
                self.assertEqual(cursor.fetchone()[0], 4)

    def test_upgrade_003_to_004_preserves_existing_hosts(self) -> None:
        old_settings = replace(
            self.settings, database=f"{self.settings.database}_upgrade"
        )
        db = HubDatabase(old_settings)
        with db.connect(include_database=False) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE `{old_settings.database}`")
            connection.commit()
        try:
            with db.connect() as connection:
                old_schema = HubSchemaManager(old_settings)
                old_schema.migrations = old_schema.migrations[:3]
                self.assertEqual(old_schema.apply(connection), 3)
                hosts = table_identifier(old_settings, "hosts")
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"INSERT INTO {hosts} "
                        "(machine_id, hostname, fqdn, first_seen_at, last_seen_at) "
                        "VALUES (%s, %s, %s, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))",
                        ("old-machine", "old-host", "old-host.example.test"),
                    )
                connection.commit()
                new_schema = HubSchemaManager(old_settings)
                self.assertEqual(new_schema.apply(connection), 4)
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"SELECT hostname, fqdn, name, description, auto_sync_enabled "
                        f"FROM {hosts} WHERE machine_id=%s",
                        ("old-machine",),
                    )
                    self.assertEqual(
                        cursor.fetchone(),
                        ("old-host", "old-host.example.test", None, None, None),
                    )
        finally:
            with db.connect(include_database=False) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"DROP DATABASE IF EXISTS `{old_settings.database}`"
                    )
                connection.commit()

    def test_host_ui_metadata_is_never_overwritten_by_sync(self) -> None:
        hosts = table_identifier(self.settings, "hosts")
        first = replace(
            self._host("machine-metadata", "host-first"),
            auto_sync_enabled=True,
        )
        self.database.sync_core(first)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT name, description, auto_sync_enabled, "
                    f"COALESCE(NULLIF(name, ''), NULLIF(fqdn, ''), hostname) "
                    f"FROM {hosts} WHERE machine_id=%s",
                    ("machine-metadata",),
                )
                self.assertEqual(
                    cursor.fetchone(),
                    (None, None, 1, "host-first.example.test"),
                )
                cursor.execute(
                    f"UPDATE {hosts} SET name=%s, description=%s WHERE machine_id=%s",
                    ("Výrobní server", "# Provoz\n\nRuční popis v **Markdownu**.", "machine-metadata"),
                )
            connection.commit()

        renamed = replace(
            first,
            hostname="host-second",
            fqdn="host-second.example.test",
            auto_sync_enabled=False,
        )
        self.database.sync_core(renamed)
        self.database.sync_core(replace(renamed, auto_sync_enabled=None))
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT name, description, auto_sync_enabled, fqdn FROM {hosts} "
                    "WHERE machine_id=%s",
                    ("machine-metadata",),
                )
                self.assertEqual(
                    cursor.fetchone(),
                    (
                        "Výrobní server",
                        "# Provoz\n\nRuční popis v **Markdownu**.",
                        0,
                        "host-second.example.test",
                    ),
                )

    def test_single_service_provider_survives_core_and_cleans_own_key_only(self) -> None:
        host = replace(
            self._host("machine-service-inventory", "host-services"),
            services=(HubService("ssh", True, port=2222, status="active"),),
        )
        self.database.sync_core(host)
        first = self.database.sync_provider(
            host.machine_id,
            HubProviderSnapshot(
                "bacula_fd", "service",
                (HubService("bacula_fd", True, status="active", version="13.0"),),
            ),
        )
        self.assertEqual(first.item_count, 1)
        # A second core inventory must not delete third-party service records.
        self.database.sync_core(host)
        table = table_identifier(self.settings, "host_services")
        hosts = table_identifier(self.settings, "hosts")
        sources = table_identifier(self.settings, "sync_sources")
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT s.service_key, s.port, s.detected, s.status "
                    f"FROM {table} s JOIN {hosts} h ON s.host_id=h.id "
                    "WHERE h.machine_id=%s ORDER BY s.service_key",
                    (host.machine_id,),
                )
                self.assertEqual(
                    cursor.fetchall(),
                    (("bacula_fd", None, 1, "active"), ("ssh", 2222, 1, "active")),
                )
        # Reject provider attempts to take over a core-owned service.
        with self.assertRaises(ValueError):
            self.database.sync_provider(
                host.machine_id,
                HubProviderSnapshot("ssh", "service", (HubService("ssh", True),)),
            )
        with self.assertRaises(ValueError):
            self.database.sync_provider(
                host.machine_id,
                HubProviderSnapshot(
                    "bacula_fd", "service",
                    (HubService("other", True),),
                ),
            )
        # An absent service remains visible as detected=False.
        self.database.sync_provider(
            host.machine_id,
            HubProviderSnapshot(
                "bacula_fd", "service",
                (HubService("bacula_fd", False, status="absent"),),
            ),
        )
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT s.detected, s.status FROM {table} s "
                    f"JOIN {hosts} h ON s.host_id=h.id "
                    "WHERE h.machine_id=%s AND s.service_key=%s",
                    (host.machine_id, "bacula_fd"),
                )
                self.assertEqual(cursor.fetchone(), (0, "absent"))
        # A complete successful empty collector snapshot deletes only its row.
        self.database.sync_provider(
            host.machine_id,
            HubProviderSnapshot("bacula_fd", "service", ()),
        )
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT s.service_key FROM {table} s "
                    f"JOIN {hosts} h ON s.host_id=h.id "
                    "WHERE h.machine_id=%s",
                    (host.machine_id,),
                )
                self.assertEqual(cursor.fetchall(), (("ssh",),))
                cursor.execute(
                    f"SELECT source_key, status, item_count FROM {sources} s "
                    f"JOIN {hosts} h ON s.host_id=h.id "
                    "WHERE h.machine_id=%s AND source_key=%s",
                    (host.machine_id, "bacula_fd"),
                )
                self.assertEqual(cursor.fetchone(), ("bacula_fd", "ok", 0))

    def test_disconnected_catalog_names_sync_without_fake_attachment(self) -> None:
        first_time = datetime.now(timezone.utc).replace(microsecond=200000)
        second_time = first_time + timedelta(seconds=1)
        self.database.sync_core(self._host("machine-d", "host-d"))

        self.database.sync_provider(
            "machine-d",
            HubProviderSnapshot(
                "disks",
                "disks",
                (
                    HubDisk(
                        ptuuid="known-offline",
                        device_name="sdc",
                        device_path="/dev/sdc",
                        display_name="old_name",
                        name_updated_at=first_time,
                        size_bytes=5_000_000,
                        device_type="disk",
                        partition_count=2,
                        mountpoint_count=0,
                        is_system_disk=False,
                    ),
                ),
            ),
        )

        disks = table_identifier(self.settings, "disks")
        host_disks = table_identifier(self.settings, "host_disks")
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT size_bytes, last_seen_at FROM {disks} WHERE ptuuid=%s",
                    ("known-offline",),
                )
                original_size, original_last_seen = cursor.fetchone()

        result = self.database.sync_provider(
            "machine-d",
            HubProviderSnapshot(
                "disks",
                "disks",
                (
                    self._catalog_disk(
                        "known-offline", "renamed_offline", second_time
                    ),
                    self._catalog_disk(
                        "catalog-only", "image_template", second_time
                    ),
                ),
            ),
        )
        self.assertEqual(result.item_count, 2)

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT display_name, size_bytes, last_seen_at FROM {disks} "
                    "WHERE ptuuid=%s",
                    ("known-offline",),
                )
                name, size_bytes, last_seen_at = cursor.fetchone()
                self.assertEqual(name, "renamed_offline")
                self.assertEqual(size_bytes, original_size)
                self.assertEqual(last_seen_at, original_last_seen)
                cursor.execute(
                    f"SELECT display_name, size_bytes FROM {disks} WHERE ptuuid=%s",
                    ("catalog-only",),
                )
                self.assertEqual(cursor.fetchone(), ("image_template", 0))
                cursor.execute(
                    f"SELECT COUNT(*) FROM {host_disks} hd "
                    f"JOIN {disks} d ON d.id=hd.disk_id "
                    "WHERE d.ptuuid IN (%s, %s)",
                    ("known-offline", "catalog-only"),
                )
                self.assertEqual(cursor.fetchone()[0], 0)

    def test_duplicate_ptuuid_on_one_host_is_rejected_transactionally(self) -> None:
        self.database.sync_core(self._host("machine-c", "host-c"))
        duplicate = HubDisk(
            **{
                **self._disk("one", datetime.now(timezone.utc)).__dict__,
                "device_name": "sdc",
                "device_path": "/dev/sdc",
            }
        )
        with self.assertRaisesRegex(ValueError, "Duplicate PTUUID"):
            self.database.sync_provider(
                "machine-c",
                HubProviderSnapshot(
                    "disks",
                    "disks",
                    (
                        self._disk("one", datetime.now(timezone.utc)),
                        duplicate,
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()
