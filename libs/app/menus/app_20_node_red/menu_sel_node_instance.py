from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu_item,c_menu_title_label
from libs.JBLibs.term import text_color,en_color
from libs.app.appHelper import getSysUsers
from .menu_edit_node_instance import menuEdit_edit_nodeInstance
from libs.app.c_service_node import c_service_node
from libs.app.install_instance import install_node_instance
from .nd_menu import nd_menu
from libs.app.c_cfg import cfg_data
from libs.app.instanceHelper import ports,createPortInUseJson
from libs.JBLibs.input import anyKey,confirm
from libs.JBLibs.c_menu import onSelReturn

class menuEdit_select_nodeInstance(nd_menu):
    # own
    sysUsers:list[int,str]=[]
    
    # protected c_menu
    afterMenu=TXT_MENUSEL_AFTERMN
    choiceQuit=False
    
    def __init__(self):
        super().__init__()
        self.sysUsers=self.sysUsers
                    
    def onShowMenu(self):
        self._setAppHeader(TXT_MENUSEL_TIT)
        
        self.menu=[]
        p=[]

        i=[]
        lst_json=[] # obsahuje pole polí [ [<int_port>,<name_instance>],... ]
        
        
        # tabulka oddělená |, 8 nzaků mezera | nazev max 50 znaků doplněno na 500 - zeleně | system user 30 znakový
        i.append(c_menu_item(text_color(f"| {'Name':<40} | {'System User':<25} |", en_color.BRIGHT_BLACK),atRight=text_color("  Status  ", en_color.BRIGHT_BLACK)))
        for item in getSysUsers():
            # service = c_service_node(item[1])
            d=cfg_data(item[1])
            p.append(int(d.port))
            lst_json.append([
                int(d.port),
                item[1],
                d.service.fullStatus()
            ])
            t:str=str(d.title)
            if len(t) > 40:
                t = t[:36] + " ..."
            ss:str=str(d.system_user)
            if len(ss) > 25:
                ss=ss[:22] + " ..."
            line = f"{t:<40}"
            line = text_color(line, en_color.BRIGHT_GREEN if d.service.running() else en_color.BRIGHT_BLACK)
            line = f"| {line} | {ss:<25} |"
            i.append(
                c_menu_item(
                    line,
                    item[0],
                    menuEdit_edit_nodeInstance(),
                    None,
                    item[1], # data systemUserName/service-instance-template
                    atRight=d.service.fullStatus() + f" | {TXT_PORT}: "+str(d.port)
                )
            )
        ports(p)
        createPortInUseJson(lst_json,self.sslStatus)
        if i:
            self.menu.append(c_menu_title_label(TXT_TITLE_INSTANCE))
            self.menu.extend(i)
            
        self.menu.extend([
            c_menu_title_label(TXT_OPT),
            c_menu_item(text_color(TXT_MENU0_INSTALL, en_color.BRIGHT_CYAN),"i",install_node_instance),
            c_menu_item(TXT_MENU0_UPD_SUDO_FL,"usd",self.mn_update_sudoers_file),
            c_menu_item(TXT_MENU0_UPD_SUDO_FL,"hu",self.mn_show_sudoer_help),
        ])
        
    def mn_update_sudoers_file(self,selItem:c_menu_item) -> onSelReturn:
        """
        Update sudoers file for node-red instances
        """
        from libs.app.instanceHelper import update_sudoers_file
        if confirm(TXT_UPDATE_SUDOERS_SURE_QUESTION):
            r = update_sudoers_file()
            if r:
                print(TXT_UPDATE_SUDOERS_FILE_ERROR.format(err=r))
            else:
                print(TXT_UPDATE_SUDOERS_FILE_OK)
            anyKey()
        
    def mn_show_sudoer_help(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show configuration help file
        """
        import os
        from libs.JBLibs.term import cls
        from libs.JBLibs.helper import getAssetsPath
        pth=getAssetsPath(TXT_MENU_SUDOER_HELP_FILE)
        if os.path.exists(pth):
            with open(pth,'r',encoding='utf-8') as f:
                cls()
                print(f.read())
                anyKey()
        else:
            print(TXT_MENU_INSTN_cfg_help_Err)
            anyKey()