from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu_item,onSelReturn,c_menu_title_label
from libs.JBLibs.input import confirm,anyKey,get_username,get_pwd_confirm,hash_password
from libs.JBLibs.term import text_inverse
from libs.app.c_cfg import cfg_user
from libs.app.c_service_node import c_service_node
from .menu_NodeUser import menuEdit_nodeUser
from .menu_data_classes import menu_data
from .nd_menu import nd_menu

from libs.JBLibs.helper import getLogger
log = getLogger(__name__)

class menuEdit_edit_nodeInstance_user(nd_menu):
    """ edituje instanci nudou podle vybraného systémového uživatele """
        
    _mData:menu_data=None
    choiceQuit=None
    
    def onShowMenu(self):        
        self._setAppHeader(TXT_MENU_INSTN_tit1,
            TXT_MENU_INSTN_tit2,
            None,
            self._mData.systemUserName,
            self._mData.cfg.port,
            None,
            self._mData.cfg.title
        )
        
        self.menu=[]
        u=[]
        for idx,user in enumerate(self._mData.cfg.admin_users):
            perm='RW' if user.permissions == '*' else 'R'
            u.append(
                c_menu_item(
                    user.user,
                    idx,
                    menuEdit_nodeUser(),
                    None,
                    menu_data(
                        self._mData.systemUserName,
                        self._mData.cfg,
                        user
                    ),
                    atRight=f'{TXT_ACC}: {perm}'
                )
            )
        
        if u:
            self.menu.append(c_menu_title_label(TXT_TITLE_NDR_USR))
            self.menu.extend(u)
            
        service=self._mData.cfg.service
        if not isinstance(service,c_service_node):
            raise Exception(f"{TXT_MENU_INSTN_U_noInit} {self._mData.systemUserName}")
                
        u=[
            c_menu_item(TXT_MENU_INSTN_U_add,'a',self.addNewUser),
        ]
        if not self._mData.cfg.uiUser:
            u.extend([
                c_menu_item(TXT_MENU_INSTN_U_sec,'u',self.uiUserSet,atRight=TXT_MENU_INSTN_U_ns),
            ])
        else:
            u.extend([
                c_menu_item(TXT_MENU_INSTN_U_ovw,'u',self.uiUserSet,atRight=self._mData.cfg.getUIUserName()),
                c_menu_item(TXT_MENU_INSTN_U_rem,'d',self.uiUserDel),
            ])
            
        if self._mData.cfg.changed:
            u.append(c_menu_item("!!!!  "+text_inverse(TXT_SAVE),'save',self.save))
            
        if u:
            self.menu.append(c_menu_title_label(TXT_OPT))
            self.menu.extend(u)
    
    def addNewUser(self,selItem:c_menu_item) -> onSelReturn:
        """
        Add new user to node instance
        """
        username = get_username(TXT_MENU_INSTN_nd_i)
        if username != "" and username != None:
            pwd=get_pwd_confirm()
            if pwd != None:
                pwd=hash_password(pwd)
                self._mData.cfg.admin_users.append(cfg_user(username,pwd,'*'))
                self._mData.cfg.changed=True    

    def uiUserSet(self,selItem:c_menu_item) -> onSelReturn:
        """
        Set UI user for node instance
        """
        username = get_username(TXT_MENU_INSTN_u_i)
        if username != "" and username != None:
            pwd=get_pwd_confirm()
            if pwd != None:
                pwd=hash_password(pwd)
                self._mData.cfg.setUiUser(username,pwd)
                
    def uiUserDel(self,selItem:c_menu_item) -> onSelReturn:
        """
        Remove UI user for node instance
        """
        
        if confirm(TXT_MENU_INSTN_u_rem_rly):
            self._mData.cfg.delUIUser()

    def save(self,selItem:c_menu_item) -> onSelReturn:
        if confirm(TXT_MENU_INSTN_save_q):
            self._mData.cfg.save()
            anyKey()

    def onExitMenu(self):
        log.debug("- exit menuEdit_edit_nodeInstance")
        if self._mData.cfg.changed:
            if confirm(TXT_MENU_INSTN_save_ex_q):
                self._mData.cfg.save()
                anyKey()