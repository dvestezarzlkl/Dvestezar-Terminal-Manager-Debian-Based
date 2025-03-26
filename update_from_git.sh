#!/bin/bash

# Zajištění, že jsme ve správném adresáři
REPO_DIR=$(pwd)
if [ ! -d ".git" ]; then
    echo "Tento adresář není git repozitář!"
    exit 1
fi

# Kontrola, zda má repozitář nastavenou readonly ochranu pro push
if git config --get remote.origin.pushurl | grep -q "no_push"; then
    echo "Repozitář je označen jako readonly. Spouštím aktualizaci ..."
else
    echo "Repozitář není označen jako readonly!"
    echo "Pro nastavení repozitáře na readonly režim spusť např. příkaz:"
    echo "    git config remote.origin.pushurl no_push"    
    exit 1
fi

# Dotaz na uživatele, zda chce provést aktualizaci na poslední verzi z remote
read -p "Chcete aktualizovat repozitář na aktuální verzi? (A/N): " volba
if [[ "$volba" != "A" && "$volba" != "a" ]]; then
    echo "Aktualizace byla zrušena uživatelem."
    exit 0
fi

# Stažení posledních změn z remote
git fetch --all

# Aktualizace submodulů
if [ -f ".gitmodules" ]; then
    echo "Repozitář obsahuje submoduly, aktualizuji i submoduly..."
    git submodule update --init --recursive
fi

# git pull --rebase , pokud budou lokální změny, může nastat problém,
# to u readonly nepředpokládádme a lokální změny ani nechceme, tzn provedeme

# Toto aktualizuje lokální soubory na poslední verzi z remote i kdyby na nich byly lokální změny
git reset --hard origin/main

echo "Repozitář byl úspěšně aktualizován."
