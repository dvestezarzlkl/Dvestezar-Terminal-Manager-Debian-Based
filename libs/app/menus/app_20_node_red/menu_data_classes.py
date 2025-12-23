from libs.app.c_cfg import cfg_data,cfg_user

class menu_data:
    """ data class pro předávání dat mezi menu """
    
    systemUserName:str
    """ název systémového uživatele (instance) """
    
    cfg:cfg_data
    """ konfigurace instance """
    
    nodeUser:cfg_user
    """ konfigurace uživatele instance """
    
    def __init__(self,systemUserName:str,cfg:cfg_data,nodeUser:cfg_user=None):
        self.systemUserName=systemUserName
        self.cfg=cfg
        self.nodeUser=nodeUser