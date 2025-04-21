import os,subprocess
from typing import Union,List
from . import cfg
from .c_service_node import c_service_node  
from libs.JBLibs.helper import userExists,getLogger,getUserHome

log = getLogger(__name__)   

def getCfgPath(username: str) -> Union[str,None]:
    """ vrátí cestu k souboru s konfigurací pro uživatele 
    
    Parameters:
        username (str): jméno uživatele
        
    Returns:
        str: cesta k souboru s konfigurací pro uživatele nebo None při chybě
    """
    username=getUserHome(username)
    if username:
        return f'{username}/muj-node-config.js'
    return None

def instanceCheck(username: str) -> bool:
    """testuje existenci instance pro uživatele, tzn existenci adresáře a souboru muj-node-config.js
    
    Parameters:
        username (str): jméno uživatele
        
    Returns:
        bool: True instance v home adresáři existuje, tzn existuje adresář uživatele a soubor muj-node-config.js
    """
    serv=c_service_node(username)
    if serv.ok:
        p=getCfgPath(username)
        if p and os.path.exists(p):
            return True    
    return False

def canInstall(username: str, clean:bool=True) -> bool:
    """testuje zda je možné instalovat instanci pro uživatele, tzn existuje systémový uživatel a má home adresář
    a neexistuje instance pro uživatele tj neexistuje konfigurační soubor muj-node-config.js a service instance
    
    Parameters:
        username (str): jméno uživatele
        clean (bool): pokud:
            - True tak vrátí true jen když neexistuje systémový uživatel, neexistuje home adresář a neexistuje instance
            - False tak vrátí true když existuje systémový uživatel, existuje home adresář a neexistuje instance
        
    Returns:
        bool: True instalace je možná
    """
    ch=userExists(username)
    if ch is None:
        return False
    if clean:
        return ch is False and not os.path.exists(getUserHome(username)) and not instanceCheck(username)
    else:
        return ch is True and os.path.exists(getUserHome(username)) and instanceCheck(username)

