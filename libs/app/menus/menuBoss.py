from libs.JBLibs.c_menu import c_menu,c_menu_item,c_menu_title_label,onSelReturn
from libs.app.appHelper import menu
from typing import List
from libs.app import cfg
from libs.JBLibs.input import anyKey
import os,string

_items_:List[c_menu_item]=[]

class menuBoss(menu):
    """
    Main APPs menu
    """
    choiceBack=None
    ESC_is_quit=False
    titleShowMyIP=True
    titleShowTime=True
    appTitle="Apps Menu"
        
    def onEnterMenu(self):
        """
        Show menu
        """
        self.menu=[
            c_menu_title_label('Nalezené aplikace')
        ]
        self.menu.extend(_items_)
        self.menu.extend([
            None,
            c_menu_item('System info','i',self.showSystemInfo),
        ])
        
        # return onSelReturn(err="test err",ok="ok test")
        
    def onShowMenu(self):
        """
        Show menu
        """
        self._setAppHeader("HOME")
        
        if cfg.machineInfo.err:
            self.menu=[
                c_menu_title_label('Error machine info'),
                c_menu_title_label(cfg.machineInfo.err)
            ]
        else:
            self.afterTitle=[
                "Distro: "+cfg.machineInfo.operating_system,
                "Kernel: "+cfg.machineInfo.kernel,
                "FQDN: "+cfg.machineInfo.hostname_full,
            ]
        
    def showSystemInfo(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show system info
        """
        print(cfg.machineInfo)
        anyKey()
            

def init() -> bool:
    """
    Initialize menu
    """
    
    # Najde všechny adresáře odpovídající vzoru 'app_*' v aktuálním adresáři
    root=os.path.dirname(__file__)
    app_dirs = os.listdir(root)
    app_dirs = [d for d in app_dirs if os.path.isdir(os.path.join(root,d)) and d.startswith('app_')]
    app_dirs = [d for d in app_dirs if os.path.isfile(os.path.join(root,d,'menu.py')) ]
        
    choice_counter = 0  # Inicializujeme počítadlo pro volby
    
    for app_dir in app_dirs:        
        name = 'menu'
        fqn = f"libs.app.menus.{app_dir}.menu"
        try:
            # Naimportuje modul podle názvu souboru
            mod = __import__(fqn, globals(), locals(), [], 0)
            # Procházíme postupně celou cestu (e.g., libs.app.menus.menu0)
            components = fqn.split(".")
            for comp in components[1:]:
                mod = getattr(mod, comp)            
            if mod is None:
                # Pokud modul neexistuje, pokračujeme dál
                continue
            menu_class = getattr(mod, name)
            if menu_class is None:
                # Pokud třída neexistuje, pokračujeme dál
                continue
            
            # Zkontroluje, jestli modul obsahuje '_MENU_NAME_' a požadovanou třídu
            if hasattr(mod, '_MENU_NAME_') and issubclass(menu_class, c_menu):
                # Vytvoří volbu (choice) na základě počítadla
                if choice_counter < 26:
                    # Použijeme písmeno od 'a' do 'z'
                    choice = string.ascii_lowercase[choice_counter]
                else:
                    # Použijeme číslo, pokud jsme přesáhli počet písmen
                    choice = str(choice_counter - 26 + 1)
                
                # Přidá položku menu s dynamicky generovanou volbou
                _items_.append(c_menu_item(mod._MENU_NAME_, choice, menu_class()))
                
                choice_counter += 1  # Zvýšíme počítadlo pro další volbu
                
        except Exception as e:
            print(f"Error: {e}")
            # print exception to terminal
            import traceback
            traceback.print_exc()                        
    
    if choice_counter:    
        x=menuBoss().run()
        if x:
            if isinstance(x,str):
                print(f"Returned error: {x}")
            return False
        return True
    else:
        print("No menu items found. END")
        return False
