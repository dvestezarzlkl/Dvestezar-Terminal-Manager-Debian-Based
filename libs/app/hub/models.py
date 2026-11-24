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
    latest_schema_version: int = 0

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
class HubFirewallVpnServer:
    server_uid: str
    name: str
    server_ip: str
    server_mask: int
    interface_name: str = "tun+"


@dataclass(frozen=True)
class HubFirewallRule:
    rule_uid: str
    rule_type: str
    enabled: bool
    name: str = ""
    direction: str = "input"
    action: str = "allow"
    protocol: str = "any"
    source: str = ""
    destination: str = ""
    destination_invert: bool = False
    port_from: Optional[int] = None
    port_to: Optional[int] = None
    src_ports: str = ""
    dst_ports: str = ""
    interface_name: str = ""
    ban_to: Optional[str] = None
    vpn_server_uid: str = ""


@dataclass(frozen=True)
class HubCentralFirewallVpnServer:
    server_uid: str
    target_kind: str
    name: str
    server_ip: str
    server_mask: int
    interface_name: str = "tun+"


@dataclass(frozen=True)
class HubCentralFirewallRule:
    rule_uid: str
    target_kind: str
    position: int
    rule_type: str
    enabled: bool
    name: str = ""
    direction: str = "input"
    action: str = "allow"
    protocol: str = "any"
    source: str = ""
    destination: str = ""
    destination_invert: bool = False
    port_from: Optional[int] = None
    port_to: Optional[int] = None
    src_ports: str = ""
    dst_ports: str = ""
    interface_name: str = ""
    ban_to: Optional[str] = None
    vpn_server_uid: str = ""


@dataclass(frozen=True)
class HubFirewallPolicyUpdate:
    machine_id: str
    group_id: Optional[int]
    generated_at: datetime
    policy_hash: str = ""
    policy_revision: int = 0
    vpn_servers: tuple[HubCentralFirewallVpnServer, ...] = field(default_factory=tuple)
    rules: tuple[HubCentralFirewallRule, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HubFirewallPolicyStatus:
    cached_hash: str = ""
    cached_revision: int = 0
    applied_hash: str = ""
    applied_revision: int = 0
    apply_status: str = "unknown"
    applied_at: Optional[datetime] = None
    last_error: str = ""


@dataclass(frozen=True)
class HubFirewallPolicyHostState:
    machine_id: str
    hostname: str
    desired_hash: str = ""
    desired_revision: int = 0
    desired_at: Optional[datetime] = None
    delivered_hash: str = ""
    delivered_revision: int = 0
    delivered_at: Optional[datetime] = None
    applied_hash: str = ""
    applied_revision: int = 0
    applied_at: Optional[datetime] = None
    apply_status: str = "unknown"
    apply_error: str = ""
    reported_at: Optional[datetime] = None

    @property
    def state(self) -> str:
        if self.desired_hash and self.desired_hash != self.delivered_hash:
            return "waiting_for_delivery"
        if self.desired_hash and self.desired_hash != self.applied_hash:
            if self.apply_status in {"failed", "rolled_back"}:
                return self.apply_status
            return "waiting_for_apply"
        if self.desired_hash and self.desired_hash == self.applied_hash:
            return "applied"
        return "unknown"


@dataclass(frozen=True)
class HubFirewallPolicyActor:
    subject: str
    permissions: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class HubFirewallPolicyTarget:
    target_kind: str
    machine_id: str = ""
    group_code: str = ""


@dataclass(frozen=True)
class HubFirewallPolicyMutationResult:
    revision: int
    affected_hosts: tuple[HubFirewallPolicyHostState, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HubFirewallPolicyRuleRecord:
    target: HubFirewallPolicyTarget
    rule: HubCentralFirewallRule


@dataclass(frozen=True)
class HubFirewallPolicyVpnServerRecord:
    target: HubFirewallPolicyTarget
    server: HubCentralFirewallVpnServer


@dataclass(frozen=True)
class HubFirewallPolicyAdminSnapshot:
    revision: int
    updated_at: Optional[datetime]
    updated_by: str
    rules: tuple[HubFirewallPolicyRuleRecord, ...] = field(default_factory=tuple)
    vpn_servers: tuple[HubFirewallPolicyVpnServerRecord, ...] = field(default_factory=tuple)
    host_states: tuple[HubFirewallPolicyHostState, ...] = field(default_factory=tuple)


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
    service_host: str = ""
    auto_sync_enabled: Optional[bool] = None
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


HubProviderItem = (
    HubNodeRedInstance
    | HubDisk
    | HubService
    | HubFirewallVpnServer
    | HubFirewallRule
    | HubFirewallPolicyStatus
)
HubRemoteUpdate = HubDiskNameUpdate | HubFirewallPolicyUpdate


@dataclass(frozen=True)
class HubProviderSnapshot:
    source_key: str
    dataset: str
    items: tuple[HubProviderItem, ...]
    min_schema_version: int = 1


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
