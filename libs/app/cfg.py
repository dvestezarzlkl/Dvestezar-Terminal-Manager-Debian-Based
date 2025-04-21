from ..JBLibs.helper import load_config
from .c_service_node import c_service_node
from libs.JBLibs.machine_info import c_machine_info

# cspell:ignore fullchain
VERSION = "1.4.1"
MAIN_TITLE: str = f"Dvestezar Terminal Manager (Debian Based) - version: {VERSION}"

# **** následují proměnné které budou přepsány z config.ini který je v root-u hlavního skriptu, tzn jak je app.py ****

MIN_WIDTH: int            = 0
LANGUAGE: str             = "en-US"                         # jazyk aplikace
SERVER_URL:str            = "moje.domena.fake"              # jen doména, popř sub path
DEFAULT_NODE_ARCHIVE: str = "/home/defaultNodeInstance.7z"  # cesta k archivu s instancí např s výchozí instalací plugin, uzlů flow atd.
DEFAULT_JS_CONFIG: str    = "muj-node-config.default.js"    # v assets
TEMP_DIRECTORY: str       = "/tmp/default_node"             # kam se dočasně rozbalí archiv
BACKUP_DIRECTORY: str     = "/var/backups"                  # kam se budou ukládat zálohy
INSTANCE_INFO: str        = ""                              # kam se budou ukládat informace o instancích, pro vypnutí nastavíme "" nebo null

httpsKey: str = None
httpsCert: str = None
"""Nastavením na None vypneme podporu https"""

load_config()

# Runtime proměnné
mainService: c_service_node = None
"""Instance služby pro práci s systemd nad šablonou node-red instancí
inicializuje se v menu0.py
"""

machineInfo: c_machine_info = c_machine_info()

# příklad ini souboru
"""
```ini
[globals]
LANGUAGE                = "cs-CZ"
SERVER_URL              = "moje.domena.real"
DEFAULT_JS_CONFIG       = "muj-node-config.default.js"
TEMP_DIRECTORY          = "/tmp/default_node"
BACKUP_DIRECTORY        = "/var/backups"
MIN_WIDTH               = 60
INSTANCE_INFO           = ""

# Pokud vynecháme bude ssl vypnuto, viz default hodnoty v cfg.py
# vynecháme zakomentováním nebo nastavením na null None
httpsKey = '/root/.acme.sh/moje.domena.real/moje.domena.real.key'
httpsCert = '/root/.acme.sh/moje.domena.real/fullchain.cer'

httpsKey = null
httpsCert = None
```
"""