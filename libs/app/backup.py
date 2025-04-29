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

    Parameters:
        userName (str): uživatelské jméno pro které se záloha vytváří, pokud je None, vytvoří se ve fullBackup adresáři
        
    Returns:
        str: cesta k adresáři pro zálohu, pokud se podařilo vytvořit, jinak None

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

def checkBackups(username:str=None) -> int:
    """
    Otestuje zda existují zálohy pro uživatele nebo fullBackup
    Vrátí počet záloh
    
    Parameters:
        username (str): uživatelské jméno pro které se testují zálohy nebo None pro fullBackup
    Returns:
        int: počet záloh
    """
    p=getBackupDir(username)
    
    #pokud neexistuje adresář pro zálohy, vrátíme 0
    if not p:
        return 0
    
    # zkontrolujeme zda existuje adresář
    if not os.path.exists(p):
        return 0
    
    # zkontrolujeme zda existují soubory
    try:
        x=[i for i in os.listdir(p) if i.endswith('.7z')]
        return len(x)
    except Exception as e:
        log.error(f"Error reading backup directory {p}", exc_info=True)
        return 0

def selectBackup(
        username:str=None,
        last:int=15,
        selMessage:str=f"{TX_BKG_FND}\r  {TX_BKG_USER_SEL}"
    ) -> tuple[bool,str|None,str|None]:
    """
    Vybere zálohu z vytvořených záloh, pro uživatele nebo fullBackup
    Vybere je posledních max <last> záloh řazených sestupně podle data
    Vrátí tuple (<ok>(bool),<cesta>|None,<chyba>|None)
    
    Pokud se vrátí ok=False a err=None tak nebylo nic vybráno
    
    Parameters:
        username (str): uživatelské jméno pro které se zobrazí výběr záloh nebo None pro fullBackup
        last (int): maximální počet záloh které se mají zobrazit, default 15, omezeno na číslo 3-50
        selMessage (str): text který se zobrazí jako hláška pro uživatele, default je f"{TX_BKG_FND}\r  {TX_BKG_USER_SEL}"
    Returns:
        tuple: (<ok>,<cesta>,<fileName>,<chyba>)
            ok (bool): True pokud je cesta platná, jinak False
            cesta (str): Pokud je ok true tak platná cesta, jinak None - jedná se o fullPath
            fileName (str): Pokud je ok true tak název souboru, jinak None
            chyba (str): Pokud je ok false tak chybová hláška, jinak None
    """
    p=getBackupDir(username)
    
    #pokud neexistuje adresář pro zálohy, vrátíme None
    if not p:
        return False, None, TX_NO_DIR
    
    # check last - upravíme hranice
    if last<3:
        last=3
    elif last>50:
        last=50
    
    # scan dir a seřazení podle data - jen posledních <last> záloh
    # vytvoříme List select_item objektů : select_item(zobrText, data=filename)
    # select_item je class z helperu
    # zobrText je 'YYYY-MM-DD_HHMMSS - <filename>'
    # data je filename
    from libs.JBLibs.input import select_item,select
    from datetime import datetime
        
    items = []
    try:
        x=[]
        for i in os.listdir(p):
            if i.endswith('.7z'):
                # get filemtime
                date_obj = datetime.fromtimestamp(os.path.getmtime(os.path.join(p, i)))
                x.append([
                    # zobrazený text
                    f"{date_obj.strftime('%Y-%m-%d %H:%M:%S')} - {i}",
                    # filename
                    i,
                    # datum souboru
                    datetime.fromtimestamp(os.path.getmtime(os.path.join(p, i)))
                ])
        # sort
        x.sort(key=lambda x: x[2], reverse=True)
        # vybereme max <last> položek
        x=x[:last]
        # vytvoříme select_item objekty
        for i in x:
            items.append(select_item(i[0], data=i[1]))
        # pokud je prázdný seznam, vrátíme None
        if not items:
            return False, None, None, TX_NO_BACKUPS
    except Exception as e:
        log.error(f"Error reading backup directory {p}", exc_info=True)
        return False, None, None, f"{TX_BKG_ERR8}"
    
    min_width=cfg.MIN_WIDTH
    x = select(selMessage, items, min_width)
    if not x.item:
        log.warning("User cancelled the operation")
        return False, None, None, None
    
    # pokud je vybraná položka, vrátíme její celou cestu
    return True, os.path.join(p, x.item.data), x.item.data, None

