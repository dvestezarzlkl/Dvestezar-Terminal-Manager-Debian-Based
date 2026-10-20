import unittest

from libs.app.hub.schema import (
    load_migrations,
    split_migration_statements,
    table_identifier,
)
from libs.app.hub.settings import HubSettings


class HubSchemaTests(unittest.TestCase):
    def setUp(self):
        self.settings = HubSettings(
            enabled=True,
            host="db.internal.example",
            port=3306,
            user="sysapps",
            password="secret",
            database="sys_apps",
            prefix="hub_",
            connect_timeout=3,
            auto_sync=True,
        )

    def test_migrations_use_only_validated_prefix_placeholder(self):
        migrations = load_migrations()
        self.assertEqual([item.version for item in migrations], [1, 2, 3, 4, 5])
        initial = migrations[0].render(self.settings.prefix)
        disks = migrations[1].render(self.settings.prefix)
        service_host = migrations[2].render(self.settings.prefix)
        metadata = migrations[3].render(self.settings.prefix)
        groups = migrations[4].render(self.settings.prefix)
        self.assertEqual(len(initial), 7)
        self.assertEqual(len(disks), 2)
        self.assertEqual(len(service_host), 1)
        self.assertEqual(len(metadata), 1)
        self.assertEqual(len(groups), 2)
        self.assertIn("CREATE TABLE IF NOT EXISTS `hub_host_groups`", groups[0])
        self.assertIn("`id` INT UNSIGNED", groups[0])
        self.assertIn("UNIQUE KEY `uq_host_groups_code`", groups[0])
        self.assertIn("ADD COLUMN `group_id` INT UNSIGNED NULL DEFAULT NULL", groups[1])
        self.assertIn("ON DELETE SET NULL", groups[1])
        self.assertIn("USER-OWNED", groups[1])
        self.assertIn("`name` VARCHAR(255) NULL", metadata[0])
        self.assertIn("`description` TEXT NULL", metadata[0])
        self.assertIn("`auto_sync_enabled` TINYINT(1) NULL", metadata[0])
        self.assertIn("Never synchronized or overwritten", metadata[0])
        self.assertTrue(any("`hub_hosts`" in item for item in initial))
        self.assertTrue(any("`hub_disks`" in item for item in disks))
        self.assertTrue(any("`hub_host_disks`" in item for item in disks))
        self.assertTrue(any("UNIQUE KEY `uq_host_disk` (`disk_id`)" in item for item in disks))
        self.assertTrue(any("`service_host` VARCHAR(255)" in item for item in service_host))
        self.assertTrue(any("`idx_hosts_service_host`" in item for item in service_host))
        self.assertTrue(
            all(
                "{{PREFIX}}" not in statement
                for migration in migrations
                for statement in migration.render(self.settings.prefix)
            )
        )

    def test_only_additive_migration_005_may_be_pending(self):
        from libs.app.hub.schema import HubSchemaManager

        class Cursor:
            def __init__(self, checksums):
                self.checksums = checksums

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                self.sql = sql

            def fetchone(self):
                return (1,)

            def fetchall(self):
                return sorted(self.checksums.items())

        class Connection:
            def __init__(self, checksums):
                self.checksums = checksums

            def cursor(self):
                return Cursor(self.checksums)

        manager = HubSchemaManager(self.settings)
        known = {m.version: m.checksum for m in manager.migrations}
        pending_005 = manager.check(Connection({
            k: v for k, v in known.items() if k <= 4
        }))
        self.assertTrue(pending_005.current)
        self.assertEqual((pending_005.current_version, pending_005.latest_version), (4, 5))

        missing_mandatory_004 = manager.check(Connection({
            k: v for k, v in known.items() if k <= 3
        }))
        self.assertFalse(missing_mandatory_004.current)

        unexpected_future = manager.check(Connection({
            **known, 6: "0" * 64
        }))
        self.assertFalse(unexpected_future.current)
        self.assertIn("Unsupported schema migrations", unexpected_future.error)

        corrupted_checksum = manager.check(Connection({
            **known, 5: "0" * 64
        }))
        self.assertFalse(corrupted_checksum.current)
        self.assertIn("Checksum mismatch", corrupted_checksum.error)

    def test_statement_marker_is_explicit(self):
        statements = split_migration_statements(
            "-- heading\n-- statement\nSELECT 1\n-- statement\nSELECT 2"
        )
        self.assertEqual(statements, ("SELECT 1", "SELECT 2"))

    def test_table_identifier_accepts_only_fixed_suffixes(self):
        self.assertEqual(table_identifier(self.settings, "hosts"), "`hub_hosts`")
        self.assertEqual(table_identifier(self.settings, "host_groups"), "`hub_host_groups`")
        self.assertEqual(table_identifier(self.settings, "disks"), "`hub_disks`")
        self.assertEqual(
            table_identifier(self.settings, "host_disks"), "`hub_host_disks`"
        )
        with self.assertRaises(ValueError):
            table_identifier(self.settings, "hosts;DROP TABLE users")


if __name__ == "__main__":
    unittest.main()
