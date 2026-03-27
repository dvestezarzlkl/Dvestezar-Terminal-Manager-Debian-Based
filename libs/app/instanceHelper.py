from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

import os,subprocess,json, re, shutil
from typing import Union,List,Optional
from . import cfg
from .c_service_node import c_service_node  
from libs.JBLibs.helper import userExists,getLogger,getUserHome

log = getLogger(__name__)   

LATEST_LTS_MAJOR = 22

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
    """testuje existenci instance node-red pro uživatele, tzn existenci adresáře a souboru muj-node-config.js
    
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
    pth=getUserHome(username) or ""
    if clean:
        return ch is False and not os.path.exists(pth) and not instanceCheck(username)
    else:
        return ch is True and os.path.exists(pth) and instanceCheck(username)

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
    
def instanceVersionNpm(username:str)->str:
    """Získá verzi Node-RED z npm list --json.
    hodně pomalé
    """
    
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

def instanceVersion_OLD(username: str) -> str:
    """Získá verzi Node-RED přímo z red.js
    
    Deprecated:
    verze node-red 3 neumí --version, tak selže (node-red se spustí místo vypsání verze) a nenačte se pak menu
    vyřazeno 2026-03-26
    
    Parameters:
        username (str): jméno uživatele
    Returns:
        str: verze Node-RED nebo "N/A" při chybě
    """
    
    if not instanceCheck(username):
        return "N/A"
    user_home = getUserHome(username)    
    path = os.path.join(user_home, 'node_instance','node_modules','node-red')
    try:
        result = subprocess.run(
            ["su", "-", username, "-c", f"cd {path} && node red.js --version"],
            check=True, capture_output=True, text=True
        )
        # pak z result.stdout vyparsovat řetězec „Node-RED v4.1.1“ → extrahovat „4.1.1“
        if result.stdout:
            for line in result.stdout.splitlines():
                if line.strip().startswith("Node-RED"):
                    return line.split("v")[1].strip()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.error("Chyba při čtení package.json: %s", e)
    return "N/A"

_ports: List[int] = []
"""Seznam portů obsazených instancemi - toto se generuje až při použití menu """


def instanceVersion(username: str) -> str:
    """Vrátí verzi Node-RED z package.json v uživatelské instanci.
    Verze z 2026-03-26

    Parameters:
        username (str): Jméno uživatele.

    Returns:
        str: Verze Node-RED, nebo "N/A" při chybě.
    """
    if not instanceCheck(username):
        return "N/A"

    user_home = getUserHome(username)
    package_json = os.path.join(
        user_home,
        "node_instance",
        "node_modules",
        "node-red",
        "package.json"
    )

    try:
        with open(package_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        version = data.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()

    except (FileNotFoundError, PermissionError, json.JSONDecodeError, OSError) as e:
        log.error("Chyba při čtení verze Node-RED z %s: %s", package_json, e)

    return "N/A"

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
        if cfg.INSTANCE_INFO_COPY_PHP==True:
            x=copyPHPToo(path2)
            if not x:
                log.error("Kopírování PHP scriptu do %s selhalo", path2)
            else:
                log.info("Zkopírován portInUse.json do %s", path2)
    else:
        log.warning("Cíl z configu %s neexistuje nebo není adresář", path2)
    
    log.info("Vytvořen soubor %s s porty %s", path, _ports)    

def copyPHPToo(jsonPath):
    """
    Zkopíruje portInUse.json do assets/php/node_red_instances.php
    
    V PHP scriptu budou nastaveny proměnné: 
    -   '%site_name%' na cfg.SITE_NAME
    -   '%appver%' na cfg.VERSION
    -   '%cidrs% na cfg.PHP_SCRIPT_CIDRS
    """
    import shutil
    from libs.JBLibs.helper import getAssetsPath
    phpPath=getAssetsPath('node_red_instances.php')
    if not os.path.exists(phpPath):
        log.error("PHP script %s neexistuje", phpPath)
        return False
    
    if not os.path.exists(jsonPath):
        log.error("JSON soubor %s neexistuje", jsonPath)
        return False
    # extrahujeme dir z cesty jsonPath
    phpDir=os.path.dirname(jsonPath)
    phpName=os.path.basename(phpPath)
    if cfg.PHP_SCRIPT_RENAME:
        phpName = f"{cfg.PHP_SCRIPT_RENAME}.php"
    
    # načteme source content z disku !!!!!!
    content = ""
    with open(phpPath, 'r') as f:
        content = f.read()
        
    # test cidrs, musí být string, dekódujeme json, pokud ok a výsledek je pole, tak sestavíme json a použijeme ho
    import json,time
    cidrs= cfg.PHP_SCRIPT_CIDRS
    if isinstance(cidrs, str):
        try:
            cidrs = json.loads(cidrs)
        except json.JSONDecodeError:
            log.error("Chyba při dekódování JSON pro CIDRs: %s", cidrs)
            return False
    if not isinstance(cidrs, list):
        log.error("CIDRs musí být seznam, ale je %s", type(cidrs))
        return False
    if not all(isinstance(i, str) for i in cidrs):
        log.error("Všechny položky v CIDRs musí být string, ale jsou %s", [type(i) for i in cidrs])
        return False
    # sestavíme json string
    cidrs_json = json.dumps(cidrs)
        
    # nahrazení proměnných
    content = content.replace('%site_name%', cfg.SITE_NAME)
    content = content.replace('%appver%', cfg.VERSION)
    content = content.replace('%cidrs%', cidrs_json)
    content = content.replace('%genAt%', str(int(time.time())))  # přidáme čas generování, pro případné ladění
    # zkopírujeme do assets/php/node_red_instances.php
    phpPath=os.path.join(phpDir, phpName)
    with open(phpPath, 'w') as f:
        f.write(content)
    
    # nastavíme práva
    os.chmod(phpPath, 0o644)
    os.chown(phpPath, 0, 0)  # root:root
    
    log.info("Zkopírován portInUse.json do %s", phpPath)
    return True
    
def writeSudoersFile(filename:str, content:str) -> bool:
    """Vytvoří nebo přepíše sudoers soubor s daným názvem a obsahem
    
    Parameters:
        filename (str): jméno sudoers souboru bez cesty
        content (str): obsah sudoers souboru
        
    Returns:
        bool: True soubor byl vytvořen nebo přepsán
    """
    path=f'/etc/sudoers.d/{filename}'
    try:
        with open(path, 'w') as f:
            f.write(content)
        os.chmod(path, 0o440)  # nastavíme práva 440
        return True
    except Exception as e:
        log.error("Chyba při zápisu sudoers souboru %s: %s", path, e)
        return False
    
def update_sudoers_file() -> Union[str,None]:
    """Zjistí list instancí, vytvoří seznam userů pro instance a nakonec vytvoří
    soubor v sudoers `node-red-instances` s právy pro restart služby bez zadání hesla.
    
    Samozřejmostí je jen právo na restart, protože když nepoběží tak se sám nespustí a obráceně
    je nežádoucí se vypnout
    
    Returns:
        str: Pokud nastala chyba
        None: pokud je vše OK
    
    """
    from libs.app.appHelper import getSysUsers
    
    # zjistíme kde je systemctl
    ctlPath=subprocess.run(['which','systemctl'],capture_output=True,text=True)
    if ctlPath.returncode!=0:
        m="Nelze najít systemctl"
        log.error(m)
        return m
    ctlPath=ctlPath.stdout.strip()
    if not os.path.exists(ctlPath):
        m="Cesta k systemctl neexistuje"
        log.error(m)
        return m
    
    services=[]
    for item in getSysUsers():
        u=item[1]
        try:
            serv=c_service_node(u)
            if serv.exists():
                services.append((u,serv.fullName)) # username,fullServiceNameWithTemplate
        except Exception as e:
            log.error("Chyba při získávání služby pro uživatele %s: %s", u, e)
            continue
    content=""
    for uItm in services:
        u, srvName = uItm
        content+=f"{u} ALL=(ALL) NOPASSWD: {ctlPath} restart {srvName}\n"
    x=writeSudoersFile('node-red-instances',content)
    if not x:
        m="Chyba při zápisu sudoers souboru pro node-red instance"
        log.error(m)
        return m
    else:
        log.info("Aktualizován sudoers soubor pro node-red instance")
    return None

# -------- 2026-06

def getNodeJsVersion(username: Optional[str] = None) -> tuple[int, bool, str]:
    """Zjistí major verzi Node.js a zda je binárka globální.

    Parameters:
        username (str | None): pokud je zadán, zjišťuje verzi v kontextu uživatele

    Returns:
        tuple[int, bool, str]: (major_verze, je_globalni, velé číslo verze)
            (major_verze, je_globalni)
            - major_verze = 0 při chybě
            - je_globalni = True pokud binárka neleží v HOME uživatele
    """
    try:
        if username:
            user_home = getUserHome(username)

            result_path = subprocess.run(
                ["su", "-", username, "-c", "which node"],
                check=True,
                capture_output=True,
                text=True
            )
            node_path = result_path.stdout.strip()

            result_ver = subprocess.run(
                ["su", "-", username, "-c", "node -v"],
                check=True,
                capture_output=True,
                text=True
            )
            version_str = result_ver.stdout.strip()
        else:
            user_home = os.path.expanduser("~")
            node_path = shutil.which("node") or ""

            if not node_path:
                return (0, False, "")

            result_ver = subprocess.run(
                [node_path, "-v"],
                check=True,
                capture_output=True,
                text=True
            )
            version_str = result_ver.stdout.strip()

        if not node_path:
            return (0, False, "")

        node_real_path = os.path.realpath(node_path)

        m = re.match(r"v(\d+)", version_str)
        if not m:
            return (0, False, "")

        major = int(m.group(1))
        user_home_real = os.path.realpath(user_home)
        is_global = not (
            node_real_path == user_home_real
            or node_real_path.startswith(user_home_real + os.sep)
        )
        
        # ošetříme verzi, pokud je v ní něco navíc, např. "v18.16.0" → "18.16.0"
        version_str = version_str.strip().lstrip("v").strip()

        return (major, is_global, version_str)

    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError, OSError) as e:
        log.error("Chyba při zjišťování verze Node.js: %s", e)
        return (0, False, "")

def getNodeSourceVersion(username: Optional[str] = None) -> tuple[int, str]:
    """Zjistí major verzi Node.js a aktuální verzi v repo

    Parameters:
        username (str | None): pokud je zadán, zjišťuje verzi v kontextu uživatele

    Returns:
        tuple[int, str]: (major_verze, verze_str)
    """
    try:
        if username:
            result = subprocess.run(
                ["su", "-", username, "-c", "apt-cache policy nodejs"],
                check=True,
                capture_output=True,
                text=True
            )
        else:
            result = subprocess.run(
                ["apt-cache", "policy", "nodejs"],
                check=True,
                capture_output=True,
                text=True
            )

        version_str = ""
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Candidate:"):
                version_str = line.split("Candidate:")[1].strip()
                break

        m = re.match(r"(\d+)", version_str)
        major = int(m.group(1)) if m else 0
        
        # ošetříme verzi, pokud je v ní něco navíc, např. "18.16.0-1nodesource1" → "18.16.0-1nodesource1"
        version_str = version_str.strip()
        version_str = version_str.split("-")[0]  # vezmeme jen část před případným pomlčkou

        return (major, version_str)

    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError, OSError) as e:
        log.error("Chyba při zjišťování verze Node.js z APT: %s", e)
        return (0, "")


def getInstalledNodeMajor() -> int:
    """Vrátí nainstalovanou major verzi systémového Node.js."""
    try:
        result = subprocess.run(
            ["node", "-v"],
            check=True,
            capture_output=True,
            text=True
        )
        m = re.match(r"v(\d+)", result.stdout.strip())
        return int(m.group(1)) if m else 0
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        log.error("Chyba při čtení nainstalované verze Node.js: %s", e)
        return 0


def isRoot() -> bool:
    """Vrátí True pokud proces běží jako root."""
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def isNodeSourceAptInstall() -> bool:
    """Ověří, zda je Node.js instalován systémově přes APT z NodeSource."""
    try:
        policy = subprocess.run(
            ["apt-cache", "policy", "nodejs"],
            check=True,
            capture_output=True,
            text=True
        )

        sources = []
        sources_path = "/etc/apt/sources.list.d/nodesource.list"
        if not os.path.isfile(sources_path):
            sources_path = "/etc/apt/sources.list.d/nodesource.sources"
            if not os.path.isfile(sources_path):
                sources_path = "/etc/apt/sources.list"
        
        if os.path.isfile(sources_path):
            with open(sources_path, "r", encoding="utf-8") as f:
                sources.append(f.read())

        sources_blob = "\n".join(sources)

        return (
            "nodesource" in policy.stdout.lower()
            and "deb.nodesource.com" in sources_blob.lower()
        )

    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError, OSError) as e:
        log.error(TX_NODEJS_APT_CHECK_ERR, e)
        return False


def getConfiguredNodeSourceMajor() -> int:
    """Vrátí major verzi nastavenou v nodesource.list, např. 18 z node_18.x."""
    path = "/etc/apt/sources.list.d/nodesource.list"
    try:
        if not os.path.isfile(path):
            return 0

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        m = re.search(r"node_(\d+)\.x", content)
        return int(m.group(1)) if m else 0

    except (PermissionError, OSError) as e:
        log.error(TX_NODEJS_READ_FILE_ERR, path, e)
        return 0


def getTargetNodeMajor(current_major: int, to_lts: bool = False) -> int:
    """Určí cílovou major verzi Node.js.

    Parameters:
        current_major (int): aktuální major verze
        to_lts (bool):
            False = o jednu major výš
            True = poslední podporovaná LTS definovaná ve skriptu

    Returns:
        int: cílová major verze, nebo 0 při chybě
    """
    if current_major <= 0:
        return 0

    if to_lts:
        return LATEST_LTS_MAJOR

    return current_major + 1


def _printAndLog(message: str, *args) -> None:
    """Zapíše informační hlášku do logu a současně ji vypíše na stdout."""
    log.info(message, *args)
    if args:
        print(message % args)
    else:
        print(message)


def _applyNodeSourceNodeMajor(target_major: int, current_major: int = 0, allow_newer: bool = False) -> tuple[bool, str]:
    """Nainstaluje nebo aktualizuje globální Node.js na zadanou major verzi.
    
    Parameters:
        target_major (int): cílová major verze k instalaci
        current_major (int): aktuální major verze, pro informativní výpisy
        allow_newer (bool): pokud True, povolí i instalaci novější major verze než je target_major, pokud je aktuální major verze 0 (není nainstalováno) a target_major je LATEST_LTS_MAJOR, což může být užitené pro nové instalace, kde chceme zajistit alespoň LTS verzi, ale nechceme selhat pokud je dostupná novější major verze než LATEST_LTS_MAJOR
    
    Returns:
        tuple[bool, str]: (ok, zprava)
        ok = True pokud instalace nebo aktualizace proběhla úspěšně a výsledná major verze je target_major (nebo novější pokud allow_newer=True a aktuální major verze je 0)
        zprava = informační zpráva o výsledku operace nebo chybová zpráva při neúspěchu
    """
    if target_major <= 0:
        return (False, TX_NODEJS_TARGET_MAJOR_ERR)

    setup_url = f"https://deb.nodesource.com/setup_{target_major}.x"
    configured_major = getConfiguredNodeSourceMajor()
    should_reconfigure_repo = configured_major != target_major
    should_purge_before_switch = current_major > 0 and should_reconfigure_repo
    should_only_upgrade = current_major > 0 and current_major == target_major and not should_reconfigure_repo

    try:
        if current_major > 0:
            _printAndLog(
                TX_NODEJS_UPDATE_RUN,
                current_major, target_major
            )
        else:
            _printAndLog(TX_NODEJS_INSTALL_RUN, target_major)

        result_setup = None
        if should_purge_before_switch:
            _printAndLog(TX_NODEJS_PURGE_RUN, current_major, target_major)
            result_purge = subprocess.run(
                ["apt-get", "purge", "-y", "nodejs"],
                check=True,
                capture_output=True,
                text=True
            )
            if result_purge.stdout.strip():
                print(result_purge.stdout.strip())
            _printAndLog(TX_NODEJS_PURGE_DONE, current_major)
            if result_purge.stdout.strip():
                log.debug("apt purge stdout: %s", result_purge.stdout.strip())

        if should_reconfigure_repo:
            setup_cmd = f"curl -fsSL {setup_url} | bash -"
            _printAndLog(TX_NODEJS_REPO_CONFIGURE_RUN, target_major)
            result_setup = subprocess.run(
                ["bash", "-lc", setup_cmd],
                check=True,
                capture_output=True,
                text=True
            )
            if result_setup.stdout.strip():
                print(result_setup.stdout.strip())
            _printAndLog(TX_NODEJS_REPO_CONFIGURED, target_major)
        else:
            _printAndLog(TX_NODEJS_REPO_CONFIGURE_SKIP, target_major)

        result_update = subprocess.run(
            ["apt-get", "update"],
            check=True,
            capture_output=True,
            text=True
        )
        if result_update.stdout.strip():
            print(result_update.stdout.strip())

        install_cmd = ["apt-get", "install", "-y", "nodejs"]
        if should_only_upgrade:
            install_cmd = ["apt-get", "install", "--only-upgrade", "-y", "nodejs"]
            _printAndLog(TX_NODEJS_PACKAGE_UPGRADE_RUN, target_major)
        else:
            _printAndLog(TX_NODEJS_INSTALL_RUN, target_major)

        result_install = subprocess.run(
            install_cmd,
            check=True,
            capture_output=True,
            text=True
        )
        if result_install.stdout.strip():
            print(result_install.stdout.strip())

        _printAndLog(TX_NODEJS_INSTALL_UPDATE_SUCCESS, target_major)
        new_major, new_is_global, new_ver_str = getNodeJsVersion()
        if new_major <= 0:
            return (False, TX_NODEJS_NEW_VERSION_ERR)

        if not new_is_global:
            return (False, TX_NODEJS_NOT_GLOBAL_AFTER)

        if allow_newer:
            if new_major < target_major:
                return (False, TX_NODEJS_AFTER_EXPECTED_MIN.format(new_major=new_major, target_major=target_major))
        else:
            if new_major != target_major:
                return (False, TX_NODEJS_AFTER_EXPECTED_EXACT.format(new_major=new_major, target_major=target_major))

        _printAndLog(TX_NODEJS_AVAILABLE_MAJOR, new_ver_str)

        if current_major > 0:
            msg = TX_NODEJS_UPDATED_OK.format(new_major=new_major, current_major=current_major)
        else:
            msg = TX_NODEJS_INSTALLED_OK.format(new_major=new_major)

        if result_setup and result_setup.stdout.strip():
            log.debug("NodeSource setup stdout: %s", result_setup.stdout.strip())
        if result_update.stdout.strip():
            log.debug("apt update stdout: %s", result_update.stdout.strip())
        if result_install.stdout.strip():
            log.debug("apt install stdout: %s", result_install.stdout.strip())

        return (True, msg)

    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        stdout = (e.stdout or "").strip()
        msg = stderr or stdout or str(e)
        log.error(TX_NODEJS_INSTALL_UPDATE_ERR, msg)
        return (False, TX_NODEJS_INSTALL_UPDATE_FAILED.format(msg=msg))
    except (FileNotFoundError, PermissionError, OSError) as e:
        log.error(TX_NODEJS_INSTALL_UPDATE_SYS_ERR, e)
        return (False, TX_NODEJS_INSTALL_UPDATE_SYS_FAILED.format(err=e))

def nodeJsUpdateActualMajorMinor() -> tuple[bool, str]:
    """Provede jen aktualizaci aktuálně nainstalované verze, tzn minor update, bez změny major verze. 
    Returns:
        tuple[bool, str]:
            (ok, zprava)
    """
    if not isRoot():
        return (False, TX_NODEJS_UPDATE_ROOT_ERR)

    current_major, is_global, ver_str = getNodeJsVersion()
    if current_major <= 0:
        return (False, TX_NODEJS_CURRENT_VERSION_ERR)

    if not is_global:
        return (False, TX_NODEJS_NOT_GLOBAL)

    if not isNodeSourceAptInstall():
        return (False, TX_NODEJS_NOT_NODESOURCE)

    ndSrcRpVer, ndSrcVerStr = getNodeSourceVersion()

    _printAndLog(
        TX_NODEJS_UPDATE_REPO_RUN,
        current_major, ndSrcRpVer, ndSrcVerStr
    )
    
    return _applyNodeSourceNodeMajor(current_major, current_major, allow_newer=True)
    

def nodeJsInstall(target_major: int = LATEST_LTS_MAJOR) -> tuple[bool, str]:
    """Nainstaluje globální Node.js přes NodeSource APT repo."""
    if not isRoot():
        return (False, TX_NODEJS_INSTALL_ROOT_ERR)

    current_major, is_global, ver_str = getNodeJsVersion()
    if current_major > 0 and is_global:
        return (False, TX_NODEJS_ALREADY_INSTALLED.format(current_major=current_major))

    return _applyNodeSourceNodeMajor(target_major)


def nodeJsUpdate(to_lts: bool = False) -> tuple[bool, str]:
    """Provede update globálního Node.js přes NodeSource APT repo.

    Parameters:
        to_lts (bool):
            False = posun o jednu major verzi
            True = přepnutí na poslední podporovanou LTS definovanou ve skriptu

    Returns:
        tuple[bool, str]:
            (ok, zprava)
    """
    if not isRoot():
        return (False, TX_NODEJS_UPDATE_ROOT_ERR)

    current_major, is_global, ver_str = getNodeJsVersion()
    if current_major <= 0:
        return (False, TX_NODEJS_CURRENT_VERSION_ERR)

    if not is_global:
        return (False, TX_NODEJS_NOT_GLOBAL)

    if not isNodeSourceAptInstall():
        return (False, TX_NODEJS_NOT_NODESOURCE)

    configured_major = getConfiguredNodeSourceMajor()
    target_major = getTargetNodeMajor(current_major, to_lts)

    if target_major <= 0:
        return (False, TX_NODEJS_TARGET_MAJOR_ERR)

    if to_lts and current_major >= target_major:
        return (True, TX_NODEJS_ALREADY_LTS.format(current_major=current_major, target_major=target_major))

    if not to_lts and current_major == target_major:
        return (True, TX_NODEJS_ALREADY_TARGET.format(current_major=current_major))

    log.info(
        TX_NODEJS_UPDATE_REPO_RUN,
        current_major, target_major, configured_major
    )
    return _applyNodeSourceNodeMajor(target_major, current_major, allow_newer=to_lts)
    
    
def update_global_npm() -> Optional[str]:
    """Aktualizuje globální npm na nejnovější verzi.

    Returns:
        str | None: None pokud OK, jinak chybová zpráva
    """
    try:
        result = subprocess.run(
            ["npm", "install", "-g", "npm@latest"],
            check=True,
            capture_output=True,
            text=True
        )

        if result.stdout.strip():
            log.info("NPM update stdout: %s", result.stdout.strip())
            print(result.stdout.strip())

        if result.stderr.strip():
            log.warning("NPM update stderr: %s", result.stderr.strip())
            print(result.stderr.strip())
            return "NPM update completed with warnings"

        return None

    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or str(e)).strip()
        log.error("Chyba při update npm: %s", msg)
        return f"Update npm selhal: {msg}"

    except (FileNotFoundError, PermissionError, OSError) as e:
        log.error("Systémová chyba při update npm: %s", e)
        return f"Systémová chyba: {e}"
