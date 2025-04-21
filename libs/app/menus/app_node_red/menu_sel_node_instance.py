from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu_item,c_menu_title_label
from libs.app.appHelper import getSysUsers
from .menu_edit_node_instance import menuEdit_edit_nodeInstance
from libs.app.c_service_node import c_service_node
from libs.app.install_instance import install_node_instance
from .nd_menu import nd_menu
from libs.app.c_cfg import cfg_data
from libs.app.instanceHelper import ports,createPortInUseJson

class menuEdit_select_nodeInstance(nd_menu):
    sysUsers:list[int,str]=[]
    afterMenu=TXT_MENUSEL_AFTERMN
    choiceQuit=False
                    
    def onShowMenu(self):
        self._setAppHeader(TXT_MENUSEL_TIT)
        
        self.menu=[]
        p=[]

        i=[]
        lst_json=[] # obsahuje pole polí [ [<int_port>,<name_instance>],... ]
        for item in getSysUsers():
            # service = c_service_node(item[1])
            d=cfg_data(item[1])
            p.append(int(d.port))
            lst_json.append([
                int(d.port),
                item[1],
                d.service.fullStatus()
            ])
            i.append(
                c_menu_item(
                    item[1],
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
            c_menu_item(TXT_MENU0_INSTALL,"i",install_node_instance)            
        ])