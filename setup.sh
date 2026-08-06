#!/bin/bash

set -e

RUN_APP=true

show_help() {
    cat <<'EOF'
Usage: ./setup.sh [--no-run]

  --no-run    Install/update sys_apps without starting run.sh.
  -h, --help  Show this help.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --no-run)
            RUN_APP=false
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            show_help >&2
            exit 2
            ;;
    esac
done

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

    # Kontrola a instalace systémových runtime balíčků (i při existujícím Pythonu)
    for pkg in python3.10-venv python3.10-distutils python3.10-dev lsof gdisk initramfs-tools; do
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

if [ "$RUN_APP" = true ]; then
    echo "Spouštím $RUN_WRAPPER..."
    ./"$RUN_WRAPPER"
else
    echo "Instalace dokončena, --no-run: aplikace nebude spuštěna."
fi
