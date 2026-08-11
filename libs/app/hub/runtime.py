from __future__ import annotations

from datetime import datetime
import re
from time import perf_counter
from typing import Callable, Optional

from libs.JBLibs.helper import getLogger
from libs.app.service_host import configured_service_host

from .core_provider import collect_host_snapshot
from .database import HubDatabase
from .models import (
    HubContext,
    HubProviderApplier,
    HubProviderCollector,
    HubProviderRegistration,
    HubProviderSyncResult,
    HubState,
    HubStatus,
    HubSyncReport,
)
from .settings import HubSettings


log = getLogger(__name__)
_PROVIDER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class HubRuntime:
    def __init__(self) -> None:
        self._providers: dict[str, HubProviderRegistration] = {}
        self.status = HubStatus(HubState.DISABLED, "disabled")
        self.last_sync_at: Optional[datetime] = None

    def clear_providers(self) -> None:
        self._providers.clear()

    def register_provider(
        self,
        key: str,
        collector: HubProviderCollector,
        applier: HubProviderApplier | None = None,
    ) -> None:
        key = str(key or "").strip()
        if not _PROVIDER_KEY_RE.fullmatch(key) or not callable(collector):
            raise ValueError("Invalid SysApps Hub provider registration.")
        if applier is not None and not callable(applier):
            raise ValueError("Invalid SysApps Hub provider applier.")
        registration = HubProviderRegistration(collector, applier)
        current = self._providers.get(key)
        if current is not None and current != registration:
            raise ValueError(f"Duplicate SysApps Hub provider key: {key}")
        self._providers[key] = registration

    def refresh_status(self) -> HubStatus:
        settings = HubSettings.from_cfg()
        if settings.enabled and not configured_service_host():
            self.status = HubStatus(
                HubState.NOT_CONFIGURED,
                "Service host / FQDN is not configured.",
                datetime.now().astimezone(),
            )
            return self.status
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
        if not configured_service_host():
            self.status = HubStatus(
                HubState.NOT_CONFIGURED,
                "Service host / FQDN is not configured.",
                datetime.now().astimezone(),
            )
            raise RuntimeError(self.status_text())
        status = HubDatabase(settings).check_status()
        self.status = status
        if not status.ready:
            raise RuntimeError(self.status_text())
        return settings, HubDatabase(settings)

    def _sync_registration(
        self,
        database: HubDatabase,
        machine_id: str,
        key: str,
        registration: HubProviderRegistration,
    ) -> int:
        provider_started = perf_counter()
        collect_started = perf_counter()
        log.info("SysApps Hub provider %s collection: start", key)
        snapshot = registration.collector(
            HubContext(
                generated_at=datetime.now().astimezone(),
                machine_id=machine_id,
            )
        )
        log.info(
            "SysApps Hub provider %s collection: done in %.3fs (%d item(s))",
            key,
            perf_counter() - collect_started,
            len(snapshot.items),
        )
        if snapshot.source_key != key:
            raise ValueError(
                f"Provider {key} returned source key {snapshot.source_key}."
            )
        sync_started = perf_counter()
        log.info("SysApps Hub provider %s database sync: start", key)
        result = database.sync_provider(machine_id, snapshot)
        log.info(
            "SysApps Hub provider %s database sync: done in %.3fs",
            key,
            perf_counter() - sync_started,
        )
        if isinstance(result, int):
            result = HubProviderSyncResult(result)
        if not isinstance(result, HubProviderSyncResult):
            raise TypeError(f"Provider {key} returned an invalid sync result.")
        if result.remote_updates:
            if registration.applier is None:
                raise RuntimeError(
                    f"Provider {key} received remote updates but has no local applier."
                )
            apply_started = perf_counter()
            log.info("SysApps Hub provider %s remote apply: start", key)
            registration.applier(result.remote_updates)
            log.info(
                "SysApps Hub provider %s remote apply: done in %.3fs",
                key,
                perf_counter() - apply_started,
            )
        log.info(
            "SysApps Hub provider %s: done in %.3fs (%d item(s))",
            key,
            perf_counter() - provider_started,
            result.item_count,
        )
        return result.item_count

    def sync_all(
        self,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> HubSyncReport:
        report = HubSyncReport()
        settings = HubSettings.from_cfg()
        started = perf_counter()
        providers = sorted(self._providers.items())
        total_steps = len(providers) + 2

        def emit_progress(step: int, label: str) -> None:
            if progress is not None:
                progress(step, total_steps, label)

        log.info(
            "SysApps Hub synchronization: start (%d provider(s))",
            len(providers),
        )
        try:
            emit_progress(1, "core inventory")
            phase_started = perf_counter()
            log.info("SysApps Hub database readiness check: start")
            _, database = self._ready_database()
            log.info(
                "SysApps Hub database readiness check: done in %.3fs",
                perf_counter() - phase_started,
            )

            phase_started = perf_counter()
            log.info("SysApps Hub core inventory collection: start")
            host = collect_host_snapshot()
            log.info(
                "SysApps Hub core inventory collection: done in %.3fs",
                perf_counter() - phase_started,
            )

            phase_started = perf_counter()
            log.info("SysApps Hub core database sync: start")
            database.sync_core(host)
            log.info(
                "SysApps Hub core database sync: done in %.3fs",
                perf_counter() - phase_started,
            )
            report.core_synced = True
        except Exception as exc:
            report.error = settings.redact_error(exc)
            log.error(
                "SysApps Hub core synchronization failed after %.3fs: %s",
                perf_counter() - started,
                report.error,
            )
            return report

        for step, (key, registration) in enumerate(providers, start=2):
            emit_progress(step, key.replace("_", " "))
            try:
                report.provider_counts[key] = self._sync_registration(
                    database,
                    host.machine_id,
                    key,
                    registration,
                )
            except Exception as exc:
                warning = f"Provider {key}: {exc}"
                report.warnings.append(warning)
                log.warning("SysApps Hub %s", warning, exc_info=True)
                database.record_source_error(host.machine_id, key, str(exc))

        self.last_sync_at = datetime.now().astimezone()
        emit_progress(total_steps, "finalization")
        phase_started = perf_counter()
        log.info("SysApps Hub final status refresh: start")
        self.refresh_status()
        log.info(
            "SysApps Hub final status refresh: done in %.3fs",
            perf_counter() - phase_started,
        )
        log.info(
            "SysApps Hub synchronization: done in %.3fs (providers=%d, warnings=%d)",
            perf_counter() - started,
            len(report.provider_counts),
            len(report.warnings),
        )
        return report

    def sync_provider(self, key: str) -> tuple[bool, str]:
        settings = HubSettings.from_cfg()
        registration = self._providers.get(key)
        if registration is None:
            return False, f"SysApps Hub provider is not registered: {key}"
        try:
            _, database = self._ready_database()
            host = collect_host_snapshot()
            database.sync_core(host)
            count = self._sync_registration(
                database,
                host.machine_id,
                key,
                registration,
            )
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
        def print_progress(step: int, total: int, label: str) -> None:
            print(f"SysApps Hub: synchronization {step}/{total} - {label}...")

        report = self.sync_all(print_progress)
        if report.error:
            print(f"SysApps Hub synchronization failed: {report.error}")
        else:
            total = sum(report.provider_counts.values())
            print(f"SysApps Hub synchronized core inventory and {total} provider item(s).")
            for warning in report.warnings:
                print(f"SysApps Hub warning: {warning}")
        return report


hub_runtime = HubRuntime()
