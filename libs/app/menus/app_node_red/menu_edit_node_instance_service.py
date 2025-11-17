from .lng.default import * 
from libs.JBLibs.helper import loadLng,getUserHome
loadLng()

import os
from libs.JBLibs.c_menu import c_menu_item,onSelReturn,c_menu_title_label
from libs.JBLibs.input import confirm,anyKey,get_port,get_input
from libs.app.appHelper import getHttps,existsSelfSignedCert
from libs.app.c_cfg import cfg_data
from libs.app.remove_instance import remove_node_instance
from libs.app.backup import backup_node_instance_for
from libs.app.c_service_node import c_service_node
from libs.app.instanceHelper import copyKeyToUser,instanceVersion
from libs.app.install_instance import updateSettingsFileForUser
from .menu_data_classes import menu_data
from .menu_edit_node_instance_user import menuEdit_edit_nodeInstance_user
from .nd_menu import nd_menu
from libs.app.update_instance import update_instance_node_red

from libs.JBLibs.helper import getLogger
log = getLogger(__name__)

class menuEdit_edit_nodeInstance_service(nd_menu):
    """ edituje instanci nudou podle vybraného systémového uživatele """
    
    cfg:cfg_data=None
    selectedSystemUSer:str=""    
    choiceQuit=None    
    afterMenu=TXT_MENU_INSTN_afterMenu

    def onEnterMenu(self):
        log.debug("- enter menuEdit_edit_nodeInstance")
        self.selectedSystemUSer=self._runSelItem.data
        self.cfg=cfg_data(self._runSelItem.data)

    def onShowMenu(self):
        ver = instanceVersion(self.selectedSystemUSer)
        
        self._setAppHeader(TXT_MENU_INSTN_editNodeInst,               
            TXT_MENU_INSTN_editNodeInst2,
            "Node-Red v:"+ver,
            self.selectedSystemUSer,
            self.cfg.port,
            None,
            self.cfg.title
        )
                
        self.menu=[]            
        service=self.cfg.service
        status=service.status()
        if not isinstance(service,c_service_node):
            raise Exception(TXT_MENU_INSTN_noInit+" "+self.selectedSystemUSer)                
                               
        # service
        self.menu.append(c_menu_title_label(TXT_MENU_INSTN_SC_SERVICE))
        self.menu.append(c_menu_item(TXT_MENU_INSTN_sts,'x',self.service_status, atRight= self.cfg.service_status_tx()))
        self.menu.append(c_menu_item(TXT_MENU_INSTN_log,'l',self.show_log))
        if service.running(status):
            self.menu.append(c_menu_item(TXT_MENU_INSTN_s_stop,'o',self.service_stop))
            self.menu.append(c_menu_item(TXT_MENU_INSTN_s_res,'r',self.service_restart))
        else:
            self.menu.append(c_menu_item(TXT_MENU_INSTN_s_start,'o',self.service_start))
            
        if not service.enabled(status):
            self.menu.append(c_menu_item(TXT_MENU_INSTN_s_ena,'ena',self.enableNodeService))
        else:
            self.menu.append(c_menu_item(TXT_MENU_INSTN_s_dis,'dis',self.disableNodeService))
            
        self.menu.append(c_menu_item(TXT_MENU_INSTN_app_run,'app',self.runAsApp))
        self.menu.append(c_menu_item(TXT_MENU_INSTN_app_run_safe,'sf',self.runAsAppSafe))        
                            
    def service_status(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show node service status for selected system user
        """
        print(os.popen(f'sudo systemctl status {self.cfg.service.fullName}').read())
        anyKey()
    
    
    def service_start(self,selItem:c_menu_item) -> onSelReturn:
        """
        Start node service for selected system user
        """
        self.cfg.service.start()
        if not self.cfg.service.running():
            print(TXT_MENU_INSTN_s_rs_1)
        else:
            print(TXT_MENU_INSTN_s_rs_2)
        anyKey()
    
    def service_stop(self,selItem:c_menu_item) -> onSelReturn:
        """
        Stop node service for selected system user
        """
        self.cfg.service.stop()
        if self.cfg.service.running():
            print(TXT_MENU_INSTN_s_st_1)
        else:
            print(TXT_MENU_INSTN_s_st_2)
        anyKey()

    def disableNodeService(self,selItem:c_menu_item) -> onSelReturn:
        """
        Disable node service for selected system user
        """
        if confirm(TXT_MENU_INSTN_s_dis_q):
            self.cfg.service.disable()
            if self.cfg.service.enabled():
                print(TXT_MENU_INSTN_s_dis_1)
            else:
                print(TXT_MENU_INSTN_s_dis_2)
            anyKey()
            
    def enableNodeService(self,selItem:c_menu_item) -> onSelReturn:
        """
        Enable node service for selected system user
        """
        if confirm(TXT_MENU_INSTN_s_ena_q):
            self.cfg.service.enable()
            if not self.cfg.service.enabled():
                print(TXT_MENU_INSTN_s_ena_1)
            else:
                print(TXT_MENU_INSTN_s_ena_2)
            anyKey()
        
    def save(self,selItem:c_menu_item) -> onSelReturn:
        if confirm(TXT_SAVE):
            self.cfg.save()
            anyKey()
            
    def saveForce(self,selItem:c_menu_item) -> onSelReturn:
        if confirm(TXT_SAVE):
            self.cfg.save(True)
            anyKey()
            
    def service_restart(self,selItem:c_menu_item) -> onSelReturn:
        if confirm(TXT_MENU_INSTN_s_res_q):
            self.cfg.restart_service(True)
            anyKey()
                        
    def runAsAppSafe(self,selItem:c_menu_item) -> onSelReturn:
        self.runAsApp(selItem,True)
            
    def runAsApp(self,selItem:c_menu_item,safe:bool=False) -> onSelReturn:
        """
        Run node instance as application
        """
        if confirm("Really run as application ? Service will be stopped and started after application is closed."):
            active=self.cfg.service.running()
            if active:
                self.cfg.service.stop()

            opak:bool=True
            txMode="SAFE MODE" if safe else "NORMAL MODE"
            while opak: # safe opakujem dokud potvrdíme volbou y
                
                # sudo -u user /home/user/node-red/node_modules/.bin/node-red
                path=getUserHome(self.selectedSystemUSer)
                # cmd sd to user home
                cmd=f'cd {path}'
                if safe:
                    path = os.path.join(path,'node_instance/node_modules/node-red')
                    # kvůli problémům se scriptem pi spouštíme přímo: /usr/bin/env node "${SCRIPT_PATH}"/../red.js --safe
                    cmd=cmd + f' && sudo -u {self.selectedSystemUSer} /usr/bin/env node "{path}/red.js" --safe'
                else:
                    path = os.path.join(path,'node_instance/node_modules/node-red/bin/node-red-pi')
                    cmd=cmd + f' && sudo -u {self.selectedSystemUSer} {path}'
                log.info(f"run as application in {txMode}: {cmd}")
                print(f"run in {txMode} cmd: {cmd}")
                
                # run as user as application
                try:
                    os.system(cmd)
                except:
                    pass
                
                if confirm(f"Do you want to restart in {txMode} again ?",False):
                    # clear screen
                    from libs.JBLibs.term import cls
                    cls()
                else:
                    opak=False
                    print(f"Exiting {txMode}.")
                
            if active:
                self.cfg.service.start()
            
    def onExitMenu(self):
        log.debug("- exit menuEdit_edit_nodeInstance")
        if self.cfg.changed:
            if confirm(TXT_SAVE, ):
                self.cfg.save()
                anyKey()
                
    def show_log(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show node service log for selected system user
        """
        cmd=f'sudo journalctl -f -u {self.cfg.service.fullName} -n 50'
        os.system(cmd)
        print()
        anyKey()
