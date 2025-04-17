#!/usr/bin/env python3.10
from libs.JBLibs.helper import setLng,check_root_user
from time import sleep
import libs.app.cfg as cfg
setLng(cfg.LANGUAGE)
from libs.JBLibs.term import reset,cls
from datetime import datetime
from libs.JBLibs.helper import getLogger
import libs.app.menus.menuBoss as menuBoss
log = getLogger(__name__)

import sys

def is_venv():
    return (
        hasattr(sys, 'real_prefix') or
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )

if not is_venv():
    print("Nejsi ve virtuálním prostředí")
    sys.exit(1)

check_root_user()

log.info("")
log.info("")
log.info("***** Start version: %s at %s *****",cfg.VERSION,datetime.now().strftime("%Y-%m-%d %H:%M:%S")) 
ok=False
try:
    reset()
    cls()
    print(cfg.MAIN_TITLE+" ... Starting ...")    
    sleep(2)
    ok=menuBoss.init()
finally:
    reset()
    log.info("***** End *****\n\n")
    if ok:
        cls()
    print("End")
    