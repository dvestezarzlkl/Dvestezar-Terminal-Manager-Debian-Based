from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

import os, shutil,subprocess
from libs.JBLibs.input import get_username, get_input, get_pwd_confirm, get_port,hash_password,confirm,anyKey,select,select_item
from libs.JBLibs.c_menu import c_menu_item,printBlock
from libs.JBLibs.input import confirm
from libs.JBLibs.helper import getAssetsPath,userExists,sanitizeUserName,getUserHome
from . import cfg
from .instanceHelper import canInstall
from .c_service_node import c_service_node

from libs.JBLibs.helper import getLogger
log = getLogger(__name__)

def print_newInstance(sys_name:str="",pwd:str="",title:str="",port:int="",type:int=None,minWidth:int=0) -> int:
    """Tiskne záhlaví
    
    Parameters:
        sys_name (str): jméno systému
        pwd (str): heslo
        title (str): titulek
        port (int): port
        type (int): typ instalace
    
    Returns:
        int: šířka záhlaví
    
    """
    
    os.system('clear')
    
    tp="error"
    if type==0:
        tp=TX_INST_TYPE_0
    elif type==1:
        tp=TX_INST_TYPE_1
    elif type is None:
        tp=TX_INST_TYPE_None    
    
    ln=[
        TX_INST_HD1,
        "=",
        "",
        (TX_INST_HD2,sys_name),
        (TX_INST_HD5,title),
        (TX_INST_HD3,pwd if not pwd else "********"),
        (TX_INST_HD4,port),
        (TX_INST_HD6,tp),
    ]
    
    return printBlock(ln,[],space_between_texts=3,charObal="|",rightTxBrackets="[",min_width=minWidth)

def install_node_instance(selItem:c_menu_item) -> str:
    global cfg
    """
    Install a new Node instance for the specified user.
    """
    # Step 1.1: Check if default node archive exists
    zipExists=os.path.exists(cfg.DEFAULT_NODE_ARCHIVE)
    # if not os.path.exists(cfg.DEFAULT_NODE_ARCHIVE):
    #     return TX_INST_ERR00.format(pth=cfg.DEFAULT_NODE_ARCHIVE)

    srv=c_service_node('')
    if not srv.serviceFileExists():
        return TX_INST_MAKE_ERR11
        
    instType=1
    """0=fresh, 1==copy"""
    
    min_width=cfg.MIN_WIDTH

    log.debug("Starting new node instance installation")
    
    w=max(min_width,print_newInstance(minWidth=min_width))
    
    log.debug("Ask for username")
    username = get_username(TX_INST_INP03,minMessageWidth=w)
    if username == None:
        log.warning("User cancelled the operation")
        return TX_ABORT
    
    # if username exists - error
    if userExists(username):
        log.error(f"User {username} already exists")
        return TX_INST_ERR01.format(username=username)
    
    w=max(min_width,print_newInstance(username,minWidth=min_width))
    
    log.debug("Ask for title")
    title = get_input(f" {TX_INST_INP01}",True,titleNote=TX_INST_INP02,minMessageWidth=w)
    if title == None:
        log.warning("User cancelled the operation")
        return TX_ABORT
    
    if title == "":
        title = username
        
    w=max(min_width,print_newInstance(username,"",title,minWidth=min_width))
    log.debug("Ask for password")
    password = get_pwd_confirm(minMessageWidth=w)
    if password == None:
        log.warning("User cancelled the operation")
        return TX_ABORT

    w=max(min_width,print_newInstance(username,password,title,minWidth=min_width))
    log.debug("Ask for port")
    port = get_port(minMessageWidth=w)
    if port == None:
        log.warning("User cancelled the operation")
        return TX_ABORT

    if zipExists:
        # pokud existuje archiv, tak vytvoříme volbu pro fresh nebo z archivu
        x=select(f"{TX_INST_TYPE_INP}\r  {TX_INST_TYPE_Q}",[
            select_item(TX_INST_TYPE_INP_o1,data=0), # fresh
            select_item(TX_INST_TYPE_INP_o2,data=1), # from archive
        ],min_width)
        if not x.item:
            log.warning("User cancelled the operation")
            return TX_ABORT
        instType=x.item.data
        w=max(x.calcWidth,min_width)
    else:
        # archiv neexistuje, tak jen fresh
        instType=0
    
    w=max(min_width,print_newInstance(username,password,title,port,instType,minWidth=min_width))
    log.debug(f"Selected:: username={username}, title={title}, port={port}, type={instType}")
    
    if not confirm(TX_INST_Q1,minMessageWidth=w):
        log.warning("User cancelled the operation")
        return TX_ABORT

    try:
        log.debug("Creating new node instance")
        ret=__make(username,title,port,password,instType==0)
        log.debug("New node instance created")
    except Exception as e:
        log.error("Error creating new node instance", exc_info=True)
        ret=TX_INST_ERR02.format(username=username)
    
    if ret:
        print("!!! "+TX_ERROR)
        print(ret)
    anyKey(minMessageWidth=w)
    
    return ""
    
