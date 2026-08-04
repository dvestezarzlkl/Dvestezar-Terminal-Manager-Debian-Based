import unittest
from unittest.mock import patch

from libs.app import cfg
from libs.app.hub.settings import HubSettings
from libs.app.settings_package import (
    apply_decoded_settings,
    decode_encrypted_settings,
    export_encrypted_settings,
    preview_decoded_settings,
    validate_settings_url,
)


_CONFIG_KEYS = (
    "HUB_ENABLED",
    "HUB_DB_HOST",
    "HUB_DB_PORT",
    "HUB_DB_USER",
    "HUB_DB_PASSWORD",
    "HUB_DB_NAME",
    "HUB_DB_PREFIX",
    "HUB_CONNECT_TIMEOUT",
    "HUB_AUTO_SYNC",
    "MAIL_SMTP_HOST",
    "MAIL_SMTP_PORT",
    "MAIL_SMTP_USER",
    "MAIL_SMTP_PASSWORD",
    "MAIL_SMTP_MODE",
    "MAIL_FROM",
    "MAIL_FALLBACK_ADMIN",
    "MAIL_TIMEOUT",
    "SETTINGS_LAST_REVISION",
    "SETTINGS_LAST_SHA256",
)


class SettingsPackageTests(unittest.TestCase):
    def setUp(self):
        self.previous = {key: getattr(cfg, key) for key in _CONFIG_KEYS}
        cfg.HUB_ENABLED = True
        cfg.HUB_DB_HOST = "db.internal.example"
        cfg.HUB_DB_PORT = 3306
        cfg.HUB_DB_USER = "sysapps"
        cfg.HUB_DB_PASSWORD = "database-secret"
        cfg.HUB_DB_NAME = "sys_apps"
        cfg.HUB_DB_PREFIX = "sysapps_"
        cfg.HUB_CONNECT_TIMEOUT = 3
        cfg.HUB_AUTO_SYNC = True
        cfg.MAIL_SMTP_HOST = "smtp.internal.example"
        cfg.MAIL_SMTP_PORT = 587
        cfg.MAIL_SMTP_USER = "sysapps@example.test"
        cfg.MAIL_SMTP_PASSWORD = "smtp-secret"
        cfg.MAIL_SMTP_MODE = "starttls"
        cfg.MAIL_FROM = "sysapps@example.test"
        cfg.MAIL_FALLBACK_ADMIN = "admin@example.test"
        cfg.MAIL_TIMEOUT = 20
        cfg.SETTINGS_LAST_REVISION = 0
        cfg.SETTINGS_LAST_SHA256 = ""

    def tearDown(self):
        for key, value in self.previous.items():
            setattr(cfg, key, value)

    def test_roundtrip_contains_hub_and_smtp_without_plaintext_secrets(self):
        package = export_encrypted_settings("package-password", revision=42)
        self.assertTrue(package.startswith("SYSAPP1E:"))
        self.assertNotIn("database-secret", package)
        self.assertNotIn("smtp-secret", package)
        self.assertNotIn("\n", package)

        decoded = decode_encrypted_settings(package, "package-password")
        self.assertEqual(decoded.revision, 42)
        self.assertEqual(set(decoded.sections), {"hub", "smtp"})
        preview = "\n".join(preview_decoded_settings(decoded))
        self.assertIn("password=set", preview)
        self.assertNotIn("database-secret", preview)
        self.assertNotIn("smtp-secret", preview)

    def test_wrong_password_is_rejected(self):
        package = export_encrypted_settings("correct", revision=1)
        with self.assertRaisesRegex(ValueError, "Wrong package password"):
            decode_encrypted_settings(package, "wrong")

    def test_same_revision_with_different_content_is_rejected(self):
        first = export_encrypted_settings("pw", revision=7)
        decoded_first = decode_encrypted_settings(first, "pw")
        with patch("libs.app.settings_package.cfg.save"):
            apply_decoded_settings(decoded_first)

        cfg.MAIL_SMTP_HOST = "changed.example"
        second = export_encrypted_settings("pw", revision=7)
        decoded_second = decode_encrypted_settings(second, "pw")
        with self.assertRaisesRegex(ValueError, "different content"):
            apply_decoded_settings(decoded_second)

    def test_older_revision_requires_explicit_manual_downgrade(self):
        cfg.SETTINGS_LAST_REVISION = 10
        cfg.SETTINGS_LAST_SHA256 = "other"
        package = export_encrypted_settings("pw", revision=9)
        decoded = decode_encrypted_settings(package, "pw")
        with self.assertRaisesRegex(ValueError, "older than local"):
            apply_decoded_settings(decoded)
        with patch("libs.app.settings_package.cfg.save"):
            report = apply_decoded_settings(decoded, allow_downgrade=True, force=True)
        self.assertTrue(report.changed)
        self.assertEqual(cfg.SETTINGS_LAST_REVISION, 9)

    def test_disabled_unconfigured_hub_can_be_exported(self):
        settings = HubSettings(
            enabled=False,
            host="",
            port=3306,
            user="",
            password="",
            database="sys_apps",
            prefix="sysapps_",
            connect_timeout=3,
            auto_sync=True,
        )
        self.assertEqual(settings.validate(), (True, ""))
        cfg.HUB_ENABLED = False
        cfg.HUB_DB_HOST = ""
        cfg.HUB_DB_USER = ""
        package = export_encrypted_settings("pw", revision=1)
        decoded = decode_encrypted_settings(package, "pw")
        self.assertFalse(decoded.sections["hub"]["data"]["enabled"])

    def test_url_policy_requires_https_by_default(self):
        self.assertEqual(
            validate_settings_url("https://config.example/settings"),
            "https://config.example/settings",
        )
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            validate_settings_url("http://config.example/settings")
        self.assertEqual(
            validate_settings_url(
                "http://config.internal/settings", allow_http=True
            ),
            "http://config.internal/settings",
        )
        with self.assertRaisesRegex(ValueError, "embedded"):
            validate_settings_url("https://user:password@config.example/settings")


if __name__ == "__main__":
    unittest.main()
