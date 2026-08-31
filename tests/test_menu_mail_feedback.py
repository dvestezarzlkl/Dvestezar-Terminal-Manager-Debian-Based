from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from libs.app import mail_hlp, runtime_flags
from libs.app.hub import menu as hub_menu
from libs.app.hub.menu import HubSettingsMenu
from libs.app.hub.models import HubState, HubStatus
from libs.app.menus import menuBoss
from libs.app.menus.app_20_node_red import handover_mail
from libs.app.menus.app_20_node_red import menu as node_red_menu
from libs.app.menus.app_30_ssh import menu as ssh_menu
from libs.app.menus.app_30_ssh import ssh_mail_hlp
from libs.app.menus.app_33_sftpmanagr import menu as sftp_menu
from libs.app.menus.app_33_sftpmanagr import menu_templates as sftp_template_menu
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

    @staticmethod
    def _menu_item(menu, choice: str):
        return next(
            item for item in menu
            if item is not None and getattr(item, "choice", None) == choice
        )

    def test_centrally_managed_app_settings_are_hidden_without_override(self):
        previous_applied = menuBoss.cfg.SETTINGS_LAST_APPLIED
        runtime_flags._set_local_settings_override_for_tests(False)
        try:
            menuBoss.cfg.SETTINGS_LAST_APPLIED = "hub:1,smtp:1"
            settings = menuBoss.m_mail_settings()
            settings.onShowMenu()
            self.assertFalse(self._menu_item(settings.menu, "b").hidden)
            for choice in ("h", "p", "u", "w", "o", "f", "a"):
                self.assertTrue(self._menu_item(settings.menu, choice).hidden)
            self.assertFalse(self._menu_item(settings.menu, "s").hidden)
            self.assertFalse(self._menu_item(settings.menu, "g").hidden)
            self.assertFalse(self._menu_item(settings.menu, "t").hidden)

            with patch.object(
                hub_menu.hub_runtime,
                "status",
                HubStatus(HubState.SCHEMA_OUTDATED, "schema 2, expected 3"),
            ):
                hub_settings = HubSettingsMenu()
                hub_settings.onShowMenu()
            for choice in ("e", "a", "h", "p", "u", "w", "d", "x", "o"):
                self.assertTrue(self._menu_item(hub_settings.menu, choice).hidden)
            for choice in ("t", "i", "s"):
                self.assertFalse(self._menu_item(hub_settings.menu, choice).hidden)
            self.assertFalse(self._menu_item(hub_settings.menu, "s").enabled)
        finally:
            menuBoss.cfg.SETTINGS_LAST_APPLIED = previous_applied
            runtime_flags._set_local_settings_override_for_tests(False)

    def test_local_settings_override_reveals_managed_editors(self):
        previous_applied = menuBoss.cfg.SETTINGS_LAST_APPLIED
        runtime_flags._set_local_settings_override_for_tests(True)
        try:
            menuBoss.cfg.SETTINGS_LAST_APPLIED = "hub:1,smtp:1[keep=from_address]"
            settings = menuBoss.m_mail_settings()
            settings.onShowMenu()
            for choice in ("b", "h", "p", "u", "w", "o", "f", "a"):
                self.assertFalse(self._menu_item(settings.menu, choice).hidden)
            hub_settings = HubSettingsMenu()
            hub_settings.onShowMenu()
            for choice in ("e", "a", "h", "p", "u", "w", "d", "x", "o", "t", "i", "s"):
                self.assertFalse(self._menu_item(hub_settings.menu, choice).hidden)
        finally:
            menuBoss.cfg.SETTINGS_LAST_APPLIED = previous_applied
            runtime_flags._set_local_settings_override_for_tests(False)

    def test_preserved_central_field_stays_locally_visible(self):
        previous_applied = menuBoss.cfg.SETTINGS_LAST_APPLIED
        runtime_flags._set_local_settings_override_for_tests(False)
        try:
            menuBoss.cfg.SETTINGS_LAST_APPLIED = "smtp:1[keep=from_address]"
            settings = menuBoss.m_mail_settings()
            settings.onShowMenu()
            self.assertTrue(self._menu_item(settings.menu, "h").hidden)
            self.assertFalse(self._menu_item(settings.menu, "f").hidden)
        finally:
            menuBoss.cfg.SETTINGS_LAST_APPLIED = previous_applied
            runtime_flags._set_local_settings_override_for_tests(False)

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
        self.assertEqual(menuBoss._get_menu_version(sftp_menu.menu), "1.3.2")

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
            sftp_menu, "selectDir", return_value=Path("/srv/docs")
        ), patch.object(
            sftp_menu, "select", return_value=selected
        ):
            submenu.add_mountpoint(SimpleNamespace())

        self.assertEqual(cfg["users"][0]["sftpmounts"]["docs"], "/srv/docs")
        self.assertFalse(cfg["users"][0]["pointsSet"]["docs"]["rw"])
        self.assertTrue(sftp_hlp.get_mountpointReadOnlyStatus(cfg, "alice", "docs"))
        self.assertTrue(main_menu.changed)

    def test_sftp_template_mountpoint_add_normalizes_selectdir_path(self):
        cfg = {"users": [], "mountpointTemplates": {"webs_dev": {"mounts": {}}}}
        main_menu = SimpleNamespace(cfg=cfg, changed=False, basicTitle=lambda **kwargs: None)
        submenu = sftp_template_menu.m_mountpoint_template("webs_dev", main_menu)

        with patch.object(
            sftp_template_menu, "get_input", return_value="web1"
        ), patch.object(
            sftp_template_menu, "selectDir", return_value=Path("/var/www/html")
        ):
            result = submenu.add_mountpoint(SimpleNamespace())

        mounts = cfg["mountpointTemplates"]["webs_dev"]["mounts"]
        self.assertEqual(len(mounts), 1)
        row = next(iter(mounts.values()))
        self.assertEqual(row["label"], "web1")
        self.assertEqual(row["path"], "/var/www/html")
        self.assertIsInstance(row["path"], str)
        self.assertTrue(main_menu.changed)
        self.assertFalse(bool(getattr(result, "err", None)))

    def test_sftp_template_only_user_count_and_cifs_preflight_use_resolved_mounts(self):
        cfg = {
            "mountpointTemplates": {
                "test": {
                    "mounts": {
                        "mp_tmp": {"label": "tmp", "path": "/tmp"},
                        "mp_var": {"label": "var", "path": "/var"},
                    }
                }
            },
            "users": [{
                "sftpuser": "testovaci_user",
                "sambaVault": True,
                "sftpmounts": {},
                "mountTemplates": ["test"],
                "templatePoints": {
                    "mp_tmp": {"enabled": True, "rw": True},
                },
                "sftpcerts": [],
            }],
        }

        records, errors = sftp_menu.list_user_mountpoint_records(cfg, "testovaci_user")
        self.assertEqual(errors, [])
        self.assertEqual(len(records), 2)
        self.assertTrue(sftp_hlp.config_requires_cifs(cfg))

        cfg["users"][0]["templatePoints"]["mp_tmp"]["enabled"] = False
        self.assertFalse(sftp_hlp.config_requires_cifs(cfg))

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
        record = sftp_menu.list_user_mountpoint_records(cfg, "alice")[0][0]

        with patch.object(
            sftp_menu, "select", return_value=selected
        ), patch.object(
            sftp_menu.os.path, "isdir", return_value=True
        ), patch.object(
            sftp_menu, "selectDir", return_value="/srv/new"
        ) as select_dir:
            submenu.modify_mountpoint(SimpleNamespace(data=record))

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
        record = sftp_menu.list_user_mountpoint_records(cfg, "alice")[0][0]

        with patch.object(
            sftp_menu, "select", return_value=selected
        ), patch.object(
            sftp_menu.os.path, "isdir", return_value=False
        ) as is_dir, patch.object(
            sftp_menu, "selectDir", return_value=None
        ) as select_dir:
            submenu.modify_mountpoint(SimpleNamespace(data=record))

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

    def test_sftp_helper_reports_nonempty_managed_target_with_recovery(self):
        cfg = {
            "users": [{
                "sftpuser": "alice",
                "sambaVault": True,
                "sftpmounts": {"docs": "/srv/docs"},
            }]
        }
        target = "/home_sftp_users/alice/__sftp__/docs"
        concrete_error = sftp_hlp.ManagedCIFSTargetNotEmptyError(target)

        with patch.object(
            sftp_hlp, "check_config_valid", return_value=(True, None)
        ), patch.object(
            sftp_hlp, "config_requires_cifs", return_value=False
        ), patch.object(
            sftp_hlp.smbHelp, "beginBatch"
        ), patch.object(
            sftp_hlp.smbHelp, "endBatch", return_value=False
        ), patch.object(
            sftp_hlp.smbHelp, "lastError", concrete_error
        ), patch.object(
            sftp_hlp, "createUserFromJson", return_value=[SimpleNamespace()]
        ):
            ok, error = sftp_hlp.apply_changes(cfg=cfg, save=True)

        self.assertFalse(ok)
        self.assertEqual(
            error,
            sftp_hlp.TXT_SFTP_HLP_SAMBA_TARGET_NOT_EMPTY.format(path=target),
        )
        self.assertIn(target, error)

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
            sftp_hlp, "_get_sftp_backup_root", return_value="/var/backups/sftpusers"
        ), patch.object(
            sftp_hlp, "uninstallUnwantedUsers", return_value=True
        ) as uninstall_mock, patch.object(
            sftp_hlp, "restart_sshd", return_value=True
        ) as restart_mock, patch.object(
            sftp_hlp, "save_config"
        ) as save_mock:
            ok, error = sftp_hlp.apply_changes(cfg=cfg, save=True)

        self.assertTrue(ok, error)
        uninstall_mock.assert_called_once_with(
            cfg=cfg, backup_root="/var/backups/sftpusers"
        )
        restart_mock.assert_called_once_with()
        save_mock.assert_called_once_with(cfg, sftp_hlp.getDefaultEtcConfigPath())

    def test_sftp_uninstall_all_uses_secure_backup_root(self):
        with patch.object(
            sftp_hlp, "_get_sftp_backup_root", return_value="/var/backups/sftpusers"
        ) as backup_root, patch.object(
            sftp_hlp, "unInstAll", return_value=True
        ) as uninstall:
            ok, error = sftp_hlp.uninstall_all_users()

        self.assertTrue(ok, error)
        backup_root.assert_called_once_with(create=True)
        uninstall.assert_called_once_with(backup_root="/var/backups/sftpusers")

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
