from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterable

import serial


BAUDRATES: tuple[int, ...] = (
    9_600,
    19_200,
    38_400,
    57_600,
    115_200,
    230_400,
    460_800,
    500_000,
    576_000,
    921_600,
    1_000_000,
    1_500_000,
    2_000_000,
)

TEST_SECONDS_PER_BAUD = 4.0
READ_TIMEOUT = 0.10
FRAME_LENGTH = 8
PAYLOAD_LENGTH = 6
FRAME_PREFIX = bytes((0xAA, 0xCC, 0xE3, 0x78, 0x38))


@dataclass(slots=True)
class BaudResult:
    baudrate: int
    sent: int = 0
    received: int = 0
    timeouts: int = 0
    crc_errors: int = 0
    data_errors: int = 0
    invalid_bytes: int = 0
    elapsed: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return (
            not self.error
            and self.sent > 0
            and self.received == self.sent
            and self.timeouts == 0
            and self.crc_errors == 0
            and self.data_errors == 0
        )


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def make_frame(index: int) -> bytes:
    payload = FRAME_PREFIX + bytes((index & 0xFF,))
    crc = crc16_modbus(payload)
    return payload + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def valid_frame(frame: bytes) -> bool:
    if len(frame) != FRAME_LENGTH or not frame.startswith(FRAME_PREFIX):
        return False
    received_crc = frame[6] | (frame[7] << 8)
    return received_crc == crc16_modbus(frame[:PAYLOAD_LENGTH])


def _read_frame(ser: serial.Serial, deadline: float, result: BaudResult) -> bytes | None:
    window = bytearray()
    while time.monotonic() < deadline:
        chunk = ser.read(max(1, ser.in_waiting))
        if not chunk:
            continue
        window.extend(chunk)

        while len(window) >= FRAME_LENGTH:
            candidate = bytes(window[:FRAME_LENGTH])
            if valid_frame(candidate):
                del window[:FRAME_LENGTH]
                return candidate

            if candidate.startswith(FRAME_PREFIX):
                result.crc_errors += 1
            else:
                result.invalid_bytes += 1
            del window[0]
    return None


def test_baudrate(
    port: str,
    baudrate: int,
    *,
    bytesize: int = 8,
    parity: str = "N",
    stopbits: float = 1,
    seconds: float = TEST_SECONDS_PER_BAUD,
) -> BaudResult:
    result = BaudResult(baudrate=baudrate)
    started = time.monotonic()

    try:
        with serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=READ_TIMEOUT,
            write_timeout=1.0,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        ) as ser:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            end_time = started + seconds
            index = 0

            while time.monotonic() < end_time:
                frame = make_frame(index)
                written = ser.write(frame)
                ser.flush()
                if written != len(frame):
                    result.error = f"Zapsáno jen {written}/{len(frame)} B"
                    break

                result.sent += 1
                deadline = min(end_time, time.monotonic() + 0.5)
                received = _read_frame(ser, deadline, result)
                if received is None:
                    result.timeouts += 1
                elif received == frame:
                    result.received += 1
                else:
                    result.data_errors += 1

                index = (index + 1) & 0xFF
                time.sleep(0.01)

    except Exception as exc:
        result.error = str(exc)

    result.elapsed = time.monotonic() - started
    return result


def run_all(
    port: str,
    *,
    baudrates: Iterable[int] = BAUDRATES,
    bytesize: int = 8,
    parity: str = "N",
    stopbits: float = 1,
    seconds_per_baud: float = TEST_SECONDS_PER_BAUD,
) -> list[BaudResult]:
    results: list[BaudResult] = []
    for baudrate in baudrates:
        results.append(
            test_baudrate(
                port,
                int(baudrate),
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                seconds=seconds_per_baud,
            )
        )
    return results


def format_result(result: BaudResult) -> str:
    state = "OK" if result.ok else "FAIL"
    detail = (
        f"TX={result.sent} RX={result.received} "
        f"TO={result.timeouts} CRC={result.crc_errors} "
        f"DATA={result.data_errors} GARBAGE={result.invalid_bytes}"
    )
    if result.error:
        detail += f" ERR={result.error}"
    return f"{result.baudrate:>8} Bd | {state:<4} | {detail} | {result.elapsed:4.1f}s"


def format_summary(results: Iterable[BaudResult]) -> str:
    items = list(results)
    ok_count = sum(1 for item in items if item.ok)
    lines = [format_result(item) for item in items]
    lines.append("")
    lines.append(f"Výsledek: {ok_count}/{len(items)} rychlostí bez chyby")
    return "\n".join(lines)
