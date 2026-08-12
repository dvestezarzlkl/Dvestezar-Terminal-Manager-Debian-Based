import sys

# from .c_service_node import c_service_node

from libs.JBLibs.machine_info import c_machine_info
from ..app import g_def as defs

# cspell:ignore fullchain
VERSION = "2.2.5"
MAIN_TITLE: str = f"Dvestezar Terminal Manager (Debian Based) - version: {VERSION}"

# **** následují proměnné které budou přepsány z config.ini který je v root-u hlavního skriptu, tzn jak je app.py ****

MIN_WIDTH: int            = 0
LANGUAGE: str             = "en-US"                         # jazyk aplikace
SERVER_URL:str            = ""                              # kompatibilní klíč: service host/FQDN/IP bez scheme, portu a path
DEFAULT_NODE_ARCHIVE: str = "/home/defaultNodeInstance.7z"  # cesta k archivu s instancí např s výchozí instalací plugin, uzlů flow atd.
DEFAULT_JS_CONFIG: str    = "muj-node-config.default.js"    # v assets
TEMP_DIRECTORY: str      = "/tmp/default_node"             # kam se dočasně rozbalí archiv
BACKUP_DIRECTORY: str    = "/var/backups"                  # kam se budou ukládat zálohy
INSTANCE_INFO: str       = ""                              # kam se budou ukládat informace o instancích, pro vypnutí nastavíme "" nebo null
INSTANCE_INFO_COPY_PHP:bool = False                # pokud je True tak se bude kopírovat do assets/php/node_red_instances.php do adresáře jako je JSON
SITE_NAME: str            = "Dvestezar Terminal Manager"  # název webu, pro hlavičku a titulky
LOG_DIR:str               = "/var/log/jb_sys_apps"         # adresář pro logy

# Mail transport pro celou aplikaci
MAIL_SMTP_HOST:str        = ""                              # SMTP server
MAIL_SMTP_PORT:int        = 587                             # SMTP port
MAIL_SMTP_USER:str        = ""                              # SMTP uživatel
MAIL_SMTP_PASSWORD:str    = ""                              # SMTP heslo
MAIL_SMTP_MODE:str        = "starttls"                      # plain / starttls / ssl
MAIL_FROM:str             = ""                              # odesílatel, pokud je prázdný použije se SMTP user
MAIL_FALLBACK_ADMIN:str   = ""                              # výchozí admin mail pro aplikace bez vlastního admin mail
MAIL_TIMEOUT:int          = 20                              # timeout pro SMTP spojení v sekundách

# SysApps Hub - centrální MySQL/MariaDB inventář
HUB_ENABLED:bool          = False                           # zapne health-check a synchronizaci Hubu
HUB_DB_HOST:str           = ""                            # MySQL/MariaDB host
HUB_DB_PORT:int           = 3306                            # MySQL/MariaDB port
HUB_DB_USER:str           = ""                            # databázový uživatel
HUB_DB_PASSWORD:str       = ""                            # databázové heslo
HUB_DB_NAME:str           = "sys_apps"                    # výchozí databáze Hubu
HUB_DB_PREFIX:str         = "sysapps_"                    # validovaný prefix tabulek
HUB_CONNECT_TIMEOUT:int   = 3                               # krátký startup/connect timeout
HUB_AUTO_SYNC:bool        = True                            # automatický sync po úspěšném startup health-checku

# Centrální distribuce přenositelných nastavení
SETTINGS_URL:str          = ""                              # HTTPS URL s jedním šifrovaným SYSAPP1E balíkem
SETTINGS_PASSWORD:str     = ""                              # lokální bootstrap heslo, nikdy se neimportuje z balíku
SETTINGS_AUTH_USER:str    = ""                              # volitelný HTTP Basic Auth uživatel, nikdy se neimportuje
SETTINGS_AUTH_PASSWORD:str = ""                             # volitelné HTTP Basic Auth heslo, nikdy se neimportuje
SETTINGS_AUTO_UPDATE:bool = False                           # při startu použije pouze vyšší revision
SETTINGS_CONNECT_TIMEOUT:int = 5                            # timeout stažení v sekundách
SETTINGS_ALLOW_HTTP:bool  = False                           # explicitní nouzová výjimka pro izolovanou LAN
SETTINGS_IMPORT_POLICY:str = "{}"                           # lokální JSON politika skip sekcí/polí; nikdy se neimportuje
SETTINGS_LAST_REVISION:int = 0                              # poslední úspěšně aplikovaná vzdálená revision
SETTINGS_LAST_SHA256:str  = ""                              # hash balíku chrání před změnou obsahu stejné revision
SETTINGS_LAST_APPLIED:str = ""                              # podpis skutečně aplikovaných sekcí a jejich verzí

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
    load_config(
        configName=defs.CONFIG_NAME,
        fromEtc=defs.CONFIG_ETC,
        appName=defs.APP_NAME
    )


def save():
    """Persist the app runtime config back to the shared config.ini."""
    from libs.JBLibs.helper import save_config

    save_config(
        config_module=sys.modules[__name__],
        fromEtc=defs.CONFIG_ETC,
        configName=defs.CONFIG_NAME,
        appName=defs.APP_NAME,
    )

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
