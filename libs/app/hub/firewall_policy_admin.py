"""Trusted central firewall desired-state writer for future web/API UI.

This module owns central DB mutations only. It intentionally exposes no method
that can invoke UFW or acknowledge the local fresh-SSH token.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from libs.app.menus.app_40_firewall.config import (
    FirewallConfigError,
    normalize_rule,
    normalize_vpn_server,
)

from .database import HubDatabase
from .firewall_policy_store import (
    current_policy_revision,
    list_policy_host_states,
    load_effective_central_policy,
    sync_policy_host_state,
)
from .models import (
    HubCentralFirewallRule,
    HubCentralFirewallVpnServer,
    HubFirewallPolicyActor,
    HubFirewallPolicyAdminSnapshot,
    HubFirewallPolicyMutationResult,
    HubFirewallPolicyRuleRecord,
    HubFirewallPolicyTarget,
    HubFirewallPolicyVpnServerRecord,
)
from .schema import table_identifier

FIREWALL_POLICY_READ_PERMISSION = "firewall.policy.read"
FIREWALL_POLICY_WRITE_PERMISSION = "firewall.policy.write"

_UID_RE = re.compile(r"^[0-9a-f]{32}$")
_INTERFACE_RE = re.compile(r"^[a-zA-Z0-9_.+-]{0,15}$")


class HubFirewallPolicyAdminError(ValueError):
    pass


class HubFirewallPolicyRevisionConflict(HubFirewallPolicyAdminError):
    pass


class HubFirewallPolicyAdmin:
    def __init__(self, database: HubDatabase):
        if not isinstance(database, HubDatabase):
            raise TypeError("HubFirewallPolicyAdmin requires HubDatabase.")
        self.database = database
        self.settings = database.settings

    @staticmethod
    def _actor_subject(
        actor: HubFirewallPolicyActor,
        *,
        write: bool,
    ) -> str:
        if not isinstance(actor, HubFirewallPolicyActor):
            raise HubFirewallPolicyAdminError("Invalid firewall policy actor.")
        subject = str(actor.subject or "").strip()
        if not subject or len(subject) > 128:
            raise HubFirewallPolicyAdminError("Invalid firewall policy actor identity.")
        permissions = set(actor.permissions)
        if write:
            if FIREWALL_POLICY_WRITE_PERMISSION not in permissions:
                raise PermissionError("Missing firewall.policy.write permission.")
        elif not (
            FIREWALL_POLICY_READ_PERMISSION in permissions
            or FIREWALL_POLICY_WRITE_PERMISSION in permissions
        ):
            raise PermissionError("Missing firewall.policy.read permission.")
        return subject

    def _resolve_target(
        self,
        cursor: Any,
        target: HubFirewallPolicyTarget,
    ) -> tuple[str, int | None, int | None]:
        if not isinstance(target, HubFirewallPolicyTarget):
            raise HubFirewallPolicyAdminError("Invalid firewall policy target.")
        kind = str(target.target_kind or "")
        hosts = table_identifier(self.settings, "hosts")
        groups = table_identifier(self.settings, "host_groups")
        if kind == "all":
            if target.machine_id or target.group_code:
                raise HubFirewallPolicyAdminError("All target cannot carry host/group identity.")
            return kind, None, None
        if kind == "host":
            machine_id = str(target.machine_id or "").strip()
            if not machine_id or target.group_code:
                raise HubFirewallPolicyAdminError("Host target requires machine_id only.")
            cursor.execute(
                f"SELECT id FROM {hosts} WHERE machine_id=%s LIMIT 1",
                (machine_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise HubFirewallPolicyAdminError("Target host does not exist.")
            return kind, int(row[0]), None
        if kind == "group":
            code = str(target.group_code or "").strip()
            if not code or target.machine_id:
                raise HubFirewallPolicyAdminError("Group target requires group_code only.")
            cursor.execute(
                f"SELECT id FROM {groups} WHERE code=%s LIMIT 1",
                (code,),
            )
            row = cursor.fetchone()
            if row is None:
                raise HubFirewallPolicyAdminError("Target group does not exist.")
            return kind, None, int(row[0])
        raise HubFirewallPolicyAdminError("Unsupported firewall policy target kind.")

    def _target_from_row(
        self,
        cursor: Any,
        target_kind: str,
        host_id: int | None,
        group_id: int | None,
    ) -> HubFirewallPolicyTarget:
        hosts = table_identifier(self.settings, "hosts")
        groups = table_identifier(self.settings, "host_groups")
        if target_kind == "all":
            return HubFirewallPolicyTarget("all")
        if target_kind == "host" and host_id is not None:
            cursor.execute(f"SELECT machine_id FROM {hosts} WHERE id=%s", (host_id,))
            row = cursor.fetchone()
            if row is None:
                raise HubFirewallPolicyAdminError("Stored target host is missing.")
            return HubFirewallPolicyTarget("host", machine_id=str(row[0]))
        if target_kind == "group" and group_id is not None:
            cursor.execute(f"SELECT code FROM {groups} WHERE id=%s", (group_id,))
            row = cursor.fetchone()
            if row is None:
                raise HubFirewallPolicyAdminError("Stored target group is missing.")
            return HubFirewallPolicyTarget("group", group_code=str(row[0]))
        raise HubFirewallPolicyAdminError("Stored firewall target is inconsistent.")

    def _affected_host_ids(
        self,
        cursor: Any,
        target: HubFirewallPolicyTarget,
    ) -> set[int]:
        kind, host_id, group_id = self._resolve_target(cursor, target)
        hosts = table_identifier(self.settings, "hosts")
        if kind == "all":
            cursor.execute(f"SELECT id FROM {hosts}")
            return {int(row[0]) for row in cursor.fetchall()}
        if kind == "host":
            assert host_id is not None
            return {host_id}
        assert group_id is not None
        cursor.execute(f"SELECT id FROM {hosts} WHERE group_id=%s", (group_id,))
        return {int(row[0]) for row in cursor.fetchall()}

    @staticmethod
    def _validate_revision(expected_revision: int, current: int) -> None:
        if isinstance(expected_revision, bool) or int(expected_revision) < 0:
            raise HubFirewallPolicyAdminError("Invalid expected policy revision.")
        if int(expected_revision) != int(current):
            raise HubFirewallPolicyRevisionConflict(
                f"Central firewall policy changed: expected revision "
                f"{expected_revision}, current {current}."
            )

    def _bump_revision(
        self,
        cursor: Any,
        *,
        actor: str,
        expected_revision: int,
        now: datetime,
    ) -> int:
        meta = table_identifier(self.settings, "firewall_policy_meta")
        cursor.execute(f"SELECT revision FROM {meta} WHERE id=1 FOR UPDATE")
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Central firewall policy metadata row is missing.")
        current = int(row[0])
        self._validate_revision(expected_revision, current)
        revision = current + 1
        cursor.execute(
            f"UPDATE {meta} SET revision=%s,updated_at=%s,updated_by=%s WHERE id=1",
            (revision, now, actor),
        )
        return revision

    @staticmethod
    def _normalize_server(
        item: HubCentralFirewallVpnServer,
    ) -> HubCentralFirewallVpnServer:
        if not isinstance(item, HubCentralFirewallVpnServer):
            raise HubFirewallPolicyAdminError("Invalid central VPN server.")
        if not _UID_RE.fullmatch(item.server_uid):
            raise HubFirewallPolicyAdminError("Invalid central VPN server UID.")
        if item.target_kind not in {"host", "group", "all"}:
            raise HubFirewallPolicyAdminError("Invalid central VPN server target.")
        try:
            normalized = normalize_vpn_server({
                "server_id": item.server_uid,
                "name": item.name,
                "ip": item.server_ip,
                "mask": item.server_mask,
                "interface": item.interface_name,
            })
        except FirewallConfigError as exc:
            raise HubFirewallPolicyAdminError(
                f"Invalid central VPN server: {exc}"
            ) from exc
        return HubCentralFirewallVpnServer(
            server_uid=normalized.server_id,
            target_kind=item.target_kind,
            name=normalized.name,
            server_ip=normalized.ip,
            server_mask=normalized.mask,
            interface_name=normalized.interface,
        )

    @staticmethod
    def _normalize_rule(
        item: HubCentralFirewallRule,
    ) -> HubCentralFirewallRule:
        if not isinstance(item, HubCentralFirewallRule):
            raise HubFirewallPolicyAdminError("Invalid central firewall rule.")
        if not _UID_RE.fullmatch(item.rule_uid):
            raise HubFirewallPolicyAdminError("Invalid central firewall rule UID.")
        if item.target_kind not in {"host", "group", "all"}:
            raise HubFirewallPolicyAdminError("Invalid central firewall rule target.")
        if isinstance(item.position, bool) or int(item.position) < 0:
            raise HubFirewallPolicyAdminError("Invalid central firewall rule position.")
        try:
            normalized = normalize_rule({
                "rule_id": item.rule_uid,
                "kind": item.rule_type,
                "enabled": item.enabled,
                "name": item.name,
                "direction": item.direction,
                "action": item.action,
                "protocol": item.protocol,
                "source": item.source,
                "destination": item.destination,
                "destination_invert": item.destination_invert,
                "port_from": item.port_from,
                "port_to": item.port_to,
                "src_ports": item.src_ports,
                "dst_ports": item.dst_ports,
                "interface": item.interface_name,
                "ban_to": item.ban_to or "",
                "vpn_server_id": item.vpn_server_uid,
            })
        except FirewallConfigError as exc:
            raise HubFirewallPolicyAdminError(
                f"Invalid central firewall rule: {exc}"
            ) from exc
        return HubCentralFirewallRule(
            rule_uid=normalized.rule_id,
            target_kind=item.target_kind,
            position=int(item.position),
            rule_type=normalized.kind,
            enabled=normalized.enabled,
            name=normalized.name,
            direction=normalized.direction,
            action=normalized.action,
            protocol=normalized.protocol,
            source=normalized.source,
            destination=normalized.destination,
            destination_invert=normalized.destination_invert,
            port_from=normalized.port_from,
            port_to=normalized.port_to,
            src_ports=normalized.src_ports,
            dst_ports=normalized.dst_ports,
            interface_name=normalized.interface,
            ban_to=normalized.ban_to or None,
            vpn_server_uid=normalized.vpn_server_id,
        )

    def _validate_vpn_reference(
        self,
        cursor: Any,
        *,
        vpn_server_uid: str,
        target: HubFirewallPolicyTarget,
    ) -> None:
        if not vpn_server_uid:
            return
        kind, host_id, group_id = self._resolve_target(cursor, target)
        table = table_identifier(self.settings, "firewall_vpn_servers")
        if kind == "all":
            cursor.execute(
                f"SELECT 1 FROM {table} WHERE server_uid=%s AND origin='central' "
                "AND target_kind='all' AND host_id IS NULL AND group_id IS NULL LIMIT 1",
                (vpn_server_uid,),
            )
        elif kind == "group":
            cursor.execute(
                f"SELECT 1 FROM {table} WHERE server_uid=%s AND origin='central' AND ("
                "(target_kind='all' AND host_id IS NULL AND group_id IS NULL) OR "
                "(target_kind='group' AND host_id IS NULL AND group_id=%s)) LIMIT 1",
                (vpn_server_uid, group_id),
            )
        else:
            hosts = table_identifier(self.settings, "hosts")
            cursor.execute(f"SELECT group_id FROM {hosts} WHERE id=%s", (host_id,))
            row = cursor.fetchone()
            host_group_id = int(row[0]) if row and row[0] is not None else None
            cursor.execute(
                f"SELECT 1 FROM {table} WHERE server_uid=%s AND origin='central' AND ("
                "(target_kind='all' AND host_id IS NULL AND group_id IS NULL) OR "
                "(target_kind='host' AND host_id=%s AND group_id IS NULL) OR "
                "(target_kind='group' AND host_id IS NULL AND group_id=%s)) LIMIT 1",
                (vpn_server_uid, host_id, host_group_id),
            )
        if cursor.fetchone() is None:
            raise HubFirewallPolicyAdminError(
                "Referenced central VPN server is not applicable to the target."
            )

    def _recompute_hosts(
        self,
        cursor: Any,
        host_ids: set[int],
        *,
        revision: int,
        now: datetime,
    ) -> tuple[str, ...]:
        if not host_ids:
            return ()
        hosts = table_identifier(self.settings, "hosts")
        machine_ids: list[str] = []
        for host_id in sorted(host_ids):
            cursor.execute(
                f"SELECT machine_id,group_id FROM {hosts} WHERE id=%s",
                (host_id,),
            )
            row = cursor.fetchone()
            if row is None:
                continue
            machine_id = str(row[0])
            group_id = int(row[1]) if row[1] is not None else None
            update = load_effective_central_policy(
                cursor,
                self.settings,
                host_id=host_id,
                machine_id=machine_id,
                group_id=group_id,
                generated_at=now.replace(tzinfo=timezone.utc),
                revision=revision,
            )
            sync_policy_host_state(
                cursor,
                self.settings,
                host_id=host_id,
                update=update,
                reported=None,
                now=now,
            )
            machine_ids.append(machine_id)
        return tuple(machine_ids)

    def _result(
        self,
        cursor: Any,
        *,
        revision: int,
        affected_machine_ids: tuple[str, ...],
    ) -> HubFirewallPolicyMutationResult:
        wanted = set(affected_machine_ids)
        states = tuple(
            state for state in list_policy_host_states(cursor, self.settings)
            if state.machine_id in wanted
        )
        return HubFirewallPolicyMutationResult(revision, states)

    def upsert_rule(
        self,
        *,
        actor: HubFirewallPolicyActor,
        target: HubFirewallPolicyTarget,
        rule: HubCentralFirewallRule,
        expected_revision: int,
    ) -> HubFirewallPolicyMutationResult:
        subject = self._actor_subject(actor, write=True)
        rule = self._normalize_rule(rule)
        if rule.target_kind != target.target_kind:
            raise HubFirewallPolicyAdminError("Rule target_kind does not match target.")
        table = table_identifier(self.settings, "firewall_rules")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self.database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    kind, host_id, group_id = self._resolve_target(cursor, target)
                    self._validate_vpn_reference(
                        cursor,
                        vpn_server_uid=rule.vpn_server_uid,
                        target=target,
                    )
                    affected = self._affected_host_ids(cursor, target)
                    cursor.execute(
                        f"SELECT origin,target_kind,host_id,group_id FROM {table} "
                        "WHERE rule_uid=%s LIMIT 1 FOR UPDATE",
                        (rule.rule_uid,),
                    )
                    old = cursor.fetchone()
                    if old is not None:
                        if str(old[0]) != "central":
                            raise HubFirewallPolicyAdminError(
                                "Rule UID is owned by host-local policy."
                            )
                        old_target = self._target_from_row(
                            cursor,
                            str(old[1]),
                            int(old[2]) if old[2] is not None else None,
                            int(old[3]) if old[3] is not None else None,
                        )
                        affected |= self._affected_host_ids(cursor, old_target)
                    revision = self._bump_revision(
                        cursor,
                        actor=subject,
                        expected_revision=expected_revision,
                        now=now,
                    )
                    if old is None:
                        cursor.execute(
                            f"INSERT INTO {table} "
                            "(rule_uid,origin,target_kind,position,host_id,group_id,"
                            "rule_type,vpn_server_uid,enabled,name,direction,action,"
                            "protocol,source,destination,destination_invert,port_from,"
                            "port_to,src_ports,dst_ports,interface_name,ban_to,last_seen_at) "
                            "VALUES (%s,'central',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                            "%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (
                                rule.rule_uid, kind, int(rule.position), host_id, group_id,
                                rule.rule_type, rule.vpn_server_uid or None,
                                1 if rule.enabled else 0, rule.name, rule.direction,
                                rule.action, rule.protocol, rule.source, rule.destination,
                                1 if rule.destination_invert else 0, rule.port_from,
                                rule.port_to, rule.src_ports, rule.dst_ports,
                                rule.interface_name, rule.ban_to or None, now,
                            ),
                        )
                    else:
                        cursor.execute(
                            f"UPDATE {table} SET target_kind=%s,position=%s,host_id=%s,"
                            "group_id=%s,rule_type=%s,vpn_server_uid=%s,enabled=%s,"
                            "name=%s,direction=%s,action=%s,protocol=%s,source=%s,"
                            "destination=%s,destination_invert=%s,port_from=%s,port_to=%s,"
                            "src_ports=%s,dst_ports=%s,interface_name=%s,ban_to=%s,"
                            "last_seen_at=%s WHERE rule_uid=%s AND origin='central'",
                            (
                                kind, int(rule.position), host_id, group_id, rule.rule_type,
                                rule.vpn_server_uid or None, 1 if rule.enabled else 0,
                                rule.name, rule.direction, rule.action, rule.protocol,
                                rule.source, rule.destination,
                                1 if rule.destination_invert else 0, rule.port_from,
                                rule.port_to, rule.src_ports, rule.dst_ports,
                                rule.interface_name, rule.ban_to or None, now,
                                rule.rule_uid,
                            ),
                        )
                    affected_ids = self._recompute_hosts(
                        cursor, affected, revision=revision, now=now
                    )
                    result = self._result(
                        cursor,
                        revision=revision,
                        affected_machine_ids=affected_ids,
                    )
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def delete_rule(
        self,
        rule_uid: str,
        *,
        actor: HubFirewallPolicyActor,
        expected_revision: int,
    ) -> HubFirewallPolicyMutationResult:
        subject = self._actor_subject(actor, write=True)
        if not _UID_RE.fullmatch(str(rule_uid or "")):
            raise HubFirewallPolicyAdminError("Invalid central firewall rule UID.")
        table = table_identifier(self.settings, "firewall_rules")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self.database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"SELECT origin,target_kind,host_id,group_id FROM {table} "
                        "WHERE rule_uid=%s LIMIT 1 FOR UPDATE",
                        (rule_uid,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise HubFirewallPolicyAdminError("Central firewall rule not found.")
                    if str(row[0]) != "central":
                        raise HubFirewallPolicyAdminError(
                            "Rule UID is owned by host-local policy."
                        )
                    target = self._target_from_row(
                        cursor,
                        str(row[1]),
                        int(row[2]) if row[2] is not None else None,
                        int(row[3]) if row[3] is not None else None,
                    )
                    affected = self._affected_host_ids(cursor, target)
                    revision = self._bump_revision(
                        cursor,
                        actor=subject,
                        expected_revision=expected_revision,
                        now=now,
                    )
                    cursor.execute(
                        f"DELETE FROM {table} WHERE rule_uid=%s AND origin='central'",
                        (rule_uid,),
                    )
                    affected_ids = self._recompute_hosts(
                        cursor, affected, revision=revision, now=now
                    )
                    result = self._result(
                        cursor,
                        revision=revision,
                        affected_machine_ids=affected_ids,
                    )
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def upsert_vpn_server(
        self,
        *,
        actor: HubFirewallPolicyActor,
        target: HubFirewallPolicyTarget,
        server: HubCentralFirewallVpnServer,
        expected_revision: int,
    ) -> HubFirewallPolicyMutationResult:
        subject = self._actor_subject(actor, write=True)
        server = self._normalize_server(server)
        if server.target_kind != target.target_kind:
            raise HubFirewallPolicyAdminError("VPN server target_kind does not match target.")
        table = table_identifier(self.settings, "firewall_vpn_servers")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self.database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    kind, host_id, group_id = self._resolve_target(cursor, target)
                    affected = self._affected_host_ids(cursor, target)
                    cursor.execute(
                        f"SELECT id FROM {table} WHERE server_uid=%s AND origin='central' "
                        "AND target_kind=%s AND host_id <=> %s AND group_id <=> %s "
                        "LIMIT 1 FOR UPDATE",
                        (server.server_uid, kind, host_id, group_id),
                    )
                    row = cursor.fetchone()
                    revision = self._bump_revision(
                        cursor,
                        actor=subject,
                        expected_revision=expected_revision,
                        now=now,
                    )
                    if row is None:
                        cursor.execute(
                            f"INSERT INTO {table} "
                            "(server_uid,origin,target_kind,host_id,group_id,name,"
                            "server_ip,server_mask,interface_name,last_seen_at) "
                            "VALUES (%s,'central',%s,%s,%s,%s,%s,%s,%s,%s)",
                            (
                                server.server_uid, kind, host_id, group_id, server.name,
                                server.server_ip, int(server.server_mask),
                                server.interface_name, now,
                            ),
                        )
                    else:
                        cursor.execute(
                            f"UPDATE {table} SET name=%s,server_ip=%s,server_mask=%s,"
                            "interface_name=%s,last_seen_at=%s WHERE id=%s",
                            (
                                server.name, server.server_ip, int(server.server_mask),
                                server.interface_name, now, int(row[0]),
                            ),
                        )
                    affected_ids = self._recompute_hosts(
                        cursor, affected, revision=revision, now=now
                    )
                    result = self._result(
                        cursor,
                        revision=revision,
                        affected_machine_ids=affected_ids,
                    )
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def delete_vpn_server(
        self,
        server_uid: str,
        *,
        target: HubFirewallPolicyTarget,
        actor: HubFirewallPolicyActor,
        expected_revision: int,
    ) -> HubFirewallPolicyMutationResult:
        subject = self._actor_subject(actor, write=True)
        if not _UID_RE.fullmatch(str(server_uid or "")):
            raise HubFirewallPolicyAdminError("Invalid central VPN server UID.")
        table = table_identifier(self.settings, "firewall_vpn_servers")
        rules = table_identifier(self.settings, "firewall_rules")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self.database.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    kind, host_id, group_id = self._resolve_target(cursor, target)
                    cursor.execute(
                        f"SELECT id FROM {table} WHERE server_uid=%s AND origin='central' "
                        "AND target_kind=%s AND host_id <=> %s AND group_id <=> %s "
                        "LIMIT 1 FOR UPDATE",
                        (server_uid, kind, host_id, group_id),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise HubFirewallPolicyAdminError("Central VPN server not found.")
                    cursor.execute(
                        f"SELECT 1 FROM {rules} WHERE origin='central' "
                        "AND vpn_server_uid=%s LIMIT 1",
                        (server_uid,),
                    )
                    if cursor.fetchone() is not None:
                        raise HubFirewallPolicyAdminError(
                            "Central VPN server is still referenced by a central rule."
                        )
                    affected = self._affected_host_ids(cursor, target)
                    revision = self._bump_revision(
                        cursor,
                        actor=subject,
                        expected_revision=expected_revision,
                        now=now,
                    )
                    cursor.execute(f"DELETE FROM {table} WHERE id=%s", (int(row[0]),))
                    affected_ids = self._recompute_hosts(
                        cursor, affected, revision=revision, now=now
                    )
                    result = self._result(
                        cursor,
                        revision=revision,
                        affected_machine_ids=affected_ids,
                    )
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def get_snapshot(
        self,
        *,
        actor: HubFirewallPolicyActor,
    ) -> HubFirewallPolicyAdminSnapshot:
        """Typed read model for future web/API policy editors."""
        self._actor_subject(actor, write=False)
        meta = table_identifier(self.settings, "firewall_policy_meta")
        rules_table = table_identifier(self.settings, "firewall_rules")
        vpn_table = table_identifier(self.settings, "firewall_vpn_servers")

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT revision,updated_at,updated_by FROM {meta} WHERE id=1"
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("Central firewall policy metadata row is missing.")
                revision = int(row[0])
                updated_at = row[1]
                if updated_at is not None and updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                updated_by = str(row[2] or "")

                cursor.execute(
                    f"SELECT rule_uid,target_kind,position,host_id,group_id,"
                    "rule_type,vpn_server_uid,enabled,name,direction,action,protocol,"
                    "source,destination,destination_invert,port_from,port_to,"
                    f"src_ports,dst_ports,interface_name,ban_to FROM {rules_table} "
                    "WHERE origin='central' "
                    "ORDER BY CASE target_kind WHEN 'all' THEN 0 "
                    "WHEN 'group' THEN 1 WHEN 'host' THEN 2 ELSE 9 END,"
                    "group_id,host_id,position,rule_uid"
                )
                rule_records = []
                for item in cursor.fetchall():
                    target = self._target_from_row(
                        cursor,
                        str(item[1]),
                        int(item[3]) if item[3] is not None else None,
                        int(item[4]) if item[4] is not None else None,
                    )
                    rule_records.append(HubFirewallPolicyRuleRecord(
                        target=target,
                        rule=HubCentralFirewallRule(
                            rule_uid=str(item[0]),
                            target_kind=str(item[1]),
                            position=int(item[2]),
                            rule_type=str(item[5]),
                            vpn_server_uid=str(item[6] or ""),
                            enabled=bool(item[7]),
                            name=str(item[8] or ""),
                            direction=str(item[9]),
                            action=str(item[10]),
                            protocol=str(item[11]),
                            source=str(item[12] or ""),
                            destination=str(item[13] or ""),
                            destination_invert=bool(item[14]),
                            port_from=int(item[15]) if item[15] is not None else None,
                            port_to=int(item[16]) if item[16] is not None else None,
                            src_ports=str(item[17] or ""),
                            dst_ports=str(item[18] or ""),
                            interface_name=str(item[19] or ""),
                            ban_to=item[20].isoformat() if item[20] is not None else None,
                        ),
                    ))

                cursor.execute(
                    f"SELECT server_uid,target_kind,host_id,group_id,name,"
                    f"server_ip,server_mask,interface_name FROM {vpn_table} "
                    "WHERE origin='central' "
                    "ORDER BY CASE target_kind WHEN 'all' THEN 0 "
                    "WHEN 'group' THEN 1 WHEN 'host' THEN 2 ELSE 9 END,"
                    "group_id,host_id,server_uid"
                )
                vpn_records = []
                for item in cursor.fetchall():
                    target = self._target_from_row(
                        cursor,
                        str(item[1]),
                        int(item[2]) if item[2] is not None else None,
                        int(item[3]) if item[3] is not None else None,
                    )
                    vpn_records.append(HubFirewallPolicyVpnServerRecord(
                        target=target,
                        server=HubCentralFirewallVpnServer(
                            server_uid=str(item[0]),
                            target_kind=str(item[1]),
                            name=str(item[4]),
                            server_ip=str(item[5]),
                            server_mask=int(item[6]),
                            interface_name=str(item[7]),
                        ),
                    ))

                states = list_policy_host_states(cursor, self.settings)

        return HubFirewallPolicyAdminSnapshot(
            revision=revision,
            updated_at=updated_at,
            updated_by=updated_by,
            rules=tuple(rule_records),
            vpn_servers=tuple(vpn_records),
            host_states=states,
        )

    def current_revision(
        self,
        *,
        actor: HubFirewallPolicyActor,
    ) -> int:
        self._actor_subject(actor, write=False)
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                return current_policy_revision(cursor, self.settings)

    def list_host_states(
        self,
        *,
        actor: HubFirewallPolicyActor,
    ):
        self._actor_subject(actor, write=False)
        return self.database.list_firewall_policy_states()
