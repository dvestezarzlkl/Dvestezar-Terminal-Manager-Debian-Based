from libs.app.c_cfg import cfg_data,cfg_user

class menu_data:
    systemUserName:str=""
    cfg:cfg_data=None
    nodeUser:cfg_user=None
    
    def __init__(self,systemUserName:str,cfg:cfg_data,nodeUser:cfg_user=None):
        self.systemUserName=systemUserName
        self.cfg=cfg
        self.nodeUser=nodeUser