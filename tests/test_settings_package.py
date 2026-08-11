import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.request import Request

from libs.app import cfg
from libs.app import settings_package as settings_package_module
from libs.app.hub.config_package import export_encrypted_settings as export_legacy_hub_settings
from libs.app.hub.settings import HubSettings
from libs.app.settings_package import (
    DecodedSettingsPackage,
    SettingsImportPolicy,
    SettingsSectionHandler,
    apply_decoded_settings,
    decode_encrypted_settings,
    detect_import_conflicts,
    download_settings_package,
    export_encrypted_settings,
    load_settings_import_policy,
    preview_decoded_settings,
    serialize_settings_import_policy,
    settings_section_label,
    settings_section_policy_fields,
    update_from_central_url,
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
    "SETTINGS_AUTH_USER",
    "SETTINGS_AUTH_PASSWORD",
    "SETTINGS_URL",
    "SETTINGS_PASSWORD",
    "SETTINGS_IMPORT_POLICY",
    "SETTINGS_LAST_REVISION",
    "SETTINGS_LAST_SHA256",
    "SETTINGS_LAST_APPLIED",
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
        cfg.SETTINGS_AUTH_USER = "http-user"
        cfg.SETTINGS_AUTH_PASSWORD = "http-secret"
        cfg.SETTINGS_URL = ""
        cfg.SETTINGS_PASSWORD = ""
        cfg.SETTINGS_IMPORT_POLICY = "{}"
        cfg.SETTINGS_LAST_REVISION = 0
        cfg.SETTINGS_LAST_SHA256 = ""
        cfg.SETTINGS_LAST_APPLIED = ""

    def tearDown(self):
        for key, value in self.previous.items():
            setattr(cfg, key, value)

    def test_registered_section_labels_are_human_readable(self):
        self.assertEqual(settings_section_label("hub"), "SysApps Hub")
        self.assertEqual(settings_section_label("smtp"), "SMTP")
        self.assertEqual(settings_section_label("future_section"), "future_section")

    def test_import_policy_roundtrip_and_registered_fields(self):
        policy = SettingsImportPolicy(
            skip_fields=(("smtp", ("from_address",)),)
        )
        cfg.SETTINGS_IMPORT_POLICY = serialize_settings_import_policy(policy)
        loaded = load_settings_import_policy()
        self.assertEqual(loaded, policy)
        fields = settings_section_policy_fields("smtp")
        self.assertEqual(
            [(item.key, item.config_key) for item in fields],
            [("from_address", "MAIL_FROM")],
        )

    def test_roundtrip_contains_hub_and_smtp_without_plaintext_secrets(self):
        package = export_encrypted_settings("package-password", revision=42)
        self.assertTrue(package.startswith("SYSAPP1E:"))
        self.assertNotIn("database-secret", package)
        self.assertNotIn("smtp-secret", package)
        self.assertNotIn("http-user", package)
        self.assertNotIn("http-secret", package)
        self.assertNotIn("\n", package)

        decoded = decode_encrypted_settings(package, "package-password")
        self.assertEqual(decoded.revision, 42)
        self.assertEqual(set(decoded.sections), {"hub", "smtp"})
        preview = "\n".join(preview_decoded_settings(decoded))
        self.assertIn("password=set", preview)
        self.assertNotIn("database-secret", preview)
        self.assertNotIn("smtp-secret", preview)

    def test_generated_revisions_strictly_increase(self):
        first = decode_encrypted_settings(
            export_encrypted_settings("password1"), "password1"
        )
        second = decode_encrypted_settings(
            export_encrypted_settings("password1"), "password1"
        )
        self.assertGreater(second.revision, first.revision)

    def test_legacy_hub_import_invalidates_current_central_hash(self):
        cfg.SETTINGS_LAST_REVISION = 42
        cfg.SETTINGS_LAST_SHA256 = "current-central-package"
        legacy = export_legacy_hub_settings(
            HubSettings.from_cfg(), "password1"
        )
        decoded = decode_encrypted_settings(legacy, "password1")
        self.assertTrue(decoded.legacy)
        with patch("libs.app.settings_package.cfg.save"):
            report = apply_decoded_settings(decoded, force=True)
        self.assertTrue(report.changed)
        self.assertEqual(cfg.SETTINGS_LAST_REVISION, 42)
        self.assertEqual(cfg.SETTINGS_LAST_SHA256, "")

    def test_unknown_future_section_is_skipped_with_warning(self):
        package = export_encrypted_settings("password1", revision=43)
        decoded = decode_encrypted_settings(package, "password1")
        future = DecodedSettingsPackage(
            revision=decoded.revision,
            created_at=decoded.created_at,
            sections={
                **decoded.sections,
                "sftp_backup": {
                    "version": 1,
                    "data": {"profile": "central_backup"},
                },
            },
            sha256=decoded.sha256,
        )
        with patch("libs.app.settings_package.cfg.save"):
            report = apply_decoded_settings(future)
        self.assertEqual(set(report.applied_sections), {"hub", "smtp"})
        self.assertEqual(report.skipped_sections, ("sftp_backup",))
        self.assertTrue(any("sftp_backup" in item for item in report.warnings))
        self.assertEqual(cfg.SETTINGS_LAST_APPLIED, "hub:1,smtp:1")

        apply_sftp = Mock()
        handler = SettingsSectionHandler(
            key="sftp_backup",
            label="SFTP backup",
            version=1,
            config_keys=(),
            exporter=lambda: {},
            validator=lambda data: dict(data),
            applier=apply_sftp,
            previewer=lambda data: "configured",
        )
        with patch.dict(
            settings_package_module._SECTIONS,
            {"sftp_backup": handler},
            clear=False,
        ), patch("libs.app.settings_package.cfg.save"):
            upgraded = apply_decoded_settings(future)
        self.assertTrue(upgraded.changed)
        self.assertEqual(
            set(upgraded.applied_sections), {"hub", "smtp", "sftp_backup"}
        )
        self.assertEqual(
            cfg.SETTINGS_LAST_APPLIED, "hub:1,sftp_backup:1,smtp:1"
        )
        apply_sftp.assert_called_once_with({"profile": "central_backup"})

    def test_local_policy_skips_smtp_and_same_revision_retries_after_change(self):
        cfg.HUB_AUTO_SYNC = False
        cfg.MAIL_SMTP_HOST = "central.example.test"
        cfg.MAIL_FROM = "central@example.test"
        package = export_encrypted_settings("pw", revision=50)
        decoded = decode_encrypted_settings(package, "pw")

        cfg.HUB_AUTO_SYNC = True
        cfg.MAIL_SMTP_HOST = "local.example.test"
        cfg.MAIL_FROM = "local@example.test"
        policy = SettingsImportPolicy(skip_sections=("smtp",))
        with patch("libs.app.settings_package.cfg.save"):
            report = apply_decoded_settings(decoded, import_policy=policy)

        self.assertTrue(report.changed)
        self.assertFalse(cfg.HUB_AUTO_SYNC)
        self.assertEqual(cfg.MAIL_SMTP_HOST, "local.example.test")
        self.assertEqual(cfg.MAIL_FROM, "local@example.test")
        self.assertEqual(cfg.SETTINGS_LAST_APPLIED, "hub:1,smtp:skip")

        cfg.SETTINGS_LAST_APPLIED = ""
        with patch("libs.app.settings_package.cfg.save"):
            retried = apply_decoded_settings(
                decoded, import_policy=SettingsImportPolicy()
            )

        self.assertTrue(retried.changed)
        self.assertEqual(cfg.MAIL_SMTP_HOST, "central.example.test")
        self.assertEqual(cfg.MAIL_FROM, "central@example.test")
        self.assertEqual(cfg.SETTINGS_LAST_APPLIED, "hub:1,smtp:1")

    def test_local_policy_preserves_only_smtp_from_address(self):
        cfg.MAIL_SMTP_HOST = "central.example.test"
        cfg.MAIL_SMTP_PORT = 465
        cfg.MAIL_SMTP_MODE = "ssl"
        cfg.MAIL_FROM = "central@example.test"
        package = export_encrypted_settings("pw", revision=51)
        decoded = decode_encrypted_settings(package, "pw")

        cfg.MAIL_SMTP_HOST = "local.example.test"
        cfg.MAIL_SMTP_PORT = 587
        cfg.MAIL_SMTP_MODE = "starttls"
        cfg.MAIL_FROM = "local@example.test"
        policy = SettingsImportPolicy(
            skip_fields=(("smtp", ("from_address",)),)
        )

        conflicts = detect_import_conflicts(decoded, policy)
        self.assertEqual(
            {item.field_key for item in conflicts},
            {"host"},
        )
        preview = "\n".join(preview_decoded_settings(decoded, policy))
        self.assertIn("local policy keeps SMTP From address", preview)

        with patch("libs.app.settings_package.cfg.save"):
            report = apply_decoded_settings(decoded, import_policy=policy)

        self.assertTrue(report.changed)
        self.assertEqual(cfg.MAIL_SMTP_HOST, "central.example.test")
        self.assertEqual(cfg.MAIL_SMTP_PORT, 465)
        self.assertEqual(cfg.MAIL_SMTP_MODE, "ssl")
        self.assertEqual(cfg.MAIL_FROM, "local@example.test")
        self.assertEqual(
            cfg.SETTINGS_LAST_APPLIED,
            "hub:1,smtp:1[keep=from_address]",
        )

    def test_local_policy_can_record_revision_with_all_sections_skipped(self):
        package = export_encrypted_settings("pw", revision=52)
        decoded = decode_encrypted_settings(package, "pw")
        policy = SettingsImportPolicy(skip_sections=("hub", "smtp"))

        with patch("libs.app.settings_package.cfg.save"):
            report = apply_decoded_settings(decoded, import_policy=policy)

        self.assertTrue(report.changed)
        self.assertEqual(report.applied_sections, ())
        self.assertEqual(cfg.SETTINGS_LAST_REVISION, 52)
        self.assertEqual(cfg.SETTINGS_LAST_APPLIED, "hub:skip,smtp:skip")

    def test_wrong_password_is_rejected(self):
        package = export_encrypted_settings("correct", revision=1)
        with self.assertRaisesRegex(ValueError, "Wrong package password"):
            decode_encrypted_settings(package, "wrong")

    def test_malformed_transport_is_reported_as_package_error(self):
        with self.assertRaisesRegex(ValueError, "Invalid SysApps settings package"):
            decode_encrypted_settings("SYSAPP1E:%%%not-base64%%%", "password1")

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

    def test_download_sends_basic_auth_only_in_authorization_header(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.geturl.return_value = "https://config.example/hidden-path"
        response.headers = {}
        response.read.return_value = b"SYSAPP1E:test"
        opener = MagicMock()
        opener.open.return_value = response

        with patch(
            "libs.app.settings_package.build_opener", return_value=opener
        ):
            package = download_settings_package(
                "https://config.example/hidden-path",
                auth_user="sysapps",
                auth_password="secret123",
            )

        self.assertEqual(package, "SYSAPP1E:test")
        request = opener.open.call_args.args[0]
        self.assertEqual(
            request.get_header("Authorization"),
            "Basic c3lzYXBwczpzZWNyZXQxMjM=",
        )
        self.assertNotIn("sysapps", request.full_url)
        self.assertNotIn("secret123", request.full_url)

    def test_incomplete_basic_auth_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must both be configured"):
            download_settings_package(
                "https://config.example/settings",
                auth_user="sysapps",
            )

    def test_redirect_handler_keeps_auth_only_on_same_origin(self):
        handler = settings_package_module._SameOriginRedirectHandler()
        request = Request("https://config.example/private/settings")
        request.add_unredirected_header("Authorization", "Basic token")

        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://config.example/rewritten/settings",
        )
        self.assertEqual(redirected.get_header("Authorization"), "Basic token")

        with self.assertRaisesRegex(ValueError, "different origin"):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://other.example/settings",
            )

    def test_smtp_conflicts_require_existing_local_identity(self):
        cfg.MAIL_SMTP_HOST = "central.example.test"
        cfg.MAIL_FROM = "central@example.test"
        package = export_encrypted_settings("pw", revision=75)
        decoded = decode_encrypted_settings(package, "pw")

        cfg.MAIL_SMTP_HOST = "local.example.test"
        cfg.MAIL_FROM = "local@example.test"
        conflicts = detect_import_conflicts(decoded)
        self.assertEqual(
            {item.field_key for item in conflicts},
            {"host", "from_address"},
        )

        cfg.MAIL_SMTP_HOST = ""
        cfg.MAIL_FROM = ""
        self.assertEqual(detect_import_conflicts(decoded), ())

    def test_central_update_logs_operational_phase_boundaries(self):
        package = export_encrypted_settings("pw", revision=77)
        cfg.SETTINGS_URL = "https://config.example/private/settings"
        cfg.SETTINGS_PASSWORD = "pw"

        with patch(
            "libs.app.settings_package.download_settings_package",
            return_value=package,
        ), patch("libs.app.settings_package.cfg.save"), patch(
            "libs.app.settings_package.log.info"
        ) as info_log:
            result = update_from_central_url()

        self.assertTrue(result.changed)
        messages = [call.args[0] for call in info_log.call_args_list]
        self.assertIn("Central settings update: start (force=%s)", messages)
        self.assertIn("Central settings decode: start", messages)
        self.assertIn("Central settings policy/conflict evaluation: start", messages)
        self.assertIn("Central settings apply: start", messages)
        self.assertIn("Central settings update: done in %.3fs (changed=%s, revision=%d, warnings=%d)", messages)

    def test_automatic_import_skips_conflicting_smtp_then_retries_same_revision(self):
        cfg.HUB_AUTO_SYNC = False
        cfg.MAIL_SMTP_HOST = "central.example.test"
        cfg.MAIL_FROM = "central@example.test"
        package = export_encrypted_settings("pw", revision=76)

        cfg.HUB_AUTO_SYNC = True
        cfg.MAIL_SMTP_HOST = "local.example.test"
        cfg.MAIL_FROM = "local@example.test"
        cfg.SETTINGS_URL = "https://config.example/settings"
        cfg.SETTINGS_PASSWORD = "pw"

        with patch(
            "libs.app.settings_package.download_settings_package",
            return_value=package,
        ), patch("libs.app.settings_package.cfg.save"):
            result = update_from_central_url()

        self.assertTrue(result.changed)
        self.assertFalse(cfg.HUB_AUTO_SYNC)
        self.assertEqual(cfg.MAIL_SMTP_HOST, "local.example.test")
        self.assertEqual(cfg.MAIL_FROM, "local@example.test")
        self.assertEqual(cfg.SETTINGS_LAST_APPLIED, "hub:1")
        self.assertTrue(any("SMTP section skipped" in item for item in result.warnings))

        cfg.MAIL_SMTP_HOST = ""
        cfg.MAIL_FROM = ""
        with patch(
            "libs.app.settings_package.download_settings_package",
            return_value=package,
        ), patch("libs.app.settings_package.cfg.save"):
            retried = update_from_central_url()

        self.assertTrue(retried.changed)
        self.assertEqual(cfg.MAIL_SMTP_HOST, "central.example.test")
        self.assertEqual(cfg.MAIL_FROM, "central@example.test")
        self.assertEqual(cfg.SETTINGS_LAST_APPLIED, "hub:1,smtp:1")


if __name__ == "__main__":
    unittest.main()
