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

def update_instance_node_red(username: str, noAnyKey:bool=False, latest: bool = False) -> str:
    """
    Odstraní adresář uživatele systému, ale nejdřív jej zazálohuje.
    Primárně je určeno pro odstranění uživatelského adresáře s konfigurací node-red.  
    Ale lze použít i pro uživatele bez instance, tzn jakéhokoliv uživatele.    
    
    Parameters:
        username (str): Uživatelské jméno uživatele systému
        noAnyKey (bool): Nečekat na stisk klávesy po dokončení
        
    
    """
    if not instanceCheck(username):
        return TX_REM_ERR1
        
    cls()
    if not confirm(TXT_MENU_INSTN_update_00):
        return TX_REM_CANCEL
    
    srv=c_service_node(username)
    if not srv.ok:
        return TX_REM_ERR3
    
    if not srv.exists():
        return TX_REM_ERR4.format(name=username)
    
    # Stop the service
    if srv.running():
        print(TX_REM_TXT0)
        srv.stop()
        if srv.running():
            return TX_REM_ERR5
    
    print(TX_REM_TXT22)
    print("")
    
    # Create backup of user's home directory
    backup_node_instance_for(username)
    print("")    

    # Update the service
    user_home=getUserHome(username)
    path=os.path.join(user_home, 'node_instance')

    print(TX_UPD_RUNNING_UPD)
    # run update tzn `npm update` pod usereme a path adresářem
    import subprocess
    if latest:
        update_cmd = f"cd {path} && npm install node-red@latest"
    else:
        update_cmd = f"cd {path} && npm update"
    
    subprocess.run(
        [
            "su",
            "-",
            username,
            "-c",
            update_cmd
        ],
        check=True,
    )


    print("")
    print(TX_UPD_RUN_SRV)
    
    # start the service
    srv.start()
    if not srv.running():
        return "... "+TX_INST_MAKE_ERR10_3

    print(TXT_MENU_INSTN_update_ok.format(name=username))
    if not noAnyKey:
        anyKey()
    return None