#!/usr/bin/env python3

import os
import subprocess
import logging
import argparse

# Cesta k root adresáři projektu
PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))


# Formát logu
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Nastavení loggeru
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File handler (píše do .log souboru)
# Název souboru logu je stejný jako název skriptu s příponou .log
log_file = os.path.splitext(os.path.basename(__file__))[0] + ".log"
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logger.info(" ")
logger.info("*" * 80)
logger.info("Pokus o instalaci knihoven...")

def main(show_console: bool):
    
    # Pokud chceme zobrazovat logy i na konzoli, přidáme StreamHandler
    if show_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
            
    # Pokud existuje requirements.txt, zpracuj ho
    requirements_path = os.path.join(PROJECT_PATH, "requirements.txt")
    err=[]
    if os.path.isfile(requirements_path):
        logger.info("Non-standard, non-project libraries used in the project:")
        with open(requirements_path, "r") as requirements_file:
            for line in requirements_file:
                package = line.split('=')[0].strip()
                package2 = None
                if package.startswith("python_"):
                    package2 = package.replace("python_", "", 1)
                
                logger.info(f"--- {line.strip()} ---")

                # Pokus o instalaci balíčku pomocí apt
                logger.info(f"Pokus o instalaci '{package}' pomocí apt...")
                result = subprocess.run(["sudo", "apt", "install", "-y", f"python3-{package}"], capture_output=True)
                if result.returncode == 0:
                    logger.info(f"OK: Balíček '{package}' byl úspěšně nainstalován pomocí apt.")
                    continue
                
                if package2:
                    logger.warning(f"Nepodařilo se nainstalovat balíček {package} pomocí apt. Pokus o instalaci {package2} pomocí apt...")
                    logger.info(f"Pokus o instalaci bez prefixu 'python_' {package2} pomocí apt...")
                    result = subprocess.run(["sudo", "apt", "install", "-y", f"python3-{package2}"], capture_output=True)
                    if result.returncode == 0:
                        logger.info(f"OK: Balíček '{package2}' byl úspěšně nainstalován pomocí apt.")
                        continue
                
                # Pokud instalace pomocí apt selže, pokus o instalaci pomocí pipx
                logger.warning(f"Nepodařilo se nainstalovat balíček {package} pomocí apt. Pokus o instalaci pomocí pipx...")
                result = subprocess.run(["pipx", "install", package], capture_output=True)
                if result.returncode == 0:
                    logger.info(f"OK: Balíček '{package}' byl úspěšně nainstalován pomocí pipx.")
                    continue
                
                # Pokud instalace selže a název balíčku má prefix "python_", zkusit znovu bez prefixu
                if package2:
                    logger.warning(f"Nepodařilo se nainstalovat balíček {package} pomocí pipx. Pokus o instalaci {package2} pomocí pipx...")
                    result = subprocess.run(["pipx", "install", package2], capture_output=True)
                    if result.returncode == 0:
                        logger.info(f"OK: Balíček '{package2}' byl úspěšně nainstalován pomocí pipx.")
                        continue
                    
                logger.error(f"Nepodařilo se nainstalovat balíček {package} pomocí apt ani pipx.")
                err.append(package)
                
        if err:
            logger.error(f"Chyba: Nepodařilo se nainstalovat následující balíčky: {', '.join(err)}")
        else:
            logger.info("SUCCESS: Všechny balíčky byly úspěšně nainstalovány.")    
    else:
        logger.error("Chyba: Nepodařilo se najít requirements.txt")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instalace requirements se záznamem do logu.")
    parser.add_argument("--console", action="store_true",
                        help="Zobrazit logy i na konzoli (kromě souboru).")
    args = parser.parse_args()

    main(show_console=args.console)