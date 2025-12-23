# Menu

`menuBoss.py` je hlavní menu které ve svém adresáři hledá adresáře se jménem začínající prefixem `app_`

V těchto adresářích se hledá jediný soubor `menu.py`

V souboru `menu.py` musí být:
    - definována property `_MENU_NAME_` která se zobrazí jako název menu v hlavním menu
    - definována class `menu` která je potomkem `c_menu` a která definuje samotné menu
    - class `menu` musí mít definován atribut `_VERSION_` který se zobrazí v hlavním menu jako verze menu

Pořadí načtení není case sensitive ale abecední, takže pokud chceme pracovat s více menu  
tak se doporučuje formát minimálně s dvěma čísly.

Pořadí lze určit názvem adresáře např. `app_01_example`, `app_02_example2`, atd.

V souboru `menu.py` je doporučeno používat funkci `basicTitle` pro vytvoření titulku menu.

Příklad použití:

```python
from libs.app.menus.menu import c_menu, c_menu_block_items,onSelReturn

_MENU_NAME_:str = "Example Menu"

def basicTitle(add:str|list=None, dir:str|Path|None=None) -> c_menu_block_items:
    return c_other.basicTitle(
        menuName=_MENU_NAME_,
        menuVer=menu._VERSION_,
        add=add,
        dir=dir
    )

class menu(c_menu):
    _VERSION_:str = "1.0.0"

    def onEnterMenu(self) -> None:
        """Inicializace menu, toto nastává jen při prvním vstupu do menu."""
        pass
    def onShowMenu(self) -> None:
        """Aktualizace menu, toto nastává při každém zobrazení menu."""
        self.title=basicTitle()
        self.subTitle=c_menu_block_items([
            ("Example Item","c"), # 'c' zarovná na střed
        ])
        self.menu=[
            c_menu_title_label("Example Menu"), # titulek sekce v menu vystředěný
            c_menu_item(
                text="Do something",
                choice="1",
                onSelect=self.do_something, # funkce která se zavolá po výběru položky
                data="Some data" # volitelná data předaná do funkce onSelect nebo submenu
            ),
            c_menu_item(
                text="Another submenu",
                choice="0",
                onSelect=c_another_menu(), # další menu, předá se mu data které je v onEnterMenu dostupné jako self._mData
                data={"key":"value"} # volitelná data předaná do funkce onEnterMenu nebo submenu jako `self._mData`
            ),
        ]

    def do_something(self,selItem:c_menu_item) -> None|onSelReturn:
        """Příklad funkce menu."""
        # pro návrat se doporučuje použít onSelReturn
        ret = onSelReturn()

        # pokud chceme vynutit překlreslení menu po návratu
        self.menuRecycle=True

        # pokud chceme po návratu z funkce ukončite menu
        ret.endMenu=True

        return ret # vše ok bez zprávy
        return ret.okRet("Zpráva pro uživatele") # vše ok se zprávou
        return ret.errRet("Chyba pro uživatele") # chyba se zprávou
```
