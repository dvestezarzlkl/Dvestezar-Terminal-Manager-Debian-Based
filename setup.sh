#!/bin/bash

set -e

# Root adresář projektu
APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_ROOT"

VENV_DIR="venv310"
PYTHON_BIN="python3.10"
INSTALL_SCRIPT="venv_install_step.py"
RUN_WRAPPER="run.sh"
PY_ENTRY="venv_run.py"

check_and_install_python310() {
    echo "Kontroluji Python 3.10 a jeho závislosti..."

    if ! command -v $PYTHON_BIN &>/dev/null; then
        echo "Python 3.10 není nainstalován. Přidávám PPA a instaluji..."
        sudo add-apt-repository -y ppa:deadsnakes/ppa
        sudo apt update
        sudo apt install -y python3.10
    else
        echo "Python 3.10 je již nainstalován."
    fi

    # Kontrola a instalace podpůrných balíčků (i při existujícím Pythonu)
    for pkg in python3.10-venv python3.10-distutils python3.10-dev; do
        if ! dpkg -s "$pkg" &>/dev/null; then
            echo "Instaluji chybějící balík: $pkg"
            sudo apt install -y "$pkg"
        fi
    done
}

# Kontrola existence Python 3.10
check_and_install_python310

# Vytvoření virtuálního prostředí
if [ ! -d "$VENV_DIR" ]; then
    echo "Vytvářím virtuální prostředí ($VENV_DIR)..."
    $PYTHON_BIN -m venv "$VENV_DIR"
else
    echo "Virtuální prostředí $VENV_DIR již existuje."
fi

# Aktivace venv a spuštění instalačního Python skriptu
echo "Aktivuji $VENV_DIR a spouštím $INSTALL_SCRIPT..."
source "$VENV_DIR/bin/activate"
python "$INSTALL_SCRIPT"

# Vytvoření run.sh pokud neexistuje
if [ ! -x "$RUN_WRAPPER" ]; then
    echo "Soubor $RUN_WRAPPER neexistuje. Vytvářím..."
    cat > "$RUN_WRAPPER" <<EOF
#!/bin/bash
source "\$(dirname "\$0")/$VENV_DIR/bin/activate"
python3 ./$PY_ENTRY "\$@"
EOF
    chmod +x "$RUN_WRAPPER"
    echo "$RUN_WRAPPER byl vytvořen."
fi

echo "Spouštím $RUN_WRAPPER..."
./"$RUN_WRAPPER"

