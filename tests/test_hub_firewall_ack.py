"""Firewall cross-session acknowledgement regression tests."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from libs.app.menus.app_40_firewall.ack import (
    FirewallAckError,
    acknowledge_pending,
    create_pending_ack,
    is_pending_acknowledged,
)


class FirewallAckTests(unittest.TestCase):
    @staticmethod
    def _origin() -> dict[str, str]:
        return {
            "SSH_CONNECTION": "10.0.0.5 41000 10.0.0.10 22",
            "SSH_TTY": "/dev/pts/1",
        }

    @staticmethod
    def _fresh() -> dict[str, str]:
        return {
            "SSH_CONNECTION": "10.0.0.5 41001 10.0.0.10 22",
            "SSH_TTY": "/dev/pts/2",
        }

    def _pending(self, root: Path) -> Path:
        return root / "run" / "jb_sys_apps" / "firewall" / "pending_ack.json"

    def test_new_ssh_session_acknowledges_matching_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._pending(Path(tmp))
            with patch(
                "libs.app.menus.app_40_firewall.ack.secrets.token_hex",
                return_value="a1b2c3d4",
            ):
                token = create_pending_ack(
                    path,
                    seconds=90,
                    rollback_unit="jb-test",
                    env=self._origin(),
                    now=1000.0,
                )

            with patch.object(os, "geteuid", return_value=0):
                result = acknowledge_pending(
                    token,
                    path=path,
                    env=self._fresh(),
                    now=1001.0,
                )

            self.assertEqual(token, "A1B2C3D4")
            self.assertFalse(result.already_acknowledged)
            self.assertEqual(result.remaining_seconds, 89)
            self.assertTrue(is_pending_acknowledged(token, path=path))
            self.assertEqual(
                stat.S_IMODE(path.stat().st_mode),
                0o600,
            )

    def test_original_ssh_session_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._pending(Path(tmp))
            with patch(
                "libs.app.menus.app_40_firewall.ack.secrets.token_hex",
                return_value="11223344",
            ):
                token = create_pending_ack(
                    path,
                    seconds=90,
                    rollback_unit="jb-test",
                    env=self._origin(),
                    now=1000.0,
                )

            with patch.object(os, "geteuid", return_value=0):
                with self.assertRaisesRegex(
                    FirewallAckError,
                    "original session",
                ):
                    acknowledge_pending(
                        token,
                        path=path,
                        env=self._origin(),
                        now=1001.0,
                    )

    def test_confirmation_requires_ssh_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._pending(Path(tmp))
            with patch(
                "libs.app.menus.app_40_firewall.ack.secrets.token_hex",
                return_value="55667788",
            ):
                token = create_pending_ack(
                    path,
                    seconds=90,
                    rollback_unit="jb-test",
                    env={},
                    now=1000.0,
                )

            with patch.object(os, "geteuid", return_value=0):
                with self.assertRaisesRegex(FirewallAckError, "newly opened SSH"):
                    acknowledge_pending(
                        token,
                        path=path,
                        env={},
                        now=1001.0,
                    )

    def test_wrong_or_expired_token_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._pending(Path(tmp))
            with patch(
                "libs.app.menus.app_40_firewall.ack.secrets.token_hex",
                return_value="99aabbcc",
            ):
                token = create_pending_ack(
                    path,
                    seconds=90,
                    rollback_unit="jb-test",
                    env=self._origin(),
                    now=1000.0,
                )

            with patch.object(os, "geteuid", return_value=0):
                with self.assertRaisesRegex(FirewallAckError, "does not match"):
                    acknowledge_pending(
                        "DEADBEEF",
                        path=path,
                        env=self._fresh(),
                        now=1001.0,
                    )
                with self.assertRaisesRegex(FirewallAckError, "expired"):
                    acknowledge_pending(
                        token,
                        path=path,
                        env=self._fresh(),
                        now=1090.0,
                    )


if __name__ == "__main__":
    unittest.main()
