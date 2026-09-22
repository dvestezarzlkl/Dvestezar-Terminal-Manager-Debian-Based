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
PYTHON_BIN="${SYS_APPS_PYTHON_BIN:-}"
OPT_PYTHON_ROOT="/opt/python/3.10"
OPT_PYTHON_BIN="$OPT_PYTHON_ROOT/bin/python3.10"
PYTHON_ASSET_URL="${SYS_APPS_PYTHON_ASSET_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20260901/cpython-3.10.21%2B20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz}"
PYTHON_ASSET_SHA256="${SYS_APPS_PYTHON_ASSET_SHA256:-a85d82bf451beea4605cecf0ad3e6cfdab833f146da8f1f82c7b7786f3ff3e3a}"
AUTO_INSTALL_PYTHON310="${SYS_APPS_AUTO_INSTALL_PYTHON310:-true}"
VENV_READY=false
INSTALL_SCRIPT="venv_install_step.py"
RUN_WRAPPER="run.sh"
PY_ENTRY="venv_run.py"

is_usable_python310() {
    local candidate="$1"

    [ -x "$candidate" ] || return 1
    "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        >/dev/null 2>&1
}

apt_package_available() {
    local package="$1"

    apt-cache show "$package" 2>/dev/null \
        | grep -q "^Package: ${package}$"
}

apt_package_installed() {
    local package="$1"

    dpkg-query -W -f='${Status}' "$package" 2>/dev/null \
        | grep -q '^install ok installed$'
}

install_available_packages() {
    local pkg

    if [ "$PYTHON_BIN" != "$OPT_PYTHON_BIN" ]; then
        for pkg in python3.10-venv python3.10-distutils python3.10-dev; do
            if apt_package_installed "$pkg"; then
                echo "Balík $pkg je již nainstalován."
            elif apt_package_available "$pkg"; then
                echo "Instaluji dostupný balík: $pkg"
                sudo apt-get install -y --no-install-recommends "$pkg"
            else
                echo "Balík $pkg není v aktuálních zdrojích APT; přeskočeno."
            fi
        done
    fi

    for pkg in lsof gdisk initramfs-tools; do
        if apt_package_installed "$pkg"; then
            echo "Balík $pkg je již nainstalován."
        elif apt_package_available "$pkg"; then
            echo "Instaluji dostupný balík: $pkg"
            sudo apt-get install -y --no-install-recommends "$pkg"
        else
            echo "Balík $pkg není v aktuálních zdrojích APT; přeskočeno."
        fi
    done
}

install_opt_python310() {
    local machine_arch
    local temp_dir
    local archive
    local stage_dir

    if [ "$AUTO_INSTALL_PYTHON310" != true ]; then
        echo "Automatická instalace izolovaného Pythonu je vypnutá (SYS_APPS_AUTO_INSTALL_PYTHON310)."
        return 1
    fi

    machine_arch="$(uname -m)"
    if [ "$machine_arch" != "x86_64" ] && [ -z "${SYS_APPS_PYTHON_ASSET_URL:-}" ]; then
        echo "Chyba: pro architekturu $machine_arch není nastaven kompatibilní Python asset."
        echo "Nastavte SYS_APPS_PYTHON_ASSET_URL a SYS_APPS_PYTHON_ASSET_SHA256."
        return 1
    fi

    if [ -e "$OPT_PYTHON_ROOT" ]; then
        echo "Chyba: $OPT_PYTHON_ROOT již existuje, ale není funkční Python 3.10+."
        echo "Nebudu jeho obsah přepisovat."
        return 1
    fi

    if ! command -v tar >/dev/null 2>&1 || ! command -v sha256sum >/dev/null 2>&1; then
        echo "Chyba: pro instalaci izolovaného Pythonu chybí tar nebo sha256sum."
        return 1
    fi

    temp_dir="$(mktemp -d /var/tmp/sys_apps-python.XXXXXX)"
    archive="$temp_dir/python.tar.gz"
    stage_dir="$temp_dir/python"

    echo "Stahuji ověřený standalone Python 3.10 do dočasného prostoru..."
    if command -v curl >/dev/null 2>&1; then
        if ! curl -fL --retry 3 --retry-delay 2 --output "$archive" "$PYTHON_ASSET_URL"; then
            echo "Chyba: stažení Python assetu selhalo."
            return 1
        fi
    elif command -v wget >/dev/null 2>&1; then
        if ! wget --tries=3 --output-document="$archive" "$PYTHON_ASSET_URL"; then
            echo "Chyba: stažení Python assetu selhalo."
            return 1
        fi
    else
        echo "Chyba: pro stažení Python assetu chybí curl i wget."
        return 1
    fi

    if ! printf '%s  %s\n' "$PYTHON_ASSET_SHA256" "$archive" | sha256sum -c -; then
        echo "Chyba: SHA-256 Python assetu nesouhlasí."
        return 1
    fi
    install -d -m 0755 "$stage_dir"
    if ! tar -xzf "$archive" --strip-components=1 -C "$stage_dir"; then
        echo "Chyba: rozbalení Python assetu selhalo."
        return 1
    fi

    if ! is_usable_python310 "$stage_dir/bin/python3.10"; then
        echo "Chyba: stažený asset neobsahuje funkční Python 3.10+."
        return 1
    fi

    if ! "$stage_dir/bin/python3.10" -c 'import ssl, sqlite3, venv'; then
        echo "Chyba: staženému Pythonu chybí potřebné moduly ssl/sqlite3/venv."
        return 1
    fi
    install -d -m 0755 "$(dirname "$OPT_PYTHON_ROOT")"
    mv "$stage_dir" "$OPT_PYTHON_ROOT"
    rm -f -- "$archive"
    rmdir "$temp_dir"
    echo "Izolovaný Python byl nainstalován do $OPT_PYTHON_ROOT."
}