def deleteBackup(username:str,backupFileName:str) -> str:
    """
    Smaže zálohu pro uživatele nebo fullBackup
    Vrátí True pokud se podařilo smazat, jinak False
    
    Parameters:
        username (str|None): uživatelské jméno pro které se záloha maže nebo None pro fullBackup
        backupFileName (str): název souboru který se maže
    Returns:
        None: pokud je vše ok
        str: chybová hláška pokud se něco nepodařilo
    """
    p=getBackupDir(username)
    
    #pokud neexistuje adresář pro zálohy, vrátíme None
    if not p:
        return TX_NO_DIR
    
    # zkontrolujeme zda existuje soubor
    if not os.path.exists(os.path.join(p,backupFileName)):
        return TX_BKG_ERR9
    
    # ověříme jestli opravdu smazat
    from libs.JBLibs.input import confirm
    x=confirm(TX_BKG_DEL_Q.format(fileName=backupFileName),True,cfg.MIN_WIDTH)
    if not x:
        log.warning("User cancelled the operation")
        return f"{TX_ABORT}"
    
    # smažeme soubor
    try:
        os.remove(os.path.join(p,backupFileName))
    except Exception as e:
        log.error(f"Error deleting backup file {backupFileName}", exc_info=True)
        return f"{TX_BKG_ERR10}"
    
    return None

