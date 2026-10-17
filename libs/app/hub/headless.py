"""Noninteractive SysApps Hub entrypoint for a systemd oneshot service."""
from __future__ import annotations

import os
import sys


def main() -> int:
    # Run outside menuBoss/c_menu and its interactive /tmp/jb_sys_apps.lock.
    if os.geteuid() != 0:
        print("SysApps Hub collection requires root.", file=sys.stderr)
        return 77

    from libs.app import cfg
    try:
        cfg.load()
    except Exception:
        print("SysApps Hub headless configuration initialization failed.", file=sys.stderr)
        return 1

    # Match the interactive bootstrap: logging is initialized after cfg.load().
    from libs.JBLibs.helper import getLogger, setLng
    from .provider_discovery import register_collectors
    from .runtime import hub_runtime

    log = getLogger(__name__)
    try:
        setLng(cfg.LANGUAGE)
    except Exception:
        log.exception("SysApps Hub headless language initialization failed.")
        return 1

    if not cfg.HUB_ENABLED:
        log.info("SysApps Hub collection skipped: Hub is disabled.")
        return 0

    hub_runtime.clear_providers()
    try:
        warnings = register_collectors(hub_runtime)
    except Exception:
        log.exception("SysApps Hub collector discovery failed.")
        return 1

    report = hub_runtime.sync_all_locked()
    if report.error:
        log.error("SysApps Hub scheduled collection failed: %s", report.error)
        return 1
    for warning in warnings + report.warnings:
        log.warning("SysApps Hub scheduled collection warning: %s", warning)
    log.info(
        "SysApps Hub scheduled collection finished: %d provider(s), %d warning(s).",
        len(report.provider_counts),
        len(warnings) + len(report.warnings),
    )
    return 2 if warnings or report.warnings else 0


if __name__ == "__main__":
    sys.exit(main())
