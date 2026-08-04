import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from libs.app.menus.app_20_node_red import handover_mail


class FakeService:
    fullName = "node-red-userInstance@competition.service"

    def running(self):
        return True

    def enabled(self):
        return True


class FakeNodeConfig:
    title = "Competition arena"
    port = 21880
    service = FakeService()
    admin_users = [
        SimpleNamespace(user="admin", permissions="*", password="$2b$secret-hash"),
        SimpleNamespace(user="viewer", permissions="read", password="$2b$other-hash"),
    ]

    def getUIUserName(self):
        raise AssertionError("legacy httpNodeAuth must not be collected as a Dashboard user")


class NodeRedHandoverMailTests(unittest.TestCase):
    def test_sanitize_git_remote_removes_embedded_credentials(self):
        remote = "https://service-user:secret-token@git.example.test/team/project.git?x=1#frag"
        self.assertEqual(
            handover_mail.sanitize_git_remote(remote),
            "https://git.example.test/team/project.git",
        )
        self.assertEqual(
            handover_mail.sanitize_git_remote("git@git.example.test:team/project.git"),
            "git@git.example.test:team/project.git",
        )

    def test_build_instance_url_adds_scheme_port_and_keeps_path(self):
        self.assertEqual(
            handover_mail.build_instance_url("server.example.test/node-red", 21880, True),
            "https://server.example.test:21880/node-red",
        )
        self.assertEqual(
            handover_mail.build_instance_url("http://192.0.2.10:XXXX", 21880, False),
            "http://192.0.2.10:21880",
        )

    @patch.object(handover_mail, "getUserHome", return_value="/home/competition")
    @patch.object(handover_mail, "_run_as_user")
    def test_active_project_reads_name_and_sanitizes_remote(self, run_as_user, _get_home):
        run_as_user.side_effect = [
            SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"activeProject": "arena-control"}),
                stderr="",
            ),
            SimpleNamespace(
                returncode=0,
                stdout="https://bot:token@git.example.test/node-red/arena-control.git\n",
                stderr="",
            ),
        ]
        project = handover_mail.get_active_project_info("competition")
        self.assertEqual(project.name, "arena-control")
        self.assertEqual(
            project.remote,
            "https://git.example.test/node-red/arena-control.git",
        )

    @patch.object(handover_mail, "get_system_disk_identity")
    @patch.object(handover_mail, "get_active_project_info")
    @patch.object(handover_mail, "existsSelfSignedCert", return_value=False)
    @patch.object(handover_mail, "getHttps", return_value=None)
    @patch.object(handover_mail, "instanceVersion", return_value="4.1.1")
    @patch.object(handover_mail, "getNodeJsVersion", return_value=(22, True, "22.23.1"))
    def test_collect_and_render_contains_protocol_but_no_password_hashes(
        self,
        _node_version,
        _node_red_version,
        _https,
        _self_signed,
        project_info,
        disk_info,
    ):
        project_info.return_value = handover_mail.NodeRedProjectInfo(
            name="arena-control",
            remote="git@git.example.test:node-red/arena-control.git",
        )
        disk_info.return_value = handover_mail.NodeRedDiskIdentity(
            device="/dev/mmcblk0",
            ptuuid="abcd-1234",
            display_name="Competition image 03",
        )
        machine = SimpleNamespace(
            static_hostname="opi-arena-03",
            hostname_full="opi-arena-03.example.test",
            machine_id="0123456789abcdef",
        )
        generated = datetime(2026, 8, 4, 10, 45, tzinfo=timezone.utc)

        with patch.object(handover_mail.app_cfg, "machineInfo", machine), patch.object(
            handover_mail.app_cfg,
            "SERVER_URL",
            "node.example.test",
        ), patch.object(handover_mail.app_cfg, "SITE_NAME", "Terminal Manager"), patch.object(
            handover_mail.app_cfg,
            "VERSION",
            "1.9.7",
        ):
            data = handover_mail.collect_handover_data(
                "competition",
                FakeNodeConfig(),
                generated_at=generated,
            )
            subject, text_body, html_body = handover_mail.render_handover_mail(
                data,
                "organizer@example.test",
            )

        self.assertIn("Competition arena", subject)
        self.assertIn("http://node.example.test:21880", text_body)
        self.assertIn("Node-RED", text_body)
        self.assertIn("4.1.1", text_body)
        self.assertIn("22.23.1", text_body)
        self.assertIn(handover_mail.TXT_HANDOVER_SECTION_USERS, text_body)
        self.assertIn("admin: RW", text_body)
        self.assertIn("viewer: R", text_body)
        self.assertNotIn("dashboard", text_body.lower())
        self.assertNotIn("dashboard", html_body.lower())
        self.assertIn("Competition image 03", text_body)
        self.assertIn("arena-control", text_body)
        self.assertIn("git@git.example.test:node-red/arena-control.git", text_body)
        self.assertIn(handover_mail.TXT_HANDOVER_SECRET_NOTICE, text_body)
        self.assertIn("Competition arena", html_body)
        self.assertNotIn("$2b$secret-hash", text_body)
        self.assertNotIn("$2b$secret-hash", html_body)
        self.assertNotIn("$2b$other-hash", text_body)

    @patch.object(handover_mail.mail_hlp, "send_mail", return_value=(True, None))
    @patch.object(handover_mail, "render_handover_mail", return_value=("subject", "text", "html"))
    @patch.object(handover_mail, "collect_handover_data")
    @patch.object(handover_mail, "get_handover_recipient", return_value="owner@example.test")
    def test_send_uses_stored_instance_contact(
        self,
        _recipient,
        collect_data,
        _render,
        send_mail,
    ):
        collect_data.return_value = SimpleNamespace()
        ok, error = handover_mail.send_handover_mail("competition", FakeNodeConfig())
        self.assertTrue(ok)
        self.assertIsNone(error)
        send_mail.assert_called_once_with(
            recipients=["owner@example.test"],
            subject="subject",
            body="text",
            html_body="html",
        )


if __name__ == "__main__":
    unittest.main()
