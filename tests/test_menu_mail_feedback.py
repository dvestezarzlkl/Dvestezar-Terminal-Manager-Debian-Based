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
        self.assertEqual(menuBoss._get_menu_version(sftp_menu.menu), "1.2.11")

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

    def test_sftp_mountpoint_add_honors_read_only_selection(self):
        cfg = {
            "users": [{
                "sftpuser": "alice",
                "sambaVault": True,
                "sftpmounts": {},
                "pointsSet": {},
            }]
        }
        main_menu = SimpleNamespace(cfg=cfg, changed=False)
        submenu = sftp_menu.m_user_mountpoints("alice", main_menu, cfg["users"][0])
        submenu.cfg = cfg
        selected = SimpleNamespace(item=SimpleNamespace(data="R"))

        with patch.object(sftp_menu, "cls"), patch.object(
            sftp_menu, "get_input", return_value="docs"
        ), patch.object(
            sftp_menu, "selectDir", return_value="/srv/docs"
        ), patch.object(
            sftp_menu, "select", return_value=selected
        ):
            submenu.add_mountpoint(SimpleNamespace())

        self.assertEqual(cfg["users"][0]["sftpmounts"]["docs"], "/srv/docs")
        self.assertFalse(cfg["users"][0]["pointsSet"]["docs"]["rw"])
        self.assertTrue(sftp_hlp.get_mountpointReadOnlyStatus(cfg, "alice", "docs"))
        self.assertTrue(main_menu.changed)

    def test_sftp_mountpoint_add_escape_selection_does_not_crash(self):
        cfg = {
            "users": [{
                "sftpuser": "alice",
                "sambaVault": True,
                "sftpmounts": {},
                "pointsSet": {},
            }]
        }
        main_menu = SimpleNamespace(cfg=cfg, changed=False)
        submenu = sftp_menu.m_user_mountpoints("alice", main_menu, cfg["users"][0])
        submenu.cfg = cfg

        with patch.object(sftp_menu, "cls"), patch.object(
            sftp_menu, "get_input", return_value="docs"
        ), patch.object(
            sftp_menu, "selectDir", return_value="/srv/docs"
        ), patch.object(
            sftp_menu, "select", return_value=SimpleNamespace(item=None)
        ):
            result = submenu.add_mountpoint(SimpleNamespace())

        self.assertFalse(main_menu.changed)
        self.assertEqual(cfg["users"][0]["sftpmounts"], {})
        self.assertIsNotNone(result.err)

    def test_sftp_mountpoint_action_escape_selection_does_not_crash(self):
        cfg = {
            "users": [{
                "sftpuser": "alice",
                "sambaVault": True,
                "sftpmounts": {"docs": "/srv/docs"},
                "pointsSet": {"docs": {"rw": False}},
            }]
        }
        main_menu = SimpleNamespace(cfg=cfg, changed=False)
        submenu = sftp_menu.m_user_mountpoints("alice", main_menu, cfg["users"][0])
        submenu.cfg = cfg

        with patch.object(
            sftp_menu, "select", return_value=SimpleNamespace(item=None)
        ):
            result = submenu.modify_mountpoint(SimpleNamespace(data="docs"))

        self.assertFalse(main_menu.changed)
        self.assertIsNotNone(result.err)

    def test_sftp_mountpoint_path_edit_keeps_alias_for_apply_diff(self):
        cfg = {
            "users": [{
                "sftpuser": "alice",
                "sambaVault": True,
                "sftpmounts": {"docs": "/srv/old"},
                "pointsSet": {"docs": {"rw": False}},
            }]
        }
        main_menu = SimpleNamespace(cfg=cfg, changed=False)
        submenu = sftp_menu.m_user_mountpoints("alice", main_menu, cfg["users"][0])
        submenu.cfg = cfg
        selected = SimpleNamespace(item=SimpleNamespace(data="P"))

        with patch.object(
            sftp_menu, "select", return_value=selected
        ), patch.object(
            sftp_menu.os.path, "isdir", return_value=True
        ), patch.object(
            sftp_menu, "selectDir", return_value="/srv/new"
        ) as select_dir:
            submenu.modify_mountpoint(SimpleNamespace(data="docs"))

        self.assertEqual(select_dir.call_args.args[0], "/srv/old")
        self.assertEqual(cfg["users"][0]["sftpmounts"]["docs"], "/srv/new")
        self.assertEqual(cfg["users"][0]["pointsSet"]["docs"]["rw"], False)
        self.assertTrue(main_menu.changed)

    def test_sftp_mountpoint_path_edit_falls_back_to_root_when_current_path_missing(self):
        cfg = {
            "users": [{
                "sftpuser": "alice",
                "sambaVault": True,
                "sftpmounts": {"docs": "/srv/missing"},
                "pointsSet": {"docs": {"rw": False}},
            }]
        }
        main_menu = SimpleNamespace(cfg=cfg, changed=False)
        submenu = sftp_menu.m_user_mountpoints("alice", main_menu, cfg["users"][0])
        submenu.cfg = cfg
        selected = SimpleNamespace(item=SimpleNamespace(data="P"))

        with patch.object(
            sftp_menu, "select", return_value=selected
        ), patch.object(
            sftp_menu.os.path, "isdir", return_value=False
        ) as is_dir, patch.object(
            sftp_menu, "selectDir", return_value=None
        ) as select_dir:
            submenu.modify_mountpoint(SimpleNamespace(data="docs"))

        is_dir.assert_called_once_with("/srv/missing")
        self.assertEqual(select_dir.call_args.args[0], "/")
        self.assertFalse(main_menu.changed)

    def test_sftp_exit_without_changes_does_not_prompt(self):
        main_menu = sftp_menu.menu()
        main_menu.changed = False

        with patch.object(sftp_menu, "confirm") as confirm_mock:
            self.assertIsNone(main_menu.onExitMenu())

        confirm_mock.assert_not_called()

    def test_sftp_exit_with_changes_can_be_vetoed(self):
        main_menu = sftp_menu.menu()
        main_menu.changed = True

        with patch.object(sftp_menu, "confirm", return_value=False) as confirm_mock:
            result = main_menu.onExitMenu()

        self.assertIs(result, False)
        confirm_mock.assert_called_once_with(sftp_menu.TXT_SFTP_MENU_EXIT_UNSAVED_CONFIRM)

    def test_sftp_exit_with_changes_can_discard_after_confirmation(self):
        main_menu = sftp_menu.menu()
        main_menu.changed = True

        with patch.object(sftp_menu, "confirm", return_value=True) as confirm_mock:
            result = main_menu.onExitMenu()

        self.assertIsNone(result)
        confirm_mock.assert_called_once_with(sftp_menu.TXT_SFTP_MENU_EXIT_UNSAVED_CONFIRM)

    def test_sftp_apply_reloads_persisted_config_for_next_edit(self):
        old_cfg = {
            "users": [{
                "sftpuser": "alice",
                "sambaVault": True,
                "sftpmounts": {"docs": "/srv/old"},
                "pointsSet": {"docs": {"rw": False}},
            }]
        }
        fresh_cfg = {
            "users": [{
                "sftpuser": "alice",
                "sambaVault": True,
                "sftpmounts": {"docs": "/srv/old"},
                "pointsSet": {"docs": {"rw": False}},
            }]
        }
        main_menu = sftp_menu.menu()
        main_menu.cfg = old_cfg
        main_menu.users = old_cfg["users"]
        main_menu.changed = True

        with patch.object(
            sftp_menu, "apply_changes", return_value=(True, None)
        ) as apply_mock, patch.object(
            sftp_menu, "load_config", return_value=(True, None, fresh_cfg)
        ) as load_mock, patch.object(
            sftp_menu, "anyKey"
        ):
            result = main_menu.apply_changes(SimpleNamespace())

        apply_mock.assert_called_once_with(cfg=old_cfg, save=True)
        load_mock.assert_called_once_with()
        self.assertIs(main_menu.cfg, fresh_cfg)
        self.assertIs(main_menu.users[0], fresh_cfg["users"][0])
        self.assertFalse(main_menu.changed)
        self.assertEqual(result.ok, sftp_menu.TXT_SFTP_MENU_CHANGES_APPLIED)

    def test_sftp_helper_failed_apply_does_not_persist_unapplied_config(self):
        cfg = {
            "users": [{
                "sftpuser": "alice",
                "sambaVault": True,
                "sftpmounts": {},
            }]
        }

        def fail_create_user(*, cfg, errors_out):
            errors_out.append("synthetic reconcile failure")
            return None

        with patch.object(
            sftp_hlp, "check_config_valid", return_value=(True, None)
        ), patch.object(
            sftp_hlp, "config_requires_cifs", return_value=False
        ), patch.object(
            sftp_hlp.smbHelp, "beginBatch"
        ), patch.object(
            sftp_hlp.smbHelp, "endBatch", return_value=True
        ), patch.object(
            sftp_hlp, "createUserFromJson", side_effect=fail_create_user
        ), patch.object(
            sftp_hlp, "save_config"
        ) as save_mock, patch.object(
            sftp_hlp, "restart_sshd"
        ) as restart_mock:
            ok, error = sftp_hlp.apply_changes(cfg=cfg, save=True)

        self.assertFalse(ok)
        self.assertIn("synthetic reconcile failure", error)
        save_mock.assert_not_called()
        restart_mock.assert_not_called()

    def test_sftp_helper_persists_only_after_successful_apply(self):
        cfg = {
            "users": [{
                "sftpuser": "alice",
                "sambaVault": True,
                "sftpmounts": {},
            }]
        }

        with patch.object(
            sftp_hlp, "check_config_valid", return_value=(True, None)
        ), patch.object(
            sftp_hlp, "config_requires_cifs", return_value=False
        ), patch.object(
            sftp_hlp.smbHelp, "beginBatch"
        ), patch.object(
            sftp_hlp.smbHelp, "endBatch", return_value=True
        ), patch.object(
            sftp_hlp, "createUserFromJson", return_value=[SimpleNamespace()]
        ), patch.object(
            sftp_hlp, "uninstallUnwantedUsers", return_value=True
        ), patch.object(
            sftp_hlp, "restart_sshd", return_value=True
        ) as restart_mock, patch.object(
            sftp_hlp, "save_config"
        ) as save_mock:
            ok, error = sftp_hlp.apply_changes(cfg=cfg, save=True)

        self.assertTrue(ok, error)
        restart_mock.assert_called_once_with()
        save_mock.assert_called_once_with(cfg, sftp_hlp.getDefaultEtcConfigPath())

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
