from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

import os, re, json5
from typing import Union,Dict
from .instanceHelper import getHttpsCfgStr

from libs.JBLibs.helper import getLogger
from libs.app.c_service_node import c_service_node
log = getLogger(__name__)

class cfg_user:
    user:str
    password:str
    permissions:str    
    def __init__(self, user: str, password: str, permissions: str):
        self.user = user
        self.password = password
        self.permissions = permissions
    def __repr__(self):
        return f"cfg_user(user='{self.user}', password='****', permissions='{self.permissions}')"
    def asJS(self) -> str:
        return "{"+f"username: '{self.user}', password: '{self.password}', permissions: '{self.permissions}'"+"}"
    
class cfg_data:
    title:str = TX_DEF
    port:int = 20000
    admin_users: list[cfg_user]
    changed: bool = False
    ok:bool=False
    err:str=""
    system_user:str=""
    uiUser:Union[Dict[str,str],None]=None
    
    service:c_service_node=None    
    
    __path:str=""
    def __init__(self,systemUser:str):
        # pokud neexistuje system user tak chyba
        if os.system(f'id -u {systemUser} > /dev/null 2>&1') != 0:
            self.err=TX_CFG_INI_ERR1.format(name=systemUser)
            return
        configPath = f'/home/{systemUser}/muj-node-config.js'
        self.system_user=systemUser
        
        if not os.path.exists(configPath):
            self.err=TX_CFG_INI_ERR2.format(pth=configPath)
            return
        
        self.__path = configPath
        self.load()
        self.service=c_service_node(systemUser)
    
    def __getRgxS(self) -> tuple[re.Pattern,re.Pattern,re.Pattern,re.Pattern,re.Pattern]:
        """
        Return compiled regular expressions for title and data.
        
        Parameters:
            None
            
        Returns:
            tuple[re.Pattern,re.Pattern,re.Pattern,re.Pattern,re.Pattern] - compiled regular expressions extract and replace
                1. r_title: title
                2. r_data: data
                3. r_port: port
                4. r_uiu: ui_user
        """
        r_title=re.compile(r'var\s+title\s*=\s*"(.*)";')
        r_port=re.compile(r'uiPort:\s*(\d+)\s*,')
        r_data=re.compile(r'admin_users\s*:\s*(\[[^]]*\])\s*,',re.DOTALL)
        r_uiu=re.compile(r'ui_user\s*:\s*(\{[^}]*\}|\s*null\s*)\s*,',re.DOTALL)
        r_https=re.compile(r'https\s*:\s*(\{[^}]*\}|\s*null\s*)\s*,',re.DOTALL)
        return r_title, r_data, r_port, r_uiu, r_https
    
    def load(self) -> bool:
        """
        Open configuration file for the specified user and return the content.
        
        Returns:
            bool - True if configuration file has been loaded successfully, False otherwise
        """
        r_title, r_data, r_port, r_uiu, r_https = self.__getRgxS()
        
        # read whole content
        file = open( self.__path , 'r')
        content = file.read()
        file.close()
        
        self.admin_users=[]
        
        # find title
        m = r_title.search(content)
        if m:
            self.title = m.group(1)
            
        # find port
        m = r_port.search(content)
        if m:
            try:
                self.port = int(m.group(1))
            except ValueError:
                self.port = 20000
                            
        # find data
        m = r_data.search(content)
        if m:
            data = json5.loads(m.group(1))
            for user in data:
                self.admin_users.append(cfg_user(user['username'], user['password'], user['permissions']))
        else:
            self.err=TX_CFG_INI_ERR3.format(pth=self.__path)
            return False
        
        # find ui_users
        m = r_uiu.search(content)
        if m:
            self.uiUser = json5.loads(m.group(1))
            if not self.uiUser:
                self.uiUser=None
            else:
                if not 'user' in self.uiUser and not 'pass' in self.uiUser:
                    self.uiUser=None
        else:
            self.uiUser=None
        
        return True
                
    def __asJS_adminUsers(self) -> str:
        """Vrací string pro JS s admin_users"""
        return f"admin_users: [{', '.join([u.asJS() for u in self.admin_users])}]"
    
    def __asJS_uiUser(self) -> str:
        """Vrací string pro JS s ui_user"""
        if self.uiUser:
            return f"ui_user: {json5.dumps(self.uiUser)}"
        return "ui_user: null"
            
    def service_running(self) -> bool:
        """
        Check if node-red service is running for this user
        """
        return self.service.running()

    def service_status_tx(self, asInt:bool=False) -> Union[str,int]:
        """
        Otestuje stav služby, vrací textové označení stavu nebo pokud asInt=True tak číslo
        
        Parameters:
            asInt (bool): pokud True, vrací stav jako číslo
            
        Returns:
            Union[str,int] - stav služby
        
        :see: c_service.fullStatus    
        """
        return self.service.fullStatus(asInt)

    def save(self,force:bool=False) -> None:
        """
        Save title and data to configuration file
        
        Parameters:
            force (bool): save even if not changed
            
        Returns:
            None
        """
        if not self.changed and not force:
            return
        
        r_title, r_data, r_port, r_uiu, r_https = self.__getRgxS()
        
        # read whole content
        file = open(self.__path, 'r')
        content = file.read()
        file.close()
        
        # replace title
        content = r_title.sub(f'var title = "{self.title}";', content)
        
        # replace port
        content = r_port.sub(f'uiPort: {self.port},', content)
        
        # replace data
        content = r_data.sub(self.__asJS_adminUsers()+",", content)
        
        # replace ui_user
        content = r_uiu.sub(self.__asJS_uiUser()+",", content)
        
        # save https
        content = r_https.sub(getHttpsCfgStr(self.system_user)+",", content)
        
        # save back
        file = open(self.__path, 'w')
        file.write(content)
        file.close()

        x=TX_CFG_SAVED.format(pth=self.__path)
        log.info(x)
        print(x)
        print(TX_CFG_SV_RST)

        x=self.restart_service()
        if x:
            log.error(x)
            print(x)
                    
        print(TX_CFG_SV_DONE)
        self.changed=False
        
    def restart_service(self,prn:bool=False) -> str:
        """
        Restart node-red service for this user
        
        Parameters:
            prn (bool): print messages
            
        Returns:
            str - error message or empty string            
        """
        if prn:
            print(TX_CFG_RST_ST)
        self.service.stop()
        if self.service.running():
            return TX_CFG_RST_ERR1.format(name=self.system_user)            
        if prn:
            print(TX_CFG_RST_STS)
        self.service.start()
        if not self.service.running():
            return TX_CFG_RST_ERR2.format(name=self.system_user)
        
        if prn:
            print(TX_CFG_RST_OK)
        return ""
    
    def setUiUser(self,userName:str, hashedPassword:str) -> None:
        """
        Set UI user for this configuration, setting changed flag to True
        
        Parameters:
            userName (str): user name
            hashedPassword (str): hashed password
            
        Returns:
            None
        """
        self.uiUser = {"user": userName, "pass": hashedPassword}
        self.changed = True
        
    def delUIUser(self)->None:
        """
        Delete UI user for this configuration, setting changed flag to True
        """
        self.uiUser = None
        self.changed = True
        
    def getUIUserName(self) -> str:
        """
        Return UI user name
        
        Parameters:
            None
            
        Returns:
            str - user name or empty string        
        """
        if self.uiUser:
            if 'user' in self.uiUser:
                return self.uiUser['user']
        return ""
        
            
        