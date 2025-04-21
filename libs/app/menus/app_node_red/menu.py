from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu_item,onSelReturn,c_menu_block_items,c_menu_title_label
from libs.JBLibs.input import confirm,anyKey
from libs.JBLibs.systemdService import c_header
from libs.app.backup import create_full_backup_for_all_users_7z
from .menu_sel_node_instance import menuEdit_select_nodeInstance
from libs.app.c_service_node import c_service_node
from libs.app.appHelper import getSysUsers
from libs.app import cfg
from .nd_menu import nd_menu

from libs.JBLibs.helper import getLogger
log = getLogger(__name__)

_MENU_NAME_:str = TXT_MAIN_NAME

class menu (nd_menu):
    serviceVersion="1.1.1"
    choiceBack=None
    ESC_is_quit=True      
        
    def onShowMenu(self):
        """
        Show the main menu.
        """
        cfg.mainService=c_service_node('')
        header=cfg.mainService.getHeader()
          
        self._setAppHeader(TXT_MENU0_HOME,"",
            c_menu_block_items([
                (TXT_MENU0_BKG_DIR      ,cfg.BACKUP_DIRECTORY),
                (TXT_MENU0_TEMP         ,cfg.TEMP_DIRECTORY),
                (TXT_MENU0_DEFAULT_INSTANCE_FILENAME ,cfg.INSTANCE_INFO if cfg.INSTANCE_INFO else TX_OFF),
            ])
        )
        
        self.menu=[
            c_menu_title_label(TXT_MENU),
            c_menu_item(TXT_MENU0_EDIT,"e",menuEdit_select_nodeInstance()),
            c_menu_item(TXT_MENU0_BACKUP,"bkg",self.fullBackup),
            c_menu_item(TXT_MENU0_BACKUP_LIST,"bklst",self.delBackups),
        ]
        
        if not cfg.mainService.serviceFileExists():
            self.menu.append(c_menu_item(TXT_MENU0_SERVICE,"inst",self.makeServiceTemplate))
        else:
            if header.checkVersion(self.serviceVersion):
                self.menu.append(c_menu_item(TXT_MENU0_SERVICE_UPD,"upd",self.updateServiceTemplate))            
            self.menu.append(c_menu_item(TXT_MENU0_SERVICE_REM,"remove",self.removeServiceFile))
        
    def fullBackup(self,selItem:c_menu_item) -> onSelReturn:
        """
        Create a full 7z backup for all users.
        """
        if confirm(TXT_MENU0_RLY_MK+'?'):
            x=create_full_backup_for_all_users_7z()
            anyKey()
            return x
        
    def makeServiceTemplate(self,selItem:c_menu_item) -> onSelReturn:
        """
        Create a service template.
        """
        try:
            cfg.mainService.create(
                "Node-RED user instance %i",
                "/home/%i/node_instance/node_modules/node-red/bin/node-red-pi --max-old-space-size=128 -v -u",
                workingDirectory="/home/%i/",
                user="%i",
                group="users",
                next_service_params={
                    "SyslogIdentifier": "node-red-userInstance_%i",
                },
                next_unit_params={
                    "Description": "Node-RED user instance %i",
                    "ConditionPathExists": [
                        "/home/%i/muj-node-config.js",
                        "/home/%i/node_instance/node_modules/node-red/bin/node-red-pi",
                    ],
                },
                header=c_header(version=self.serviceVersion,author="dvestezar.cz (c) 2024",date="2024-11-03")
            )
        except Exception as e:
            log.error(TXT_ERROR+": %s")
            log.error()
            return onSelReturn(TXT_ERROR+": %s" % e)
        
        cfg.mainService.systemdRestart()
        return onSelReturn(ok=TXT_MENU0_serv_created)
        
    def removeServiceFile(self,selItem:c_menu_item) -> onSelReturn:
        """
        Remove the service file.
        """
        x=getSysUsers()
        if len(x) > 1:
            return TXT_MENU0_inst_count_err.format(num=len(x))        
        
        if confirm(TXT_MENU_rly_rem_tmpl):
            cfg.mainService.remove()
            cfg.mainService.systemdRestart()
            return onSelReturn(ok=TXT_MENU0_serv_removed)
        return onSelReturn()
    
    def updateServiceTemplate(self,selItem:c_menu_item) -> onSelReturn:
        """
        Update the service template.
        """
        if not confirm(TXT_MENU0_RLY_UPD):
            return onSelReturn()
        try:
            cfg.mainService.remove()
            return self.makeServiceTemplate(selItem)
        except Exception as e:
            log.error("Error: %s")
            log.error()
            return onSelReturn(TXT_ERROR+": %s" % e)
        
    def delBackups(self,selItem:c_menu_item) -> onSelReturn:
        """
        Delete backups.
        """
        from libs.app.backup import selectBackup,deleteBackup
        
        ok,p,fnm,errMsg=selectBackup(None,10,TXT_BKG_FOUND)
        if not ok and errMsg:
            return onSelReturn(err=errMsg)
        elif not ok and not errMsg:
            return
        elif ok:
            e=deleteBackup(None,fnm)
            if not e is None:
                return onSelReturn(err=e)
        print(TXT_BKG_DELETED.format(fnm=fnm,usr='.:HOME:.'))
        anyKey()        
