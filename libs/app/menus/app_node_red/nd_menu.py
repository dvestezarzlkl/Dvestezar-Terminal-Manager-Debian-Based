from .lng.default import * 
from libs.JBLibs.helper import loadLng
loadLng()

from libs.app.appHelper import menu as menuX

class nd_menu(menuX):
    appTitle:str = TXT_MAIN_NAME