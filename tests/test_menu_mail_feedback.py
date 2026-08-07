from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from libs.app import mail_hlp
from libs.app.menus import menuBoss
from libs.app.menus.app_20_node_red import handover_mail
from libs.app.menus.app_20_node_red import menu as node_red_menu
from libs.app.menus.app_30_ssh import menu as ssh_menu
from libs.app.menus.app_30_ssh import ssh_mail_hlp
from libs.app.menus.app_33_sftpmanagr import menu as sftp_menu
from libs.app.menus.app_33_sftpmanagr import sftp_manager_hlp as sftp_hlp


PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestPayload user@example"
PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nprivate-test-data\n-----END OPENSSH PRIVATE KEY-----"


class MenuAndMailFeedbackTests(unittest.TestCase):
    def configured_mail(self):
        return patch.multiple(
            mail_hlp.app_cfg,
            MAIL_SMTP_HOST="smtp.example.test",
            MAIL_SMTP_PORT=465,
            MAIL_SMTP_USER="service@example.test",
            MAIL_SMTP_PASSWORD="secret-value",
            MAIL_SMTP_MODE="ssl",
            MAIL_FROM="",
            MAIL_TIMEOUT=12,
        )

    def test_component_version_resolver_and_current_menus(self):
        class LegacyMenu:
            __VERSION__ = "9.8.7"

        class MissingVersion:
            pass

        self.assertEqual(menuBoss._get_menu_version(LegacyMenu), "9.8.7")
        self.assertEqual(menuBoss._get_menu_version(MissingVersion), "")
        self.assertEqual(menuBoss._format_menu_version("3.5.0"), "v. 3.5.0")
        self.assertEqual(menuBoss._format_menu_version(""), "?")
        self.assertEqual(menuBoss._get_menu_version(node_red_menu.menu), "1.0.0")
        self.assertEqual(menuBoss._get_menu_version(ssh_menu.menu), "1.0.0")
        self.assertEqual(menuBoss._get_menu_version(sftp_menu.menu), "1.2.5")

    def test_global_host_context_uses_fqdn_and_home_avoids_duplicate(self):
        original = menuBoss.c_menu.globalTitle
        try:
            with patch.object(
                menuBoss.cfg,
                "machineInfo",
                SimpleNamespace(
                    hostname_full="server-01.example.test",
                    static_hostname="server-01",
                ),
            ):
                menuBoss._configure_global_menu_context()
                title = menuBoss.c_menu.globalTitle()
                self.assertIn(("Host", "server-01.example.test"), list(title))
                self.assertFalse(menuBoss.menuBoss.showGlobalTitle)
        finally:
            menuBoss.c_menu.globalTitle = original

    def test_shared_mail_transport_prints_delivery_progress(self):
        output = io.StringIO()
        with self.configured_mail(), patch.object(
            mail_hlp,
            "send_smtp_message",
            return_value=(True, None),
        ), redirect_stdout(output):
            ok, error = mail_hlp.send_mail(
                ["recipient@example.test"],
                "Subject",
                "Body",
            )

        self.assertTrue(ok, error)
        self.assertIn(mail_hlp.TX_MAIL_SENDING, output.getvalue())

    def test_node_red_prints_generation_before_shared_send(self):
        output = io.StringIO()
        with patch.object(
            handover_mail,
            "collect_handover_data",
            return_value=SimpleNamespace(),
        ), patch.object(
            handover_mail,
            "render_handover_mail",
            return_value=("subject", "text", "html"),
        ), patch.object(
            handover_mail.mail_hlp,
            "send_mail",
            return_value=(True, None),
        ), redirect_stdout(output):
            ok, error = handover_mail.send_handover_mail(
                "competition",
                SimpleNamespace(),
                recipient="owner@example.test",
            )

        self.assertTrue(ok, error)
        self.assertIn(handover_mail.TXT_HANDOVER_GENERATING, output.getvalue())

    def test_ssh_prints_generation_before_shared_send(self):
        output = io.StringIO()
        with patch.object(
            ssh_mail_hlp.ssh_key_bundle,
            "read_managed_key_pair",
            return_value=(True, (PUBLIC_KEY, PRIVATE_KEY), None),
        ), patch.object(
            ssh_mail_hlp,
            "build_key_mail_payload",
            return_value=("subject", "text", "html", []),
        ), patch.object(
            ssh_mail_hlp.mail_hlp,
            "send_mail",
            return_value=(True, None),
        ), redirect_stdout(output):
            ok, error = ssh_mail_hlp.send_managed_key_by_mail(
                "alice",
                "work-key",
                "alice@example.test",
            )

        self.assertTrue(ok, error)
        self.assertIn(ssh_mail_hlp.TXT_MENU3_TITLE_05, output.getvalue())

    def test_sftp_prints_generation_before_shared_send(self):
        cfg = {
            "adminMail": "admin@example.test",
            "users": [{"sftpuser": "alice", "sftpcerts": []}],
        }
        output = io.StringIO()
        with patch.object(
            sftp_hlp,
            "get_printable_keys",
            return_value=(True, (PUBLIC_KEY, PRIVATE_KEY)),
        ), patch.object(
            sftp_hlp,
            "build_key_mail_payload",
            return_value=("subject", "text", "html", []),
        ), patch.object(
            sftp_hlp.mail_hlp,
            "send_mail",
            return_value=(True, None),
        ), redirect_stdout(output):
            ok, error = sftp_hlp.send_key_by_mail(cfg, "alice", "stored-key")

        self.assertTrue(ok, error)
        self.assertIn(sftp_hlp.TXT_SFTP_HLP_MAIL_GENERATING, output.getvalue())


if __name__ == "__main__":
    unittest.main()
