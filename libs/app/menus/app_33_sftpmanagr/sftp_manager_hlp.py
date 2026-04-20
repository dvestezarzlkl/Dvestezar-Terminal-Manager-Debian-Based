from __future__ import annotations

import json5
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple
import tempfile
import time

from libs.JBLibs.helper import getLogger
from libs.JBLibs.sftp.parser import check_config_exists, check_config_valid, uninstallAllUsers as unInstAll, createUserFromJson, getDefaultEtcConfigPath,uninstallUnwantedUsers
from libs.JBLibs.sftp.sambaPoint import smbHelp

log = getLogger("sftpprs")

def load_config(path: Optional[str] = None) -> Tuple[bool,Optional[str],Optional[Dict]]:
    """Load and parse the SFTP manager configuration.

    Args:
        path: Optional alternative path to a configuration file.  If not
            provided, :data:`CONFIG_PATH` is used.

    Returns:
        A tuple ``(success, error_message, config)`` where ``success`` is
        ``True`` if the configuration was loaded successfully, otherwise ``False``.
        If ``success`` is ``False``, ``error_message`` contains a descriptive error message;
        if ``success`` is ``True``, ``error_message`` is ``None``. 
        The ``config`` is a dictionary representing the decoded JSON configuration if loading was successful,
        otherwise ``None``.  If the file does not exist or cannot be parsed, a minimal configuration containing
        an empty ``users`` list is returned and ``success`` is ``True``.
    """
    
    cfg_path = path or getDefaultEtcConfigPath()
    if not os.path.isfile(cfg_path):
        # Return a minimal configuration if no file exists yet.
        return True, None, {"users": []}
    try:
        with open(cfg_path, "r") as fh:
            data = json5.load(fh)        
        if not isinstance(data, dict):
            return True, None, {"users": []}
        # Ensure there is always a users list.
        data.setdefault("users", [])
        return True, None, data
    except Exception as e:
        log.error(f"Error loading config from {cfg_path}: {e}")
        # In the face of any parsing error return an empty config.
        return False, f"Failed to load configuration: {e}", {"users": []}


def save_config(cfg: Dict, path: Optional[str] = None) -> None:
    """Write a configuration dictionary back to disk.

    Args:
        cfg: Configuration dictionary to serialise.
        path: Optional override for the file path.

    The configuration is serialised to JSON using an indentation of
    four spaces.  Comments are not preserved; subsequent calls to
    :func:`load_config` will therefore return a comment‑free structure.
    """
    cfg_path = path or getDefaultEtcConfigPath()
    cfg_dir = os.path.dirname(cfg_path)
    os.makedirs(cfg_dir, exist_ok=True)
    
    # Write to temporary file first
    temp_fd, temp_path = tempfile.mkstemp(dir=cfg_dir, text=True)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as fh:
            json5.dump(cfg, fh, indent=4)
        
        # If original exists, create backup with timestamp
        if os.path.isfile(cfg_path):
            timestamp = int(time.time())
            backup_path = f"{cfg_path}.bak.{timestamp}"
            os.rename(cfg_path, backup_path)
            
            # Clean up old backups (keep last 10)
            backups = sorted([
                f for f in os.listdir(cfg_dir)
                if f.startswith(os.path.basename(cfg_path) + ".bak.")
            ])
            for old_backup in backups[:-9]:
                try:
                    os.remove(os.path.join(cfg_dir, old_backup))
                except OSError:
                    pass
        
        # Atomic rename: move temp file to final location
        os.rename(temp_path, cfg_path)
    except Exception as e:
        log.error(f"Error saving config to {cfg_path}: {e}")
        # Clean up temp file if something went wrong
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def list_users(cfg: Optional[Dict] = None) -> List[Dict]:
    """Return a shallow list of SFTP user objects.

    Each user object is the raw dictionary from the configuration and
    contains keys such as ``sftpuser``, ``sambaVault``, ``sftpmounts``
    and ``sftpcerts``.
    """
    cfg = cfg or load_config()
    return cfg.get("users", [])


def find_user(cfg: Dict, username: str) -> Optional[Dict]:
    """Locate a user dictionary by name.

    Args:
        cfg: The configuration dictionary to search.
        username: The ``sftpuser`` value to look for.

    Returns:
        The user dictionary if found, otherwise ``None``.
    """
    for usr in cfg.get("users", []):
        if usr.get("sftpuser") == username:
            return usr
    return None


