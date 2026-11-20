"""Pure composition of host-local and cached central firewall desired state.

No filesystem writes, Hub access, UFW commands or Apply operations belong here.
The result preserves provenance so preview/UI can explain why every effective
rule exists and which scope wins.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from libs.app.hub.models import (
    HubCentralFirewallRule,
    HubCentralFirewallVpnServer,
    HubFirewallPolicyUpdate,
)

from .config import (
    FirewallConfig,
    FirewallRule,
    FirewallVpnServer,
    normalize_config,
    normalize_rule,
    normalize_vpn_server,
)


class FirewallCompositionError(ValueError):
    pass


_SCOPE_RANK = {"all": 0, "group": 1, "host": 2}


@dataclass(frozen=True)
class PolicySource:
    origin: str
    target_kind: str
    position: int

    @property
    def key(self) -> str:
        if self.origin == "host_local":
            return "host_local"
        return f"central_{self.target_kind}"


@dataclass(frozen=True)
class ComposedFirewallPolicy:
    config: FirewallConfig
    vpn_sources: tuple[PolicySource, ...]
    rule_sources: tuple[PolicySource, ...]
    central_generated_at: str = ""
    central_group_id: Optional[int] = None

    def rule_count(self, source_key: str) -> int:
        return sum(1 for item in self.rule_sources if item.key == source_key)


def _central_server(
    item: HubCentralFirewallVpnServer,
) -> FirewallVpnServer:
    return normalize_vpn_server({
        "server_id": item.server_uid,
        "name": item.name,
        "ip": item.server_ip,
        "mask": item.server_mask,
        "interface": item.interface_name,
    })


def _central_rule(item: HubCentralFirewallRule) -> FirewallRule:
    return normalize_rule({
        "rule_id": item.rule_uid,
        "kind": item.rule_type,
        "enabled": item.enabled,
        "name": item.name,
        "source": item.source,
        "destination": item.destination,
        "destination_invert": item.destination_invert,
        "direction": item.direction,
        "action": item.action,
        "protocol": item.protocol,
        "port_from": item.port_from,
        "port_to": item.port_to,
        "src_ports": item.src_ports,
        "dst_ports": item.dst_ports,
        "interface": item.interface_name,
        "ban_to": item.ban_to or "",
        "vpn_server_id": item.vpn_server_uid,
    })


def compose_firewall_policy(
    local: FirewallConfig,
    central: HubFirewallPolicyUpdate | None,
    *,
    machine_id: str = "",
) -> ComposedFirewallPolicy:
    """Compose effective desired state without mutating either source.

    Effective ordinary-rule precedence is most-specific first:
    host-local -> central host -> central group -> central all.

    The existing compiler still owns the higher-level safety ordering of
    OpenVPN BAN/isolation blocks, trusted hard-source ALLOW and ordinary
    standard rules.
    """
    local_cfg = normalize_config(local)
    local_server_ids = {item.server_id for item in local_cfg.vpn_servers}
    local_rule_ids = {item.rule_id for item in local_cfg.rules}

    local_vpn_sources = tuple(
        PolicySource("host_local", "host", index)
        for index, _ in enumerate(local_cfg.vpn_servers)
    )
    local_rule_sources = tuple(
        PolicySource("host_local", "host", index)
        for index, _ in enumerate(local_cfg.rules)
    )

    if central is None:
        return ComposedFirewallPolicy(
            local_cfg,
            local_vpn_sources,
            local_rule_sources,
        )
    if not isinstance(central, HubFirewallPolicyUpdate):
        raise FirewallCompositionError("Invalid central firewall policy.")
    if machine_id and central.machine_id != machine_id:
        raise FirewallCompositionError(
            "Central firewall policy belongs to another machine."
        )

    selected_servers: dict[str, tuple[FirewallVpnServer, PolicySource]] = {}
    for item in sorted(
        central.vpn_servers,
        key=lambda value: (
            _SCOPE_RANK.get(value.target_kind, -1),
            value.server_uid,
        ),
    ):
        if item.target_kind not in _SCOPE_RANK:
            raise FirewallCompositionError("Unsupported central VPN server scope.")
        server = _central_server(item)
        source = PolicySource("central", item.target_kind, 0)
        selected_servers[item.server_uid] = (server, source)

    central_server_ids = set(selected_servers)
    duplicate_server_ids = local_server_ids & central_server_ids
    if duplicate_server_ids:
        raise FirewallCompositionError(
            "Local/central VPN server ID collision: "
            + ", ".join(sorted(duplicate_server_ids))
        )

    ordered_central_servers = sorted(
        selected_servers.values(),
        key=lambda value: (
            -_SCOPE_RANK[value[1].target_kind],
            value[0].server_id,
        ),
    )
    effective_servers = (
        *local_cfg.vpn_servers,
        *(item[0] for item in ordered_central_servers),
    )
    vpn_sources = (
        *local_vpn_sources,
        *(item[1] for item in ordered_central_servers),
    )

    central_rules: list[tuple[FirewallRule, PolicySource]] = []
    seen_central_rule_ids: set[str] = set()
    for item in central.rules:
        if item.target_kind not in _SCOPE_RANK:
            raise FirewallCompositionError("Unsupported central firewall rule scope.")
        if item.rule_uid in seen_central_rule_ids:
            raise FirewallCompositionError(
                f"Duplicate central firewall rule ID: {item.rule_uid}."
            )
        seen_central_rule_ids.add(item.rule_uid)
        if item.rule_uid in local_rule_ids:
            raise FirewallCompositionError(
                f"Local/central firewall rule ID collision: {item.rule_uid}."
            )
        rule = _central_rule(item)
        if rule.vpn_server_id and rule.vpn_server_id not in central_server_ids:
            raise FirewallCompositionError(
                "Central firewall rule references an unknown central VPN server: "
                f"{rule.vpn_server_id}."
            )
        central_rules.append((
            rule,
            PolicySource("central", item.target_kind, int(item.position)),
        ))

    # Most-specific layer is first because iptables is first-match. Position is
    # authoritative only within one central target scope; rule_id is a stable
    # deterministic tie-breaker.
    central_rules.sort(key=lambda value: (
        -_SCOPE_RANK[value[1].target_kind],
        value[1].position,
        value[0].rule_id,
    ))

    effective_rules = (
        *local_cfg.rules,
        *(item[0] for item in central_rules),
    )
    rule_sources = (
        *local_rule_sources,
        *(item[1] for item in central_rules),
    )

    try:
        config = normalize_config(FirewallConfig(
            vpn_servers=tuple(effective_servers),
            rules=tuple(effective_rules),
        ))
    except ValueError as exc:
        raise FirewallCompositionError(
            "Composed firewall policy is invalid."
        ) from exc

    return ComposedFirewallPolicy(
        config=config,
        vpn_sources=tuple(vpn_sources),
        rule_sources=tuple(rule_sources),
        central_generated_at=central.generated_at.isoformat(),
        central_group_id=central.group_id,
    )
