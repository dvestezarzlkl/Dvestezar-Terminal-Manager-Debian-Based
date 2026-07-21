from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Iterable

import serial

BAUDRATES = (9600, 19200, 38400, 57600, 115200, 230400, 460800,
             500000, 576000, 921600, 1000000, 1500000, 2000000)
TEST_SECONDS_PER_BAUD = 4.0
READ_TIMEOUT = 0.05
FRAME_TIMEOUT = 0.50
FRAME_PREFIX = bytes((0xAA, 0xCC, 0xE3, 0x78, 0x38))
FRAME_LENGTH = 8
Printer = Callable[[str], None]


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
        return (not self.error and self.sent > 0 and self.received == self.sent
                and not self.timeouts and not self.crc_errors
                and not self.data_errors and not self.invalid_bytes)


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def make_frame(index: int) -> bytes:
    payload = FRAME_PREFIX + bytes((index & 0xFF,))
    crc = crc16_modbus(payload)
    return payload + bytes((crc & 0xFF, crc >> 8))


def valid_frame(frame: bytes) -> bool:
    if len(frame) != FRAME_LENGTH or not frame.startswith(FRAME_PREFIX):
        return False
    return (frame[6] | frame[7] << 8) == crc16_modbus(frame[:6])


def hex_data(data: bytes | None) -> str:
    return "-" if data is None else data.hex(" ").upper()


def read_frame(ser: serial.Serial, deadline: float,
               result: BaudResult) -> bytes | None:
    window = bytearray()
    while time.monotonic() < deadline:
        chunk = ser.read(max(1, ser.in_waiting))
        if not chunk:
            continue
        window.extend(chunk)
        while len(window) >= FRAME_LENGTH:
            candidate = bytes(window[:FRAME_LENGTH])
            if valid_frame(candidate):
                return candidate
            if candidate.startswith(FRAME_PREFIX):
                result.crc_errors += 1
            else:
                result.invalid_bytes += 1
            del window[0]
    return None


def test_baudrate(port: str, baudrate: int, *, bytesize: int = 8,
                  parity: str = "N", stopbits: float = 1,
                  seconds: float = TEST_SECONDS_PER_BAUD,
                  output: Printer = print) -> BaudResult:
    result = BaudResult(baudrate)
    started = time.monotonic()
    output(f"\n--- {baudrate} Bd | {bytesize}{parity}{stopbits:g} | {seconds:.1f} s ---")
    try:
        with serial.Serial(port, baudrate, bytesize=bytesize, parity=parity,
                           stopbits=stopbits, timeout=READ_TIMEOUT,
                           write_timeout=1.0, xonxoff=False, rtscts=False,
                           dsrdtr=False) as ser:
            output(f"OPEN port={ser.port} requested={baudrate} actual={ser.baudrate}")
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            end_time = started + seconds
            index = 0
            while time.monotonic() < end_time:
                frame = make_frame(index)
                sent_at = time.monotonic()
                written = ser.write(frame)
                ser.flush()
                result.sent += 1
                if written != FRAME_LENGTH:
                    result.error = f"write {written}/{FRAME_LENGTH} B"
                    output(f"[{index:03d}] TX ERROR {result.error}")
                    break
                rx = read_frame(ser, min(end_time, sent_at + FRAME_TIMEOUT), result)
                latency = (time.monotonic() - sent_at) * 1000.0
                if rx is None:
                    result.timeouts += 1
                    output(f"[{index:03d}] TIMEOUT {latency:7.2f} ms TX={hex_data(frame)}")
                elif rx != frame:
                    result.data_errors += 1
                    output(f"[{index:03d}] DATAERR {latency:7.2f} ms TX={hex_data(frame)} RX={hex_data(rx)}")
                else:
                    result.received += 1
                    output(f"[{index:03d}] OK      {latency:7.2f} ms TX={hex_data(frame)} RX={hex_data(rx)}")
                index = (index + 1) & 0xFF
                time.sleep(0.01)
    except Exception as exc:
        result.error = str(exc)
        output(f"ERROR: {exc}")
    result.elapsed = time.monotonic() - started
    output(format_result(result))
    return result


def run_all(port: str, *, baudrates: Iterable[int] = BAUDRATES,
            bytesize: int = 8, parity: str = "N", stopbits: float = 1,
            seconds_per_baud: float = TEST_SECONDS_PER_BAUD,
            output: Printer = print) -> list[BaudResult]:
    output("Propojte TX <-> RX na testovanem UART prevodniku.")
    output(f"Port: {port}; test: {seconds_per_baud:.1f} s na rychlost")
    results = []
    for baudrate in baudrates:
        results.append(test_baudrate(port, int(baudrate), bytesize=bytesize,
                      parity=parity, stopbits=stopbits,
                      seconds=seconds_per_baud, output=output))
    output("\n=== SOUHRN UART LOOPBACK ===")
    output(format_summary(results))
    return results


def format_result(result: BaudResult) -> str:
    state = "OK" if result.ok else "FAIL"
    tail = f" ERR={result.error}" if result.error else ""
    return (f"{result.baudrate:>8} Bd | {state:<4} | TX={result.sent} "
            f"RX={result.received} TO={result.timeouts} CRC={result.crc_errors} "
            f"DATA={result.data_errors} GARBAGE={result.invalid_bytes} "
            f"TIME={result.elapsed:.2f}s{tail}")


def format_summary(results: Iterable[BaudResult]) -> str:
    items = list(results)
    lines = [format_result(item) for item in items]
    lines += ["", f"Vysledek: {sum(x.ok for x in items)}/{len(items)} rychlosti bez chyby"]
    return "\n".join(lines)
