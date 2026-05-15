import os
import glob
from dataclasses import dataclass


@dataclass
class UartPortInfo:
    device: str
    name: str
    sys_device: str = ""
    driver: str = ""
    is_usb: bool = False
    source: str = ""


def _readlink(path: str) -> str:
    try:
        return os.path.realpath(path)
    except Exception:
        return ""


def _get_driver(name: str) -> str:
    path = f"/sys/class/tty/{name}/device/driver"
    try:
        real = os.path.realpath(path)
        if real and os.path.exists(real):
            return os.path.basename(real)
    except Exception:
        pass
    return ""


def _get_sys_device(name: str) -> str:
    path = f"/sys/class/tty/{name}/device"
    try:
        real = os.path.realpath(path)
        if real and os.path.exists(real):
            return real
    except Exception:
        pass
    return ""


def _is_usb_path(path: str) -> bool:
    return "/usb" in path.lower()


def _is_real_tty(device: str) -> bool:
    if not os.path.exists(device):
        return False

    name = os.path.basename(device)
    sys_device = _get_sys_device(name)
    driver = _get_driver(name)

    # Bez sysfs device je to většinou pseudo/virtuální bordel
    if not sys_device:
        return False

    # tty zařízení bez driveru bych do defaultního seznamu nedával
    if not driver:
        return False

    return True


def list_uart_ports(include_legacy: bool = False) -> list[UartPortInfo]:
    result: list[UartPortInfo] = []
    seen: set[str] = set()

    patterns = [
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
        "/dev/ttyAMA*",
        "/dev/ttyS*",
    ]

    for pattern in patterns:
        for device in sorted(glob.glob(pattern)):
            name = os.path.basename(device)

            if device in seen:
                continue

            if not _is_real_tty(device):
                continue

            sys_device = _get_sys_device(name)
            driver = _get_driver(name)
            is_usb = _is_usb_path(sys_device)

            # ttyS vyšší čísla jsou často falešný bordel,
            # pokud nechceš legacy režim, nech jen nízké porty
            if name.startswith("ttyS") and not include_legacy:
                try:
                    num = int(name[4:])
                    if num > 5:
                        continue
                except ValueError:
                    continue

            seen.add(device)

            result.append(
                UartPortInfo(
                    device=device,
                    name=name,
                    sys_device=sys_device,
                    driver=driver,
                    is_usb=is_usb,
                    source="sysfs",
                )
            )

    return result

def classify_uart_port(p: UartPortInfo) -> tuple[int, str]:
    name = p.name
    driver = p.driver
    sys_device = p.sys_device

    if name.startswith("ttyUSB"):
        return 10, "USB serial"

    if name.startswith("ttyACM"):
        return 20, "USB ACM"

    if name.startswith("ttyAMA"):
        return 30, "SBC UART"

    if name.startswith("ttyS"):
        # PC/VM legacy bordel
        if "serial8250" in sys_device and driver == "port":
            return 900, "legacy serial8250"

        # OPi/SBC placeholdery přes serial8250
        # Na Orange Pi zapnuté UARTy často běží přes konkrétní driver,
        # např. dw-apb-uart. Generický serial8250 bych do selectu nedával.
        if driver == "serial8250":
            return 900, "legacy serial8250"

        # Reálný SoC UART, např. dw-apb-uart
        return 40, "hardware UART"

    return 1000, "unknown"


def list_uart_ports_for_select(
    include_legacy: bool = False,
    include_unknown: bool = False,
) -> list[UartPortInfo]:
    ports = list_uart_ports(include_legacy=True)

    result: list[UartPortInfo] = []

    for p in ports:
        p.priority, p.kind = classify_uart_port(p)

        if not include_legacy and p.kind == "legacy serial8250":
            continue

        if not include_unknown and p.kind == "unknown":
            continue

        result.append(p)

    result.sort(key=lambda p: (p.priority, p.name))
    return result



ports = list_uart_ports_for_select()

if not ports:
    print("Není detekován žádný připojitelný UART port.")
else:
    for p in ports:
        print(f"{p.device:12} {p.kind:18} {p.driver}")