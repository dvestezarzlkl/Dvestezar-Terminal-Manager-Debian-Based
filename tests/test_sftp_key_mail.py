from __future__ import annotations

import io
import unittest
import zipfile
from unittest.mock import patch

from libs.app.menus.app_33_sftpmanagr import sftp_manager_hlp as sftp_hlp


PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestPayload user@example"
PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nprivate-test-data\n-----END OPENSSH PRIVATE KEY-----"


class SftpKeyMailTests(unittest.TestCase):
    def zip_files(self, attachment):
        with zipfile.ZipFile(io.BytesIO(attachment.read_bytes()), "r") as archive:
            return {
                name: archive.read(name).decode("utf-8")
                for name in archive.namelist()
            }

    def test_private_key_pair_is_attached_and_not_exposed_in_body(self):
        subject, text_body, html_body, attachments = sftp_hlp.build_key_mail_payload(
            "team/user",
            PUBLIC_KEY,
            PRIVATE_KEY,
            ["admin@example.test", "user@example.test"],
        )

        self.assertIn("team/user", subject)
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].safe_filename(), "team_user_sftp_keys.zip")
        self.assertNotIn(PUBLIC_KEY, text_body)
        self.assertNotIn(PRIVATE_KEY, text_body)
        self.assertNotIn(PUBLIC_KEY, html_body)
        self.assertNotIn(PRIVATE_KEY, html_body)

        files = self.zip_files(attachments[0])
        self.assertEqual(
            set(files),
            {
                "team_user_id_ed25519",
                "team_user_id_ed25519.pub",
                "team_user_README.txt",
            },
        )
        self.assertEqual(files["team_user_id_ed25519"].strip(), PRIVATE_KEY)
        self.assertEqual(files["team_user_id_ed25519.pub"].strip(), PUBLIC_KEY)
        self.assertIn("team_user_id_ed25519", files["team_user_README.txt"])
        self.assertIn("chmod 600", files["team_user_README.txt"])

    def test_public_only_archive_has_no_private_file(self):
        _, text_body, html_body, attachments = sftp_hlp.build_key_mail_payload(
            "public-user",
            PUBLIC_KEY,
            "",
            ["admin@example.test"],
        )

        files = self.zip_files(attachments[0])
        self.assertEqual(
            set(files),
            {
                "public-user_id_ed25519.pub",
                "public-user_README.txt",
            },
        )
        self.assertNotIn(PRIVATE_KEY, text_body)
        self.assertNotIn(PRIVATE_KEY, html_body)
        self.assertIn("public-user_id_ed25519.pub", files["public-user_README.txt"])

    def test_rsa_key_uses_familiar_filename(self):
        rsa_public = "ssh-rsa AAAATestPayload rsa@example"
        _, _, _, attachments = sftp_hlp.build_key_mail_payload(
            "rsa-user",
            rsa_public,
            PRIVATE_KEY,
            ["admin@example.test"],
        )

        files = self.zip_files(attachments[0])
        self.assertIn("rsa-user_id_rsa", files)
        self.assertIn("rsa-user_id_rsa.pub", files)

    def test_send_key_mail_uses_admin_and_user_recipient(self):
        cfg = {
            "adminMail": "admin@example.test",
            "users": [
                {
                    "sftpuser": "alice",
                    "mail": "alice@example.test",
                    "sftpcerts": [],
                }
            ],
        }
        with patch.object(
            sftp_hlp,
            "get_printable_keys",
            return_value=(True, (PUBLIC_KEY, PRIVATE_KEY)),
        ), patch.object(
            sftp_hlp.mail_hlp,
            "send_mail",
            return_value=(True, None),
        ) as send_mail:
            ok, error = sftp_hlp.send_key_by_mail(cfg, "alice", "stored-key")

        self.assertTrue(ok)
        self.assertIsNone(error)
        args = send_mail.call_args.args
        kwargs = send_mail.call_args.kwargs
        self.assertEqual(
            args[0],
            ["admin@example.test", "alice@example.test"],
        )
        self.assertNotIn(PRIVATE_KEY, args[2])
        self.assertNotIn(PRIVATE_KEY, kwargs["html_body"])
        self.assertEqual(len(kwargs["attachments"]), 1)
        self.assertEqual(
            kwargs["attachments"][0].safe_filename(),
            "alice_sftp_keys.zip",
        )


if __name__ == "__main__":
    unittest.main()
