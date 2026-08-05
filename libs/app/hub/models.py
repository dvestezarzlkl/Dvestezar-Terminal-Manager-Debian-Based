from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional


class HubState(str, Enum):
    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"
    OFFLINE = "offline"
    DATABASE_MISSING = "database_missing"
    SCHEMA_MISSING = "schema_missing"
    SCHEMA_OUTDATED = "schema_outdated"
    READY = "ready"
    ERROR = "error"


@dataclass(frozen=True)
class HubStatus:
    state: HubState
    message: str = ""
    checked_at: Optional[datetime] = None
    server_version: str = ""
    schema_version: int = 0

    @property
    def ready(self) -> bool:
        return self.state is HubState.READY


@dataclass(frozen=True)
class HubAddress:
    interface_name: str
    family: str
    address: str
    netmask: str = ""
    prefix_length: Optional[int] = None
    mac: str = ""
    scope: str = ""


@dataclass(frozen=True)
class HubService:
    service_key: str
    detected: bool
    port: Optional[int] = None
    url: str = ""
    status: str = ""
    version: str = ""


@dataclass(frozen=True)
class HubHostSnapshot:
    machine_id: str
    hostname: str
    fqdn: str
    operating_system: str
    kernel: str
    architecture: str
    hardware_vendor: str
    hardware_model: str
    sys_apps_version: str
    jblibs_version: str
    addresses: tuple[HubAddress, ...] = field(default_factory=tuple)
    services: tuple[HubService, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HubNodeRedEditorUser:
    username: str
    access: str


@dataclass(frozen=True)
class HubNodeRedInstance:
    system_user: str
    title: str
    service_name: str
    port: int
    url: str
    node_red_version: str
    node_js_version: str
    node_js_global: Optional[bool]
    project_name: str
    git_remote: str
    service_running: Optional[bool]
    service_enabled: Optional[bool]
    editor_users: tuple[HubNodeRedEditorUser, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HubDisk:
    ptuuid: str
    device_name: str
    device_path: str
    display_name: str
    name_updated_at: Optional[datetime]
    size_bytes: int
    device_type: str
    partition_count: int
    mountpoint_count: int
    is_system_disk: bool
    attached: bool = True


@dataclass(frozen=True)
class HubDiskNameUpdate:
    ptuuid: str
    display_name: str
    updated_at: datetime


HubProviderItem = HubNodeRedInstance | HubDisk
HubRemoteUpdate = HubDiskNameUpdate


@dataclass(frozen=True)
class HubProviderSnapshot:
    source_key: str
    dataset: str
    items: tuple[HubProviderItem, ...]


@dataclass(frozen=True)
class HubProviderSyncResult:
    item_count: int
    remote_updates: tuple[HubRemoteUpdate, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HubContext:
    generated_at: datetime
    machine_id: str


HubProviderCollector = Callable[[HubContext], HubProviderSnapshot]
HubProviderApplier = Callable[[tuple[HubRemoteUpdate, ...]], None]


@dataclass(frozen=True)
class HubProviderRegistration:
    collector: HubProviderCollector
    applier: Optional[HubProviderApplier] = None


@dataclass
class HubSyncReport:
    core_synced: bool = False
    provider_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def success(self) -> bool:
        return self.core_synced and not self.error
