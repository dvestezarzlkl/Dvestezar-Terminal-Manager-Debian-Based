from pathlib import Path
from datetime import datetime
from libs.JBLibs.term import en_color, text_color
from libs.JBLibs.input import select, select_item
from libs.JBLibs.c_menu import c_menu_block_items
from libs.JBLibs.fs_utils import lsblkDiskInfo, getDiskByPartition, getDiskyByName
from libs.app import g_def as defs
from libs.JBLibs.helper import getConfigPath

__isINIT__:bool=False
class disk_settings:        
    MNT_DIR:str=Path("/mnt").resolve()
    BKP_DIR:str=Path("/var/backups").resolve()
    
    diskNames:dict[str,str]={}
    """Slovník pro mapování disků podle jejich PUUID na uživatelská jména."""
    
    # uloží komplet toto nastavení do souboru
    @staticmethod
    def save() -> None:
        fl=getConfigPath(
            configName=defs.DISK_CFG,
            appName=defs.APP_NAME,
            fromEtc=defs.CONFIG_ETC,
            createIfNotExist=True
        )
        
        # pokud neexistuje adresář vytvoříme jej
        if not fl.parent.is_dir():
            fl.parent.mkdir(parents=True, exist_ok=True)
            
        # převedeme tento objekt na json
        import json
        data={
            "MNT_DIR": str(disk_settings.MNT_DIR),
            "BKP_DIR": str(disk_settings.BKP_DIR),
            "diskNames": disk_settings.diskNames
        }
        with fl.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            
    # načte komplet toto nastavení ze souboru
    @staticmethod
    def load() -> None:        
        fl=getConfigPath(
            configName=defs.DISK_CFG,
            appName=defs.APP_NAME,
            fromEtc=defs.CONFIG_ETC,
            createIfNotExist=True
        )
        
        if not fl.is_file():
            return
        import json
        with fl.open("r", encoding="utf-8") as f:
            data=json.load(f)
        if "MNT_DIR" in data:
            disk_settings.MNT_DIR=Path(data["MNT_DIR"]).resolve()
        if "BKP_DIR" in data:
            disk_settings.BKP_DIR=Path(data["BKP_DIR"]).resolve()
        if "diskNames" in data:
            disk_settings.diskNames=data["diskNames"]
            
    @staticmethod
    def find_disk_name(puuid:str) -> str|None:
        """Najde uživatelské jméno disku podle jeho PUUID.
        
        Parameters:
            puuid (str): PUUID disku
            
        Returns:
            str|None: Uživatelské jméno disku nebo None pokud není nalezeno
        """
        if puuid in disk_settings.diskNames:
            return disk_settings.diskNames[puuid]
        return None
    
    @staticmethod
    def set_disk_name(puuid:str, name:str) -> None:
        """Nastaví uživatelské jméno disku podle jeho PUUID.
        
        Parameters:
            puuid (str): PUUID disku
            name (str): Uživatelské jméno disku
        """
        disk_settings.diskNames[puuid]=name
        disk_settings.save()
        
    @staticmethod
    def init() -> None:
        global __isINIT__
        if not __isINIT__:
            disk_settings.load()
            __isINIT__=True

