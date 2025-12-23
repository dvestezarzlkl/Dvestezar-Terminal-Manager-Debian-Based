from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.app.appHelper import menu as menuX
from libs.JBLibs.systemUserManager import sshUsers,sshUser,listKeyRow

_sshManager = None

class ssh_menu(menuX):
    _mData :'sshMenu_data' = None
    appTitle:str = TXT_MAIN_NAME
    titleDisableURL:bool = True
    titleDisableSSLStatus:bool = True
    titleShowMyIP:bool = True
    titleShowTime:bool = True

class sshMenu_data:
    selectedUser:sshUser=None
    selectedKey:listKeyRow = None
    
    def __init__(self,selectedUser:str=None,selectedKey:str=None):
        self.selectedUser = selectedUser
        self.selectedKey = selectedKey
    
def getSshManager(refresh:bool=False)->sshUsers:    
    global _sshManager
    if _sshManager is None or refresh:
        _sshManager = sshUsers()
    return _sshManager