def checkBackupIntegrity(username:str,backupFileName:str) -> str:
    """
    Checks the integrity of a backup file for a given user.
    This function verifies the integrity of a backup file using the 7z utility.
    It is assumed that the backup file is located in a user-specific directory.
    Args:
        username (str): The username associated with the backup file.
        backupFileName (str): The name of the backup file to be checked.
    Returns:
        str: A message indicating the result of the integrity check.
        None if the check is successful.
    """
    p = getBackupDir(username)

    if not p:
        return TX_NO_DIR

    backup_path = os.path.join(p, backupFileName)

    if not os.path.exists(backup_path):
        return TX_BKG_ERR9

    try:
        result = subprocess.run(["7z", "t", backup_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return
        else:
            # můžeš si zalogovat chybu: result.stderr nebo result.stdout
            return TX_BKG_ERR11.format(err=result.stderr)
    except FileNotFoundError:
        return TX_BKG_7Z_NOT_FOUND
    except Exception as e:
        return TX_BKG_INT_IRR.format(e=e)
    
def restoreBackupInstance(username: str, backupFileName: str) -> str | None:
    """
    Obnoví Node-RED instanci uživatele ze zálohy .7z (omezeno na instance soubory).
    Zastaví službu, obnoví data, nastaví oprávnění, spustí službu a zkontroluje výsledek.

    Returns:
        None při úspěchu, jinak chybová hláška (str)
    """
    from libs.JBLibs.input import confirm, get_input
    import shutil, tempfile
    from .c_service_node import c_service_node

    backup_dir = getBackupDir(username)
    if not backup_dir:
        return TX_NO_DIR

    backup_path = os.path.join(backup_dir, backupFileName)
    if not os.path.exists(backup_path):
        return TX_BKG_ERR9

    # 1. Trojitý dotaz
    if not confirm(TXT_BKG_MNG_RESTORE_Q1, True, cfg.MIN_WIDTH):
        return TX_ABORT
    if confirm(TXT_BKG_MNG_RESTORE_Q2, True, cfg.MIN_WIDTH):
        return TX_ABORT
    name_check = get_input(TXT_BKG_MNG_RESTORE_Q3)
    if name_check.strip() != username:
        return TXT_BKG_MNG_ERR12

    # print restoring begin
    print(TXT_BKG_MNG_RESTORE_PREPARE.format(usr=username, fnm=backupFileName))

    # 2. Test integrity
    integrity_result = checkBackupIntegrity(username, backupFileName)
    if integrity_result:
        return integrity_result

    # 3. Zjištění prefixu (root adresáře v archivu)
    prefix = get_archive_root_dir(backup_path)
    if not prefix:
        return TXT_BKG_MNG_ERR14

    # 4. Zastavení služby
    print(TXT_BKG_MNG_STOPPING_SERVICE)
    srv = c_service_node(username)
    if srv.running():
        srv.stop()
    if srv.running():
        return TXT_BKG_MNG_ERR_STOP

    # 5. Cílové cesty - pročištění
    home_path = os.path.join("/home", username)
    paths_to_clean = [
        os.path.join(home_path, ".npm"),
        os.path.join(home_path, ".node-red"),
        os.path.join(home_path, "node_instance"),
        os.path.join(home_path, "muj-node-config.js"),
    ]
    for target in paths_to_clean:
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        elif os.path.isfile(target):
            try:
                os.remove(target)
            except:
                pass

    # 6.1. Extrakce pouze relevantních částí
    tmp_dir = tempfile.mkdtemp(prefix="restore_", dir="/tmp")
    
    # 6.2. Rozbal celý archiv do tmp
    try:
        subprocess.run(["7z", "x", backup_path, f"-o{tmp_dir}", "-y"], check=True)
    except subprocess.CalledProcessError as e:
        log.error("Chyba při extrakci archivu", exc_info=True)
        return TXT_BKG_MNG_ERR13.format(err=e)
    
    
    # 6.3. Sestav cílové cesty
    extract_root = os.path.join(tmp_dir, prefix)
    source_paths = {
        ".node-red": os.path.join(extract_root, ".node-red"),
        "node_instance": os.path.join(extract_root, "node_instance"),
        "muj-node-config.js": os.path.join(extract_root, "muj-node-config.js")
    }

    home_path = os.path.join("/home", username)
    target_paths = {
        ".node-red": os.path.join(home_path, ".node-red"),
        "node_instance": os.path.join(home_path, "node_instance"),
        "muj-node-config.js": os.path.join(home_path, "muj-node-config.js")
    }

    # 6.4. Kopírování
    for name, src in source_paths.items():
        dst = target_paths[name]
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        elif os.path.isfile(src):
            shutil.copy2(src, dst)

    # 7. Smazat tmp
    shutil.rmtree(tmp_dir)

    # 7. Vlastnictví
    try:
        subprocess.run(
            ["chown", "-R", f"{username}:users", home_path],
            check=True
        )
    except subprocess.CalledProcessError as e:
        log.error(f"Chyba při nastavování oprávnění pro {username}", exc_info=True)
        return TXT_BKG_MNG_ERR15.format(err=e)

    # 8. Spuštění služby
    print(TXT_BKG_MNG_STARTING_SERVICE)
    srv.start()
    if not srv.running():
        return TXT_BKG_MNG_ERR_START

    # 9. Hotovo
    print(TXT_BKG_MNG_OK_RESTORED)
    return None


def get_archive_root_dir(archive_path: str) -> str | None:
    """
    Zjistí root adresář uvnitř 7z archivu.
    Validuje, že kořenový adresář odpovídá názvu instance ve jménu souboru.
    """
    try:
        result = subprocess.run(["7z", "l", archive_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return None

        lines = result.stdout.splitlines()

        try:
            start_idx = lines.index(next(l for l in lines if l.startswith("----------")))
        except StopIteration:
            return None

        files = lines[start_idx + 1:]
        paths = [line.split()[-1] for line in files if "/" in line]

        if not paths:
            return None

        first_path = paths[0]
        parts = first_path.split("/")

        if len(parts) < 2:
            return None

        root_dir = parts[0]

        # Validace – root adresář musí být ve jménu archivu
        archive_name = os.path.basename(archive_path).lower()
        if root_dir.lower() not in archive_name:
            return None

        return root_dir

    except Exception as e:
        log.error(f"Chyba při získávání root adresáře z archivu {archive_path}", exc_info=True)
        return None
