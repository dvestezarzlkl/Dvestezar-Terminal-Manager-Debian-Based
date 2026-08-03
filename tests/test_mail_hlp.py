from __future__ import annotations

import unittest
from unittest.mock import patch

from libs.app import mail_hlp


class MailHelperTests(unittest.TestCase):
    def configured_mail(self, *, port=465, mode="ssl"):
        return patch.multiple(
            mail_hlp.app_cfg,
            MAIL_SMTP_HOST="smtp.example.test",
            MAIL_SMTP_PORT=port,
            MAIL_SMTP_USER="service@example.test",
            MAIL_SMTP_PASSWORD="secret-value",
            MAIL_SMTP_MODE=mode,
            MAIL_FROM="",
            MAIL_TIMEOUT=12,
        )

    def test_get_smtp_settings_uses_global_config(self):
        with self.configured_mail():
            settings = mail_hlp.get_smtp_settings()

        self.assertEqual(settings.host, "smtp.example.test")
        self.assertEqual(settings.port, 465)
        self.assertEqual(settings.mode, "ssl")
        self.assertEqual(settings.username, "service@example.test")
        self.assertEqual(settings.password, "secret-value")
        self.assertEqual(settings.timeout, 12)
        self.assertNotIn("secret-value", repr(settings))

    def test_send_mail_forwards_attachments_and_keeps_invalid_reply_to_compatible(self):
        attachment = mail_hlp.MailAttachment.from_bytes(
            "protocol.txt",
            b"instance protocol",
            "text/plain",
        )
        with self.configured_mail(), patch.object(
            mail_hlp,
            "send_smtp_message",
            return_value=(True, None),
        ) as sender:
            ok, error = mail_hlp.send_mail(
                ["recipient@example.test"],
                "Subject",
                "Body",
                reply_to="not-an-address",
                attachments=[attachment],
            )

        self.assertTrue(ok)
        self.assertIsNone(error)
        kwargs = sender.call_args.kwargs
        self.assertEqual(kwargs["mail_from"], "service@example.test")
        self.assertEqual(kwargs["recipients"], ["recipient@example.test"])
        self.assertIsNone(kwargs["reply_to"])
        self.assertEqual(kwargs["attachments"], [attachment])
        self.assertEqual(kwargs["smtp_settings"].timeout, 12)

    def test_send_mail_preserves_port_hint(self):
        with self.configured_mail(port=993, mode="ssl"), patch.object(
            mail_hlp,
            "send_smtp_message",
            return_value=(False, "Failed to send mail via SMTP: connection refused"),
        ):
            ok, error = mail_hlp.send_mail(
                ["recipient@example.test"],
                "Subject",
                "Body",
            )

        self.assertFalse(ok)
        self.assertIsNotNone(error)
        self.assertIn("port 993", error)
        self.assertIn("expected 465", error)

    def test_send_mail_rejects_missing_to_recipient_before_transport(self):
        with self.configured_mail(), patch.object(
            mail_hlp,
            "send_smtp_message",
        ) as sender:
            ok, error = mail_hlp.send_mail([], "Subject", "Body")

        self.assertFalse(ok)
        self.assertEqual(error, "No mail recipients configured.")
        sender.assert_not_called()

    def test_zip_helpers_are_reexported_for_application_menus(self):
        archive = mail_hlp.create_zip_attachment(
            "keys.zip",
            [
                mail_hlp.ZipItem("private.key", b"private"),
                mail_hlp.ZipItem("public.key", b"public"),
            ],
        )
        self.assertEqual(archive.safe_filename(), "keys.zip")
        self.assertEqual(archive.mime_type(), ("application", "zip"))


if __name__ == "__main__":
    unittest.main()