class c_other:

    @staticmethod
    def basicTitle(menuName:str,menuVer:str,add:str|list=None, dir:str|Path|None=None) -> c_menu_block_items:
        """Vytvoří základní titulní blok pro menu.
        
        Returns:
            c_menu_block_items: titulní blok menu
        """
        if isinstance(dir, str):
            dir = Path(dir).resolve()
        if not isinstance(dir, (Path, type(None)) ):
            raise ValueError("dir musí být str nebo Path")
        
        header=c_menu_block_items(blockColor=en_color.BRIGHT_CYAN )
        header.append( (menuName,'c') )
        header.append("-")
        header.append(f"Verze: {menuVer}")
        if dir is not None:
            header.append( ("Aktuální backup dir", f"{str(disk_settings.BKP_DIR)}") )
            header.append( ("Aktuální mount dir", f"{str(disk_settings.MNT_DIR)}") )
        
        if isinstance(add, str):
            header.append( add )
        elif isinstance(add, list):
            header.extend( add )
        elif add is None:
            pass
        else:
            raise ValueError("Vstup musí být str nebo list")
        
        return header
    
    @staticmethod
    def selectBkType(disk:bool=True,minMenuWidth:int=80) -> tuple[str,str,str,str]|None:
        """Zobrazí menu pro výběr typu zálohy.
        
        Args:
            minMenuWidth (int): Minimální šířka menu.
        
        Returns:
            tuple[str,str,str,str] Vybraný typ zálohy ( typ, zkratka, popis, detail ).
            None znamená zrušení uživatelem.
        """
        if not isinstance(disk, bool):
            raise ValueError("disk musí být bool")
        
        ls=[
            ("d","s","Smart Backup","Inteligentní záloha pomocí partmagic, tzn partitiony a metadata,\n - nejmenší možná velikost s použitím komprese"),
            ("d","j","Raw Smart Backup","Záloha partitionů (dd) a rozložení disku pomocí manifestu\n - s možností komprese\n - bez komprese lze mountnout img jako partition\n - při použití shrink je potřeba pouze volné místo součtu partitionů"),
            ("d","r","Raw Backup","Bitová kopie pomocí dd s možností komprese\nToto je jeden img celého disku\n - bez komprese lze mountnout jako celý disk\n - bez komporese je nutné mít volné místo jako je velikost celého disku"),
            ("p","s","Smart Backup","Záloha pomocí partmagic, největší možná komprese."),
            ("p","r","Raw Backup","Bitová kopie pomocí dd s možností komprese\n - Bez komprese lze mountnout jako partition\n - je potřeba mít volné místo velikosti partition"),
        ]
        
        if disk:
            tta=[ (i[2] , i[3] ) for i in ls if i[0]=="d"]
            opt=[ select_item(i[2],i[1], i ) for i in ls if i[0]=="d" ]
        else:
            # texty pro partition
            tta=[ (i[2] , i[3] ) for i in ls if i[0]=="p"]
            opt=[ select_item(i[2],i[1], i ) for i in ls if i[0]=="p" ]
 
        from libs.JBLibs.term import text_color, en_color
        tt=c_menu_block_items(rightBrackets=False)
        tt.append(( text_color(" Výběr typu zálohy: ",color=en_color.BRIGHT_YELLOW,inverse=True),"c"))
        tt.append("-")
        st=c_menu_block_items()
        for ttai in tta:
            ltx,rtx=ttai
            if ltx:
                ltx = text_color(ltx, en_color.BRIGHT_CYAN)
            st.append((ltx, rtx))
            st.append("")
        st.append(".")
                
        x=select(
            "Vyberte typ zálohy:",
            opt,
            minMenuWidth,
            tt,
            st
        )
        if x is None or x.item is None:
            return None
        return x.item.data
    
    @staticmethod
    def selectCompressionLevel(minMenuWidth:int=80) -> int|None:
        """Zobrazí menu pro výběr kompresní úrovně.
        
        Args:
            minMenuWidth (int): Minimální šířka menu.
        
        Returns:
            int: Vybraná kompresní úroveň (0-9).
            None znamená zrušení uživatelem.
        """
        opt=[]
        for i in range(0,10):
            desc=""
            if i==0:
                desc="Žádná komprese"
            elif i==3:
                desc="Rychlá komprese"
            elif i==7:
                desc="Vyvážená komprese"
            elif i==9:
                desc="Maximální komprese, nejpomalejší"
            if desc!="":
                opt.append( select_item(f"{desc}", str(i), i) )
        
        x=select(
            "Vyberte úroveň komprese (0-9):",
            opt,
            minMenuWidth
        )
        if x is None:
            return None
        return x.item.data
    
    def get_bkp_dir(
        _dev:str,
        typZalohyChoice:str,
        create:bool=True,
        relative:bool=True,
        addTimestamp:bool=False,
        realName:str|None=None        
    )->str:
        """Vrátí název adresáře pro zálohu disku nebo partition relativně k BKP_DIR
        
        Parameters:
            _dev (str): název disku nebo partition
            typZalohyChoice (str): typ zálohy "s"=smart, "j"=jb, "r"=raw
            create (bool): vytvořit adresář pokud neexistuje
            relative (bool): vrátit relativní cestu k BKP_DIR, jinak vratí absolutní cestu
            addTimestamp (bool): přidat časové razítko jako podadresář
        
        Returns:
            str: cesta k adresáři pro zálohu, relativní k BKP_DIR        
        """        
        dev=getDiskyByName(_dev)
        
        if realName is None or not isinstance(realName, str):
            realName = _dev
        
        isDisk=False
        if dev:
            if dev.type=="disk" or dev.type=="loop":
                isDisk=True
        if not isDisk:
            dev=getDiskByPartition(_dev)
            if dev is None:
                raise ValueError(f"Nenalezen disk nebo partition pro {_dev}")
        base = Path(disk_settings.BKP_DIR)
        tp=None
        if typZalohyChoice == "s":
            tp="smart"
        elif typZalohyChoice=="j":
            tp="jb"
        elif typZalohyChoice=="r":
            tp="raw"
        else:
            raise ValueError(f"Nepodporovaný typ zálohy: {typZalohyChoice}")
        
        if addTimestamp:
            timestamp=datetime.now().strftime("%Y%m%d_%H%M%S")
            tp=Path(tp) / timestamp
        
        n = base / ("disk" if isDisk else "partition") / f"{realName}" / f"{tp}"
        if create and not n.is_dir():
            n.mkdir(parents=True, exist_ok=True)
            
        if not relative:
            return str(n)
        # vrátíme jen relativní cestu k BKP_DIR
        return str(n.relative_to(base))
        
    @staticmethod
    def getDiskDisplayName(disk:lsblkDiskInfo)->str|None:
        """Vrátí uživatelské jméno disku podle jeho PUUID.
        
        Parameters:
            disk (lsblkDiskInfo): objekt disku
            
        Returns:
            str : name + Uživatelské jméno disku nebo None pokud není nalezeno    
        """
        disk_name_display = disk.name + " "
        user_name=disk_settings.find_disk_name(disk.ptuuid)
        if user_name:
            disk_name_display += text_color(user_name,color=en_color.BRIGHT_CYAN)
        else:
            disk_name_display += text_color("-unnamed-",color=en_color.BRIGHT_BLACK)
        return disk_name_display 

    @staticmethod
    def reset_machine_id(partInfo: lsblkDiskInfo) -> str|None:
        """Zkontroluje jestli je disk mountlý, pokud ano a má jen jeden mount tak se pokusí resetovat jeho machine-id,
        což je užitečné pro klony RPi a OPi, které mají stejné machine-id a tím pádem stejné UUID disků, a tprotože se
        MAC generuje z UUID disku, tak mají všechny klony stejné MAC adresy, což může způsobovat problémy při připojování k síti
        Reset se provede smazáním machineid souborů, provede se touch v etc/machine-id, následně je vytvořena služba,
        která díky nulovému obsahu vygeneruje nové machine-id, tzn
        v `mountPoint.../etc/systemd/system` vytvoří `reset-machine-id-firstboot.service` s obsahem:
        ```
        [Unit]
        Description=Reset machine-id on first boot
        ConditionFirstBoot=yes

        [Service]
        Type=oneshot
        ExecStart=/usr/bin/systemd-machine-id-setup

        [Install]
        WantedBy=multi-user.target
        ```
        a následně se služba povolí vytvořením symlinku, který ale musí být relativní
        `ln -s ../reset-machine-id-firstboot.service /mnt/x/etc/systemd/system/multi-user.target.wants/reset-machine-id-firstboot.service`
        
        ```sh
        rm -f /mnt/x/etc/machine-id
        rm -f /mnt/x/var/lib/dbus/machine-id
        touch /mnt/x/etc/machine-id        
        ```
    
        Args:
            diskInfo (lsblkDiskInfo): informace o disku, který chceme resetovat
            
        Returns:
            str|None: chybová hláška pokud se nepodařilo resetovat, None pokud se reset povedl
    
        """
        if not partInfo.mountpoints:
            return "Disk není připojený, nelze resetovat machine-id"
        if len(partInfo.mountpoints)>1:
            return "Disk má více mountů, nelze resetovat machine-id"
        mountPoint=Path(partInfo.mountpoints[0])
        if not mountPoint.is_dir():
            return "Mount point není adresář, nelze resetovat machine-id"
        
        # smažeme machine-id soubory
        machine_id_path = mountPoint / "etc/machine-id"
        dbus_machine_id_path = mountPoint / "var/lib/dbus/machine-id"
        if machine_id_path.is_file():
            machine_id_path.unlink()
        if dbus_machine_id_path.is_file():
            dbus_machine_id_path.unlink()
            
        # vytvoříme prázdný machine-id pro vygenerování nového
        (mountPoint / "etc/machine-id").touch()
        # vytvoříme službu pro reset machine-id
        service_content ="""[Unit]
Description=Reset machine-id on first boot
ConditionFirstBoot=yes

[Service]
Type=oneshot
ExecStart=/usr/bin/systemd-machine-id-setup

[Install]
WantedBy=multi-user.target
        """
        service_path = mountPoint / "etc/systemd/system/reset-machine-id-firstboot.service"
        with service_path.open("w", encoding="utf-8") as f:
            f.write(service_content)
        # povolíme službu vytvořením relativního symlinku
        wants_dir = mountPoint / "etc/systemd/system/multi-user.target.wants"
        if not wants_dir.is_dir():
            wants_dir.mkdir(parents=True, exist_ok=True)
        symlink_path = wants_dir / "reset-machine-id-firstboot.service"
        if not symlink_path.is_symlink():
            symlink_path.symlink_to("../reset-machine-id-firstboot.service")
            
        return None