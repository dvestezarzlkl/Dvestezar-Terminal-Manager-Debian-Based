from .lng.default import * 
from libs.JBLibs.helper import loadLng,getUserHome
loadLng()

# cspell:ignore userdel
import os, shutil
from .backup import backup_node_instance_for
from .instanceHelper import instanceCheck
from .c_service_node import c_service_node
from libs.JBLibs.input import confirm,anyKey
from libs.JBLibs.term import cls

def remove_node_instance(username: str,ignoreCheckInstance:bool=False, noAnyKey:bool=False) -> str:
    """
    Odstraní adresář uživatele systému, ale nejdřív jej zazálohuje.
    Primárně je určeno pro odstranění uživatelského adresáře s konfigurací node-red.  
    Ale lze použít i pro uživatele bez instance, tzn jakéhokoliv uživatele.    
    
    Parameters:
        username (str): Uživatelské jméno uživatele systému
        ignoreCheckInstance (bool): Ignorovat kontrolu existence instance, pak lze mazat i uživatele bez instance
        noAnyKey (bool): Nečekat na stisk klávesy po dokončení
        
    
    """
    if not ignoreCheckInstance and not instanceCheck(username):
        return TX_REM_ERR1
        
    cls()
    if not confirm(TXT_MENU_INSTN_del_inst0):
        return TX_REM_CANCEL
    
    if confirm(TXT_MENU_INSTN_del_inst1):
        return TX_REM_CANCEL
        
    # Confirm deletion
    confirm_username = input(f"Confirm removal by re-entering the username: ")
    if confirm_username != username:
        return TX_REM_ERR2

    srv=c_service_node(username)
    if not srv.ok and not ignoreCheckInstance:
        return TX_REM_ERR3
    
    if not srv.exists() and not ignoreCheckInstance:
        return TX_REM_ERR4.format(name=username)
    
    # Stop and disable the service
    if srv.running():
        print(TX_REM_TXT0)
        srv.stop()
        if srv.running() and not ignoreCheckInstance:
            return TX_REM_ERR5
    
    if srv.enabled():
        print(TX_REM_TXT1)
        srv.disable()
        if srv.enabled() and not ignoreCheckInstance:
            return TX_REM_ERR6

    print(TX_REM_TXT2)
    print("")
    # Create backup of user's home directory
    backup_node_instance_for(username)

    # Remove the user from the system
    os.system(f'sudo userdel -r {username}')

    # Clean up remaining files in home directory
    p=getUserHome(username)
    if os.path.exists(p):        
        shutil.rmtree(p)

    print(TX_REM_TXT_OK.format(name=username))
    if not noAnyKey:
        anyKey()
    return None