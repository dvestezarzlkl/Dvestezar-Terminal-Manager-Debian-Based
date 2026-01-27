#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# run as : sudo python3 install.py

CONFIG_FILE_PATH = "/etc/jb_sys_apps/config.ini"

import os
import sys
import subprocess
from pathlib import Path
import libs.app.g_def as defs

allow_paths:list[str] = [
    "libs/JBLibs",
    # "libs/app/menus/app_50_zlkl", # privat, standartně ne, jen pokud dostane přístup
]

def check_venv():
    """Ověří, že skript běží ve virtuálním prostředí (venv)."""
    if sys.prefix == sys.base_prefix:
        print("Chyba: Skript musí být spuštěn uvnitř virtuálního prostředí (venv). Ukončuji.")
        sys.exit(1)
    else:
        print(f"Virtuální prostředí aktivní: {sys.prefix}")

def check_sudo()->None:
    """Ověří, zda je skript spuštěn s právy roota (sudo)."""
    if os.geteuid() != 0:
        print("Chyba: Skript není spuštěn s právy roota (sudo). Ukončuji.")
        sys.exit(1)


def check_run_py_file()->None:
    """Zkontroluje, zda v aktuálním adresáři existuje soubor venv_run.py,
       čímž ověří, že jsme ve správném (root) adresáři projektu."""
    file_name = "venv_run.py"
    if not os.path.exists(file_name):
        print(f"Chyba: V aktuálním adresáři ({os.getcwd()}) "
              f"není nalezen soubor '{file_name}'. Ukončuji.")
        sys.exit(1)