def add_user(cfg: Dict, username: str) -> bool:
    """Append a new user to the configuration.

    Args:
        cfg: The configuration dictionary to modify.
        username: Name of the new SFTP user.

    Returns:
        ``True`` if the user was added; ``False`` if a user with the
        same name already exists.
    """
    if find_user(cfg, username):
        return False
    cfg.setdefault("users", []).append({
        "sftpuser": username,
        "sambaVault": True,
        "sftpmounts": {},
        "sftpcerts": [],
    })
    return True


def delete_user(cfg: Dict, username: str) -> bool:
    """Remove a user from the configuration.

    Args:
        cfg: Configuration dictionary to mutate.
        username: Name of the user to remove.

    Returns:
        ``True`` if a user was removed; ``False`` otherwise.
    """
    users = cfg.get("users", [])
    for idx, usr in enumerate(users):
        if usr.get("sftpuser") == username:
            del users[idx]
            return True
    return False


def list_mountpoints(cfg: Dict, username: str) -> List[Tuple[str, str]]:
    """List all mountpoints for a given user.

    Returns:
        A list of tuples ``(label, target_path)``.  If the user does not
        exist, an empty list is returned.
    """
    usr = find_user(cfg, username)
    if not usr:
        return []
    mounts = usr.get("sftpmounts", {})
    return list(mounts.items())

def checkMountpointExists(cfg: Dict, username: str, label: str) -> bool:
    """Check if a mountpoint with the given label exists for the user.
    
    Parameters:
        cfg: Configuration dictionary to search.
        username: Name of the user to check.
        label: The mountpoint label (alias) to look for.
        
    Returns:
        bool: True if a mountpoint with the specified label exists for the user; False otherwise.        
    
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    mounts = usr.get("sftpmounts", {})
    return label in mounts

def checkMountPointPathExists(cfg: Dict, username: str, target_path: str) -> Optional[str]:
    """Check if a mountpoint with the given target path exists for the user.
    
    Parameters:
        cfg: Configuration dictionary to search.
        username: Name of the user to check.
        target_path: The absolute path that the mountpoint points to.
        
    Returns:
        Optional[str]: None pokud nenalezeno, jinak vrací label (alias) mountpointu, který již používá zadanou cestu jako cílovou.
    
    """
    usr = find_user(cfg, username)
    if not usr:
        return None
    mounts = usr.get("sftpmounts", {})
    for label, path in mounts.items():
        if path == target_path:
            return label
    return None

def add_mountpoint(cfg: Dict, username: str, label: str, path: str, readOnly:bool) -> bool:
    """Add or replace a mountpoint for the given user.

    Returns:
        ``True`` if the mountpoint was added/updated; ``False`` if the
        user does not exist.
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    mounts = usr.setdefault("sftpmounts", {})
    mounts[label] = path
    
    pointSet = usr.setdefault("pointsSet", {})
    pointSet[label] = {"rw": not readOnly}
    
    return True

def set_mountpoint_readonly(cfg: Dict, username: str, label: str, readOnly: bool) -> bool:
    """Set the read-only status of an existing mountpoint.

    Returns:
        ``True`` if the mountpoint was updated; ``False`` if the
        user or mountpoint does not exist.
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    pointSet = usr.setdefault("pointsSet", {})
    if label not in pointSet:
        pointSet[label] = {"rw": not readOnly}
    else:
        pointSet[label]["rw"] = not readOnly
    return True

def get_mountpointReadOnlyStatus(cfg: Dict, username: str, label: str) -> Optional[bool]:
    """Get the read-only status of an existing mountpoint.

    Returns:
        ``True`` if the mountpoint is read-only, ``False`` if it is read-write, or ``None`` if the user or mountpoint does not exist.
    """
    usr = find_user(cfg, username)
    if not usr:
        return None
    pointSet = usr.get("pointsSet", {})
    if label not in pointSet:
        return None
    # pokud neexistuje tak je default RW
    return not pointSet[label].get("rw", True)

def delete_mountpoint(cfg: Dict, username: str, label: str) -> bool:
    """Remove a mountpoint from the given user.

    Returns:
        ``True`` if a mountpoint was removed; ``False`` if not found or
        if the user does not exist.
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    mounts = usr.get("sftpmounts", {})
    pointSet = usr.get("pointsSet", {})
    if label in mounts:
        del mounts[label]
        if label in pointSet:
            del pointSet[label]
        return True
    return False


