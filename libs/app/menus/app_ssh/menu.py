from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu_item,c_menu_block_items,c_menu_title_label,onSelReturn
from .ssh_menu import ssh_menu,getSshManager,sshMenu_data
from .menu_user_edit import menu_user_edit

from libs.JBLibs.helper import getLogger
log = getLogger(__name__)

_MENU_NAME_:str = TXT_MAIN_NAME

# ******* SSH    MANAGER   MENU    *******
class menu (ssh_menu):
    choiceBack=None
    choiceQuit=None
    ESC_is_quit=True      
        
    def onShowMenu(self):
        """
        Show the main menu.
        """        
        u=getSshManager(True)
            
        self._setAppHeader(TXT_TITLE_01,"",
            c_menu_block_items([
                (TXT_TITLE_02      ,str(len(u)) ),
            ])
        )
        
        self.menu=[
            c_menu_title_label(TXT_TITLE_03),
        ]
        
        c=0
        for ux in u:
            self.menu.append(c_menu_item(
                ux.userName,
                str(c),
                menu_user_edit(),
                None,
                sshMenu_data(ux),
                atRight=(TXT_MENU_01 if ux.hasSudo else TXT_MENU_00 )+f", {TXT_MENU_02}: {ux.keyCount}"
            ))
            c+=1
        
        self.menu.extend([
            None,
            c_menu_item(TXT_TITLE_04,"make",self.createSysUser),
        ])
        
    def createSysUser(self,selItem:c_menu_item) -> onSelReturn:
        """
        Create a new system user.
        """
        from libs.JBLibs.systemUserManager import sshMng
        return sshMng.createSysUser()

