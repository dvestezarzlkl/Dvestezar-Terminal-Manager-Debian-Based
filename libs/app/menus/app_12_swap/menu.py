from pathlib import Path
from libs.JBLibs import fs_swap as swp
from libs.JBLibs.c_menu import (
    c_menu,
    c_menu_item,
    c_menu_title_label,
    c_menu_block_items,
    onSelReturn,
)
from libs.app.disk_hlp import c_other,disk_settings
from libs.JBLibs.input import (
    get_input,
    confirm,
    reset,
    inputCliSize,
    anyKey,
    text_color,
    en_color
)

def basicTitle(add:str|list=None, dir:str|Path|None=None) -> c_menu_block_items:
    return c_other.basicTitle(
        menuName=_MENU_NAME_,
        menuVer=menu._VERSION_,
        add=add,
        dir=dir
    )

_MENU_NAME_:str = "Swap manager"

class menu(c_menu):
    """Menu pro správu SWAP souborů
    """
    
    _VERSION_:str="2.5.0"
    
    minMenuWidth=80
    
    def onEnterMenu(self) -> None:
        disk_settings.init()
    
    def onShowMenu(self) -> None:
        mem_nfo=swp.getCurMemInfo()
        
        self.title=basicTitle()
        self.subTitle=c_menu_block_items([
            (text_color("Total Memory", color=en_color.BRIGHT_BLUE),text_color(f"{mem_nfo.mem_total}", color=en_color.BRIGHT_BLUE)),
            ("Free Memory",f"{mem_nfo.mem_available}"),
            ("Used Memory",f"{mem_nfo.mem_used} {mem_nfo.mem_usage_percent:.2f}%"),
            (text_color("Total SWAP", color=en_color.BRIGHT_BLUE),text_color(f"{mem_nfo.swap_total}", color=en_color.BRIGHT_BLUE)),
            ("Free SWAP",f"{mem_nfo.swap_free}"),
            ("Used SWAP",f"{mem_nfo.swap_used} {mem_nfo.swap_usage_percent:.2f}%"),
        ])
        
        
        self.menu=[]
        self.menu.append( c_menu_title_label("SWAP Manager") )
        self.menu.append( c_menu_item("Přidat SWAP image", "a", self.create_swap_img) )
        self.menu.append( c_menu_item("Ukaž procesy využívající SWAP", "p", self.show_swap_processes) )
        
        self.menu.append( c_menu_title_label(text_color("Aktivní SWAP image", color=en_color.BRIGHT_CYAN) ) )
        lst=swp.getListOfActiveSwaps()
        if not lst:
            self.menu.append( c_menu_item( text_color("Žádná aktivní SWAP image.",color=en_color.BRIGHT_RED) ) )
        else:
            tit=f"{'Device':<26} | {'Type':>8} | {'Size':>8} | {'Used':>8} | {'Priority':>8}"
            self.menu.append( c_menu_item( text_color(tit, color=en_color.BRIGHT_BLACK) ) )
            self.menu.append( c_menu_item( text_color("-" * len(tit), color=en_color.BRIGHT_BLACK) ) )
            choice:int=0
            for s in lst:
                used=f"{s.used:>8}"
                s:swp.swap_info
                uset_proc= round( int(s.used) / int(s.size) * 100 , 2) 
                if uset_proc > 80:
                    used=text_color(used, color=en_color.BRIGHT_RED)
                elif uset_proc > 50:
                    used=text_color(used, color=en_color.BRIGHT_YELLOW)
                else:
                    used=text_color(used, color=en_color.BRIGHT_GREEN)
                
                itm= c_menu_item(
                    f"{str(s.file):<26} | {s.type:>8} | {s.size:>8} | {used} | {s.priority:>8}"
                )
                itm.choice=f"{choice:02}"
                itm.onSelect=m_swap_img_mngr()
                itm.data=s
                itm.atRight="menu"
                self.menu.append( itm )
                choice+=1
                
    def create_swap_img(self,selItem:c_menu_item) -> None|onSelReturn:
        ret = onSelReturn()
        reset()
        flnm=get_input(
            "Zadejte název pro nový SWAP .img soubor, bez přípony",
            minMessageWidth=self.minMenuWidth,
        )
        flnm = Path("/") / flnm
        flnm=flnm.with_suffix(".img")
        if flnm.is_file():
            return ret.errRet(f"SWAP .img soubor již existuje: {str(flnm)}")
         
        return swp.swap_mng.create_swap_img(
            flnm,
            None,
            minMessageWidth=self.minMenuWidth
        )
        
    def show_swap_processes(self,selItem:c_menu_item) -> None|onSelReturn:
        ret = onSelReturn()
        from libs.JBLibs.fs_swap_nfo import print_table
        try:
            print_table()
        except Exception as e:
            return ret.errRet(f"Chyba při získávání procesů využívajících SWAP: {e}")
        anyKey()
        return ret
            

class m_swap_img_mngr(c_menu):
    """Menu pro správu vybraného SWAP .img souboru
    """
    
    minMenuWidth=80
    selectedImage:swp.swap_info=None
    
    def onEnterMenu(self) -> None:
        x:swp.swap_info=self._mData
        self.selectedImage=x
    
    def onShowMenu(self) -> None:
        self.title=basicTitle()
        self.title.append( ("SWAP Image Manager",'c') )
        self.subTitle=c_menu_block_items([
            (f"SWAP Device",f"{self.selectedImage.file}"),
            (f"Type",f"{self.selectedImage.type}"),
            (f"Size",f"{self.selectedImage.size}"),
            (f"Used",f"{self.selectedImage.used}"),
            (f"Priority",f"{self.selectedImage.priority}"),
        ])
        
        self.menu=[]
        self.menu.append( c_menu_title_label(f"SWAP Image Menu: {self.selectedImage.file}") )
        self.menu.append( c_menu_item(text_color("Odebrat SWAP image", color=en_color.BRIGHT_RED), "r", self.remove_swap) )
        self.menu.append( c_menu_item("Změnit velikost SWAP .img souboru", "s", self.resize_swap_img) )
            
    def resize_swap_img(self,selItem:c_menu_item) -> None|onSelReturn:
        ret = onSelReturn()
        reset()
        x = inputCliSize(
            "100MB",
            minMessageWidth=self.minMenuWidth
        )
        if x is None:
            return ret.errRet("Zrušeno uživatelem.")
        
        print(f"Měním velikost SWAP .img souboru {self.selectedImage.file} na {x}...")
        self.menuRecycle=True
        return swp.swap_mng.modifySizeSwapFile(
            self.selectedImage.file,
            x.inBytes
        )
    
    def remove_swap(self,selItem:c_menu_item) -> None|onSelReturn:
        if not confirm(text_color(f" Opravdu chcete odebrat SWAP image {self.selectedImage.file}? ", color=en_color.BRIGHT_RED,inverse=True,bold=True)):
            return onSelReturn(err="Zrušeno uživatelem.")
        
        print(f"Odebírám SWAP image {self.selectedImage.file}...")
        x=swp.swap_mng.remove_swap_img(self.selectedImage.file)
        x:onSelReturn
        x.endMenu=True # po odebrání se vracíme o úroveň výš
        return x
