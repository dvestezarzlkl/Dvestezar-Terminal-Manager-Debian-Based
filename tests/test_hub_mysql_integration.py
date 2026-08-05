from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import unittest

from libs.app.hub.database import HubDatabase
from libs.app.hub.models import (
    HubDisk,
    HubHostSnapshot,
    HubProviderSnapshot,
)
from libs.app.hub.schema import table_identifier
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
        if version != 2:
            raise AssertionError(f"Expected schema version 2, got {version}")

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
                cursor.execute(f"SELECT MAX(version) FROM {migrations}")
                self.assertEqual(cursor.fetchone()[0], 2)

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
