from .lng.default import * 
from libs.JBLibs.helper import loadLng,getUserHome
loadLng()

import os
from libs.JBLibs.c_menu import c_menu_item,onSelReturn,c_menu_title_label
from libs.JBLibs.input import confirm,anyKey,get_port,get_input
from libs.JBLibs.term import text_inverse
from libs.app.appHelper import getHttps,existsSelfSignedCert
from libs.app.c_cfg import cfg_data
from libs.app.remove_instance import remove_node_instance
from libs.app.backup import backup_node_instance_for,checkBackups
from libs.app.c_service_node import c_service_node
from libs.app.instanceHelper import instanceCheck,copyKeyToUser,instanceVersion
from libs.app.install_instance import updateSettingsFileForUser
from .menu_data_classes import menu_data
from .menu_edit_node_instance_user import menuEdit_edit_nodeInstance_user
from .nd_menu import nd_menu
from libs.app.update_instance import update_instance_node_red

from libs.JBLibs.helper import getLogger
log = getLogger(__name__)

class menuEdit_edit_nodeInstance(nd_menu):
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
                
                
        self.menu.append(c_menu_item(TXT_MENU_INSTN_u_edit,"e",menuEdit_edit_nodeInstance_user(),
            data=menu_data(
                self.selectedSystemUSer,
                self.cfg,
                None
            )
        ))
        
        # instance
        bkgs=checkBackups(self.selectedSystemUSer)
        self.menu.append(c_menu_item(''))
        self.menu.append(c_menu_title_label(TXT_MENU_INSTN_SC_GEN))
        self.menu.extend([
            c_menu_item(TXT_MENU_INSTN_tit_ch,'t',self.change_title),
            c_menu_item(TXT_MENU_INSTN_p_ch,'p',self.change_port,atRight=str(self.cfg.port)),
            c_menu_item(TXT_MENU_INSTN_bkg,'b',self.backup_node_instance),
            c_menu_item(TXT_MENU_INSTN_bkg_del,'bs',self.backups,atRight=TXT_MENU_INSTN_bkg_del_c.format(cnt=bkgs)),
            c_menu_item(TXT_MENU_INSTN_set_upd,'cfg',self.updateSettingsFile),
            c_menu_item(TXT_MENU_INSTN_show_help,'cfgh',self.showCfgHelpFile),
            c_menu_item(TXT_MENU_PSINSR_REP,'dr',self.updateDirStruct),
        ])        

        # ssl
        self.menu.append(c_menu_title_label(TXT_MENU_INSTN_SC_HTTPS))
        if self.sslStatus==0:
            self.menu.append(c_menu_item(TXT_MENU_CREATE_CRT,'crtm',self.makeSelfCrt))
        elif self.sslStatus==2:
            self.menu.append(c_menu_item(TXT_MENU_CREATE_CRT_DIS,'crtd',self.delSelfCrt))
            
        if self.sslStatus >0:
            self.menu.append(c_menu_item(TXT_MENU_INSTN_ssl,'c',self.updateHttps))
        
        # service
        self.menu.append(c_menu_title_label(TXT_MENU_INSTN_SC_SERVICE))
        self.menu.append(c_menu_item(TXT_MENU_INSTN_sts,'x',self.service_status, atRight= self.cfg.service_status_tx()))        
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
        self.menu.append(c_menu_item(TXT_MENU_INSTN_app_run,'appsf',self.runAsAppSafe))
        
        last=[]
        if instanceCheck(self.selectedSystemUSer):
            last.append(c_menu_item(TXT_MENU_INSTN_s_upd,'u',self.update_instance))
            last.append(c_menu_item(TXT_MENU_INSTN_s_upd_lat,'ulatest',self.update_instance_latest))
            last.append(c_menu_item(TXT_MENU_INSTN_s_del,'delete',self.delete_instance))

        if self.cfg.changed:
            last.append(c_menu_item("!!!!  "+ text_inverse(TXT_SAVE),'s',self.save))
        else:
            last.append(c_menu_item(TXT_MENU_INSTN_f_save,'s',self.saveForce))
        
        if last:
            self.menu.append(c_menu_title_label(TXT_MENU_INSTN_SC_INSTANCE))
            self.menu.extend(last)
            
    def  update_instance_latest(self,selItem:c_menu_item) -> onSelReturn:
        """
        Update node instance for selected system user
        """
        from libs.JBLibs.term import cls
        if confirm(TXT_MENU_INSTN_s_upd_latQ,True):
            return update_instance_node_red(self.selectedSystemUSer,latest=True)
        cls()
    
    def  update_instance(self,selItem:c_menu_item) -> onSelReturn:
        """
        Update node instance for selected system user
        """
        return update_instance_node_red(self.selectedSystemUSer)
    
    def delete_instance(self,selItem:c_menu_item) -> onSelReturn:
        """
        Delete node instance for selected system user
        """
        try:
            x=remove_node_instance(self.selectedSystemUSer,noAnyKey=True)
            print(x)
        except Exception as e:
            log.error(TXT_MENU_INSTN_del_inst_Err, exc_info=True)
            print(TXT_MENU_INSTN_del_inst_Err+f": {e}")                    
        anyKey()
        return onSelReturn(endMenu=True)
    
    def change_title(self,selItem:c_menu_item) -> onSelReturn:
        """
        Change title for node instance
        """
        title = get_input(TXT_MENU_INSTN_ed_tit)
        if title != None:
            self.cfg.title = TXT_NODE+' '+title
            self.cfg.changed=True
    
    def change_port(self,selItem:c_menu_item) -> onSelReturn:
        """
        Change port for node instance
        """
        port = get_port()
        if port != None:
            try:
                self.cfg.port = int(port)
                self.cfg.changed=True
            except ValueError:
                print(TXT_MENU_INSTN_ed_port_err)
                anyKey()
            
    def service_status(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show node service status for selected system user
        """
        print(os.popen(f'sudo systemctl status {self.cfg.service.fullName}').read())
        anyKey()
    
    def backup_node_instance(self,selItem:c_menu_item) -> onSelReturn:
        """
        Backup node instance for selected system user
        """
        if confirm(TXT_MENU_INSTN_rly_bkg):
            err=backup_node_instance_for(self.selectedSystemUSer)
            print(err)
            anyKey()
            return err
    
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

    def updateHttps(self,selItem:c_menu_item) -> onSelReturn:
        """
        Update https for node instance
        """
        if confirm("Really update https ?"):
            if getHttps(self.selectedSystemUSer):
                if copyKeyToUser(self.selectedSystemUSer):
                    print(TXT_MENU_INSTN_ssl_u)
            elif existsSelfSignedCert(self.selectedSystemUSer):
                print(TXT_MENU_INSTN_ssl_uSelf)
            else:
                print(TXT_MENU_INSTN_ssl_uEr)
                pass
            self.cfg.save(True)
            anyKey()
            
    def makeSelfCrt(self,selItem:c_menu_item) -> onSelReturn:
        """
        Create self-signed certificate
        """
        
        if confirm(TXT_Q_RLY_CREATE_CRT):
            from libs.app.instanceHelper import generate_certificate
            generate_certificate(self.selectedSystemUSer)
            self.cfg.save(True)
            anyKey()
            
            
    def delSelfCrt(self,selItem:c_menu_item) -> onSelReturn:
        """
        Delete self-signed certificate
        """
        if confirm(TXT_Q_RLY_CREATE_CRT_DEL):
            from libs.app.instanceHelper import deleteSelfSignedCert
            deleteSelfSignedCert(self.selectedSystemUSer)
            self.cfg.save(True)
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
                
            # sudo -u user /home/user/node-red/node_modules/.bin/node-red
            path=getUserHome(self.selectedSystemUSer)
            # cmd sd to user home
            cmd=f'cd {path}'
            path = os.path.join(path,'node_instance/node_modules/node-red/bin/node-red-pi')
            cmd=cmd + f' && sudo -u {self.selectedSystemUSer} {path}'
            if safe:
                cmd=cmd + ' --safe'
            log.info(f"run as application: {cmd}")
            
            # run as user as application
            try:
                os.system(cmd)
            except:
                pass
            
            if active:
                self.cfg.service.start()
            anyKey()
            
    def updateSettingsFile(self,selItem:c_menu_item) -> onSelReturn:
        """
        Update settings.js file
        """
        if confirm(TX_Q_001):
            x=updateSettingsFileForUser(self.selectedSystemUSer)
            if x:
                print(x)
            else:
                print(TX_T_001)
            anyKey()
            
    def updateDirStruct(self,selItem:c_menu_item) -> onSelReturn:
        """
        Update directory structure like log dir
        """
        from libs.app.install_instance import postInstall
        if confirm(TX_Q_002.format(id=self.selectedSystemUSer)):
            try:
                postInstall(self.selectedSystemUSer)
            except Exception as e:
                print(ERR_PI_001.format(id=self.selectedSystemUSer,e=e))
                anyKey()
                return onSelReturn(endMenu=True)
                
            print(TX_T_001)
            anyKey()
        
    def backups(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show backups for node instance
        """
        from libs.app.backup import selectBackup,deleteBackup,checkBackupIntegrity,restoreBackupInstance
        
        while True:
            ok,p,fnm,errMsg=selectBackup(self.selectedSystemUSer,10,TXT_BKG_FOUND)
            if not ok and errMsg:
                return onSelReturn(err=errMsg)
            elif not ok and not errMsg:
                return
            elif ok:
                from libs.JBLibs.input import select_item,select
                
                items = []
                items.append(select_item('Delete backup', 'd'))
                items.append(select_item('Check integrity', 'c'))
                items.append(select_item('Restore backup', 'r'))
                items.append(select_item('Back', 'q'))
                
                any=True
                x = select('Select ', items)
                if not x.item:
                    log.warning("User cancelled the operation")
                    return False, None, None, None
                x=x.item.choice
                if x == 'd':
                    e=deleteBackup(self.selectedSystemUSer,fnm)
                    if not e is None:
                        return onSelReturn(err=e)
                    print(TXT_BKG_DELETED.format(fnm=fnm,usr=self.selectedSystemUSer))    
                elif x == 'c':
                    print(TXT_BKG_INT_CHECK.format(fnm=fnm))
                    x=checkBackupIntegrity(self.selectedSystemUSer,fnm)
                    if not x is None:
                        return onSelReturn(err=x)
                    print(TXT_BKG_INT_OK)
                elif x == 'r':
                    x=restoreBackupInstance(self.selectedSystemUSer,fnm)
                    # print('Not implemented yet')
                    if not x is None:
                        return onSelReturn(err=x)
                    anyKey()
                    return                    
                elif x == 'q':
                    any=False
                else:
                    print(TXT_BKG_INV_SEL)
                
                if any:
                    anyKey()
                    
    def showCfgHelpFile(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show configuration help file
        """
        from libs.JBLibs.term import cls
        from libs.JBLibs.helper import getAssetsPath
        pth=getAssetsPath(TXT_MENU_INSTN_cfg_help_fileName)
        if os.path.exists(pth):
            with open(pth,'r',encoding='utf-8') as f:
                cls()
                print(f.read())
                anyKey()
        else:
            print(TXT_MENU_INSTN_cfg_help_Err)
            anyKey()
                
    def onExitMenu(self):
        log.debug("- exit menuEdit_edit_nodeInstance")
        if self.cfg.changed:
            if confirm(TXT_SAVE, ):
                self.cfg.save()
                anyKey()
                