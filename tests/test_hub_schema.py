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

    def test_initial_migration_uses_only_validated_prefix_placeholder(self):
        migrations = load_migrations()
        self.assertEqual([item.version for item in migrations], [1])
        statements = migrations[0].render(self.settings.prefix)
        self.assertEqual(len(statements), 7)
        self.assertTrue(any("`hub_hosts`" in item for item in statements))
        self.assertTrue(all("{{PREFIX}}" not in item for item in statements))

    def test_statement_marker_is_explicit(self):
        statements = split_migration_statements(
            "-- heading\n-- statement\nSELECT 1\n-- statement\nSELECT 2"
        )
        self.assertEqual(statements, ("SELECT 1", "SELECT 2"))

    def test_table_identifier_accepts_only_fixed_suffixes(self):
        self.assertEqual(table_identifier(self.settings, "hosts"), "`hub_hosts`")
        with self.assertRaises(ValueError):
            table_identifier(self.settings, "hosts;DROP TABLE users")


if __name__ == "__main__":
    unittest.main()
