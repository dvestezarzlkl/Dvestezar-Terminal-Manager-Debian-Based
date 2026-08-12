from __future__ import annotations

from collections.abc import Iterable


_LOCAL_SETTINGS_OVERRIDE = False


def configure_runtime_args(args: Iterable[str]) -> tuple[str, ...]:
    """Consume SysApps-only runtime flags and return all unhandled arguments.

    Runtime flags are intentionally process-local. They are not configuration,
    are never persisted by cfg.save(), and cannot be imported from SYSAPP1E.
    Unhandled arguments are preserved for current or future downstream consumers.
    """
    global _LOCAL_SETTINGS_OVERRIDE

    remaining: list[str] = []
    for raw in args:
        arg = str(raw)
        if arg == "--local-settings":
            _LOCAL_SETTINGS_OVERRIDE = True
            continue
        remaining.append(arg)
    return tuple(remaining)


def local_settings_override_enabled() -> bool:
    """Return whether centrally managed local settings are editable this run."""
    return bool(_LOCAL_SETTINGS_OVERRIDE)


def _set_local_settings_override_for_tests(value: bool) -> None:
    """Test-only state setter; production code configures flags from argv."""
    global _LOCAL_SETTINGS_OVERRIDE
    _LOCAL_SETTINGS_OVERRIDE = bool(value)
