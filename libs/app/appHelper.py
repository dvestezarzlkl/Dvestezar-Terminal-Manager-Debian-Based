
from libs.JBLibs.helper import loadLng
from .lng.default import * 
loadLng()

from . import cfg
from libs.JBLibs.c_menu import c_menu,c_menu_block_items
from libs.JBLibs.helper import userExists,getUserList,getInterfaces,c_interface
from libs.JBLibs.term import text_inverse
from .instanceHelper import getHttps,existsSelfSignedCert
from typing import Union,List
from datetime import datetime
import os

def defTitle(lf:bool=True) -> str:
    """
    Return default title for node instance
    """
    return cfg.MAIN_TITLE+(chr(10) if lf else "")

def _userListFilter(user:str) -> bool:
    """
    Filter for user list
    """
    p=f'/home/{user}/muj-node-config.js'
    return os.path.exists(p)

def getSysUsers()->list[int,str]:
    """
    Return list of system users with node config file in hos home directory
    vrací seznam uživatelů s konfiguračním souborem pro node v domovském adresáři
    return list of tuples (index,username)
    """
    return getUserList(_userListFilter,True)

class menu(c_menu):
    
    # protected
    minMenuWidth:int = cfg.MIN_WIDTH
    afterMenu:List[str]=[
        "F5 - Refresh menu",
    ]
    
    
    # own
    sslStatus:int=0
    """0=not set, 1=cfg, 2=self"""
    
    appTitle:str="App Title"
    """Application title"""
    
    titleDisableSSLStatus:bool=False
    titleDisableURL:bool=False
    
    titleShowMyIP:bool=False
    titleShowTime:bool=False
    
    _interfaces:List[c_interface]=None
    
    def __init__(self):
        super().__init__()
        self.sslStatus=self.sslStatus
        self.appTitle=self.appTitle
        self.titleDisableSSLStatus=self.titleDisableSSLStatus
        self.titleDisableURL=self.titleDisableURL
        self.titleShowMyIP=self.titleShowMyIP
        self.titleShowTime=self.titleShowTime
        self._interfaces=self._interfaces
        
    def _setAppHeader(
        self,
        menuName:str="",
        menuTitle:str="",
        subItems:c_menu_block_items=None,
        systemUser:str=None,
        port:int=None,
        breadCrumbs:Union[str,dict,List[str]]=None,
        instanceTitle:str=None
    ) -> None:
        """
        Set the application header
        
        Parameters:
            menuName (str): menu name, je převedeno do velkých písmen
            menuTitle (str): menu title, pokud zadáme zobrazí se za menuName s prefixem " - "
            subItems (c_menu_block_items): list of tuples with additional information
            systemUser (str): system user name zobrazí se jen pokud je zadán, můžeme vynechat a použít jen breadCrumbs
            port (int): port number zobrazí se jen pokud je zadán
            breadCrumbs (Union[str,dict],List[str]): cesta k aktuálnímu menu, pokud:
                - (str) tak je zobrazen 'TX_HD_NODE_USER: {breadCrumbs}'
                - (dict) tak je zobrazen '{key}: {value}' pro každý prvek a ty jsou odděleny ' -> '
                - (List[str]) tak je zobrazen '{breadCrumbs[0]} -> {breadCrumbs[1]} -> ...'                
            instanceTitle (str): Titulek stránek instance, zobrazí se jen pokud je zadán
            
        Returns:
            None
        """ 
        if cfg.mainService:
            srv_hd=cfg.mainService.getHeader()
        else:
            srv_hd=None
        
        h=c_menu_block_items()
        h.append(defTitle(False))
        h.append(self.appTitle)
        h.append(" ")
        if menuName and isinstance(menuName,str):            
            t=menuName.upper()
            if menuTitle and isinstance(menuTitle,str):
                t+=f" - {menuTitle}"
            h.append(t)
            
        ssu=None
        if systemUser and isinstance(systemUser,str):
            if userExists(systemUser):
                ssu=systemUser
            else:
                systemUser=TX_HD_USR_NF
        else:
            if systemUser is None:
                systemUser=""
            else:
                systemUser=TX_HD_USR_TERR
                        
        ls=""
        if systemUser:
            ls=f"{TX_HD_USER}: {systemUser}"
        if breadCrumbs and isinstance(breadCrumbs,str):
            ls+=( " -> " if ls else ""  ) + f"{TX_HD_NODE_USER}: {breadCrumbs}"
        elif breadCrumbs and isinstance(breadCrumbs,dict):
            for k,v in breadCrumbs.items():
                ls+=( " -> " if ls else ""  ) + f"{k}: {v}"
        elif breadCrumbs and isinstance(breadCrumbs,list):
            for v in breadCrumbs:
                ls+=( " -> " if ls else ""  ) + v
        if ls:
            h.append(text_inverse(f" {ls} "))
        
        self.title=h
        
        s=c_menu_block_items()
        if srv_hd:
            s.append((TX_HD_SERV_VER,    f"v{srv_hd.version}"))
        
        
        stx=TX_HD_SSL_NAN
        self.sslStatus=0
        sslM=[]
        if ssu:
            ssl=getHttps(systemUser)
            if ssl:
                stx=TX_HD_SSL_CFG
                self.sslStatus=1
            elif existsSelfSignedCert(systemUser):
                stx=TX_HD_SSL_SELF
                self.sslStatus=2
            if not self.titleDisableSSLStatus:
                sslM.extend([
                    (
                        TX_HD_SSL_STATUS,stx
                    )
                ])

        s.append((
            TX_HD_VERSION,
            cfg.VERSION
        )),
        if not self.titleDisableURL:
            # URL
            s.append((          
                TX_HD_URL,
                ( 'http' if self.sslStatus==0 else 'https' ) + "://" + cfg.SERVER_URL+( (":"+str(port)) if port else ":XXXX")
            ))
            
        if self.titleShowMyIP:
            if not self._interfaces:
                self._interfaces=getInterfaces()
            if self._interfaces:
                s.append( "Interfaces:" )
                for xi in self._interfaces:
                    s.append((
                        "-- IPV4/6 "+xi.name,
                        xi.ipv4 +" / "+ xi.ipv6
                    ))
        if self.titleShowTime:
            s.append((
                "Time",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            
        s.extend(sslM)
        
        
        if instanceTitle:
            s.append([TX_HD_InstanceTitle,instanceTitle])
        
        if subItems:
            s.extend(subItems)
                        
        self.subTitle=s
                
        
        