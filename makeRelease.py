#!/usr/bin/env python3

import os
import zipfile
import re
from datetime import datetime
from libs.app import cfg

EXCLUDED_DIRS = {"__pycache__","release"}
EXCLUDED_FILES = {"config.ini", "makeRelease.py"}
EXCLUDED_EXTENSIONS = {".log"}

v=cfg.VERSION.replace(".","-")
#d=datetime.now().strftime("%Y-%m-%d-%H%M")
d=datetime.now().strftime("%Y-%m-%d")
OUTPUT_ZIP = f"{d}_release-clean_v{v}.zip"

LOG_PATTERN = re.compile(r".*\.log(\.\d+)?$")

def should_exclude(file_path):
    # Vyloučit tečkované adresáře a specifické adresáře
    if any(part.startswith('.') for part in file_path.split(os.sep)):
        return True
    # Vyloučit soubory podle jména
    if os.path.basename(file_path) in EXCLUDED_FILES:
        return True
    # Vyloučit soubory podle přípony nebo logovací soubory s čísly
    if any(file_path.endswith(ext) for ext in EXCLUDED_EXTENSIONS) or LOG_PATTERN.match(file_path):
        return True
    return False

def create_clean_archive(root_dir, output_zip):
    # Smazat existující ZIP soubor, pokud existuje
    if os.path.exists(output_zip):
        os.remove(output_zip)

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for foldername, subfolders, filenames in os.walk(root_dir):
            # Odstranit všechny složky, které jsou v seznamu vyloučených
            subfolders[:] = [d for d in subfolders if d not in EXCLUDED_DIRS and not d.startswith('.')]

            for filename in filenames:
                file_path = os.path.join(foldername, filename)
                if should_exclude(file_path):
                    continue
                # Přidat soubor do ZIP archivu s relativní cestou
                relative_path = os.path.relpath(file_path, root_dir)
                zipf.write(file_path, relative_path)

def main():
    root_dir = os.getcwd()  # Použij aktuální adresář jako kořen
    
    bkg_to = os.path.join(root_dir, "release")
    os.makedirs(bkg_to, exist_ok=True )
    
    o = os.path.join(bkg_to, OUTPUT_ZIP)
    create_clean_archive(root_dir, o)
    print(f"Archiv '{o}' byl úspěšně vytvořen.")

if __name__ == "__main__":
    main()
