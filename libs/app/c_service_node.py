from libs.JBLibs.systemdService import c_service
import os

class c_service_node(c_service):
    """Spec třída inicializující c_service pro šablonu node-red instanci"""
    
    def __init__(self, templateName = None):
        serviceName = "node-red-userInstance"
        super().__init__(serviceName, templateName)
        
    def exists(self)->bool:
        if not self._templateName:
            return self.existsFile()
        
        p=os.path.join('/home/',self._templateName)
        if not os.path.exists(p):
            return False
        
        p=os.path.join(p,'muj-node-config.js')
        return os.path.exists(p)
        