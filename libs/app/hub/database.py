from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import re
from typing import Any, Iterator

from .models import (
    HubDisk,
    HubDiskNameUpdate,
    HubHostSnapshot,
    HubNodeRedInstance,
    HubProviderSnapshot,
    HubProviderSyncResult,
    HubState,
    HubStatus,
)
from .schema import HubSchemaManager, table_identifier
from .settings import HubSettings


_PTUUID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_DEVICE_NAME_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,128}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("Expected a datetime value.")
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _optional_bool(value: Any) -> Any:
    if value is None:
        return None
    return 1 if bool(value) else 0


class HubDatabase:
    def __init__(self, settings: HubSettings):
        self.settings = settings

    def _pymysql(self):
        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError(
                "PyMySQL is not installed. Run the sys_apps setup/update step."
            ) from exc
        return pymysql

    @contextmanager
    def connect(self, include_database: bool = True) -> Iterator[Any]:
        ok, error = self.settings.validate()
        if not ok:
            raise ValueError(error)
        pymysql = self._pymysql()
        kwargs = {
            "host": self.settings.host,
            "port": self.settings.port,
            "user": self.settings.user,
            "password": self.settings.password,
            "charset": "utf8mb4",
            "connect_timeout": self.settings.connect_timeout,
            "read_timeout": max(3, self.settings.connect_timeout),
            "write_timeout": max(3, self.settings.connect_timeout),
            "autocommit": False,
        }
        if include_database:
            kwargs["database"] = self.settings.database
        connection = pymysql.connect(**kwargs)
        try:
            yield connection
        finally:
            connection.close()

    def check_status(self) -> HubStatus:
        checked_at = datetime.now().astimezone()
        if not self.settings.enabled:
            return HubStatus(HubState.DISABLED, "disabled", checked_at)
        ok, error = self.settings.validate(require_enabled=True)
        if not ok:
            return HubStatus(HubState.NOT_CONFIGURED, error, checked_at)

        try:
            with self.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT VERSION()")
                    row = cursor.fetchone()
                    server_version = str(row[0]) if row else ""
                check = HubSchemaManager(self.settings).check(connection)
        except Exception as exc:
            pymysql = None
            try:
                pymysql = self._pymysql()
            except Exception:
                pass
            if pymysql is not None and isinstance(exc, pymysql.err.OperationalError):
                code = int(exc.args[0]) if exc.args else 0
                if code == 1049:
                    return HubStatus(
                        HubState.DATABASE_MISSING,
                        "database does not exist",
                        checked_at,
                    )
            return HubStatus(
                HubState.OFFLINE,
                self.settings.redact_error(exc),
                checked_at,
            )

        if check.error:
            return HubStatus(
                HubState.ERROR,
                check.error,
                checked_at,
                server_version,
                check.current_version,
            )
        if not check.exists:
            return HubStatus(
                HubState.SCHEMA_MISSING,
                "schema is not initialized",
                checked_at,
                server_version,
                0,
            )
        if not check.current:
            return HubStatus(
                HubState.SCHEMA_OUTDATED,
                f"schema {check.current_version}, expected {check.latest_version}",
                checked_at,
                server_version,
                check.current_version,
            )
        return HubStatus(
            HubState.READY,
            "ready",
            checked_at,
            server_version,
            check.current_version,
        )

    def initialize_or_upgrade_schema(self) -> int:
        ok, error = self.settings.validate(require_enabled=True)
        if not ok:
            raise ValueError(error)
        database_identifier = f"`{self.settings.database}`"
        with self.connect(include_database=False) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS {database_identifier} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            connection.commit()
        with self.connect() as connection:
            return HubSchemaManager(self.settings).apply(connection)

    def _host_id(self, cursor: Any, machine_id: str) -> int:
        hosts = table_identifier(self.settings, "hosts")
        cursor.execute(
            f"SELECT id FROM {hosts} WHERE machine_id=%s LIMIT 1",
            (machine_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Hub host record is missing.")
        return int(row[0])

    def _upsert_source(
        self,
        cursor: Any,
        host_id: int,
        source_key: str,
        status: str,
        item_count: int,
        error_text: str = "",
    ) -> None:
        sources = table_identifier(self.settings, "sync_sources")
        cursor.execute(
            f"INSERT INTO {sources} "
            "(host_id, source_key, status, item_count, error_text, synced_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "status=VALUES(status), item_count=VALUES(item_count), "
            "error_text=VALUES(error_text), synced_at=VALUES(synced_at)",
            (
                host_id,
                source_key,
                status,
                max(0, int(item_count)),
                str(error_text or "")[:1024],
                _utc_now(),
            ),
        )

    def sync_core(self, snapshot: HubHostSnapshot) -> int:
        if not snapshot.machine_id:
            raise ValueError("Machine ID is required for SysApps Hub synchronization.")
        hosts = table_identifier(self.settings, "hosts")
        addresses = table_identifier(self.settings, "host_addresses")
        services = table_identifier(self.settings, "host_services")
        now = _utc_now()

        with self.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"INSERT INTO {hosts} "
                        "(machine_id, hostname, fqdn, operating_system, kernel, "
                        "architecture, hardware_vendor, hardware_model, "
                        "sys_apps_version, jblibs_version, first_seen_at, last_seen_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON DUPLICATE KEY UPDATE "
                        "hostname=VALUES(hostname), fqdn=VALUES(fqdn), "
                        "operating_system=VALUES(operating_system), kernel=VALUES(kernel), "
                        "architecture=VALUES(architecture), "
                        "hardware_vendor=VALUES(hardware_vendor), "
                        "hardware_model=VALUES(hardware_model), "
                        "sys_apps_version=VALUES(sys_apps_version), "
                        "jblibs_version=VALUES(jblibs_version), "
                        "last_seen_at=VALUES(last_seen_at)",
                        (
                            snapshot.machine_id,
                            snapshot.hostname,
                            snapshot.fqdn,
                            snapshot.operating_system,
                            snapshot.kernel,
                            snapshot.architecture,
                            snapshot.hardware_vendor,
                            snapshot.hardware_model,
                            snapshot.sys_apps_version,
                            snapshot.jblibs_version,
                            now,
                            now,
                        ),
                    )
                    host_id = self._host_id(cursor, snapshot.machine_id)

                    cursor.execute(f"DELETE FROM {addresses} WHERE host_id=%s", (host_id,))
                    if snapshot.addresses:
                        cursor.executemany(
                            f"INSERT INTO {addresses} "
                            "(host_id, interface_name, family, address, netmask, "
                            "prefix_length, mac, scope, last_seen_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            [
                                (
                                    host_id,
                                    item.interface_name,
                                    item.family,
                                    item.address,
                                    item.netmask,
                                    item.prefix_length,
                                    item.mac,
                                    item.scope,
                                    now,
                                )
                                for item in snapshot.addresses
                            ],
                        )

                    cursor.execute(f"DELETE FROM {services} WHERE host_id=%s", (host_id,))
                    if snapshot.services:
                        cursor.executemany(
                            f"INSERT INTO {services} "
                            "(host_id, service_key, detected, port, url, status, "
                            "version, last_seen_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            [
                                (
                                    host_id,
                                    item.service_key,
                                    1 if item.detected else 0,
                                    item.port,
                                    item.url,
                                    item.status,
                                    item.version,
                                    now,
                                )
                                for item in snapshot.services
                            ],
                        )

                    self._upsert_source(
                        cursor,
                        host_id,
                        "core",
                        "ok",
                        len(snapshot.addresses) + len(snapshot.services),
                    )
                connection.commit()
                return host_id
            except Exception:
                connection.rollback()
                raise

    def sync_provider(
        self,
        machine_id: str,
        snapshot: HubProviderSnapshot,
    ) -> HubProviderSyncResult:
        if snapshot.dataset == "node_red_instances":
            return self._sync_node_red_provider(machine_id, snapshot)
        if snapshot.dataset == "disks":
            return self._sync_disk_provider(machine_id, snapshot)
        raise ValueError(f"Unsupported Hub dataset: {snapshot.dataset}")

    def _sync_node_red_provider(
        self,
        machine_id: str,
        snapshot: HubProviderSnapshot,
    ) -> HubProviderSyncResult:
        instances = table_identifier(self.settings, "node_red_instances")
        editor_users = table_identifier(self.settings, "node_red_editor_users")
        now = _utc_now()

        with self.connect() as connection:
            try:
                with connection.cursor() as cursor:
                    host_id = self._host_id(cursor, machine_id)
                    active_users: list[str] = []
                    for item in snapshot.items:
                        if not isinstance(item, HubNodeRedInstance):
                            raise TypeError("Invalid Node-RED Hub provider item.")
                        if not item.system_user or not 1 <= int(item.port) <= 65535:
                            raise ValueError("Invalid Node-RED Hub provider record.")
                        active_users.append(item.system_user)
                        cursor.execute(
                            f"INSERT INTO {instances} "
                            "(host_id, system_user, title, service_name, port, url, "
                            "node_red_version, node_js_version, node_js_global, "
                            "project_name, git_remote, service_running, "
                            "service_enabled, last_seen_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                            "%s, %s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE "
                            "title=VALUES(title), service_name=VALUES(service_name), "
                            "port=VALUES(port), url=VALUES(url), "
                            "node_red_version=VALUES(node_red_version), "
                            "node_js_version=VALUES(node_js_version), "
                            "node_js_global=VALUES(node_js_global), "
                            "project_name=VALUES(project_name), "
                            "git_remote=VALUES(git_remote), "
                            "service_running=VALUES(service_running), "
                            "service_enabled=VALUES(service_enabled), "
                            "last_seen_at=VALUES(last_seen_at)",
                            (
                                host_id,
                                item.system_user,
                                item.title,
                                item.service_name,
                                int(item.port),
                                item.url,
                                item.node_red_version,
                                item.node_js_version,
                                _optional_bool(item.node_js_global),
                                item.project_name,
                                item.git_remote,
                                _optional_bool(item.service_running),
                                _optional_bool(item.service_enabled),
                                now,
                            ),
                        )
                        cursor.execute(
                            f"SELECT id FROM {instances} "
                            "WHERE host_id=%s AND system_user=%s LIMIT 1",
                            (host_id, item.system_user),
                        )
                        row = cursor.fetchone()
                        if not row:
                            raise RuntimeError("Cannot resolve synchronized Node-RED instance.")
                        instance_id = int(row[0])
                        cursor.execute(
                            f"DELETE FROM {editor_users} WHERE instance_id=%s",
                            (instance_id,),
                        )
                        if item.editor_users:
                            cursor.executemany(
                                f"INSERT INTO {editor_users} "
                                "(instance_id, username, access_level) "
                                "VALUES (%s, %s, %s)",
                                [
                                    (instance_id, user.username, user.access)
                                    for user in item.editor_users
                                ],
                            )

                    if active_users:
                        placeholders = ",".join(["%s"] * len(active_users))
                        cursor.execute(
                            f"DELETE FROM {instances} WHERE host_id=%s "
                            f"AND system_user NOT IN ({placeholders})",
                            (host_id, *active_users),
                        )
                    else:
                        cursor.execute(
                            f"DELETE FROM {instances} WHERE host_id=%s", (host_id,)
                        )

                    self._upsert_source(
                        cursor,
                        host_id,
                        snapshot.source_key,
                        "ok",
                        len(snapshot.items),
                    )
                connection.commit()
                return HubProviderSyncResult(len(snapshot.items))
            except Exception:
                connection.rollback()
                raise

    def _sync_disk_provider(
        self,
        machine_id: str,
        snapshot: HubProviderSnapshot,
    ) -> HubProviderSyncResult:
        disks = table_identifier(self.settings, "disks")
        host_disks = table_identifier(self.settings, "host_disks")
        now = _utc_now()

        normalized_items: list[HubDisk] = []
        seen_ptuuids: set[str] = set()
        seen_devices: set[str] = set()
        for raw_item in snapshot.items:
            if not isinstance(raw_item, HubDisk):
                raise TypeError("Invalid disk Hub provider item.")
            ptuuid = str(raw_item.ptuuid or "").strip().lower()
            device_name = str(raw_item.device_name or "").strip()
            if not _PTUUID_RE.fullmatch(ptuuid):
                raise ValueError(f"Invalid disk PTUUID: {ptuuid or '<empty>'}")
            if not _DEVICE_NAME_RE.fullmatch(device_name):
                raise ValueError(f"Invalid disk device name: {device_name or '<empty>'}")
            if ptuuid in seen_ptuuids:
                raise ValueError(
                    f"Duplicate PTUUID {ptuuid} detected on one host. "
                    "Check cloned disks before synchronizing."
                )
            if device_name in seen_devices:
                raise ValueError(f"Duplicate disk device name: {device_name}")
            if len(str(raw_item.display_name or "")) > 64:
                raise ValueError(f"Disk name is too long for PTUUID {ptuuid}.")
            if int(raw_item.size_bytes) < 0:
                raise ValueError(f"Invalid disk size for PTUUID {ptuuid}.")
            seen_ptuuids.add(ptuuid)
            seen_devices.add(device_name)
            normalized_items.append(
                HubDisk(
                    ptuuid=ptuuid,
                    device_name=device_name,
                    device_path=str(raw_item.device_path or "")[:255],
                    display_name=str(raw_item.display_name or ""),
                    name_updated_at=raw_item.name_updated_at,
                    size_bytes=int(raw_item.size_bytes),
                    device_type=str(raw_item.device_type or "disk")[:32],
                    partition_count=max(0, int(raw_item.partition_count)),
                    mountpoint_count=max(0, int(raw_item.mountpoint_count)),
                    is_system_disk=bool(raw_item.is_system_disk),
                )
            )

        with self.connect() as connection:
            try:
                remote_updates: list[HubDiskNameUpdate] = []
                active_disk_ids: list[int] = []
                with connection.cursor() as cursor:
                    host_id = self._host_id(cursor, machine_id)
                    for item in normalized_items:
                        cursor.execute(
                            f"INSERT INTO {disks} "
                            "(ptuuid, display_name, name_updated_at, size_bytes, "
                            "first_seen_at, last_seen_at) "
                            "VALUES (%s, '', NULL, %s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE "
                            "size_bytes=VALUES(size_bytes), last_seen_at=VALUES(last_seen_at)",
                            (item.ptuuid, item.size_bytes, now, now),
                        )
                        cursor.execute(
                            f"SELECT id, display_name, name_updated_at FROM {disks} "
                            "WHERE ptuuid=%s LIMIT 1",
                            (item.ptuuid,),
                        )
                        row = cursor.fetchone()
                        if not row:
                            raise RuntimeError(
                                f"Cannot resolve synchronized disk {item.ptuuid}."
                            )
                        disk_id = int(row[0])
                        central_name = str(row[1] or "")
                        central_updated_at = row[2]
                        local_updated_at = _utc_naive(item.name_updated_at)

                        if local_updated_at is not None:
                            if (
                                central_updated_at is None
                                or local_updated_at > central_updated_at
                            ):
                                cursor.execute(
                                    f"UPDATE {disks} SET display_name=%s, "
                                    "name_updated_at=%s WHERE id=%s",
                                    (item.display_name, local_updated_at, disk_id),
                                )
                                central_name = item.display_name
                                central_updated_at = local_updated_at
                            elif central_name != item.display_name:
                                remote_updates.append(
                                    HubDiskNameUpdate(
                                        item.ptuuid,
                                        central_name,
                                        _utc_aware(central_updated_at),
                                    )
                                )
                        elif central_updated_at is not None:
                            if central_name != item.display_name:
                                remote_updates.append(
                                    HubDiskNameUpdate(
                                        item.ptuuid,
                                        central_name,
                                        _utc_aware(central_updated_at),
                                    )
                                )
                        elif item.display_name:
                            cursor.execute(
                                f"UPDATE {disks} SET display_name=%s, "
                                "name_updated_at=%s WHERE id=%s",
                                (item.display_name, now, disk_id),
                            )

                        cursor.execute(
                            f"DELETE FROM {host_disks} WHERE host_id=%s "
                            "AND (disk_id=%s OR device_name=%s)",
                            (host_id, disk_id, item.device_name),
                        )
                        cursor.execute(
                            f"INSERT INTO {host_disks} "
                            "(host_id, disk_id, device_name, device_path, size_bytes, "
                            "device_type, partition_count, mountpoint_count, "
                            "is_system_disk, last_seen_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (
                                host_id,
                                disk_id,
                                item.device_name,
                                item.device_path,
                                item.size_bytes,
                                item.device_type,
                                item.partition_count,
                                item.mountpoint_count,
                                1 if item.is_system_disk else 0,
                                now,
                            ),
                        )
                        active_disk_ids.append(disk_id)

                    if active_disk_ids:
                        placeholders = ",".join(["%s"] * len(active_disk_ids))
                        cursor.execute(
                            f"DELETE FROM {host_disks} WHERE host_id=%s "
                            f"AND disk_id NOT IN ({placeholders})",
                            (host_id, *active_disk_ids),
                        )
                    else:
                        cursor.execute(
                            f"DELETE FROM {host_disks} WHERE host_id=%s", (host_id,)
                        )

                    self._upsert_source(
                        cursor,
                        host_id,
                        snapshot.source_key,
                        "ok",
                        len(normalized_items),
                    )
                connection.commit()
                return HubProviderSyncResult(
                    len(normalized_items), tuple(remote_updates)
                )
            except Exception:
                connection.rollback()
                raise

    def record_source_error(
        self,
        machine_id: str,
        source_key: str,
        error_text: str,
    ) -> None:
        try:
            with self.connect() as connection:
                with connection.cursor() as cursor:
                    host_id = self._host_id(cursor, machine_id)
                    self._upsert_source(
                        cursor,
                        host_id,
                        source_key,
                        "error",
                        0,
                        error_text,
                    )
                connection.commit()
        except Exception:
            return
