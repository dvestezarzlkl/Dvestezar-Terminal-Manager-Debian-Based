from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu_item,onSelReturn
from libs.JBLibs.input import confirm,hash_password,get_pwd_confirm
from .menu_data_classes import menu_data
from .nd_menu import nd_menu

from libs.JBLibs.helper import getLogger
log = getLogger(__name__)

class menuEdit_nodeUser(nd_menu):
    
    # own
    _mData:menu_data=None
    
    # protected c_menu
    choiceQuit=False
    
    def __init__(self):
        super().__init__()
        self._mData=self._mData
    
    def onShowMenu(self):
        self._setAppHeader(TX_MENU_NDU_TIT1,
            TX_MENU_NDU_TIT2,
            [
                ".",
                [TXT_MENU_INSTN_run,    str(self._mData.cfg.service_running())],
                [TXT_MENU_INSTN_nd_acl,   self._mData.nodeUser.permissions],
            ],
            self._mData.systemUserName,
            self._mData.cfg.port,
            self._mData.nodeUser.user,
            self._mData.cfg.title
        )
        
        
        self.menu=[]
        if self._mData.nodeUser.permissions == '*':
            self.menu.append(c_menu_item(TXT_MENU_NDUSR_ro,'r',self.changeToReadOnly))
        else:
            self.menu.append(c_menu_item(TXT_MENU_NDUSR_rw,'w',self.changeToReadWrite))
        self.menu.extend([
            c_menu_item(TXT_MENU_NDUSR_pwd,'p',self.changePassword),
            c_menu_item(''),
            c_menu_item(TXT_MENU_NDUSR_del,'d',self.deleteUser),
        ])
        
    def changeToReadOnly(self,selItem:c_menu_item) -> onSelReturn:
        """
        Change node user to read-only access
        """
        self._mData.nodeUser.permissions = 'read'
        self._mData.cfg.changed=True
        
    def changeToReadWrite(self,selItem:c_menu_item) -> onSelReturn:
        """
        Change node user to read-write access
        """
        self._mData.nodeUser.permissions = '*'
        self._mData.cfg.changed=True
        
    def changePassword(self,selItem:c_menu_item) -> onSelReturn:
        """
        Change password for node user
        """
        pwd=get_pwd_confirm()
        if pwd != None:
            pwd=hash_password(pwd)
            self._mData.nodeUser.password = pwd
            self._mData.cfg.changed=True
            
    def deleteUser(self,selItem:c_menu_item) -> onSelReturn:
        """
        Delete node user
        """
        if confirm(TXT_MENU_NDUSR_del_q):
            if len(self._mData.cfg.admin_users) < 2:
                return TXT_MENU_NDUSR_del_err
            self._mData.cfg.admin_users.remove(self._mData.nodeUser)
            self._mData.cfg.changed=True
            return onSelReturn(endMenu=True)