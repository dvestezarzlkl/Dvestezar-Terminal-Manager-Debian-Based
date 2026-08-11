#!/usr/bin/env python3.10
from datetime import datetime
import sys
from time import perf_counter

_bootstrap_started = perf_counter()

_cfg_import_started = perf_counter()
import libs.app.cfg as cfg
_cfg_import_elapsed = perf_counter() - _cfg_import_started

_cfg_load_started = perf_counter()
cfg.load()
_cfg_load_elapsed = perf_counter() - _cfg_load_started

_helper_import_started = perf_counter()
from libs.JBLibs.helper import setLng, check_root_user, getLogger
_helper_import_elapsed = perf_counter() - _helper_import_started

_logger_started = perf_counter()
log = getLogger(__name__)
_logger_elapsed = perf_counter() - _logger_started

log.info("")
log.info("")
log.info("***** Start version: %s at %s *****", cfg.VERSION, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
log.info("Startup bootstrap cfg module import: done in %.3fs", _cfg_import_elapsed)
log.info("Startup bootstrap cfg load: done in %.3fs", _cfg_load_elapsed)
log.info("Startup bootstrap helper import: done in %.3fs", _helper_import_elapsed)
log.info("Startup bootstrap logger initialization: done in %.3fs", _logger_elapsed)

_language_started = perf_counter()
setLng(cfg.LANGUAGE)
log.info("Startup bootstrap language setup: done in %.3fs", perf_counter() - _language_started)

_term_import_started = perf_counter()
from libs.JBLibs.term import reset, cls
log.info("Startup bootstrap terminal import: done in %.3fs", perf_counter() - _term_import_started)

_menu_import_started = perf_counter()
import libs.app.menus.menuBoss as menuBoss
log.info("Startup bootstrap menuBoss import: done in %.3fs", perf_counter() - _menu_import_started)


def is_venv():
    return (
        hasattr(sys, 'real_prefix') or
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )


_preflight_started = perf_counter()
if not is_venv():
    print("Nejsi ve virtuálním prostředí")
    sys.exit(1)

# Zajištění spuštění jako root
check_root_user()

# Zajištění jediného běhu aplikace
lock_file_path = "/tmp/jb_sys_apps.lock"
import fcntl
try:
    lock_file = open(lock_file_path, 'w')
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("App running in another instance - exiting")
    sys.exit(1)
log.info("Startup bootstrap runtime preflight: done in %.3fs", perf_counter() - _preflight_started)

ok = False
try:
    reset()
    cls()
    print(cfg.MAIN_TITLE + " ... Starting ...")
    log.info("Startup bootstrap: ready for menu initialization in %.3fs", perf_counter() - _bootstrap_started)

    _menu_init_started = perf_counter()
    log.info("Startup menuBoss init/run call: start")
    try:
        ok = menuBoss.init()
    except Exception:
        log.exception(
            "Startup menuBoss init/run call: failed after %.3fs",
            perf_counter() - _menu_init_started,
        )
        raise
    else:
        log.info(
            "Application menuBoss init/run call: returned after %.3fs (result=%s)",
            perf_counter() - _menu_init_started,
            ok,
        )
finally:
    reset()
    log.info("***** End *****\n\n")
    if ok:
        cls()
    print("End")
