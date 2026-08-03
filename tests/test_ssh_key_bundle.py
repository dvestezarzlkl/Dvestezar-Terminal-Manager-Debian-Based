from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from libs.app import ssh_key_bundle


PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestPayload user@example"
PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nprivate-test-data\n-----END OPENSSH PRIVATE KEY-----"


class SshKeyBundleTests(unittest.TestCase):
    def test_names_and_archive_content(self):
        names = ssh_key_bundle.build_bundle_names(
            "alice/work key",
            PUBLIC_KEY,
            "ssh_keys",
        )
        self.assertEqual(names.public_filename, "alice_work_key_id_ed25519.pub")
        self.assertEqual(names.private_filename, "alice_work_key_id_ed25519")
        self.assertEqual(names.archive_filename, "alice_work_key_ssh_keys.zip")

        attachment = ssh_key_bundle.create_key_bundle_attachment(
            names,
            PUBLIC_KEY,
            PRIVATE_KEY,
            "README text",
        )
        with zipfile.ZipFile(io.BytesIO(attachment.read_bytes()), "r") as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    names.private_filename,
                    names.public_filename,
                    names.readme_filename,
                },
            )

    def test_public_only_dummy_private_key_is_omitted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager_dir = Path(temp_dir)
            (manager_dir / "imported.pub").write_text(PUBLIC_KEY + "\n", encoding="utf-8")
            (manager_dir / "imported").write_text(
                "DUMMY PRIVATE KEY - IMPORTED PUBLIC KEY ONLY\n",
                encoding="utf-8",
            )
            with patch.object(
                ssh_key_bundle.sshMng,
                "getDirPath_sshManager",
                return_value=str(manager_dir),
            ):
                ok, pair, error = ssh_key_bundle.read_managed_key_pair(
                    "alice",
                    "imported",
                )

        self.assertTrue(ok, error)
        self.assertEqual(pair, (PUBLIC_KEY, ""))

    def test_private_key_pair_is_read(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager_dir = Path(temp_dir)
            (manager_dir / "generated.pub").write_text(PUBLIC_KEY + "\n", encoding="utf-8")
            (manager_dir / "generated").write_text(PRIVATE_KEY + "\n", encoding="utf-8")
            with patch.object(
                ssh_key_bundle.sshMng,
                "getDirPath_sshManager",
                return_value=str(manager_dir),
            ):
                ok, pair, error = ssh_key_bundle.read_managed_key_pair(
                    "alice",
                    "generated",
                )

        self.assertTrue(ok, error)
        self.assertEqual(pair, (PUBLIC_KEY, PRIVATE_KEY))

    def test_path_traversal_key_name_is_rejected(self):
        ok, pair, error = ssh_key_bundle.read_managed_key_pair("alice", "../secret")
        self.assertFalse(ok)
        self.assertIsNone(pair)
        self.assertIn("invalid", error.lower())


if __name__ == "__main__":
    unittest.main()
