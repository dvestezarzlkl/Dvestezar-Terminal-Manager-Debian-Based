# Dvestezar Terminal Manager – Debian-Based
<!-- cspell:ignore submoduly,submodul,symlinku,pipx,venv,pipreqs,ensurepath,pushurl,utilitku,standartní -->

v1.9.3

[CZ](readme.md)

[Preview](preview_v1-3-1.mp4)

## Application Description

Dvestezar Terminal Manager is a terminal-based administration tool for Debian-based systems such as Ubuntu, Debian, Raspbian, or Orange Pi. The application is built around a modular menu system where individual features are loaded as standalone plugins from `libs/app/menus/app_*`.

The main menu automatically loads every plugin that contains a `menu.py` entry point, so the project can be extended without modifying the main menu implementation.

## Current Menu Plugins

### Disk manager

- list physical disks, partitions, and image files
- mount and unmount partitions or `.img` files through loop devices
- validate and manage mountpoints
- perform disk and partition operations including format, shrink, and expand
- support backup-related filesystem work

### Swap manager

- create new SWAP image files
- enable, disable, and manage existing SWAP files
- display RAM and SWAP usage including active SWAP devices
- show processes currently using SWAP
- resize SWAP images according to system state

### Node-RED manager

- install new Node-RED instances for system users
- edit existing instances including title, port, and dashboard users
- start, stop, restart, enable, and disable instance systemd services
- create instance backups, full backups, list backups, and verify backup integrity
- manage service templates, sudoers rules, and HTTPS certificates
- run an instance directly as an application, including SAFE MODE
- manage global Node.js and npm installation, including LTS update and uninstall

### SSH manager

- list relevant system users for SSH administration
- create a new system user
- manage user SSH keys and `authorized_keys`
- change password, sudo privileges, and `dialout` group membership
- open a dedicated submenu for a selected user

### SFTP manager

- manage SFTP users defined in configuration
- create and delete SFTP users
- add and remove mountpoints inside the SFTP jail
- manage public keys and display them in readable form
- toggle mountpoints to read-only mode
- save and apply system changes only when explicitly confirmed

See also [sftp_manager_readme.md](sftp_manager_readme.md).

### UART tester

- detect relevant serial ports through sysfs filtering
- run transmitter, receiver, and saved test-command modes
- configure port, baudrate, parity, data bits, stop bits, and timeout
- persist UART settings and reload them on next start
- generate test commands in the form `test{len}n{repeat}`
- configure test text length and repeat count directly from the menu

See also [uart_tester.md](uart_tester.md).

### ZLKL plugin

- `app_50_zlkl` currently contains an external or proprietary module snapshot
- because it does not provide `menu.py`, it is not loaded into the main application menu

## What The Application Covers

- a unified terminal menu for multiple administrative tools
- storage, swap, Node-RED, SSH, SFTP, and UART testing workflows in one place
- persisted configuration for selected plugins
- localized UI texts using `lng` files
- simple extension through additional menu plugins

### Call for Contributions

The application is designed to be expandable with new modules and sub-applications. If you have ideas for new features or want to add support for a specific service, contributions are welcome!

New modules can be added as sub-applications to the `libs/app/menus/<app_dir>` directory. This structure allows easy integration into the main menu and clean code organization.

## Menu Application Structure

The main menu is built dynamically by scanning `libs/app/menus/<app_dir>`, where `app_dir` must include:

- `menu.py`, which must define:
  - A `_MENU_NAME_` property for the display name in the main menu.
  - A `menu` class that serves as the default entry point when the app is launched from the menu.

## Key Files

### `run.sh`

Main launcher script. It is created or completed by `setup.sh` and used to start the application.

### `setup.sh`

Initial setup script that installs required packages, Python environment dependencies, submodules, Node.js, and other runtime tools.

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

- `sys_apps.sh` – Global launch helper script:

```sh
ln -s /path/to/sys_apps.sh /usr/local/bin/sys_apps
```

Then launch with:

```sh
sys_apps
```

- `rq.sh` – Auto-generates `requirements.txt` using `pipreqs`

  > Requires `pipx` and `pipreqs`. Install with:
  ```sh
  apt install python3-pip pipx
  pipx install pipreqs
  pipx ensurepath
  ```

- `update_from_git.sh` – Git auto-sync script (readonly mode only)  
- `makeRelease.py` – Creates ZIP archive for release (ignores `release/` and cache/logs)

### File Permissions

Make sure the main scripts are executable:

```sh
chmod +x 'setup.sh' 'sys_apps.sh' 'run.sh' 'update_from_git.sh'
```