def check_and_install_7zip()->None:
    """Zkontroluje, zda je nainstalován 7zip (p7zip-full). Pokud ne, nainstaluje."""
    print("Kontroluji instalaci 7zip (p7zip-full)...")
    cmd = ["which", "7z"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.returncode == 0:
            print("7zip je již nainstalován.")
            return
    except subprocess.CalledProcessError:
        pass

    # Není nainstalováno -> instalace
    print("7zip není nainstalován. Pokusím se jej nainstalovat přes apt...")
    install_cmd = ["apt", "install", "-y", "p7zip-full"]
    try:
        subprocess.run(install_cmd, check=True)
        print("7zip úspěšně nainstalováno.")
    except subprocess.CalledProcessError as e:
        print("Chyba při instalaci 7zip:\n", e)
        sys.exit(1)


def check_and_install_node():
    """Zkontroluje, zda je nainstalován Node.js (a ideálně i verze).
       Pokud ne, zkusí nainstalovat LTS 22."""
    print("Kontroluji instalaci Node.js...")
    cmd = ["node", "-v"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        version = result.stdout.strip()
        print(f"Node.js je již nainstalován (verze {version}).")
    except FileNotFoundError:
        print("Node.js není nainstalován nebo není dostupný v PATH.")
        install_nodejs()
    except subprocess.CalledProcessError:
        print("Node.js není správně nainstalován nebo neodpovídá.")
        install_nodejs()


def install_nodejs():
    """Instaluje Node.js LTS 22."""
    print("Pokusím se nainstalovat Node.js (LTS 22)...")
    try:
        # 1) Přidání repozitáře
        curl_cmd = ["bash", "-c",
                    "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -"]
        subprocess.run(curl_cmd, shell=False, check=True)

        # 2) Instalace Node.js
        install_cmd = ["apt-get", "install", "-y", "nodejs"]
        subprocess.run(install_cmd, check=True)
        print("Node.js úspěšně nainstalován.")
    except subprocess.CalledProcessError as e:
        print("Chyba při instalaci Node.js:\n", e)
        sys.exit(1)


def update_submodules(recursive:bool=True):
    """
    Inicializuje/aktualizuje jen vybrané submoduly (whitelist).
    allow_paths: seznam cest (path z .gitmodules), např. ["libs/JBLibs"]
    """
    if not allow_paths:
        print("Nejsou zadané žádné submoduly k inicializaci, přeskakuji.")
        return

    base = ["git", "submodule", "update", "--init"]
    if recursive:
        base.append("--recursive")

    print("Provádím init/update submodulů:", ", ".join(allow_paths))
    cmd = base + allow_paths

    try:
        subprocess.run(cmd, check=True)
        print("Submoduly úspěšně inicializovány/aktualizovány.")
    except subprocess.CalledProcessError as e:
        print("Chyba při inicializaci/aktualizovány submodulů:\n", e, file=sys.stderr)
        sys.exit(1)

def run_requirements_install():
    """Spustí pip install -r requirements.txt, pokud soubor existuje."""
    req_file = "requirements.txt"
    if os.path.exists(req_file):
        print(f"Instaluji knihovny z {req_file}...")
        try:
            subprocess.run(["pip", "install", "-r", req_file], check=True)
            print("Knihovny byly úspěšně nainstalovány.")
        except subprocess.CalledProcessError as e:
            print("Chyba při instalaci knihoven přes pip:\n", e)
            sys.exit(1)
    else:
        print(f"Soubor {req_file} neexistuje. Přeskakuji instalaci knihoven.")


def check_and_create_config():
    """Ověří, zda existuje soubor config.ini, a pokud ne, vytvoří ho s výchozím obsahem."""
    from libs.JBLibs.helper import getConfigPath
    
    config_file = Path(getConfigPath(
        configName=defs.CONFIG_NAME,
        fromEtc=defs.CONFIG_ETC,
        appName=defs.APP_NAME,
        createIfNotExist=True
    ))
    if not config_file.parent.is_dir():
        print(f"Chyba: Cesta '{config_file.parent}' není adresář. Ukončuji.")
        sys.exit(1)
    
    if config_file.exists():
        print(f"Soubor '{config_file}' existuje, není nutné vytvářet.")
        return
    elif config_file.exists() and not config_file.is_file():
        print(f"Chyba: Cesta '{config_file}' existuje, ale není to soubor. Ukončuji.")
        sys.exit(1)

    print(f"Soubor '{config_file}' neexistuje. Vytvářím defaultní config.ini...")
    # Zde dejte výchozí nastavení, jaké potřebujete:
    default_config = """[globals]
LANGUAGE                = "cs-CZ"
SERVER_URL              = "moje.domena.real"
DEFAULT_JS_CONFIG       = "muj-node-config.default.js"
TEMP_DIRECTORY          = "/tmp/default_node"
BACKUP_DIRECTORY        = "/var/backups"
MIN_WIDTH               = 60

# Pokud vynecháme bude SSL vypnuto, viz default hodnoty v cfg.py
# httpsKey = '/root/.acme.sh/moje.domena.real/moje.domena.real.key'
# httpsCert = '/root/.acme.sh/moje.domena.real/fullchain.cer'
"""
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(default_config)
        print(f"Soubor '{config_file}' byl vytvořen s výchozím obsahem.")
    except OSError as e:
        print(f"Chyba při vytváření config.ini: {e}")
        sys.exit(1)

def setup_sys_apps_symlink():
    """
    1) Ověří existenci `sys_apps.sh` v aktuálním adresáři.
    2) Zkontroluje, zda je spustitelný (`chmod +x`).
    3) Pokud v /usr/local/bin/ neexistuje symlink `sys_apps`,
       vytvoří jej tak, aby cílil na lokální sys_apps.sh.
    """
    script_name = "sys_apps.sh"
    script_path = os.path.join(os.getcwd(), script_name)

    # 1) Ověřit existenci sys_apps.sh
    if not os.path.isfile(script_path):
        print(f"Soubor '{script_name}' neexistuje - nelze vytvořit symlink. Přeskakuji.")
        return

    # 2) Zajistit, aby byl soubor spustitelný
    if not os.access(script_path, os.X_OK):
        print(f"Soubor '{script_name}' není spustitelný. Nastavuji spustitelné oprávnění.")
        try:
            subprocess.run(["chmod", "+x", script_path], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Chyba při nastavování oprávnění u '{script_name}': {e}")
            return

    # 3) Vytvořit symlink, pokud neexistuje
    link_path = "/usr/local/bin/sys_apps"
    if os.path.islink(link_path) or os.path.exists(link_path):
        print(f"Symlink nebo soubor '{link_path}' už existuje. Přeskakuji vytváření.")
    else:
        try:
            subprocess.run(["ln", "-s", script_path, link_path], check=True)
            print(f"Vytvořen symlink: {link_path} -> {script_path}")
            print("Nyní lze skript spustit kdykoliv příkazem 'sys_apps'.")
        except subprocess.CalledProcessError as e:
            print(f"Chyba při vytváření symlinku '{link_path}': {e}")


def main():
    print("===== Spouštím instalační skript =====")

    # 1) Kontrola sudo
    print(" ---- Kontrola sudo ----")
    check_sudo()

    # 1.1) Kontrola, že jsme ve virtuálním prostředí
    print(" ---- Kontrola virtuálního prostředí (venv) ----")
    check_venv()

    # 2) Kontrola, že běžíme z root adresáře aplikace (!run.py)
    print(" ---- Kontrola root adresáře aplikace ----")
    check_run_py_file()

    # 3) Kontrola a instalace 7z
    print(" ---- Kontrola a instalace 7zip ----")
    check_and_install_7zip()

    # 4) Kontrola a instalace Node.js
    print(" ---- Kontrola a instalace Node.js ----")
    check_and_install_node()

    # 5) Inicializace submodulů
    print(" ---- Inicializace git submodulů ----")
    update_submodules()

    # 6) Spuštění instalačního skriptu rq_try_install_requirements.py
    print(" ---- Instalace Python knihoven z requirements.txt ----")
    run_requirements_install()

    # 7) Kontrola a případné vytvoření výchozího config.ini
    print(" ---- Kontrola a vytvoření config.ini ----")
    check_and_create_config()

    # 8) Vytvoření symlinku pro sys_apps.sh
    print(" ---- Vytvoření symlinku pro sys_apps.sh ----")
    setup_sys_apps_symlink()

    print("===== Instalační skript dokončen úspěšně. =====")


if __name__ == "__main__":
    main()
