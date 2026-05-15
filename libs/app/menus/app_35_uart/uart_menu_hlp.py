from __future__ import annotations

from .lng.default import *
from libs.JBLibs.helper import getConfigPath, getLogger, loadLng

loadLng()

import glob
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from libs.JBLibs import uart_tester
from libs.app import g_def as defs

log = getLogger("uart_menu")

CONFIG_NAME = "uart_tester.json"

BAUDRATES: list[int] = [
    9600,
    19200,
    38400,
    57600,
    115200,
    230400,
    250000,
    256000,
    460800,
    500000,
    512000,
]

PARITIES: list[str] = ["N", "E", "O", "M", "S"]
BYTESIZES: list[int] = [5, 6, 7, 8]
STOPBITS: list[float] = [1, 1.5, 2]
TIMEOUTS: list[float] = [0.1, 0.2, 0.5, 1, 2, 5]
MODES: list[str] = ["transmitter", "receiver"]


@dataclass
class UartPortInfo:
    device: str
    description: str = ""
    hwid: str = ""

    @property
    def label(self) -> str:
        if self.description and self.description != "n/a":
            return f"{self.device} - {self.description}"
        return self.device


@dataclass
class UartSettings:
    port: str = ""
    baudrate: int = uart_tester.DEFAULT_BAUDRATE
    parity: str = uart_tester.DEFAULT_PARITY
    bytesize: int = uart_tester.DEFAULT_BYTESIZE
    stopbits: float = uart_tester.DEFAULT_STOPBITS
    timeout: float = uart_tester.DEFAULT_SERIAL_TIMEOUT
    mode: str = "transmitter"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "UartSettings":
        data = data if isinstance(data, dict) else {}
        cfg = cls()
        cfg.port = _as_str(data.get("port"), cfg.port)
        cfg.baudrate = _as_choice_int(data.get("baudrate"), BAUDRATES, cfg.baudrate)
        cfg.parity = _as_choice_str(data.get("parity"), PARITIES, cfg.parity).upper()
        cfg.bytesize = _as_choice_int(data.get("bytesize"), BYTESIZES, cfg.bytesize)
        cfg.stopbits = _as_choice_float(data.get("stopbits"), STOPBITS, cfg.stopbits)
        cfg.timeout = _as_choice_float(data.get("timeout"), TIMEOUTS, cfg.timeout)
        cfg.mode = _as_choice_str(data.get("mode"), MODES, cfg.mode)
        return cfg

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "parity": self.parity,
            "bytesize": self.bytesize,
            "stopbits": self.stopbits,
            "timeout": self.timeout,
            "mode": self.mode,
        }

    def serial_kwargs(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "serial_timeout": self.timeout,
            "bytesize": self.bytesize,
            "parity": self.parity,
            "stopbits": self.stopbits,
        }


def _as_str(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value).strip()


def _as_choice_str(value: Any, choices: list[str], default: str) -> str:
    value = _as_str(value, default)
    return value if value in choices else default


def _as_choice_int(value: Any, choices: list[int], default: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value in choices else default


def _as_choice_float(value: Any, choices: list[float], default: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if value in choices else default


def get_config_path(create: bool = False) -> Path:
    return getConfigPath(
        configName=CONFIG_NAME,
        appName=defs.APP_NAME,
        fromEtc=defs.CONFIG_ETC,
        createIfNotExist=create,
    )


def load_settings() -> UartSettings:
    cfg_path = get_config_path(create=True)
    if not cfg_path.is_file():
        return UartSettings()

    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            return UartSettings.from_dict(json.load(f))
    except Exception as e:
        log.error(f"Failed to load UART settings from {cfg_path}: {e}")
        return UartSettings()


def save_settings(settings: UartSettings) -> None:
    cfg_path = get_config_path(create=True)
    if not cfg_path.parent.is_dir():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)

    with cfg_path.open("w", encoding="utf-8") as f:
        json.dump(settings.to_dict(), f, indent=4)


def _get_tty_driver(name: str) -> str:
    path = f"/sys/class/tty/{name}/device/driver"
    try:
        real = os.path.realpath(path)
        if real and os.path.exists(real):
            return os.path.basename(real)
    except Exception:
        pass
    return ""


def _get_tty_sys_device(name: str) -> str:
    path = f"/sys/class/tty/{name}/device"
    try:
        real = os.path.realpath(path)
        if real and os.path.exists(real):
            return real
    except Exception:
        pass
    return ""


def _is_real_tty(device: str) -> bool:
    if not os.path.exists(device):
        return False

    name = os.path.basename(device)
    sys_device = _get_tty_sys_device(name)
    driver = _get_tty_driver(name)

    if not sys_device:
        return False

    if not driver:
        return False

    return True


def _classify_tty(name: str, sys_device: str, driver: str) -> str:
    if name.startswith("ttyUSB"):
        return "USB serial"

    if name.startswith("ttyACM"):
        return "USB ACM"

    if name.startswith("ttyAMA"):
        return "SBC UART"

    if name.startswith("ttyS"):
        if "serial8250" in sys_device and driver == "port":
            return "legacy serial8250"

        if driver == "serial8250":
            return "legacy serial8250"

        return "hardware UART"

    return "unknown"


def list_serial_ports() -> list[UartPortInfo]:
    ports: list[UartPortInfo] = []
    seen: set[str] = set()

    for pattern in (
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
        "/dev/ttyAMA*",
        "/dev/ttyS*",
    ):
        for device in sorted(glob.glob(pattern)):
            if not _is_real_tty(device):
                continue

            name = os.path.basename(device)
            sys_device = _get_tty_sys_device(name)
            driver = _get_tty_driver(name)
            kind = _classify_tty(name, sys_device, driver)

            if kind in ("legacy serial8250", "unknown"):
                continue

            _add_port(ports, seen, device, kind, driver)

    return ports


def _add_port(
    ports: list[UartPortInfo],
    seen: set[str],
    device: str,
    description: str = "",
    hwid: str = "",
) -> None:
    device = _as_str(device, "")
    if not device or device in seen:
        return

    if device.startswith("/dev") and not os.path.exists(device):
        return

    real_device = os.path.realpath(device) if device.startswith("/dev") else device
    if real_device in seen:
        return

    seen.add(device)
    seen.add(real_device)
    ports.append(UartPortInfo(device=device, description=description, hwid=hwid))


def parity_label(parity: str) -> str:
    labels = {
        "N": TXT_UART_MENU_PARITY_NONE,
        "E": TXT_UART_MENU_PARITY_EVEN,
        "O": TXT_UART_MENU_PARITY_ODD,
        "M": TXT_UART_MENU_PARITY_MARK,
        "S": TXT_UART_MENU_PARITY_SPACE,
    }
    return labels.get(parity, parity)


def mode_label(mode: str) -> str:
    if mode == "receiver":
        return TXT_UART_MENU_MODE_RECEIVER
    return TXT_UART_MENU_MODE_TRANSMITTER
