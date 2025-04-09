# Dvestezar Terminal Manager – Debian-Based  
<!-- cspell:ignore submoduly,submodul,symlinku,pipx,venv,pipreqs,ensurepath,pushurl,utilitku,standartní -->

**v1.3.4**

[ENG](readme_en.md)

[Preview](preview_v1-3-1.mp4)

## Application Description

Dvestezar Terminal Manager is a tool for managing Debian-based systems such as Ubuntu, Raspbian, OrangePi, and other related distributions. It offers a simple terminal menu interface for managing various system functionalities.

This tool is built as a modular framework, which allows easy expansion with new sub-applications and features as needed.

**Current features:**

1. **User Management:**
   - Manage system users, including adding, deleting, and setting passwords.
   - Generate and manage SSH keys with automatic `authorized_keys` handling.
   - Manage user sudo access.

2. **Node-RED Instance Manager:**
   - Create, edit, back up, and delete Node-RED instances.
   - Manage templates for quick deployment.
   - Automatically check and configure services per instance.

### Call for Contributions

The application is designed to be expandable with new modules and sub-applications. If you have ideas for new features or want to add support for a specific service, contributions are welcome!

New modules can be added as sub-applications to the `libs/app/menus/<app_dir>` directory. This structure allows easy integration into the main menu and clean code organization.

## Menu Application Structure

The main menu is built dynamically by scanning `libs/app/menus/<app_dir>`, where `app_dir` must include:

- `menu.py`, which must define:
  - A `_MENU_NAME_` property for the display name in the main menu.
  - A `menu` class that serves as the default entry point when the app is launched from the menu.

### Node-RED Instance Control

A terminal-based Node-RED instance management tool that allows creating, editing, backing up, and deleting user-specific Node-RED instances. Ideal for multi-user setups, each with its own isolated Node-RED service.

#### Key Features:

1. **Instance Setup & Editing:**
   - Create a new instance for a specific system user.
   - Edit existing instances (name, password, port, install type).
   - Set access mode (read-only or full access).

2. **Service Management:**
   - Start, stop, disable individual services.
   - Check instance service status.

3. **Backup & Restore:**
   - Automatically back up all or individual instances.
   - Save configurations and user data.

4. **Service Templates:**
   - Create default service templates for future instances.
   - Remove or uninstall templates.

5. **User Access Control:**
   - Add new users.
   - Manage access to Node-RED dashboards.
   - Set permission levels (read-only / full access).

#### Menus and Navigation:

- **Main Menu** – Overview of instance configs (URL, backup/temp dirs, defaults) + create/edit/backup/template.
- **Edit Menu** – Modify individual instance settings (port, name, access).
- **User Menu** – Add/manage users, access levels, and individual profiles.

#### Installation Types:

- **Fresh** – Clean install from repo, good for new users.
- **Copy** – Restore from archive, useful for cloning or quick re-deploys.

#### Additional Features:

- **Security & Access** – User roles (read-only / full) support auditing or limited access use cases.

The tool simplifies management of multiple Node-RED environments with centralized and user-specific control.

### SSH Groups Manager

This utility manages SSH keys for terminal access. While primarily designed for server admins managing tools like Node-RED, it can be repurposed as needed.

It directly edits the user's `authorized_keys` file and supports:

- Creating/deleting system users (with home backup before deletion).
- Managing sudo/dialout group memberships.
- Managing SSH keys in `~/.ssh/sshManager`:
  - Generate keys
  - Add/remove public keys
  - View private key for user setup

## Key Files

### `!run.py`  
Main application launcher.

### `install.py`  
Initial setup script that installs required software, libraries, submodules, Node.js, zip, etc. Also runs `rq_try_install_requirements.py` for Python dependencies.

> ⚠️ Must be run as **root** or with **sudo**.  
> ⚠️ Node.js will be installed globally as v22.x unless already present in PATH.

### `update_from_git.sh`  
Updates local repo to match Git. Local changes will be discarded. Only runs if repo is in **readonly** mode:

```sh
git config remote.origin.pushurl no_push
```

## Requirements

### Required Files

- `config.ini` – Must be created before the first run (see `cfg.py` for options). Example:

```ini
[globals]
LANGUAGE = "cs-CZ"
SERVER_URL = "my.domain.com"
DEFAULT_NODE_ARCHIVE = "/home/defaultNodeInstance.7z"
DEFAULT_JS_CONFIG = "my-config.js"
TEMP_DIRECTORY = "/tmp/default_node"
BACKUP_DIRECTORY = "/var/backups"
MIN_WIDTH = 60
```

Optional SSL:
```ini
httpsKey = '/path/to/key'
httpsCert = '/path/to/cert'
```

- `/home/defaultNodeInstance.7z` – Optional pre-packed Node-RED instance archive.

### System Requirements

- Ubuntu 22+  
- Python 3.10+  
- Python dependencies: see [requirements.txt](requirements.txt)

Install with:

```sh
pip install -r requirements.txt
```

Or use:

```sh
python3 rq_try_install_requirements.py
```

### APT Applications

Install required tools:

```sh
apt install p7zip-full
```

For Node.js v22:

```sh
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
```

### Git Submodules

This app uses the `JBLibs-python` submodule. After cloning, run:

```sh
git submodule update --init --recursive
```

Or add manually:

```sh
git submodule add -b <branch> https://github.com/dvestezarzlkl/JBLibs-python.git libs/JBLibs
```

### Root Directory Files

- `!run.py` – Main launcher  
- `sys_apps.sh` – Global launch helper script:

```sh
ln -s /path/to/sys_apps.sh /usr/local/bin/sys_apps
```

Then launch with:

```sh
sys_apps
```

- `install.py` – Initial installer  
- `rq.sh` – Auto-generates `requirements.txt` using `pipreqs`

  > Requires `pipx` and `pipreqs`. Install with:
  ```sh
  apt install python3-pip pipx
  pipx install pipreqs
  pipx ensurepath
  ```

- `rq_try_install_requirements.py` – Installs dependencies via APT and pipx  
- `update_from_git.sh` – Git auto-sync script (readonly mode only)  
- `makeRelease.py` – Creates ZIP archive for release (ignores `release/` and cache/logs)

### File Permissions

Make sure the main scripts are executable:

```sh
chmod +x '!run.py' 'sys_apps.sh'
```

