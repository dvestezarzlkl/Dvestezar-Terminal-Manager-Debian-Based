from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu_item,c_menu_block_items,c_menu_title_label,onSelReturn
from .ssh_menu import ssh_menu,sshMenu_data
from .menu_user_key_edit import menu_user_key_edit
from libs.JBLibs.input import confirm,anyKey
from libs.JBLibs.term import cls

from libs.JBLibs.helper import getLogger,loadLng
log = getLogger(__name__)

_MENU_NAME_:str = TXT_MAIN_NAME

# ******* SSH    MANAGER   MENU    *******
class menu_user_edit (ssh_menu):
    choiceBack=None
    choiceQuit=None
    ESC_is_quit=True      
        
    
        
    def onShowMenu(self):
        
        self._mData.selectedUser.refresh()
        
        t=TXT_MENU2_TITLE_01 + " (" + ( TXT_MENU_01 if self._mData.selectedUser.hasSudo else TXT_MENU_00 ) + ")"
        self._setAppHeader(t,"",
            c_menu_block_items([
                (TXT_MENU2_TITLE_02      ,str( self._mData.selectedUser.keyCount ) ),
            ]),
            self._mData.selectedUser.userName
        )
        
        self.menu=[
            c_menu_title_label(TXT_TITLE_05),
        ]
        
        c=0
        for k in self._mData.selectedUser.keys:
            self.menu.append(c_menu_item(
                k.fileName,
                str(c),
                menu_user_key_edit(),
                None,
                sshMenu_data(
                    self._mData.selectedUser,
                    k
                ),
                atRight=TXT_INCLUDED if k.included else TXT_NOT_INCLUDED
            ))
            c+=1
            
        if self._mData.selectedUser.hasSudo:
            # delete sudo
            self.menu.append(c_menu_item(TXT_MENU2_TITLE_12,"srm",self.removeSudo))
        else:
            # add sudo
            self.menu.append(c_menu_item(TXT_MENU2_TITLE_13,"sad",self.addSudo))
        
        self.menu.extend([
            None,
            c_menu_item(TXT_MENU2_TITLE_03,"a",self.createKey),
            c_menu_item(TXT_MENU2_TITLE_08,"d",self.deleteUser),
            c_menu_item(TXT_MENU2_TITLE_09,"p",self.pwdUser),
            c_menu_item(TXT_MENU2_TITLE_10,"u",self.updateUserSSH),
        ])
        
    def createKey(self,selItem:c_menu_item) -> onSelReturn:
        """
        Create a new system user.
        """
        return self._mData.selectedUser.createCerKey()

    def deleteKey(self,selItem:c_menu_item) -> onSelReturn:
        """
        Delete a key.
        """
        x=self._selectedItem
        if x is None:
            return "Select a key first"
        if not isinstance(x,c_menu_item):
            return "Invalid selection"
        if not isinstance(x.data,sshMenu_data):
            return "Invalid selection"
        if confirm(f"Delete key {x.data.selectedKey.fileName} from user {x.data.selectedKey.userName}"):
            if (e:=x.data.selectedKey.delKey()):
                return e
            print("Key deleted")
            anyKey()
            return None
        return None
            
    def deleteUser(self,selItem:c_menu_item) -> onSelReturn:
        """Není podporováno z bezpečnostních důvodů, user musí jít do terminálu a smazat sám
        """
        from libs.app.remove_instance import remove_node_instance
        if (e:=remove_node_instance(self._mData.selectedUser.userName,True)):
            return e
        return onSelReturn(endMenu=True)


    def pwdUser(self,selItem:c_menu_item) -> onSelReturn:
        """
        Change user password.
        """
        from libs.JBLibs.systemUserManager import sshMng
        return sshMng.changeSystemUserPwd(self._mData.selectedUser.userName)
    
    def updateUserSSH(self,selItem:c_menu_item) -> onSelReturn:
        """
        Update user SSH directory.
        """
        cls()
        print(TXT_MENU2_TITLE_14)
        from libs.JBLibs.systemUserManager import sshMng
        x=sshMng.repairSshFile(self._mData.selectedUser.userName)
        if x:
            print(x)
        else:
            print(TXT_MENU2_TITLE_11)
        anyKey()
        return None
    
    def removeSudo(self,selItem:c_menu_item) -> onSelReturn:
        """
        Remove sudo permissions from user.
        """
        cls()
        print(f"{TXT_MENU2_TITLE_16} {self._mData.selectedUser.userName}")
        from libs.JBLibs.systemUserManager import sshMng
        if (e:=sshMng.remove_sudo_privileges(self._mData.selectedUser.userName)):
            print(e)
        else:
            print(TXT_MENU2_TITLE_15)
        anyKey()
        return None
    
    def addSudo(self,selItem:c_menu_item) -> onSelReturn:
        """
        Add sudo permissions to user.
        """
        cls()
        print(f"{TXT_MENU2_TITLE_17} {self._mData.selectedUser.userName}")
        from libs.JBLibs.systemUserManager import sshMng
        if (e:=sshMng.add_sudo_privileges(self._mData.selectedUser.userName)):
            print(e)
        else:
            print(TXT_MENU2_TITLE_18)
        anyKey()
        return None