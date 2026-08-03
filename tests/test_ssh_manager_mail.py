from __future__ import annotations

import io
import unittest
import zipfile
from unittest.mock import patch

from libs.app.menus.app_30_ssh import ssh_mail_hlp


PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestPayload user@example"
PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nprivate-test-data\n-----END OPENSSH PRIVATE KEY-----"


class SshManagerMailTests(unittest.TestCase):
    def zip_files(self, attachment):
        with zipfile.ZipFile(io.BytesIO(attachment.read_bytes()), "r") as archive:
            return {
                name: archive.read(name).decode("utf-8")
                for name in archive.namelist()
            }

    def test_private_key_mail_contains_zip_but_not_key_material_in_body(self):
        subject, text_body, html_body, attachments = ssh_mail_hlp.build_key_mail_payload(
            "alice",
            "work-key",
            PUBLIC_KEY,
            PRIVATE_KEY,
            "alice@example.test",
        )

        self.assertIn("alice", subject)
        self.assertNotIn(PUBLIC_KEY, text_body)
        self.assertNotIn(PRIVATE_KEY, text_body)
        self.assertNotIn(PUBLIC_KEY, html_body)
        self.assertNotIn(PRIVATE_KEY, html_body)
        self.assertEqual(len(attachments), 1)
        self.assertEqual(
            attachments[0].safe_filename(),
            "alice_work-key_ssh_keys.zip",
        )

        files = self.zip_files(attachments[0])
        self.assertEqual(
            set(files),
            {
                "alice_work-key_id_ed25519",
                "alice_work-key_id_ed25519.pub",
                "alice_work-key_README.txt",
            },
        )
        readme = files["alice_work-key_README.txt"]
        self.assertIn("22", readme)
        self.assertIn("Total Commander", readme)
        self.assertIn("WinSCP", readme)

    def test_public_only_mail_has_no_private_file_or_client_setup_steps(self):
        _, _, _, attachments = ssh_mail_hlp.build_key_mail_payload(
            "alice",
            "imported",
            PUBLIC_KEY,
            "",
            "alice@example.test",
        )
        files = self.zip_files(attachments[0])
        self.assertEqual(
            set(files),
            {
                "alice_imported_id_ed25519.pub",
                "alice_imported_README.txt",
            },
        )
        readme = files["alice_imported_README.txt"]
        self.assertNotIn("Total Commander", readme)
        self.assertNotIn("WinSCP", readme)
        self.assertIn("alice_imported_id_ed25519.pub", readme)

    def test_send_uses_only_configured_recipient(self):
        with patch.object(
            ssh_mail_hlp.ssh_key_bundle,
            "read_managed_key_pair",
            return_value=(True, (PUBLIC_KEY, PRIVATE_KEY), None),
        ), patch.object(
            ssh_mail_hlp.mail_hlp,
            "send_mail",
            return_value=(True, None),
        ) as send_mail:
            ok, error = ssh_mail_hlp.send_managed_key_by_mail(
                "alice",
                "work-key",
                "alice@example.test",
            )

        self.assertTrue(ok, error)
        self.assertEqual(send_mail.call_args.args[0], ["alice@example.test"])
        self.assertEqual(len(send_mail.call_args.kwargs["attachments"]), 1)

    def test_invalid_recipient_is_rejected_before_key_read(self):
        with patch.object(
            ssh_mail_hlp.ssh_key_bundle,
            "read_managed_key_pair",
        ) as read_pair:
            ok, error = ssh_mail_hlp.send_managed_key_by_mail(
                "alice",
                "work-key",
                "invalid",
            )
        self.assertFalse(ok)
        self.assertTrue(error)
        read_pair.assert_not_called()


if __name__ == "__main__":
    unittest.main()
