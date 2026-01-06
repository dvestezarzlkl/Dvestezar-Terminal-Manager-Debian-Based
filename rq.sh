#!/bin/bash
set -euo pipefail
clear

PROJECT_PATH="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
LOG_FILE="$PROJECT_PATH/rq.log"
VENV_DIR="$PROJECT_PATH/venv310"
REQ_OUT="$PROJECT_PATH/requirements.txt"

LOG=$'\n'

log_and_exit() {
  LOG+="$1"$'\n'
  echo -e "$LOG" > "$LOG_FILE"
  cat "$LOG_FILE"
  exit 1
}

# kontrola venv
if [[ ! -d "$VENV_DIR" ]]; then
  log_and_exit "Chyba: venv310 neexistuje v $PROJECT_PATH"
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  log_and_exit "Chyba: $VENV_DIR/bin/python není spustitelný"
fi

# aktivace venv
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

PY_VER="$(python --version 2>&1)"
LOG+="Virtuální prostředí aktivní: $VIRTUAL_ENV"$'\n'
LOG+="Python: $PY_VER"$'\n'

# vygeneruj requirements z reálného env
# (pip-tools/pip/setuptools/wheel vyhoď - nejsou to runtime deps)
pip freeze | grep -Ev '^(pip|setuptools|wheel)==(.*)$' > "$REQ_OUT"

LOG+=$'\n'"Vygenerováno requirements.txt z aktuálního venv (pip freeze)."$'\n'
LOG+=$'\n'"Obsah requirements.txt:"$'\n'

while IFS= read -r line; do
  LOG+="- $line"$'\n'
done < "$REQ_OUT"

LOG+=$'\n'"Instalace:"$'\n'
LOG+="> pip install -r requirements.txt"$'\n'

echo -e "$LOG" > "$LOG_FILE"
cat "$LOG_FILE"
