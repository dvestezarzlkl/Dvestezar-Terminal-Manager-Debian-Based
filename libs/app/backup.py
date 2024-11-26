from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

import os, subprocess
from typing import Union
from datetime import datetime
from . import cfg
from .appHelper import getSysUsers

from libs.JBLibs.helper import getLogger
log = getLogger(__name__)

def getBackupDir(userName:str=None)->Union[str,None]:
    """Vrátí cestu pro zazálohování, pokud cesta z konfigurace neexistuje, vrátí None  
    pokud existuje tak se v ní pokusí vytvořit adresář pro uživatele nebo fullBackup, pokud neexistuje, pokud se nepovede vrací None    
    """        
    p=cfg.BACKUP_DIRECTORY
    if not os.path.exists(p):
        log.error(f"Backup directory {p} does not exist.")
        return None
    p=os.path.join(p,"node_red_instances_backups")
    if userName is None:
        p=os.path.join(p,"fullBackup")
    else:
        userName=str(userName).strip()
        if not userName:
            return None
        p=os.path.join(p,"users",userName)
    if not os.path.exists(p):
        try:
            os.makedirs(p)
        except:
            log.error(f"Error creating backup directory {p}.", exc_info=True)
            return None
    return p

# Helper function to create backup of user's home directory
def _create_backup(username: str) -> str:
    """
    Create a backup of the user's home directory using 7z.
    """
    log.info(f"{TX_BKG_START} {username}...")
    
    p_u=os.path.join('/home',username)
    if not os.path.exists(p_u):
        return TX_BKG_ERR6
    
    p=getBackupDir(username)
    if not p:
        return TX_BKG_ERR7
    print(TX_BKG_TXT00_1.format(name=username))
    print(TX_BKG_TXT01.format(pth=p))
        
    # Vytvoření názvu záložního souboru
    backup_filename = datetime.now().strftime(f"%Y-%m-%d_%H%M%S_{username}_backup.7z")
    backup_path = os.path.join(p, backup_filename)
    print(TX_BKG_TXT02.format(name=backup_filename))
    
    # Spuštění 7z příkazu pro zálohu domovského adresáře uživatele
    command = ['7z', 'a', '-t7z', backup_path, p_u]
    
    try:
        subprocess.run(command, check=True)
        log.info(f"Backup created at {backup_path}.")
    except subprocess.CalledProcessError as e:
        log.error(f"Error during backup for {username}", exc_info=True)
        return f"{TX_BKG_ERR0} {username}: {e}" 
    
    return TX_OK
        
def create_full_backup_7z(users: list[str]) -> str:
    """
    Create a single 7z backup archive containing home directories of all users.
    """
    
    p=getBackupDir()
    if not p:
        return TX_BKG_ERR7
    print(TX_BKG_TXT00.format(num=len(users)))
    print(TX_BKG_TXT01.format(pth=p))
    
    # Název souboru pro zálohu
    backup_filename = datetime.now().strftime(f"%Y-%m-%d_%H%M%S_node_red_instances_fullBackup.7z")
    backup_path = os.path.join(p, backup_filename)
    print(TX_BKG_TXT02.format(name=backup_filename))

    # Připravení příkazu pro 7z
    home_directories = [f"/home/{user}" for user in users if os.path.exists(f"/home/{user}")]
    if not home_directories:
        return TX_BKG_ERR1

    command = ['7z', 'a', '-t7z', backup_path] + home_directories

    # Spuštění 7z příkazu
    log.info(f"Creating full 7z backup at {backup_path}...")
    try:
        subprocess.run(command, check=True)
        log.debug(f"Full 7z backup created successfully at {backup_path}.")
    except subprocess.CalledProcessError as e:
        log.error(f"Error creating 7z backup", exc_info=True)
        return f"{TX_BKG_ERR2}: {e}"
        
    return TX_OK
                
def create_full_backup_for_all_users_7z() -> str:
    """
    Create a full 7z backup for all users returned by getSysUsers().
    """    
    users = getSysUsers()
    if not users:
        return TX_BKG_ERR3
    # využijeme jen jména uživatelů, tzn z elementů jen index 1
    users = [user[1] for user in users]
    
    x=TX_FND+f" {len(users)} {TX_BKG_USER_INCL}"
    log.info(x)
    print(x)
    try:
        x=create_full_backup_7z(users)
        if x!="":
            return x
    except Exception as e:
        log.error(f"Error creating full 7z backup", exc_info=True)
        return f"{TX_BKG_ERR4}: {e}"    
    
    return TX_OK

def backup_node_instance_for(username: str) -> str:
    """
    Backup the Node instance for the specified user.
    """
    # Step 1: Ask for the username
    if username == None:
        return
    
    # Step 2: Check if user exists
    if os.system(f'id -u {username} > /dev/null 2>&1') != 0:
        return TX_BKG_ERR5

    # Step 3: Check if user's home directory exists
    user_home = f'/home/{username}'
    if not os.path.exists(user_home):
        return TX_BKG_ERR6

    # Step 4: Create backup
    return _create_backup(username)