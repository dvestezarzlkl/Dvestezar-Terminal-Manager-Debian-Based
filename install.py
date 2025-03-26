#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# run as : sudo python3 install.py

import os
import sys
import subprocess

# not tested yet

def check_sudo()->None:
    """Ověří, zda je skript spuštěn s právy roota (sudo)."""
    if os.geteuid() != 0:
        print("Chyba: Skript není spuštěn s právy roota (sudo). Ukončuji.")
        sys.exit(1)


def check_run_py_file()->None:
    """Zkontroluje, zda v aktuálním adresáři existuje soubor !run.py,
       čímž ověří, že jsme ve správném (root) adresáři projektu."""
    file_name = "!run.py"
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
    except subprocess.CalledProcessError:
        # Pokud node není nainstalován (nebo neodpoví)
        print("Node.js není nainstalován. Pokusím se jej nainstalovat (LTS 22)...")
        # Instalace Node.js LTS 22
        try:
            # 1) přidání repozitáře
            curl_cmd = ["bash", "-c",
                        "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -"]
            subprocess.run(curl_cmd, shell=False, check=True)

            # 2) instalace nodejs
            install_cmd = ["apt-get", "install", "-y", "nodejs"]
            subprocess.run(install_cmd, check=True)
            print("Node.js úspěšně nainstalován.")
        except subprocess.CalledProcessError as e:
            print("Chyba při instalaci Node.js:\n", e)
            sys.exit(1)


def update_submodules():
    """Provede init a update všech git submodulů včetně rekurzivních."""
    print("Provádím git submodule update --init --recursive...")
    cmd = ["git", "submodule", "update", "--init", "--recursive"]
    try:
        subprocess.run(cmd, check=True)
        print("Submoduly úspěšně inicializovány/aktualizovány.")
    except subprocess.CalledProcessError as e:
        print("Chyba při inicializaci/aktualizaci submodulů:\n", e)
        sys.exit(1)


def run_requirements_install_script():
    """Spustí skript rq_try_install_requirements.py, pokud existuje."""
    script_name = "rq_try_install_requirements.py"
    if os.path.exists(script_name):
        print(f"Spouštím skript {script_name} pro instalaci Python knihoven...")
        try:
            # Spuštění "python3 rq_try_install_requirements.py"
            subprocess.run(["python3", script_name], check=True)
            print("Instalační skript knihoven byl úspěšně proveden.")
        except subprocess.CalledProcessError as e:
            print("Chyba při spouštění instalačního skriptu knihoven:\n", e)
            sys.exit(1)
    else:
        print(f"Skript {script_name} neexistuje, přeskočeno.")


def check_and_create_config():
    """Ověří, zda existuje soubor config.ini, a pokud ne, vytvoří ho s výchozím obsahem."""
    config_file = "config.ini"
    if os.path.exists(config_file):
        print(f"Soubor '{config_file}' existuje, není nutné vytvářet.")
        return

    print(f"Soubor '{config_file}' neexistuje. Vytvářím defaultní config.ini...")
    # Zde dejte výchozí nastavení, jaké potřebujete:
    default_config = """[globals]
LANGUAGE                = "cs-CZ"
SERVER_URL              = "moje.domena.real"
DEFAULT_NODE_ARCHIVE    = "/home/defaultNodeInstance.7z"
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


def main():
    print("===== Spouštím instalační skript =====")

    # 1) Kontrola sudo
    check_sudo()

    # 2) Kontrola, že běžíme z root adresáře aplikace (!run.py)
    check_run_py_file()

    # 3) Kontrola a instalace 7z
    check_and_install_7zip()

    # 4) Kontrola a instalace Node.js
    check_and_install_node()

    # 5) Inicializace submodulů
    update_submodules()

    # 6) Spuštění instalačního skriptu rq_try_install_requirements.py
    run_requirements_install_script()

    # 7) Kontrola a případné vytvoření výchozího config.ini
    check_and_create_config()

    print("===== Instalační skript dokončen úspěšně. =====")


if __name__ == "__main__":
    main()
