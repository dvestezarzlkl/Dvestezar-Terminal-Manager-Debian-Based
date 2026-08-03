from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from libs.app import user_contact


class UserContactTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name)
        self.record = SimpleNamespace(
            pw_dir=str(self.home),
            pw_uid=os.getuid(),
            pw_gid=os.getgid(),
        )
        self.patcher = patch.object(
            user_contact.pwd,
            "getpwnam",
            return_value=self.record,
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_set_get_and_clear_user_email(self):
        ok, error = user_contact.set_user_email("alice", " Alice@Example.TEST ")
        self.assertTrue(ok, error)
        self.assertEqual(user_contact.get_user_email("alice"), "alice@example.test")

        path = user_contact.get_user_contact_path("alice")
        self.assertTrue(path.is_file())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

        ok, error = user_contact.set_user_email("alice", "")
        self.assertTrue(ok, error)
        self.assertIsNone(user_contact.get_user_email("alice"))

    def test_invalid_address_is_rejected_without_creating_file(self):
        ok, error = user_contact.set_user_email("alice", "not-an-email")
        self.assertFalse(ok)
        self.assertIn("Invalid", error)
        self.assertFalse(user_contact.get_user_contact_path("alice").exists())

    def test_jsonc_comments_are_accepted(self):
        path = user_contact.get_user_contact_path("alice")
        path.parent.mkdir(parents=True)
        path.write_text('{\n  // recipient\n  "email": "alice@example.test"\n}\n', encoding="utf-8")
        self.assertEqual(user_contact.get_user_email("alice"), "alice@example.test")

    def test_symlink_app_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside_dir:
            config_dir = self.home / ".config"
            config_dir.mkdir()
            os.symlink(outside_dir, config_dir / "jb_sys_apps")
            ok, error = user_contact.set_user_email("alice", "alice@example.test")

        self.assertFalse(ok)
        self.assertTrue(error)

    def test_symlink_contact_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside_dir:
            app_dir = self.home / ".config" / "jb_sys_apps"
            app_dir.mkdir(parents=True)
            outside = Path(outside_dir) / "contact.jsonc"
            outside.write_text('{"email":"outside@example.test"}\n', encoding="utf-8")
            os.symlink(outside, app_dir / "contact.jsonc")
            ok, data, error = user_contact.load_user_contact("alice")

        self.assertFalse(ok)
        self.assertEqual(data, {})
        self.assertTrue(error)


if __name__ == "__main__":
    unittest.main()