def copyKeyToUser(username: str) -> bool:
    """zkopíruje klíč do domovského adresáře uživatele a nastavíme práva pro čtení jen pro uživatele
    
    Parameters:
        username (str): jméno uživatele
        
    Returns:
        bool: True klíč byl zkopírován
    """
    key=cfg.httpsKey    
    userHome=getUserHome(username)
    if not userHome:
        return False
    if not os.path.exists(userHome):
        return False
    if not os.path.exists(key):
        return False
    try:
        subprocess.run(['cp', key, f'{userHome}/ssl.key'], check=True)
        subprocess.run(['chown', f'{username}:users', f'{userHome}/ssl.key'], check=True)
        subprocess.run(['chmod', '600', f'{userHome}/ssl.key'], check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def getHttps(userName:str)->Union[dict,None]:
    """vrací slovník s cestami k certifikátu a klíči pro https
    
    Parameters:
        None
        
    Returns:
        Union[dict,None]: slovník s cestami k certifikátu a klíči pro https  
            nebo None pokud nejsou cesty k certifikátu a klíči nastaveny nebo nejsou soubory k dispozici
            - cert: cesta k certifikátu
            - key: cesta k klíči
    """
    key=getUserHome(userName)
    key=os.path.join(key,'ssl.key')
    if not cfg.httpsCert:
        return None
    if os.path.exists(cfg.httpsCert) and os.path.exists(key):
        return {"cert":cfg.httpsCert,"key":key}
    return None

def getHttpsCfgStr(userName:str)->str:
    """vrátí řetězec s konfigurací pro https
    
    Parameters:
        None
        
    Returns:
        str: řetězec s konfigurací pro https
    """
    x=getHttps(userName)
    if not x:
        if existsSelfSignedCert(userName):
            x=_getSelfignedPaths(userName)
    if x:
        s="https:{"
        s+=f"cert: '{x['cert']}',"
        s+=f"key:  '{x['key']}'"
        s+="}"
        return s
    return "https: null"

def _getSelfignedPaths(userName:str)->Union[dict,None]:
    """vrací slovník s cestami k self-signed certifikátu a klíči pro uživatele
    
    Parameters:
        userName (str): jméno uživatele
        
    Returns:
        Union[dict,None]: slovník s cestami k self-signed certifikátu a klíči pro uživatele nebo None pokud neexistuje certifikát a klíč
            - cert: cesta k certifikátu
            - key: cesta k klíči
    """
    userHome=getUserHome(userName)
    if not userHome:
        return None
    cert=os.path.join(userHome,'node-red-selfsigned.crt')
    key=os.path.join(userHome,'node-red-selfsigned.key')
    return {
        "cert": cert,
        "key": key
    }

def existsSelfSignedCert(userName:str)->bool:
    """testuje zda existuje self-signed certifikát pro uživatele
    
    Parameters:
        userName (str): jméno uživatele
        
    Returns:
        bool: True certifikát existuje
    """
    c=_getSelfignedPaths(userName)
    if not c:
        return False    
    cert=c['cert']
    key=c['key']
    return os.path.exists(cert) and os.path.exists(key)

def generate_certificate(sysUserName: str) -> dict:
    """
    Vygeneruje self-signed certifikát a klíč v domovském adresáři uživatele.

    Parameters:
        sysUserName (str): Uživatelské jméno systému, pro které se má generovat certifikát.

    Returns:
        dict: Slovník s cestami k 'key' a 'cert' souborům, nebo None v případě chyby.
    """
    c=_getSelfignedPaths(sysUserName)
    if not c:
        return None
    
    if existsSelfSignedCert(sysUserName):
        return c
    
    try:        
        # Cesty k certifikátu a klíči v domovském adresáři
        cert_path = c['cert']
        key_path = c['key']

        # Příkaz pro generování certifikátu
        command = [
            "openssl", "req", "-x509", "-nodes", "-days", "365",
            "-newkey", "rsa:2048",
            "-keyout", key_path,
            "-out", cert_path,
            "-subj", f"/C=CZ/ST=YourState/L=YourCity/O=YourCompany/CN=localhost"
        ]

        # Spuštění příkazu
        subprocess.run(command, check=True)
        
        # nastavíme práva na uživatele protože jsou jako root a nastavíme jen pro čtení uživatele
        command = ["chown", f"{sysUserName}:users", cert_path, key_path]
        subprocess.run(command, check=True)
        command = ["chmod", "600", cert_path, key_path]
        subprocess.run(command, check=True)        

        # Návrat slovníku s cestami k certifikátu a klíči
        return {"cert": cert_path, "key": key_path}
    
    except subprocess.CalledProcessError as e:
        log.error("Chyba při generování certifikátu: %s", e)
        return None
    
def deleteSelfSignedCert(userName:str)->bool:
    """smaže self-signed certifikát a klíč pro uživatele
    
    Parameters:
        userName (str): jméno uživatele
        
    Returns:
        bool: True certifikát a klíč byl smazán
    """
    if not existsSelfSignedCert(userName):
        return True
    
    c=_getSelfignedPaths(userName)
    if not c:
        return False
    cert=c['cert']
    key=c['key']
    try:
        os.remove(cert)
        os.remove(key)
        return True
    except FileNotFoundError:
        return False
    
def instanceVersion(username:str)->str:
    """Získá verzi Node-RED z npm list --json."""
    
    if not instanceCheck(username):
        return "N/A"
    
    # Update the service
    user_home=getUserHome(username)
    path=os.path.join(user_home, 'node_instance')
    
    import subprocess, json
    try:
        result = subprocess.run(
            [
                "su",
                "-",
                username,
                "-c",
                f"cd {path} && npm list --depth=0 --json"
            ],
            check=True,
            capture_output=True,
            text=True
        )
        data = json.loads(result.stdout)
        return data['dependencies']['node-red']['version']
    except (subprocess.CalledProcessError, KeyError, json.JSONDecodeError) as e:
        log.error("Chyba při získávání verze Node-RED: %s", e)
        return "N/A"

_ports: List[int] = []
"""Seznam portů obsazených instancemi - toto se generuje až při použití menu """

def ports(toSet:List[int]=None) -> List[int]:
    """
    Vrací nebo nastavuje seznam portů obsazených instancemi
    """
    global _ports
    if not isinstance(toSet, list):
        raise TypeError("toSet must be a list")
    if not all(isinstance(i, int) for i in toSet):
        raise TypeError("all elements in toSet must be int")
    if toSet is not None:
        _ports = toSet
    return _ports
def isPortUsed(port:int) -> bool:
    """Otestuje jestli je pour použitý jinou instancí

    Args:
        port (int): číslo portu

    Returns:
        bool: true pokud je port použitý jinou instancí
    """
    global _ports
    if not isinstance(port, int):
        raise TypeError("port must be int")
    if port in _ports:
        return True
    return False

def createPortInUseJson(data:List, sslStatus:int=0):
    """Vytvoří json soubor do appdir/assets/portInUse.json"""
    import json
    from libs.JBLibs.helper import getAssetsPath
    path=getAssetsPath('portInUse.json')    
    data = {
        'instances': data,
        'url': ( 'http' if sslStatus==0 else 'https' ) + "://" + cfg.SERVER_URL
    }
    with open(path, 'w') as f:
        json.dump(data, f)
        
    # set práva read pro všechny a zápis pro root
    os.chmod(path, 0o644)
    os.chown(path, 0, 0)  # root:root
    
    path2=cfg.INSTANCE_INFO
    # zkopírujeme do path2, pokud je path 2 existující dir, jinak přeskakujeme
    if path2 and os.path.exists(path2) and os.path.isdir(path2):
        path2=os.path.join(path2,'portInUse.json')
        with open(path2, 'w') as f:
            json.dump(data, f)
        os.chmod(path2, 0o644)
        os.chown(path2, 0, 0)  # root:root
    else:
        log.warning("Cíl z configu %s neexistuje nebo není adresář", path2)
    
    log.info("Vytvořen soubor %s s porty %s", path, _ports)
    