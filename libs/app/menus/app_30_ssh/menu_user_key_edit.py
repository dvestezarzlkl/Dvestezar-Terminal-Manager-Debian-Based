from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu_item,c_menu_title_label,onSelReturn
from .ssh_menu import ssh_menu
from libs.JBLibs.systemUserManager import listKeyRow
from libs.JBLibs.term import text_color,en_color

from libs.JBLibs.helper import getLogger
log = getLogger(__name__)

_MENU_NAME_:str = TXT_MAIN_NAME

# ******* SSH    MANAGER   MENU    *******
class menu_user_key_edit(ssh_menu):
    choiceBack=None
    choiceQuit=None
    ESC_is_quit=True      
        
    
        
    def onShowMenu(self):
        
        self._mData.selectedUser.refresh()
        self._mData.selectedKey.check()
        
        self._setAppHeader(TXT_MENU3_TITLE_01,"",
            [
                [TXT_MENU3_TITLE_02, TXT_INCLUDED if self._mData.selectedKey.included else TXT_NOT_INCLUDED]
            ],
            systemUser=self._mData.selectedUser.userName,
            breadCrumbs={
                TXT_MENU3_TITLE_02:self._mData.selectedKey.fileName
            }
        )
        
        self.menu=[
            c_menu_title_label(TXT_TITLE_06),
        ]
        
        self.menu.append(c_menu_item(TXT_MENU2_TITLE_07,"show",self.showKey))
        
        if self._mData.selectedKey.included:
            self.menu.append(c_menu_item(text_color(TXT_MENU2_TITLE_06,color=en_color.RED),"rem",self.remKey))
        else:
            self.menu.append(c_menu_item(text_color(TXT_MENU2_TITLE_05,color=en_color.GREEN),"ins",self.insKey))
        
        self.menu.extend([
            c_menu_item(text_color(TXT_MENU2_TITLE_04,color=en_color.BRIGHT_RED,bold=True),"del",self.deleteKey),
        ])

    def deleteKey(self,selItem:c_menu_item) -> onSelReturn:
        """
        Delete a key.
        """
        x=self._mData.selectedKey
        if not isinstance(x,listKeyRow):
            return "Invalid selection"
        
        if (e:=x.delMe()):
            return e
        return onSelReturn(endMenu=True)
            
    def insKey(self,selItem:c_menu_item) -> onSelReturn:
        """
        Include a key in authorized_keys.
        """
        x=self._mData.selectedKey
        if not isinstance(x,listKeyRow):
            return "Invalid selection"
        
        if (e:=x.addKey()):
            return e
    
    def remKey(self,selItem:c_menu_item) -> onSelReturn:
        """
        Remove a key from authorized_keys.
        """
        x=self._mData.selectedKey
        if not isinstance(x,listKeyRow):
            return "Invalid selection"
        
        if (e:=x.remKey()):
            return e
    
    def showKey(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show the private key.
        """
        x=self._mData.selectedKey
        if not isinstance(x,listKeyRow):
            return "Invalid selection"
        
        x.showCert()