"""Trusted fixed-schema storage helpers for central firewall policy state."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .firewall_policy import firewall_policy_hash, valid_firewall_policy_hash
from .models import (
    HubCentralFirewallRule,
    HubCentralFirewallVpnServer,
    HubFirewallPolicyHostState,
    HubFirewallPolicyStatus,
    HubFirewallPolicyUpdate,
)
from .schema import table_identifier
from .settings import HubSettings


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def current_policy_revision(cursor: Any, settings: HubSettings) -> int:
    meta = table_identifier(settings, "firewall_policy_meta")
    cursor.execute(f"SELECT revision FROM {meta} WHERE id=1")
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Central firewall policy metadata row is missing.")
    return int(row[0])


def load_effective_central_policy(
    cursor: Any,
    settings: HubSettings,
    *,
    host_id: int,
    machine_id: str,
    group_id: int | None,
    generated_at: datetime,
    revision: int | None = None,
) -> HubFirewallPolicyUpdate:
    rules_table = table_identifier(settings, "firewall_rules")
    vpn_table = table_identifier(settings, "firewall_vpn_servers")
    policy_revision = (
        current_policy_revision(cursor, settings)
        if revision is None else int(revision)
    )

    scope_sql = (
        "origin=%s AND ("
        "(target_kind='all' AND host_id IS NULL AND group_id IS NULL) OR "
        "(target_kind='host' AND host_id=%s AND group_id IS NULL) OR "
        "(target_kind='group' AND host_id IS NULL AND group_id=%s)"
        ")"
    )
    scope_params = ("central", host_id, group_id)

    cursor.execute(
        f"SELECT server_uid,target_kind,name,server_ip,server_mask,"
        f"interface_name FROM {vpn_table} WHERE {scope_sql} "
        "ORDER BY CASE target_kind WHEN 'all' THEN 0 "
        "WHEN 'group' THEN 1 WHEN 'host' THEN 2 ELSE 9 END, "
        "server_uid",
        scope_params,
    )
    vpn_servers = tuple(
        HubCentralFirewallVpnServer(
            server_uid=str(item[0]),
            target_kind=str(item[1]),
            name=str(item[2]),
            server_ip=str(item[3]),
            server_mask=int(item[4]),
            interface_name=str(item[5]),
        )
        for item in cursor.fetchall()
    )

    cursor.execute(
        f"SELECT rule_uid,target_kind,position,rule_type,"
        "vpn_server_uid,enabled,name,direction,action,protocol,"
        "source,destination,destination_invert,port_from,port_to,"
        f"src_ports,dst_ports,interface_name,ban_to FROM {rules_table} "
        f"WHERE {scope_sql} "
        "ORDER BY CASE target_kind WHEN 'all' THEN 0 "
        "WHEN 'group' THEN 1 WHEN 'host' THEN 2 ELSE 9 END, "
        "position,rule_uid",
        scope_params,
    )
    rules = tuple(
        HubCentralFirewallRule(
            rule_uid=str(item[0]),
            target_kind=str(item[1]),
            position=int(item[2]),
            rule_type=str(item[3]),
            vpn_server_uid=str(item[4] or ""),
            enabled=bool(item[5]),
            name=str(item[6] or ""),
            direction=str(item[7]),
            action=str(item[8]),
            protocol=str(item[9]),
            source=str(item[10] or ""),
            destination=str(item[11] or ""),
            destination_invert=bool(item[12]),
            port_from=int(item[13]) if item[13] is not None else None,
            port_to=int(item[14]) if item[14] is not None else None,
            src_ports=str(item[15] or ""),
            dst_ports=str(item[16] or ""),
            interface_name=str(item[17] or ""),
            ban_to=item[18].isoformat() if item[18] is not None else None,
        )
        for item in cursor.fetchall()
    )

    base = HubFirewallPolicyUpdate(
        machine_id=machine_id,
        group_id=group_id,
        generated_at=generated_at,
        policy_revision=policy_revision,
        vpn_servers=vpn_servers,
        rules=rules,
    )
    return HubFirewallPolicyUpdate(
        machine_id=base.machine_id,
        group_id=base.group_id,
        generated_at=base.generated_at,
        policy_hash=firewall_policy_hash(base),
        policy_revision=base.policy_revision,
        vpn_servers=base.vpn_servers,
        rules=base.rules,
    )


def sync_policy_host_state(
    cursor: Any,
    settings: HubSettings,
    *,
    host_id: int,
    update: HubFirewallPolicyUpdate,
    reported: HubFirewallPolicyStatus | None,
    now: datetime,
) -> None:
    state = table_identifier(settings, "firewall_policy_host_state")
    if not valid_firewall_policy_hash(update.policy_hash):
        raise ValueError("Invalid desired central firewall policy hash.")

    cursor.execute(
        f"SELECT desired_hash,delivered_hash,applied_hash "
        f"FROM {state} WHERE host_id=%s FOR UPDATE",
        (host_id,),
    )
    existing = cursor.fetchone()
    if existing is None:
        baseline = not update.rules and not update.vpn_servers
        cursor.execute(
            f"INSERT INTO {state} "
            "(host_id,desired_hash,desired_revision,desired_at,"
            "delivered_hash,delivered_revision,delivered_at,"
            "applied_hash,applied_revision,applied_at,apply_status,"
            "apply_error,reported_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'',NULL)",
            (
                host_id,
                update.policy_hash,
                update.policy_revision,
                now,
                update.policy_hash if baseline else "",
                update.policy_revision if baseline else 0,
                now if baseline else None,
                update.policy_hash if baseline else "",
                update.policy_revision if baseline else 0,
                now if baseline else None,
                "applied" if baseline else "unknown",
            ),
        )
    else:
        cursor.execute(
            f"UPDATE {state} SET desired_hash=%s,desired_revision=%s,"
            "desired_at=%s WHERE host_id=%s",
            (
                update.policy_hash,
                update.policy_revision,
                now,
                host_id,
            ),
        )

    if reported is None:
        return

    cached_hash = str(reported.cached_hash or "")
    applied_hash = str(reported.applied_hash or "")
    if cached_hash and not valid_firewall_policy_hash(cached_hash):
        raise ValueError("Invalid reported cached firewall policy hash.")
    if applied_hash and not valid_firewall_policy_hash(applied_hash):
        raise ValueError("Invalid reported applied firewall policy hash.")
    if isinstance(reported.cached_revision, bool) or int(reported.cached_revision) < 0:
        raise ValueError("Invalid reported cached firewall revision.")
    if isinstance(reported.applied_revision, bool) or int(reported.applied_revision) < 0:
        raise ValueError("Invalid reported applied firewall revision.")
    if reported.apply_status not in {"unknown", "applied", "failed", "rolled_back"}:
        raise ValueError("Invalid reported firewall apply status.")
    if len(str(reported.last_error or "")) > 512:
        raise ValueError("Reported firewall apply error exceeds column limit.")

    if cached_hash:
        cursor.execute(
            f"UPDATE {state} SET delivered_hash=%s,delivered_revision=%s,"
            "delivered_at=%s WHERE host_id=%s",
            (
                cached_hash,
                int(reported.cached_revision),
                now,
                host_id,
            ),
        )

    if applied_hash:
        cursor.execute(
            f"UPDATE {state} SET applied_hash=%s,applied_revision=%s,"
            "applied_at=%s,apply_status=%s,apply_error=%s,reported_at=%s "
            "WHERE host_id=%s",
            (
                applied_hash,
                int(reported.applied_revision),
                (
                    reported.applied_at.astimezone(timezone.utc).replace(tzinfo=None)
                    if reported.applied_at is not None
                    else now
                ),
                reported.apply_status,
                str(reported.last_error or "")[:512],
                now,
                host_id,
            ),
        )
    else:
        fields = ["reported_at=%s"]
        params: list[Any] = [now]
        if reported.apply_status in {"failed", "rolled_back"}:
            fields.extend(("apply_status=%s", "apply_error=%s"))
            params.extend((
                reported.apply_status,
                str(reported.last_error or "")[:512],
            ))
        params.append(host_id)
        cursor.execute(
            f"UPDATE {state} SET {','.join(fields)} WHERE host_id=%s",
            tuple(params),
        )


def acknowledge_policy_delivery(
    cursor: Any,
    settings: HubSettings,
    *,
    host_id: int,
    update: HubFirewallPolicyUpdate,
    now: datetime,
) -> None:
    if not valid_firewall_policy_hash(update.policy_hash):
        raise ValueError("Invalid delivered central firewall policy hash.")
    state = table_identifier(settings, "firewall_policy_host_state")
    cursor.execute(
        f"UPDATE {state} SET delivered_hash=%s,delivered_revision=%s,"
        "delivered_at=%s WHERE host_id=%s",
        (
            update.policy_hash,
            int(update.policy_revision),
            now,
            host_id,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("Central firewall host state is missing for delivery ack.")


def list_policy_host_states(
    cursor: Any,
    settings: HubSettings,
) -> tuple[HubFirewallPolicyHostState, ...]:
    hosts = table_identifier(settings, "hosts")
    state = table_identifier(settings, "firewall_policy_host_state")
    cursor.execute(
        f"SELECT h.machine_id,h.hostname,"
        "COALESCE(s.desired_hash,''),COALESCE(s.desired_revision,0),s.desired_at,"
        "COALESCE(s.delivered_hash,''),COALESCE(s.delivered_revision,0),s.delivered_at,"
        "COALESCE(s.applied_hash,''),COALESCE(s.applied_revision,0),s.applied_at,"
        "COALESCE(s.apply_status,'unknown'),COALESCE(s.apply_error,''),s.reported_at "
        f"FROM {hosts} h LEFT JOIN {state} s ON s.host_id=h.id "
        "ORDER BY COALESCE(NULLIF(h.name,''),NULLIF(h.fqdn,''),h.hostname),h.id"
    )
    return tuple(
        HubFirewallPolicyHostState(
            machine_id=str(row[0]),
            hostname=str(row[1]),
            desired_hash=str(row[2] or ""),
            desired_revision=int(row[3] or 0),
            desired_at=_aware(row[4]),
            delivered_hash=str(row[5] or ""),
            delivered_revision=int(row[6] or 0),
            delivered_at=_aware(row[7]),
            applied_hash=str(row[8] or ""),
            applied_revision=int(row[9] or 0),
            applied_at=_aware(row[10]),
            apply_status=str(row[11] or "unknown"),
            apply_error=str(row[12] or ""),
            reported_at=_aware(row[13]),
        )
        for row in cursor.fetchall()
    )
