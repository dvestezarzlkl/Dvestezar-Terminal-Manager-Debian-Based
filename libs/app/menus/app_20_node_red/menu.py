from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu_item,onSelReturn,c_menu_block_items,c_menu_title_label
from libs.JBLibs.input import confirm,anyKey
from libs.JBLibs.term import text_color,en_color
from libs.JBLibs.systemdService import c_header
from libs.app.backup import create_full_backup_for_all_users_7z
from .menu_sel_node_instance import menuEdit_select_nodeInstance
from libs.app.c_service_node import c_service_node
from libs.app.appHelper import getSysUsers
from libs.app import cfg
from .nd_menu import nd_menu
from libs.app.instanceHelper import getNodeJsVersion, LATEST_LTS_MAJOR, nodeJsInstall, nodeJsUpdate, nodeJsUpdateActualMajorMinor, getNodeSourceVersion, update_global_npm, nodeJsDelete

from libs.JBLibs.helper import getLogger
log = getLogger(__name__)

_MENU_NAME_:str = TXT_MAIN_NAME

class menu (nd_menu):
    # own
    serviceVersion="1.1.1"
    
    # protected c_menu
    choiceBack=None
    ESC_is_quit=True  
    
    def __init__(self):
        super().__init__()
        self.serviceVersion=self.serviceVersion
        
    def onShowMenu(self):
        """
        Show the main menu.
        """
        cfg.mainService=c_service_node('')
        header=cfg.mainService.getHeader()
        
        nodeVer,isGlobal, fVer=getNodeJsVersion()
        candidatMajor,candidat=getNodeSourceVersion()
        
          
        self._setAppHeader(TXT_MENU0_HOME,"",
            c_menu_block_items([
                (TXT_MENU0_BKG_DIR      ,cfg.BACKUP_DIRECTORY),
                (TXT_MENU0_TEMP         ,cfg.TEMP_DIRECTORY),
                (TXT_MENU0_DEFAULT_INSTANCE_FILENAME ,cfg.INSTANCE_INFO if cfg.INSTANCE_INFO else TX_OFF),
            ])
        )
        
        self.menu=[]
        
        if nodeVer==0 or isGlobal==False:
            # není nainstalovaná globální verze
            self.menu.extend([
                c_menu_title_label(TXT_NODEJS_NOTEXISTS),
                c_menu_item(text_color(TXT_NODEJS_LATEST_GLOB.format(ver=LATEST_LTS_MAJOR),color=en_color.GREEN),"llts",self.installGlobLatest)
            ])
        else:
            # je instalovaná verze
            self.menu.append(c_menu_title_label(TXT_NODEJS_IS_INSTALLED.format(ver=nodeVer,fver=fVer)))
            if nodeVer < LATEST_LTS_MAJOR:
                # je nainstalovaná verze nižší než LTS
                if (LATEST_LTS_MAJOR - nodeVer) >= 2:
                    self.menu.append(c_menu_item(text_color(TXT_NODEJS_UPDATE_MAJOR.format(ver=nodeVer+1),color=en_color.GREEN),"upmaj",self.updateGlobNodeJs))
                self.menu.append(c_menu_item(text_color(TXT_NODEJS_LATEST_GLOB.format(ver=LATEST_LTS_MAJOR),color=en_color.YELLOW),"llts",self.installGlobLatest))
            else:
                # updated není potřeba
                self.menu.append(c_menu_item(text_color(TXT_NODEJS_IS_FRESH,color=en_color.BRIGHT_BLACK)))
                # update minor verze
                self.menu.append(c_menu_item(text_color(TXT_NODEJS_UPDATE.format(ver=candidat),color=en_color.YELLOW),"updt",self.updateGlobNodeJsMinor))
                
            # přidáme npm update, když je nainstalovaný Node.js a je globální
            self.menu.append(c_menu_item(text_color(TXT_MENU0_NPM_UPD,color=en_color.BRIGHT_BLUE),"npmup",self.npmUpdateGlob))
            
            # uninstall globální verze
            self.menu.append(c_menu_item(text_color(TXT_NODEJS_UNINSTALL,color=en_color.RED),"uninst",self.uninstallGlobNodeJs))
            
        self.menu.append(c_menu_item(TXT_NODEJS_HELP_MN,"hlp",self.nodeJsHelp))        
        self.menu.extend(
            [
                c_menu_title_label(TXT_MENU),
                c_menu_item(text_color(TXT_MENU0_EDIT,color=en_color.BRIGHT_CYAN),"e",menuEdit_select_nodeInstance()),
                c_menu_item(TXT_MENU0_BACKUP,"bkg",self.fullBackup),
                c_menu_item(TXT_MENU0_BACKUP_LIST,"bklst",self.delBackups),
            ]
        )
        
        if not cfg.mainService.serviceFileExists():
            self.menu.append(c_menu_item(text_color(TXT_MENU0_SERVICE,color=en_color.BRIGHT_YELLOW),"inst",self.makeServiceTemplate))
        else:
            if header.checkVersion(self.serviceVersion):
                self.menu.append(c_menu_item(text_color(TXT_MENU0_SERVICE_UPD,color=en_color.BRIGHT_YELLOW),"upd",self.updateServiceTemplate))            
            self.menu.append(c_menu_item(text_color(TXT_MENU0_SERVICE_REM,color=en_color.RED),"remove",self.removeServiceFile))
     
    def uninstallGlobNodeJs(self,selItem:c_menu_item) -> onSelReturn:
        """
        Uninstall the global Node.js installation.
        """
        nodeVer,isGlobal,strVer=getNodeJsVersion()
        if nodeVer <= 0 or not isGlobal:
            return onSelReturn(err=TXT_NODEJS_NOTEXISTS)

        if not confirm(TXT_NODEJS_UNINSTALL+'?'):
            return onSelReturn(err=TXT_CANCELED_U)

        purge=False
        if confirm(TXT_NODEJS_UNINSTALL_PURGE_Q):
            purge=True

        ok,msg=nodeJsDelete(purge)
        anyKey()
        if ok:
            return onSelReturn(ok=msg)
        
        return onSelReturn(err=msg)
     
    def npmUpdateGlob(self,selItem:c_menu_item) -> onSelReturn:
        """
        Update npm for the global Node.js installation.
        """
        if not confirm(TXT_MENU0_NPM_UPD+'?'):
            return onSelReturn(err=TXT_CANCELED_U)
        
        nodeVer,isGlobal,strVer=getNodeJsVersion()
        if nodeVer <= 0 or not isGlobal:
            return onSelReturn(err=TXT_NODEJS_NOTEXISTS)

        msg=update_global_npm()
        anyKey()
        if msg:
            return onSelReturn(err=msg)
        return onSelReturn()
     
    def nodeJsHelp(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show help for Node.js installation.
        """
        from libs.JBLibs.term import cls
        
        cls()
        print(TXT_NODEJS_HELP_INFO)
        anyKey()
        
    def updateGlobNodeJsMinor(self,selItem:c_menu_item) -> onSelReturn:
        """Update global Node.js to the latest minor version."""
        if not confirm(TXT_NODEJS_UPDATE.format(ver='latest')+'?'):
            return onSelReturn(err=TXT_CANCELED_U)
        
        ok, msg = nodeJsUpdateActualMajorMinor()
        anyKey()
        
        if ok:
            return onSelReturn(ok=msg)        
        return onSelReturn(err=msg)

    def updateGlobNodeJs(self,selItem:c_menu_item) -> onSelReturn:
        """Update global Node.js to the next major version."""        
        nodeVer,isGlobal,strVer=getNodeJsVersion()
        if nodeVer <= 0 or not isGlobal:
            return onSelReturn(err=TXT_NODEJS_NOTEXISTS)

        if not confirm(TXT_NODEJS_UPDATE_MAJOR.format(ver=nodeVer+1)+'?'):
            return onSelReturn(err=TXT_CANCELED_U)

        ok,msg=nodeJsUpdate(False)
        anyKey()
        if ok:
            return onSelReturn(ok=msg)
        
        return onSelReturn(err=msg)

    def installGlobLatest(self,selItem:c_menu_item) -> onSelReturn:
        """Install or update the global Node.js to the recommended LTS version."""
        if not confirm(TXT_NODEJS_LATEST_GLOB_Q.format(ver=LATEST_LTS_MAJOR)):
            return onSelReturn(err=TXT_CANCELED_U)

        nodeVer,isGlobal,strVer=getNodeJsVersion()
        if nodeVer > 0 and isGlobal:
            ok,msg=nodeJsUpdate(True)
        else:
            ok,msg=nodeJsInstall(LATEST_LTS_MAJOR)

        anyKey()
        if ok:
            return onSelReturn(ok=msg)
        
        return onSelReturn(err=msg)
        
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
