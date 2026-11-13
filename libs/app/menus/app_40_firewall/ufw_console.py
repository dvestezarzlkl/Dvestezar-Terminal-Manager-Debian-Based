"""Pure parser and port/profile helpers for the native UFW console."""
from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address, ip_network
import re
import shlex


class UfwConsoleError(ValueError):
    pass


@dataclass(frozen=True)
class UfwPortSpec:
    start: int
    end: int
    protocol: str

    def contains(self, port: int) -> bool:
        return self.start <= port <= self.end


@dataclass(frozen=True)
class UfwAddPort:
    port: int
    protocol: str = "tcp"
    source: str = ""
    destination: str = ""


@dataclass(frozen=True)
class UfwAddService:
    profile: str


@dataclass(frozen=True)
class UfwConsoleCommand:
    kind: str
    value: object | None = None


def _normalize_network(value: str, *, label: str) -> str:
    raw = value.strip()
    if raw.lower() == "any":
        return "any"
    try:
        if "/" in raw:
            return str(ip_network(raw, strict=False))
        return str(ip_address(raw))
    except ValueError as exc:
        raise UfwConsoleError(f"Invalid {label} address/network: {value}") from exc


def _parse_add_port(tokens: list[str]) -> UfwAddPort:
    if len(tokens) < 3:
        raise UfwConsoleError("Usage: add p <port> [from <ip/cidr>] [to <ip/cidr>] [proto <tcp|udp>]")
    try:
        port = int(tokens[2])
    except ValueError as exc:
        raise UfwConsoleError("Port must be a number from 1 to 65535.") from exc
    if not 1 <= port <= 65535:
        raise UfwConsoleError("Port must be a number from 1 to 65535.")

    source = ""
    destination = ""
    protocol = "tcp"
    index = 3
    seen: set[str] = set()
    while index < len(tokens):
        key = tokens[index].lower()
        if key not in {"from", "to", "proto"}:
            raise UfwConsoleError(f"Unknown add option: {tokens[index]}")
        if key in seen:
            raise UfwConsoleError(f"Duplicate add option: {key}")
        if index + 1 >= len(tokens):
            raise UfwConsoleError(f"Missing value after {key}.")
        value = tokens[index + 1]
        seen.add(key)
        if key == "from":
            source = _normalize_network(value, label="source")
        elif key == "to":
            destination = _normalize_network(value, label="destination")
        else:
            protocol = value.lower()
            if protocol not in {"tcp", "udp"}:
                raise UfwConsoleError("Protocol must be tcp or udp.")
        index += 2

    return UfwAddPort(
        port=port,
        protocol=protocol,
        source=source,
        destination=destination,
    )


def parse_console_command(text: str) -> UfwConsoleCommand:
    raw = str(text).strip()
    if not raw:
        raise UfwConsoleError("Command is empty.")

    if raw.startswith(":info "):
        profile = raw[6:].strip()
        if not profile:
            raise UfwConsoleError("Usage: :info <profile>")
        return UfwConsoleCommand("info", profile)

    if raw.startswith(":list p "):
        query = raw[8:].strip()
        if not query:
            raise UfwConsoleError("Usage: :list p <port|profile>")
        return UfwConsoleCommand("list-port", query)

    lowered = raw.lower()
    if lowered == ":help":
        return UfwConsoleCommand("help")
    if lowered == ":srv":
        return UfwConsoleCommand("services")
    if lowered == ":ver":
        return UfwConsoleCommand("version")
    if lowered == ":list":
        return UfwConsoleCommand("list")

    if raw.isdigit():
        return UfwConsoleCommand("delete", int(raw))

    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        raise UfwConsoleError(f"Invalid command quoting: {exc}") from exc
    if not tokens:
        raise UfwConsoleError("Command is empty.")

    head = tokens[0].lower()
    if head != "add":
        raise UfwConsoleError("Unknown command. Use :help.")

    if len(tokens) >= 2 and tokens[1].lower() in {"p", "port"}:
        return UfwConsoleCommand("add-port", _parse_add_port(tokens))

    if len(tokens) >= 3 and tokens[1].lower() in {"srv", "service"}:
        profile = " ".join(tokens[2:]).strip()
        if not profile:
            raise UfwConsoleError("Usage: add srv <profile>")
        return UfwConsoleCommand("add-service", UfwAddService(profile))

    raise UfwConsoleError("Usage: add p <port> ... | add srv <profile>")