def list_keys(cfg: Dict, username: str) -> List[str]:
    """List public keys (and raw certificates) for the given user."""
    usr = find_user(cfg, username)
    if not usr:
        return []
    return list(usr.get("sftpcerts", []))


def add_key(cfg: Dict, username: str, key: str) -> bool:
    """Append a new public key or certificate to a user.

    Returns:
        ``True`` if the key was added; ``False`` if the user does not
        exist.
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    
    #test jestli tam už není
    keys = usr.get("sftpcerts", [])
    if key in keys:
        return False
    
    usr.setdefault("sftpcerts", []).append(key)
    return True


def delete_key(cfg: Dict, username: str, key: str) -> bool:
    """Remove a key from a user.  Keys are compared as exact strings.

    Returns:
        ``True`` if the key was removed; ``False`` otherwise.
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    keys = usr.get("sftpcerts", [])
    try:
        keys.remove(key)
        return True
    except ValueError:
        return False



def apply_changes(cfg: Optional[Dict] = None, save:bool=False) -> Tuple[bool, Optional[str]]:
    """Apply configuration changes by invoking ``sftpmanager.py``.

    This helper calls the underlying command line script with the
    ``install`` subcommand.  If you installed ``sftpmanager.py``
    system‑wide or inside a virtual environment you may need to adjust
    the script discovery.  The helper attempts to locate the script in
    several common locations and will silently return if no script is
    found.

    Args:
        cfg: Optional configuration to save before applying.  If
            provided, it will be written to disk using :func:`save_config`.
        path: Deprecated - nevyužívá se -  Optional override for the configuration path.  By
            default :data:`CONFIG_PATH` is used.
        save: If True, the configuration will be saved to disk before applying.  If False, the configuration will not be saved and the caller is responsible for ensuring that any changes are persisted.
            
    Returns:
        Tuple[bool, Optional[str]]: První prvek je True pokud se změny úspěšně aplikovaly, jinak False. Druhý prvek je chybová zpráva pokud se změny nepodařilo aplikovat, jinak None.
    """
    
    log.info("Applying configuration changes via sftpmanager ...")
    
    log.info("Checking configuration validity before applying...")
    b,cfg_path = check_config_exists()
    if not b:
        return False, f"Cannot determine JSON input file path: {cfg_path}"
    
    if cfg is None:
        return False, "No configuration provided to apply."
    
    ok,msg = check_config_valid(cfg)
    if not ok:
        return False, f"Configuration validation failed: {msg}"
    
    if save:
        save_config(cfg, cfg_path)
        
    try:
        log.info(f"Applying configuration via sftpmanager lib with config file: {cfg_path}")
        createUserFromJson()
        smbHelp.reloadSystemdDaemon()
        
        log.info("Uninstalling unwanted users who are not in the configuration...")
        uninstallUnwantedUsers()
    except Exception as e:
        return False, f"Failed to apply configuration via sftpmanager.py: {e}"
    
    return True, None

def uninstall_all_users(user:str=None) -> Tuple[bool, Optional[str]]:
    """Uninstall all users by invoking ``sftpmanager.py uninstall`` config není potřeba, ani žádné přepínače, automaticky je to all
    
    Args:
        user: Optional username to uninstall.  If not provided, all users will be uninstalled.
            Pokud je použit user tak se používá argument --user pro sftpmanager.py

    Returns:
        Tuple[bool, Optional[str]]: První prvek je True pokud se změny úspěšně aplikovaly, jinak False. Druhý prvek je chybová zpráva pokud se změny nepodařilo aplikovat, jinak None.
        
    """
    # Potential locations for the sftpmanager.py script.  Adjust these
    # paths if you have installed the script elsewhere.
    
    try:
        if unInstAll():
            return True, None
        else:
            return False, "Failed to uninstall users via sftpmanager.py"
                
    except Exception:
        # Suppress all exceptions – the caller can inspect logs if needed.
        pass
    
    return True, None
