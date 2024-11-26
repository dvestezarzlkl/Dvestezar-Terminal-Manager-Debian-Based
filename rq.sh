#!/bin/bash

# Vyčisti terminál
clear

# Cesta k root adresáři projektu
PROJECT_PATH=$(dirname "$(realpath "$0")")

# Název souboru logu
LOG_FILE="rq.log"

# Zkontroluj, zda je nainstalován pipreqs
LOG="\n"
if ! command -v pipreqs &> /dev/null
then
    LOG+="pipreqs není nainstalován. Prosím, nainstalujte ho pomocí následujícího příkazu:\n"
    LOG+="pip install pipreqs\n"
    echo -e "$LOG" > "$LOG_FILE"
    exit 1
fi

# Zjištění verze Pythonu
PYTHON_VERSION=$(python3 --version 2>&1)

# Použij pipreqs k vygenerování requirements.txt
pipreqs "$PROJECT_PATH" --force --quiet

# Vytvoření logu do proměnné LOG
if [ -f "$PROJECT_PATH/requirements.txt" ]; then
    LOG+="Non-standard, non-project libraries used in the project (pro verzi $PYTHON_VERSION):\n"
    while IFS= read -r line; do
        LOG+="- $line\n"
    done < "$PROJECT_PATH/requirements.txt"
    LOG+="\nChybějící knihovny lze doinstalovat pomocí následujícího příkazu:\n"
    LOG+="> pip install -r requirements.txt\n"
else
    LOG+="Chyba: Nepodařilo se vygenerovat requirements.txt\n"
fi

# Zápis obsahu logu do souboru a jeho zobrazení
LOG+="\n"
echo -e "$LOG" > "$LOG_FILE"
cat "$LOG_FILE"
