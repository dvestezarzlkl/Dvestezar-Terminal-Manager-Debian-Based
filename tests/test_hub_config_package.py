import unittest

from libs.app.hub.config_package import (
    export_encrypted_settings,
    import_encrypted_settings,
)
from libs.app.hub.settings import HubSettings


class HubConfigPackageTests(unittest.TestCase):
    def setUp(self):
        self.settings = HubSettings(
            enabled=True,
            host="db.internal.example",
            port=3306,
            user="sysapps",
            password="database-secret",
            database="sys_apps",
            prefix="sysapps_",
            connect_timeout=3,
            auto_sync=True,
        )

    def test_encrypted_roundtrip_is_one_line_and_hides_database_password(self):
        package = export_encrypted_settings(self.settings, "package-password")
        self.assertTrue(package.startswith("SYSHUB1E:"))
        self.assertNotIn("\n", package)
        self.assertNotIn("database-secret", package)

        decoded = import_encrypted_settings(package, "package-password")
        self.assertEqual(decoded, self.settings.export_dict())

    def test_wrong_password_is_rejected(self):
        package = export_encrypted_settings(self.settings, "correct-password")
        with self.assertRaisesRegex(ValueError, "Wrong package password"):
            import_encrypted_settings(package, "wrong-password")

    def test_prefix_is_strictly_validated(self):
        invalid = HubSettings(
            **{**self.settings.export_dict(), "prefix": "bad-prefix;DROP"}
        )
        ok, error = invalid.validate()
        self.assertFalse(ok)
        self.assertIn("Table prefix", error)


if __name__ == "__main__":
    unittest.main()