def __copyNodeFromArchive(destination_path:str,userChown:str=None) -> str:
    
    if not userExists(userChown):
        return TX_BKG_ERR5_TX.format(name=userChown)
    
   # Extract the node default setup to temporary directory from '/home/defaultNodeInstance.7z'
    defPkgPth=cfg.DEFAULT_NODE_ARCHIVE
    if not os.path.exists(defPkgPth):
        return TX_INST_MAKE_ERR06.format(pth=defPkgPth)
    
    tmpDir=cfg.TEMP_DIRECTORY
    if os.path.exists(tmpDir):
        shutil.rmtree(tmpDir)
    
    print(TX_INST_MAKE01.format(pth=tmpDir))
    command = ['7z', 'x', '-o'+tmpDir, defPkgPth]
    log.debug(f"Running command: {command}")
    try:
        subprocess.run(command, check=True)
        print( TX_INST_MAKE02.format(pth=tmpDir) )
    except subprocess.CalledProcessError as e:
        log.error(f"Error extracting default node setup", exc_info=True)
        return TX_INST_MAKE_ERR07.format(e=e)
    
    tmpDirFrom=os.path.join(tmpDir,'defaultNodeInstance')
    if not os.path.exists(tmpDirFrom):
        return f"Error: Default node setup directory {tmpDirFrom} does not exist."
    
    print(TX_INST_MAKE03.format(pth=destination_path))
    # Move contents from /tmp/default_node/default_node to /home/username = userHome  
    for item in os.listdir(tmpDirFrom):
        s = os.path.join(tmpDirFrom, item)
        d = os.path.join(destination_path, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
            
    print(TX_INST_MAKE04)
    # Remove the temporary directory after moving contents
    shutil.rmtree(tmpDir)
    
    print(TX_INST_MAKE05)
    
    # Set ownership of home directory
    if userChown:
        os.system(f'sudo chown -R {userChown}:users {destination_path}')
        
    return "" # OK
    
def _getFreshNodeInstallation(userName:str)->str:
    """Do home usera vytvoří novou instalaci node-red z aktuálního repa
    
    Parameters:
        userName (str): jméno uživatele
    
    Returns:
        Union[str,None]: None pokud vše proběhlo v pořádku, jinak chybovou hlášku
    """
    
    if not userExists(userName):
        return TX_BKG_ERR5_TX.format(name=userName)
    
    # Cesta do domovského adresáře uživatele a adresáře pro novou instalaci
    user_home=getUserHome(userName)
    
    node_instance_path = os.path.join(user_home, 'node_instance')
    node_cfg_path=os.path.join(user_home,'.node-red')
    if os.path.exists(node_instance_path):
        return TX_FRESH_ERR0.format(path=node_instance_path)
        
    try:
        print(TX_INST_MAKE_STR.format(name=userName))
        # Vytvoření adresáře node_instance, pokud neexistuje
        os.makedirs(node_instance_path, exist_ok=True)
        os.makedirs(node_cfg_path, exist_ok=True)
        os.system(f'sudo chown -R {userName}:users {user_home}')
        
        print(TX_INST_MAKE_INST)
        # Instalace Node-RED do adresáře node_instance
        subprocess.run(
            ['su', '-', userName, '-c', f'cd {node_instance_path} && npm i node-red'],
            check=True
        )
        
    except subprocess.CalledProcessError as e:
        return TX_FRESH_ERR1.format(e=e)
    except Exception as e:
        return TX_FRESH_ERR2.format(e=e)
    
    return "" # OK
    
def __make(username:str,title:str,port:int,pwdPlain:str, fresh:bool=False) -> str:
    """
    Create a new Node instance for the specified user.
    """
    
    log.debug(f"Creating new node instance for user {username}")
    username=sanitizeUserName(username)
    if not username:
        return TX_INST_MAKE_ERR01
    
    if not canInstall(username):
        log.error(f"User {username} cannot install a new instance")
        return TX_INST_MAKE_ERR02
    
    try:
        log.debug(f"Creating user {username}")
        os.system(f'sudo useradd -m {username}')
    except Exception as e:
        log.error(f"Error creating user {username}", exc_info=True)
        return TX_INST_MAKE_ERR03.format(username=username,e=e)
    
    log.debug(f"User {username} created")
    userHome=getUserHome(username)
    if not userHome:
        log.error(f"Error getting home directory for user {username}")
        return TX_INST_MAKE_ERR04
    
    if not os.path.exists(userHome):
        log.error(f"Home directory {userHome} does not exist")
        return TX_INST_MAKE_ERR04
    
    log.debug(f"Checking assets")
    assetMujCfg=getAssetsPath('muj-node-config.default.js')
    assetNodeCfg=getAssetsPath('settings.default.js')
    if not os.path.exists(assetMujCfg):
        log.error(f"Asset {assetMujCfg} does not exist")
        return TX_INST_MAKE_ERR05.format(asset=assetMujCfg)
    if not os.path.exists(assetNodeCfg):
        log.error(f"Asset {assetNodeCfg} does not exist")
        return TX_INST_MAKE_ERR05.format(asset=assetNodeCfg)
    
    if fresh:
        log.debug(f"Creating fresh node installation for user {username}")
        # Create a fresh node installation in the user's home directory to node_instance subdirectory
        if (e := _getFreshNodeInstallation(username)):
            log.error(f"Error creating fresh node installation for user {username}")
            return e
    else:
        log.debug(f"Copying default node setup for user {username}")
        # Copy the default node setup to the user's home directory
        if (e := __copyNodeFromArchive(userHome,username)):
            log.error(f"Error copying default node setup for user {username}")
            return e    
    
    log.debug(f"Updating scripts in user's home directory")
    # Update scripts in user's home directory
    nodeUserConfig=os.path.join(userHome,'muj-node-config.js')
    nodeAppConfig=os.path.join(userHome,'.node-red')
    
    log.debug(f"Creating node configuration files")
    # pokud .node-red addr neexistuje tak vytvoříme
    if not os.path.exists(nodeAppConfig):
        os.makedirs(nodeAppConfig)

    log.debug(f"Copying assets to user's home directory")        
    nodeAppConfig=os.path.join(nodeAppConfig,'settings.js')
    
    print(TX_INST_MAKE06)
    # kopírujeme s assets
    shutil.copy2(assetMujCfg, nodeUserConfig)
    shutil.copy2(assetNodeCfg, nodeAppConfig)
    
    # update dir structure like logs
    try:
        postInstall(username)
    except Exception as e:
        log.error(f"Error creating logs directory for user {username}", exc_info=True)
        return TX_INST_MAKE_ERR12.format(username=username,e=e)
    
    try:
        log.debug(f"Reading configuration files")
        # upravíme konfig
        with open(nodeUserConfig, 'r') as file:
            config_content = file.read()
    
    except Exception as e:
        log.error(f"Error reading configuration file {nodeUserConfig}", exc_info=True)
        return TX_INST_MAKE_ERR08.format(name=nodeUserConfig,e=e)    
    
    try:
        hashed_password = hash_password(pwdPlain)
        log.debug(f"Updating configuration files")
        config_content = config_content.replace('%usr%', username)
        config_content = config_content.replace('%title%', username)
        config_content = config_content.replace('%port%', str(port))
        config_content = config_content.replace('%pwd%', hashed_password)

        with open(nodeUserConfig, 'w') as file:
            log.debug(f"Writing configuration file {nodeUserConfig}")
            file.write(config_content)
            
    except Exception as e:
        log.error(f"Error updating configuration file {nodeUserConfig}", exc_info=True)
        return TX_INST_MAKE_ERR09.format(name=nodeUserConfig,e=e)
    
    log.debug(f"Creating service for user {username}")
    print(TX_INST_MAKE07)
    serv=c_service_node(username)
    err=f"{TX_INST_MAKE_ERR10} {username}"
    if not serv.ok:
        log.error(f"Error creating service for user {username}")
        return f"{err} {TX_INST_MAKE_ERR10_1}."
    
    log.debug(f"Enabling service for user {username}")
    print(TX_INST_MAKE08)
    serv.enable()
    if not serv.enabled():
        log.error(f"Error enabling service for user {username}")
        return f"{err} {TX_INST_MAKE_ERR10_2}."
    
    log.debug(f"Starting service for user {username}")
    print(TX_INST_MAKE09)
    serv.start()
    if not serv.running():
        log.error(f"Error starting service for user {username}")
        return f"{err} {TX_INST_MAKE_ERR10_3}."
    
    log.debug(f"Node instance for user {username} created")
    print(TX_INST_MAKE_OK.format(name=username))
    return ""

def updateSettingsFileForUser(sysUserName:str)->str:
    """Provede update settings.js souboru pro uživatele
    z assets/settings.default.js
    
    Properties:
        sysUserName (str): jméno systémového uživatele
        
    Returns:
        Union[str,None]: None pokud vše proběhlo v pořádku, jinak chybovou hlášku
    """
    if not userExists(sysUserName):
        return TX_BKG_ERR5_TX.format(name=sysUserName)
    path=os.path.join(
        getUserHome(sysUserName),
        '.node-red',
        'settings.js'
    )
    try:
        # new or overwrite
        if os.path.exists(path):
            os.remove(path)
        shutil.copy2(
            getAssetsPath('settings.default.js'),
            path
        )
        os.system(f'chown {sysUserName}:users {path}')
        os.system(f'chmod 600 {path}')
    except Exception as e:
        log.error(f"Error updating settings.js for user {sysUserName}", exc_info=True)
        return TX_BKG_ERR6_TX.format(name=sysUserName)
    return None

def postInstall(sysUserName:str)->str:
    """Vytvoří
    - adresář /home/username/logs/node-red
    - nastaví práva pro uživatele
    """
    # Vytvoření adresáře pro logy
    log.debug("Creating logs directory for node-red")
    try:
        logs_path = os.path.join(getUserHome(sysUserName), 'logs', 'node-red')
        os.makedirs(logs_path, exist_ok=True)
        os.system(f'sudo chown -R {sysUserName}:users {logs_path}')
        os.system(f'sudo chmod 700 {logs_path}')
    except Exception as e:
        log.error(f"Error creating logs directory for user {sysUserName}", exc_info=True)
        return TX_POST_INST_ERR01_TX.format(name=sysUserName)
    
    return None