select_python310() {
    local candidate=""

    if is_usable_python310 "$APP_ROOT/$VENV_DIR/bin/python"; then
        PYTHON_BIN="$APP_ROOT/$VENV_DIR/bin/python"
        VENV_READY=true
        echo "Používám existující funkční venv: $PYTHON_BIN"
        return 0
    fi

    if [ -n "$PYTHON_BIN" ]; then
        if [[ "$PYTHON_BIN" == */* ]]; then
            candidate="$PYTHON_BIN"
        else
            candidate="$(command -v "$PYTHON_BIN" 2>/dev/null || true)"
        fi

        if is_usable_python310 "$candidate"; then
            PYTHON_BIN="$candidate"
            echo "Používám Python z SYS_APPS_PYTHON_BIN: $PYTHON_BIN"
            return 0
        fi
    fi

    candidate="$(command -v python3.10 2>/dev/null || true)"
    if is_usable_python310 "$candidate"; then
        PYTHON_BIN="$candidate"
        echo "Používám systémově dostupný Python 3.10+: $PYTHON_BIN"
        return 0
    fi

    if is_usable_python310 "$OPT_PYTHON_BIN"; then
        PYTHON_BIN="$OPT_PYTHON_BIN"
        echo "Používám izolovaný Python 3.10+: $PYTHON_BIN"
        return 0
    fi

    if install_opt_python310 && is_usable_python310 "$OPT_PYTHON_BIN"; then
        PYTHON_BIN="$OPT_PYTHON_BIN"
        echo "Používám nově nainstalovaný izolovaný Python 3.10+: $PYTHON_BIN"
        return 0
    fi

    echo "Chyba: nebyl nalezen funkční Python 3.10+."
    echo "Nebudu přidávat PPA ani měnit /usr/bin/python3."
    echo "Připravte izolovaný interpreter v $OPT_PYTHON_BIN,"
    echo "nebo nastavte SYS_APPS_PYTHON_BIN na platný Python 3.10+."
    return 1
}

# Nejprve ověř existující venv/interpreter; žádný systémový Python se nenahrazuje.
select_python310

if [ "$VENV_READY" != true ]; then
    install_available_packages
    if ! "$PYTHON_BIN" -c 'import venv' >/dev/null 2>&1; then
        echo "Chyba: vybraný Python nemá modul venv; virtuální prostředí nelze vytvořit."
        exit 1
    fi
fi

# Vytvoření virtuálního prostředí
if [ "$VENV_READY" != true ]; then
    echo "Vytvářím virtuální prostředí ($VENV_DIR)..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "Virtuální prostředí $VENV_DIR je funkční."
fi

# Aktivace venv a spuštění instalačního Python skriptu
echo "Aktivuji $VENV_DIR a spouštím $INSTALL_SCRIPT..."
source "$VENV_DIR/bin/activate"
"$VENV_DIR/bin/python" "$INSTALL_SCRIPT"

# Vytvoření run.sh pokud neexistuje
if [ ! -x "$RUN_WRAPPER" ]; then
    echo "Soubor $RUN_WRAPPER neexistuje. Vytvářím..."
    cat > "$RUN_WRAPPER" <<EOF
#!/bin/bash
source "\$(dirname "\$0")/$VENV_DIR/bin/activate"
exec "\$(dirname "\$0")/$VENV_DIR/bin/python" "\$(dirname "\$0")/$PY_ENTRY" "\$@"
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