def build_ufw_add_args(spec: UfwAddPort | UfwAddService) -> list[str]:
    if isinstance(spec, UfwAddService):
        return ["allow", spec.profile]

    if not spec.source and not spec.destination:
        return ["allow", f"{spec.port}/{spec.protocol}"]

    args = ["allow"]
    args += ["from", spec.source or "any"]
    args += ["to", spec.destination or "any"]
    args += ["port", str(spec.port), "proto", spec.protocol]
    return args


_APP_PORT_RE = re.compile(r"(?<!\d)(\d+(?::\d+)?(?:,\d+(?::\d+)?)*)/(tcp|udp)\b", re.IGNORECASE)


def parse_ufw_app_ports(output: str) -> tuple[UfwPortSpec, ...]:
    result: list[UfwPortSpec] = []
    seen: set[tuple[int, int, str]] = set()
    for ports_text, protocol_raw in _APP_PORT_RE.findall(str(output)):
        protocol = protocol_raw.lower()
        for part in ports_text.split(","):
            lo_text, sep, hi_text = part.partition(":")
            try:
                lo = int(lo_text)
                hi = int(hi_text) if sep else lo
            except ValueError:
                continue
            if not (1 <= lo <= hi <= 65535):
                continue
            key = (lo, hi, protocol)
            if key not in seen:
                seen.add(key)
                result.append(UfwPortSpec(lo, hi, protocol))
    return tuple(result)


def port_specs_for_query(query: str, app_info: str | None = None) -> tuple[UfwPortSpec, ...]:
    raw = str(query).strip()
    if raw.isdigit():
        port = int(raw)
        if not 1 <= port <= 65535:
            raise UfwConsoleError("Port must be a number from 1 to 65535.")
        return (
            UfwPortSpec(port, port, "tcp"),
            UfwPortSpec(port, port, "udp"),
        )
    if app_info is None:
        raise UfwConsoleError("Profile information is required for a named query.")
    specs = parse_ufw_app_ports(app_info)
    if not specs:
        raise UfwConsoleError(f"No numeric TCP/UDP ports found in profile: {query}")
    return specs


def _parse_endpoint_port(endpoint: str) -> int | None:
    value = endpoint.strip()
    if not value:
        return None
    if value.startswith("[") and "]:" in value:
        value = value.rsplit(":", 1)[1]
    elif ":" in value:
        value = value.rsplit(":", 1)[1]
    try:
        port = int(value)
    except ValueError:
        return None
    return port if 1 <= port <= 65535 else None


def filter_ss_listeners(output: str, specs: tuple[UfwPortSpec, ...]) -> tuple[str, ...]:
    lines: list[str] = []
    for raw in str(output).splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        protocol = parts[0].lower()
        if protocol not in {"tcp", "udp"}:
            continue
        port = _parse_endpoint_port(parts[4])
        if port is None:
            continue
        if any(spec.protocol == protocol and spec.contains(port) for spec in specs):
            lines.append(line)
    return tuple(lines)


_PORT_OPT_RE = re.compile(r"--dports?\s+([^\s]+)")


def _port_token_overlaps(token: str, specs: tuple[UfwPortSpec, ...]) -> bool:
    for part in token.split(","):
        lo_text, sep, hi_text = part.partition(":")
        try:
            lo = int(lo_text)
            hi = int(hi_text) if sep else lo
        except ValueError:
            return True
        for spec in specs:
            if lo <= spec.end and spec.start <= hi:
                return True
    return False


def filter_table_rules(output: str, specs: tuple[UfwPortSpec, ...]) -> tuple[str, ...]:
    lines: list[str] = []
    for raw in str(output).splitlines():
        line = raw.strip()
        if not line or not line.startswith("-A "):
            continue
        protocol = ""
        proto_match = re.search(r"(?:^|\s)-p\s+(tcp|udp)(?:\s|$)", line)
        if proto_match:
            protocol = proto_match.group(1)
        matches = _PORT_OPT_RE.findall(line)
        if not matches:
            continue
        relevant_specs = specs
        if protocol:
            relevant_specs = tuple(spec for spec in specs if spec.protocol == protocol)
        if relevant_specs and any(_port_token_overlaps(token, relevant_specs) for token in matches):
            lines.append(line)
    return tuple(lines)


def native_rule_matches_specs(text: str, specs: tuple[UfwPortSpec, ...]) -> bool:
    lowered = str(text).lower()
    for match in re.finditer(r"(?<!\d)(\d+)(?::(\d+))?(?:/(tcp|udp))?", lowered):
        lo = int(match.group(1))
        hi = int(match.group(2) or lo)
        proto = match.group(3)
        for spec in specs:
            if proto and proto != spec.protocol:
                continue
            if lo <= spec.end and spec.start <= hi:
                return True
    return False
