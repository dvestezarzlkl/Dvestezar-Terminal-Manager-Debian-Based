from __future__ import annotations

import unittest
from unittest.mock import patch

from libs.app.menus.app_33_sftpmanagr import sftp_template_hlp as hlp


class SftpMountpointTemplateHelperTests(unittest.TestCase):
    def _cfg(self):
        return {
            "users": [
                {
                    "sftpuser": "source",
                    "sftpmounts": {
                        "web1": "/var/www/web1",
                        "web2": "/var/www/web2",
                    },
                    "pointsSet": {
                        "web1": {"rw": True},
                        "web2": {"rw": False},
                    },
                    "sftpcerts": [],
                },
                {
                    "sftpuser": "developer",
                    "sftpmounts": {},
                    "sftpcerts": [],
                },
            ]
        }

    def test_create_template_from_user_does_not_change_source_user(self):
        cfg = self._cfg()
        source_before = dict(cfg["users"][0])
        source_mounts_before = dict(cfg["users"][0]["sftpmounts"])

        ok, count = hlp.create_template_from_user(cfg, "webdev", "source")

        self.assertTrue(ok)
        self.assertEqual(count, 2)
        self.assertEqual(cfg["users"][0].get("mountTemplates"), None)
        self.assertEqual(cfg["users"][0]["sftpmounts"], source_mounts_before)
        self.assertEqual(cfg["users"][0]["sftpuser"], source_before["sftpuser"])
        mounts = dict(hlp.list_template_mounts(cfg, "webdev"))
        self.assertEqual({row["label"] for row in mounts.values()}, {"web1", "web2"})
        self.assertTrue(all(mount_id.startswith("mp_") for mount_id in mounts))

    def test_assign_starts_template_mounts_disabled_and_readonly(self):
        cfg = self._cfg()
        ok, _ = hlp.create_template_from_user(cfg, "webdev", "source")
        self.assertTrue(ok)
        self.assertTrue(hlp.assign_template(cfg, "developer", "webdev"))

        records, errors = hlp.list_user_mountpoint_records(cfg, "developer")

        self.assertEqual(errors, [])
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.source == "template" for record in records))
        self.assertTrue(all(not record.enabled for record in records))
        self.assertTrue(all(not record.rw for record in records))
        self.assertTrue(all(not record.my for record in records))

    def test_same_template_point_keeps_per_user_access_and_physical_share_identity(self):
        cfg = self._cfg()
        cfg["users"].append({"sftpuser": "reviewer", "sftpmounts": {}, "sftpcerts": []})
        self.assertTrue(hlp.create_template_from_user(cfg, "webdev", "source")[0])
        self.assertTrue(hlp.assign_template(cfg, "developer", "webdev"))
        self.assertTrue(hlp.assign_template(cfg, "reviewer", "webdev"))
        mount_id, row = hlp.list_template_mounts(cfg, "webdev")[0]

        self.assertTrue(hlp.set_template_mountpoint_enabled(cfg, "developer", mount_id, True))
        self.assertTrue(hlp.set_template_mountpoint_readonly(cfg, "developer", mount_id, True))
        self.assertTrue(hlp.set_template_mountpoint_enabled(cfg, "reviewer", mount_id, True))
        self.assertTrue(hlp.set_template_mountpoint_readonly(cfg, "reviewer", mount_id, False))

        developer_records, developer_errors = hlp.list_user_mountpoint_records(cfg, "developer")
        reviewer_records, reviewer_errors = hlp.list_user_mountpoint_records(cfg, "reviewer")
        developer = next(record for record in developer_records if record.record_id == mount_id)
        reviewer = next(record for record in reviewer_records if record.record_id == mount_id)

        self.assertEqual(developer_errors, [])
        self.assertEqual(reviewer_errors, [])
        self.assertFalse(developer.rw)
        self.assertTrue(reviewer.rw)

        from libs.JBLibs.sftp import sambaPoint

        developer_share = sambaPoint.makeShareNameSafe(row["label"], "developer", True)
        reviewer_share = sambaPoint.makeShareNameSafe(row["label"], "reviewer", True)
        self.assertEqual(developer_share, f"sftp_mount_developer_{row['label']}")
        self.assertEqual(reviewer_share, f"sftp_mount_reviewer_{row['label']}")
        self.assertNotEqual(developer_share, reviewer_share)

    def test_per_user_override_survives_template_label_and_path_change(self):
        cfg = self._cfg()
        hlp.create_template_from_user(cfg, "webdev", "source")
        hlp.assign_template(cfg, "developer", "webdev")
        mount_id, row = hlp.list_template_mounts(cfg, "webdev")[0]
        self.assertTrue(hlp.set_template_mountpoint_enabled(cfg, "developer", mount_id, True))
        self.assertTrue(hlp.set_template_mountpoint_readonly(cfg, "developer", mount_id, False))

        self.assertTrue(hlp.set_template_mountpoint_label(cfg, "webdev", mount_id, "renamed"))
        self.assertTrue(hlp.set_template_mountpoint_path(cfg, "webdev", mount_id, "/srv/renamed"))
        records, errors = hlp.list_user_mountpoint_records(cfg, "developer")
        record = next(item for item in records if item.record_id == mount_id)

        self.assertEqual(errors, [])
        self.assertEqual(record.label, "renamed")
        self.assertEqual(record.path, "/srv/renamed")
        self.assertTrue(record.enabled)
        self.assertTrue(record.rw)

    def test_delete_and_recreate_same_label_gets_new_id_and_no_old_access(self):
        cfg = self._cfg()
        hlp.create_template_from_user(cfg, "webdev", "source")
        hlp.assign_template(cfg, "developer", "webdev")
        old_id, old_row = hlp.list_template_mounts(cfg, "webdev")[0]
        label = old_row["label"]
        path = old_row["path"]
        hlp.set_template_mountpoint_enabled(cfg, "developer", old_id, True)

        self.assertTrue(hlp.delete_template_mountpoint(cfg, "webdev", old_id))
        with patch.object(hlp.uuid, "uuid4", return_value=type("U", (), {"hex": "abcdef"})()):
            new_id = hlp.add_template_mountpoint(cfg, "webdev", label, path)

        self.assertEqual(new_id, "mp_abcdef")
        self.assertNotEqual(new_id, old_id)
        user = cfg["users"][1]
        self.assertNotIn(old_id, user.get("templatePoints", {}))
        records, errors = hlp.list_user_mountpoint_records(cfg, "developer")
        record = next(item for item in records if item.record_id == new_id)
        self.assertEqual(errors, [])
        self.assertFalse(record.enabled)
        self.assertFalse(record.rw)

    def test_unassign_prunes_overrides_and_reassign_starts_safe(self):
        cfg = self._cfg()
        hlp.create_template_from_user(cfg, "webdev", "source")
        hlp.assign_template(cfg, "developer", "webdev")
        mount_id, _ = hlp.list_template_mounts(cfg, "webdev")[0]
        hlp.set_template_mountpoint_enabled(cfg, "developer", mount_id, True)
        hlp.set_template_mountpoint_readonly(cfg, "developer", mount_id, False)

        self.assertTrue(hlp.unassign_template(cfg, "developer", "webdev"))
        self.assertNotIn("templatePoints", cfg["users"][1])
        self.assertTrue(hlp.assign_template(cfg, "developer", "webdev"))
        records, errors = hlp.list_user_mountpoint_records(cfg, "developer")
        record = next(item for item in records if item.record_id == mount_id)
        self.assertEqual(errors, [])
        self.assertFalse(record.enabled)
        self.assertFalse(record.rw)

    def test_assign_conflicting_template_rolls_back(self):
        cfg = self._cfg()
        cfg["users"][1]["sftpmounts"] = {"web1": "/srv/local-web1"}
        hlp.create_template_from_user(cfg, "webdev", "source")

        self.assertFalse(hlp.assign_template(cfg, "developer", "webdev"))
        self.assertNotIn("webdev", cfg["users"][1].get("mountTemplates", []))

    def test_local_enabled_flag_is_explicit_and_legacy_default_stays_enabled(self):
        cfg = self._cfg()
        records, errors = hlp.list_user_mountpoint_records(cfg, "source")
        self.assertEqual(errors, [])
        self.assertTrue(all(record.enabled for record in records))

        self.assertTrue(hlp.set_local_mountpoint_enabled(cfg, "source", "web1", False))
        records, errors = hlp.list_user_mountpoint_records(cfg, "source")
        self.assertEqual(errors, [])
        web1 = next(record for record in records if record.label == "web1")
        web2 = next(record for record in records if record.label == "web2")
        self.assertFalse(web1.enabled)
        self.assertTrue(web2.enabled)


if __name__ == "__main__":
    unittest.main()
