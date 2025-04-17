#!/bin/bash

# Kontrola, zda je skript spuštěn přes symlink
if [ ! -L "${BASH_SOURCE[0]}" ]; then
    echo
    echo "Tento skript je určen pouze pro spuštění přes symlink." >&2
    echo
    exit 1
fi

# Zjistí skutečný adresář, kde je skript (i pokud je spuštěn přes symlink)
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# Přesune se do adresáře, kde je skript
cd "$SCRIPT_DIR"

# Spustí app
./run.sh "$@"
