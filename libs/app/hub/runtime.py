from __future__ import annotations

from datetime import datetime
import re
from typing import Optional

from libs.JBLibs.helper import getLogger

from .core_provider import collect_host_snapshot
from .database import HubDatabase
from .models import (
    HubContext,
    HubProviderCollector,
    HubState,
    HubStatus,
    HubSyncReport,
)
from .settings import HubSettings


log = getLogger(__name__)
_PROVIDER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class HubRuntime:
    def __init__(self) -> None:
        self._providers: dict[str, HubProviderCollector] = {}
        self.status = HubStatus(HubState.DISABLED, "disabled")
        self.last_sync_at: Optional[datetime] = None

    def clear_providers(self) -> None:
        self._providers.clear()

    def register_provider(self, key: str, collector: HubProviderCollector) -> None:
        key = str(key or "").strip()
        if not _PROVIDER_KEY_RE.fullmatch(key) or not callable(collector):
            raise ValueError("Invalid SysApps Hub provider registration.")
        if key in self._providers and self._providers[key] is not collector:
            raise ValueError(f"Duplicate SysApps Hub provider key: {key}")
        self._providers[key] = collector

    def refresh_status(self) -> HubStatus:
        settings = HubSettings.from_cfg()
        try:
            self.status = HubDatabase(settings).check_status()
        except Exception as exc:
            safe_error = settings.redact_error(exc)
            log.warning("SysApps Hub status check failed: %s", safe_error)
            self.status = HubStatus(
                HubState.ERROR,
                safe_error,
                datetime.now().astimezone(),
            )
        return self.status

    def status_text(self) -> str:
        state = self.status.state
        labels = {
            HubState.DISABLED: "DISABLED",
            HubState.NOT_CONFIGURED: "NOT CONFIGURED",
            HubState.OFFLINE: "OFFLINE",
            HubState.DATABASE_MISSING: "DATABASE MISSING",
            HubState.SCHEMA_MISSING: "SCHEMA MISSING",
            HubState.SCHEMA_OUTDATED: "SCHEMA OUTDATED",
            HubState.READY: "READY",
            HubState.ERROR: "ERROR",
        }
        label = labels.get(state, state.value.upper())
        if state is HubState.READY and self.last_sync_at is not None:
            return f"{label}, sync {self.last_sync_at.strftime('%Y-%m-%d %H:%M:%S')}"
        return f"{label}: {self.status.message}" if self.status.message else label

    def initialize_schema(self) -> tuple[bool, str]:
        settings = HubSettings.from_cfg()
        try:
            version = HubDatabase(settings).initialize_or_upgrade_schema()
            self.refresh_status()
            return True, f"SysApps Hub schema is ready at version {version}."
        except Exception as exc:
            safe_error = settings.redact_error(exc)
            log.error("SysApps Hub schema initialization failed: %s", safe_error)
            self.refresh_status()
            return False, safe_error

    def _ready_database(self) -> tuple[HubSettings, HubDatabase]:
        settings = HubSettings.from_cfg()
        status = HubDatabase(settings).check_status()
        self.status = status
        if not status.ready:
            raise RuntimeError(self.status_text())
        return settings, HubDatabase(settings)

    def sync_all(self) -> HubSyncReport:
        report = HubSyncReport()
        settings = HubSettings.from_cfg()
        try:
            _, database = self._ready_database()
            host = collect_host_snapshot()
            database.sync_core(host)
            report.core_synced = True
        except Exception as exc:
            report.error = settings.redact_error(exc)
            log.error("SysApps Hub core synchronization failed: %s", report.error)
            return report

        context = HubContext(
            generated_at=datetime.now().astimezone(),
            machine_id=host.machine_id,
        )
        for key, collector in sorted(self._providers.items()):
            try:
                snapshot = collector(context)
                if snapshot.source_key != key:
                    raise ValueError(
                        f"Provider {key} returned source key {snapshot.source_key}."
                    )
                report.provider_counts[key] = database.sync_provider(
                    host.machine_id, snapshot
                )
            except Exception as exc:
                warning = f"Provider {key}: {exc}"
                report.warnings.append(warning)
                log.warning("SysApps Hub %s", warning, exc_info=True)
                database.record_source_error(host.machine_id, key, str(exc))

        self.last_sync_at = datetime.now().astimezone()
        self.refresh_status()
        return report

    def sync_provider(self, key: str) -> tuple[bool, str]:
        settings = HubSettings.from_cfg()
        collector = self._providers.get(key)
        if collector is None:
            return False, f"SysApps Hub provider is not registered: {key}"
        try:
            _, database = self._ready_database()
            host = collect_host_snapshot()
            database.sync_core(host)
            snapshot = collector(
                HubContext(
                    generated_at=datetime.now().astimezone(),
                    machine_id=host.machine_id,
                )
            )
            if snapshot.source_key != key:
                raise ValueError("Provider returned a different source key.")
            count = database.sync_provider(host.machine_id, snapshot)
            self.last_sync_at = datetime.now().astimezone()
            self.refresh_status()
            return True, f"Synchronized {count} item(s) from {key}."
        except Exception as exc:
            safe_error = settings.redact_error(exc)
            log.warning(
                "SysApps Hub provider synchronization failed for %s: %s",
                key,
                safe_error,
            )
            return False, safe_error

    def sync_provider_best_effort(self, key: str) -> None:
        settings = HubSettings.from_cfg()
        if not settings.enabled:
            return
        ok, error = self.sync_provider(key)
        if not ok:
            log.warning("Best-effort SysApps Hub sync skipped/failed for %s: %s", key, error)

    def startup(self) -> HubSyncReport | None:
        status = self.refresh_status()
        settings = HubSettings.from_cfg()
        if not status.ready or not settings.auto_sync:
            return None
        print("SysApps Hub: synchronizing inventory...")
        report = self.sync_all()
        if report.error:
            print(f"SysApps Hub synchronization failed: {report.error}")
        else:
            total = sum(report.provider_counts.values())
            print(f"SysApps Hub synchronized core inventory and {total} provider item(s).")
            for warning in report.warnings:
                print(f"SysApps Hub warning: {warning}")
        return report


hub_runtime = HubRuntime()
