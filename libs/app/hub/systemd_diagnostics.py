"""Read-only verification and explicitly confirmed test of the SysApps Hub timer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import re
import subprocess
import time

from .scheduler import (
    UNIT_DIR, SERVICE_NAME, TIMER_NAME, _read_managed, render_units,
)

# OnCalendar=hourly with AccuracySec=1min and RandomizedDelaySec=2min.
# 65 minutes allows a small scheduling margin without hiding missed hours.
MAX_INTERVAL_SECONDS = 65 * 60


@dataclass(frozen=True)
class HubTimerCheck:
    managed: bool
    timer_loaded: bool
    timer_enabled: bool
    timer_active: bool
    service_loaded: bool
    service_state: str
    last_trigger: str
    last_start: str
    last_completion: str
    next_run: str
    result: str
    exit_status: str
    trigger_age_seconds: float | None
    start_age_seconds: float | None
    completion_age_seconds: float | None
    next_due_seconds: float | None

    @property
    def can_test(self) -> bool:
        return (
            self.managed and self.timer_loaded and self.timer_enabled
            and self.timer_active and self.service_loaded
            and self.service_state in ("inactive", "failed")
        )

    @property
    def healthy(self) -> bool:
        return (
            self.can_test
            and self.result == "success" and self.exit_status == "0"
            and self.trigger_age_seconds is not None
            and 0 <= self.trigger_age_seconds <= MAX_INTERVAL_SECONDS
            and self.start_age_seconds is not None
            # Do not let a later manual service run masquerade as a timer
            # success. The service must have started near the last timer event.
            and -30 <= self.trigger_age_seconds - self.start_age_seconds <= 180
            and self.completion_age_seconds is not None
            and 0 <= self.completion_age_seconds <= MAX_INTERVAL_SECONDS
            and self.next_due_seconds is not None
            and 0 < self.next_due_seconds <= MAX_INTERVAL_SECONDS
        )


def _show_properties(unit: str, properties: tuple[str, ...]) -> dict[str, str]:
    # Unit names/properties are hard-coded. Never invoke a shell.
    result = subprocess.run(
        ["systemctl", "show", "--no-pager", unit,
         *(f"--property={name}" for name in properties)],
        capture_output=True, text=True, timeout=8, check=False,
        env={**os.environ, "LC_TIME": "C", "LANG": "C"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"systemctl show failed for {unit} (exit {result.returncode})")
    return dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if "=" in line
    )


def _timestamp_seconds(value: str) -> float | None:
    # systemctl show formats human timestamps in the local timezone.
    # mktime handles the local DST rules for the date being parsed.
    match = re.search(r"\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\b", value)
    if not match:
        return None
    try:
        parsed = datetime.strptime(match.group(), "%Y-%m-%d %H:%M:%S")
        return time.mktime(parsed.timetuple())
    except (ValueError, OverflowError):
        return None


def inspect_timer_sync() -> HubTimerCheck:
    """Inspect actual systemd state, last timer trigger and last service result."""
    try:
        service_unit, timer_unit = render_units()
        managed = (
            _read_managed(UNIT_DIR / SERVICE_NAME) == service_unit.encode("utf-8")
            and _read_managed(UNIT_DIR / TIMER_NAME) == timer_unit.encode("utf-8")
        )
    except (OSError, RuntimeError, ValueError):
        managed = False

    timer = _show_properties(TIMER_NAME, (
        "LoadState", "UnitFileState", "ActiveState",
        "LastTriggerUSec", "NextElapseUSecRealtime",
    ))
    service = _show_properties(SERVICE_NAME, (
        "LoadState", "ActiveState", "Result",
        "ExecMainStatus", "ExecMainStartTimestamp", "ExecMainExitTimestamp",
    ))
    now = time.time()
    last_trigger = timer.get("LastTriggerUSec", "n/a")
    last_start = service.get("ExecMainStartTimestamp", "n/a")
    last_completion = service.get("ExecMainExitTimestamp", "n/a")
    next_run = timer.get("NextElapseUSecRealtime", "n/a")
    trigger = _timestamp_seconds(last_trigger)
    start = _timestamp_seconds(last_start)
    completion = _timestamp_seconds(last_completion)
    next_due = _timestamp_seconds(next_run)
    return HubTimerCheck(
        managed=managed,
        timer_loaded=timer.get("LoadState") == "loaded",
        timer_enabled=timer.get("UnitFileState") == "enabled",
        timer_active=timer.get("ActiveState") == "active",
        service_loaded=service.get("LoadState") == "loaded",
        service_state=service.get("ActiveState", "unknown"),
        last_trigger=last_trigger,
        last_start=last_start,
        last_completion=last_completion,
        next_run=next_run,
        result=service.get("Result", "unknown"),
        exit_status=service.get("ExecMainStatus", "?"),
        trigger_age_seconds=None if trigger is None else now - trigger,
        start_age_seconds=None if start is None else now - start,
        completion_age_seconds=None if completion is None else now - completion,
        next_due_seconds=None if next_due is None else next_due - now,
    )


def last_service_run() -> tuple[str | None, str, str, str]:
    """Read the last service start and result without querying or changing the timer.

    The service might have been started manually: this is not evidence that
    the hourly timer has already fired.
    """
    props = _show_properties(SERVICE_NAME, (
        "LoadState", "ActiveState", "Result",
        "ExecMainStatus", "ExecMainStartTimestamp",
    ))
    if props.get("LoadState") != "loaded":
        raise RuntimeError("SysApps Hub systemd service is not loaded.")
    started_at = _timestamp_seconds(props.get("ExecMainStartTimestamp", ""))
    started = (
        datetime.fromtimestamp(started_at).strftime("%Y-%m-%d %H:%M:%S")
        if started_at is not None else None
    )
    return (
        started,
        props.get("ActiveState", "unknown"),
        props.get("Result", "unknown"),
        props.get("ExecMainStatus", "?"),
    )


def run_systemd_sync() -> tuple[bool, str]:
    """Explicit oneshot test without changing the hourly timer's configuration."""
    if os.geteuid() != 0:
        return False, "The systemd sync test requires root."
    if not inspect_timer_sync().can_test:
        return False, "The managed systemd timer/service is not ready for a test."
    try:
        result = subprocess.run(
            ["systemctl", "start", "--no-ask-password", SERVICE_NAME],
            capture_output=True, text=True, check=False, timeout=660,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"systemctl start failed ({type(exc).__name__})."
    if result.returncode != 0:
        return False, f"systemctl start failed (exit {result.returncode})."
    after = inspect_timer_sync()
    if not (
        after.result == "success" and after.exit_status == "0"
        and after.completion_age_seconds is not None
        and 0 <= after.completion_age_seconds <= 120
    ):
        return False, (
            "systemd did not confirm a successful recent service completion "
            f"(Result={after.result}, ExecMainStatus={after.exit_status})."
        )
    return True, "The systemd oneshot completed successfully (exit 0)."
