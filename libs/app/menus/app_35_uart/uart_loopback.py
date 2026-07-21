from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from typing import Callable, Iterable

import serial

from libs.JBLibs.term import restoreAndClearDown, savePos

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
                  log_output: Printer = print,
                  screen_output: Printer = print) -> BaudResult:
    result = BaudResult(baudrate)
    started = time.monotonic()
    send_until = started + seconds
    log_output(f"\n--- {baudrate} Bd | {bytesize}{parity}{stopbits:g} | {seconds:.1f} s ---")
    screen_output(f"{baudrate:>8} Bd | starting ...")
    savePos()

    try:
        with serial.Serial(port, baudrate, bytesize=bytesize, parity=parity,
                           stopbits=stopbits, timeout=READ_TIMEOUT,
                           write_timeout=1.0, xonxoff=False, rtscts=False,
                           dsrdtr=False) as ser:
            open_line = f"OPEN port={ser.port} requested={baudrate} actual={ser.baudrate}"
            log_output(open_line)
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            index = 0

            while time.monotonic() < send_until:
                frame = make_frame(index)
                sent_at = time.monotonic()
                written = ser.write(frame)
                ser.flush()
                result.sent += 1

                if written != FRAME_LENGTH:
                    result.error = f"write {written}/{FRAME_LENGTH} B"
                    detail = f"[{index:03d}] TX ERROR {result.error}"
                    log_output(detail)
                    restoreAndClearDown()
                    screen_output(f"{baudrate:>8} Bd | {detail}")
                    break

                rx = read_frame(ser, sent_at + FRAME_TIMEOUT, result)
                latency = (time.monotonic() - sent_at) * 1000.0

                if rx is None:
                    result.timeouts += 1
                    detail = f"[{index:03d}] TIMEOUT {latency:7.2f} ms TX={hex_data(frame)}"
                elif rx != frame:
                    result.data_errors += 1
                    detail = (f"[{index:03d}] DATAERR {latency:7.2f} ms "
                              f"TX={hex_data(frame)} RX={hex_data(rx)}")
                else:
                    result.received += 1
                    detail = (f"[{index:03d}] OK {latency:7.2f} ms "
                              f"TX={hex_data(frame)} RX={hex_data(rx)}")

                log_output(detail)
                restoreAndClearDown()
                screen_output(
                    f"{baudrate:>8} Bd | idx={index:03d} "
                    f"TX={result.sent} RX={result.received} TO={result.timeouts} "
                    f"CRC={result.crc_errors} DATA={result.data_errors} "
                    f"GARBAGE={result.invalid_bytes} {latency:7.2f} ms"
                )
                index = (index + 1) & 0xFF
                time.sleep(0.01)

    except Exception as exc:
        result.error = str(exc)
        log_output(f"ERROR: {exc}")

    result.elapsed = time.monotonic() - started
    final_line = format_result(result)
    log_output(final_line)
    restoreAndClearDown()
    screen_output(final_line)
    return result


def _log_path() -> Path:
    log_dir = Path.cwd() / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return log_dir / f"{stamp}_uart_loopback_test.log"


def run_all(port: str, *, baudrates: Iterable[int] = BAUDRATES,
            bytesize: int = 8, parity: str = "N", stopbits: float = 1,
            seconds_per_baud: float = TEST_SECONDS_PER_BAUD,
            output: Printer = print) -> list[BaudResult]:
    log_path = _log_path()
    results: list[BaudResult] = []

    with log_path.open("x", encoding="utf-8", buffering=1) as log_file:
        def log_only(message: str) -> None:
            print(str(message), file=log_file, flush=True)

        def both(message: str) -> None:
            text = str(message)
            output(text)
            log_only(text)

        both("=== NEW UART LOOPBACK RUN ===")
        both(f"Started: {datetime.now().isoformat(timespec='seconds')}")
        both("Connect TX <-> RX on the tested UART adapter.")
        both(f"Port: {port}; format: {bytesize}{parity}{stopbits:g}; "
             f"test: {seconds_per_baud:.1f} s per baudrate")
        both(f"Log: {log_path.resolve()}")
        output("")

        for baudrate in baudrates:
            results.append(test_baudrate(
                port,
                int(baudrate),
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                seconds=seconds_per_baud,
                log_output=log_only,
                screen_output=output,
            ))

        both("\n=== UART LOOPBACK SUMMARY ===")
        both(format_summary(results))
        both(f"Finished: {datetime.now().isoformat(timespec='seconds')}")
        both(f"Log saved to: {log_path.resolve()}")

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
    lines += ["", f"Result: {sum(x.ok for x in items)}/{len(items)} baudrates without error"]
    return "\n".join(lines)
