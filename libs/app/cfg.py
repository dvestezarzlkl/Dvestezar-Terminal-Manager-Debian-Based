# from .c_service_node import c_service_node
from libs.JBLibs.machine_info import c_machine_info

# cspell:ignore fullchain
VERSION = "1.6.1"
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
INSTANCE_INFO_COPY_PHP:bool = False                # pokud je True tak se bude kopírovat do assets/php/node_red_instances.php do adresáře jako je JSON
SITE_NAME: str            = "Dvestezar Terminal Manager"  # název webu, pro hlavičku a titulky
LOG_DIR:str               = "/var/log/jb_sys_apps"         # adresář pro logy

# seznam CIDR adres, které budou mít přístup k PHP skriptu
# zadáváme jako JSON string pole string-ů !!!
# pokud zadáme v ini "[]"" nebude omezení zapnuto
PHP_SCRIPT_CIDRS:str      = """[ "192.168.0.0/24", "127.0.0.1" ]"""

PHP_SCRIPT_RENAME:str     = None # pokud není None tak se použije pro přejmenování PHP skriptu, např. 'index' na index.php, zapisuje se jméno bez přípony .php
    

httpsKey: str = None
httpsCert: str = None
"""Nastavením na None vypneme podporu https"""

# Runtime proměnné
mainService = None
"""Instance služby pro práci s systemd nad šablonou node-red instancí
inicializuje se v menu0.py
"""

machineInfo: c_machine_info = c_machine_info()

def load():
    from libs.JBLibs.helper import load_config
    load_config()

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

# pokud chceme u php scriptu zadat CIDR adresy, tak zadáme takto
# PHP_SCRIPT_CIDRS = "["192.168.1.1/32"]"
# !!! config bere jako string vše od první uvozovky do poslední, takže uvozovky mezi nimi jsou brány jako text !!!

```
"""