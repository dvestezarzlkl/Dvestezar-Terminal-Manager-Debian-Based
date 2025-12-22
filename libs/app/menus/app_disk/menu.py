from ....JBLibs.c_menu import c_menu,c_menu_title_label,c_menu_item,c_menu_block_items,onSelReturn
from ....JBLibs.format import bytesTx
from ....JBLibs.fs_utils import *
from ....JBLibs.fs_helper import c_fs_itm
from ....JBLibs.input import anyKey,selectDir,selectFile,confirm,select,select_item,get_input,inputCliSize
from ....JBLibs.helper import run
from pathlib import Path
from ....JBLibs.disk_shrink import shrink_disk,extend_disk_part_max as expand_disk
from ....JBLibs.term import text_color, en_color,reset
from libs.JBLibs import fs_smart_bkp as bkp
from datetime import datetime
from libs.JBLibs import fs_swap
from ....JBLibs.helper import getConfigPath
from ....app import g_def as defs

_MENU_NAME_:str = "Disk a Swap manager"
DISK_CFG:str = "settings.conf"

class disk_settings:
    MNT_DIR:str=Path("/mnt").resolve()
    BKP_DIR:str=Path("/var/backups").resolve()
    
    diskNames:dict[str,str]={}
    """Slovník pro mapování disků podle jejich PUUID na uživatelská jména."""
    
    # uloží komplet toto nastavení do souboru
    @staticmethod
    def save() -> None:
        fl=getConfigPath(
            configName=DISK_CFG,
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
            configName=DISK_CFG,
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

class c_other:

    @staticmethod
    def basicTitle(add:str|list=None, dir:str|Path|None=None) -> c_menu_block_items:
        """Vytvoří základní titulní blok pro menu.
        
        Returns:
            c_menu_block_items: titulní blok menu
        """
        if isinstance(dir, str):
            dir = Path(dir).resolve()
        if not isinstance(dir, (Path, type(None)) ):
            raise ValueError("dir musí být str nebo Path")
        
        header=c_menu_block_items(blockColor=en_color.BRIGHT_CYAN )
        header.append( ("Disk Tool",'c') )
        header.append("-")
        header.append(f"Verze: {menu._VERSION_}")
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
        addTimestamp:bool=False
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
        
        n = base / ("disk" if isDisk else "partition") / f"{dev.name}" / f"{tp}"
        if create and not n.is_dir():
            n.mkdir(parents=True, exist_ok=True)
            
        if not relative:
            return str(n)
        # vrátéme jen relativní cestu k BKP_DIR
        return str(n.relative_to(base))
        

class c_mountpointSelector:    
    def __init__(self, curDir:Path, minMenuWidth:int=80) -> None:
        self.curDir=curDir
        self.minMenuWidth=minMenuWidth
    
    __currMountPoint:Path|None=None
    
    @staticmethod        
    def _mp_sel_onShowMenuItem(itm:c_fs_itm,lText:str,rText:str) -> tuple[str,str]:
        """Funkce pro úpravu zobrazení položky v menu výběru zálohy disku.
        """
        p=Path(itm.path)
        # pokud je cesta dir a dir je empty tak označíme <OK>
        if p.is_dir() and not any(p.iterdir()):
            rText=text_color("<OK>", en_color.BRIGHT_GREEN)
        return (lText, rText)
    
    @staticmethod
    def _mountable(pth:Path) -> bool:
        """Funkce pro ověření jestli je cesta použitelná jako mountpoint.
        """        
        if not pth.is_dir():
            return False
        if any(pth.iterdir()):
            return False            
        return True
    
    @staticmethod
    def _mp_sel_onSelectMenuItem(pth:Path) -> Union[onSelReturn|None|bool]:
        """Funkce pro ověření výběru položky v menu výběru zálohy disku.
        """        
        if not c_mountpointSelector._mountable(pth):
            return onSelReturn(err="Vybraný adresář není platný prázdný adresář.")
        if chkMountpointUsed(pth):
            return onSelReturn(err="Vybraný adresář je již použit jako mountpoint.")
        return True # vše ok výběr je platný
    
    def run(self) -> Path|None:
        if self.__currMountPoint is not None:
            self.__currMountPoint=self.curDir
        while True:
            fs=selectDir(
                str(self.__currMountPoint) if self.__currMountPoint else self.curDir,
                minMenuWidth=self.minMenuWidth,
                message=["-",("Vyberte prázdný adresář pro připojení .img souboru","c"),"-"],
                onSelectItem=self._mp_sel_onSelectMenuItem,
                onShowMenuItem=self._mp_sel_onShowMenuItem
            )
            if fs is None:
                return None
            fsPath=Path(fs).resolve()
            self.__currMountPoint=fsPath
            return fsPath    

class c_partOper:    
    mount_selector:c_mountpointSelector|None=None
    
    @staticmethod
    def mount_partition(
        dev:str,
        minMenuWidth:int=80,
    ) -> None|onSelReturn:
        """Mountne partition disku nebo loop
        """
        ret = onSelReturn()
        
        dev=normalizeDiskPath(dev,False)       
        if c_partOper.mount_selector is None:            
            c_partOper.mount_selector=c_mountpointSelector(
                disk_settings.MNT_DIR,
                minMenuWidth=minMenuWidth
            )
        mnt=c_partOper.mount_selector.run()
        if mnt is None:
            ret.err="Zrušeno uživatelem."
            return ret
        try:
            devPath=normalizeDiskPath(dev,False)
            print(f"mount {devPath} {str(mnt)}")
            o,r,e=runRet(f"sudo mount {devPath} {str(mnt)}",False)
        except Exception as e:
            print(f"Chyba errCode: {r}, stderr: {e}")
            ret.err=f"Chyba při mountování {devPath} na {str(mnt)}: {e}"
            return ret
        if r != 0:
            print(f"Chyba errCode: {r}, stderr: {e}")
            ret.err=f"Chyba při mountování {devPath} na {str(mnt)}: {e}"
            return ret
        
        ret.ok=f"Partition {devPath} připojena na {str(mnt)}"
        return ret

    @staticmethod
    def umonunt_partition(
        dev:str,
    ) -> None|onSelReturn:
        """Umountne mountpoint disku nebo loop
        """
        ret = onSelReturn()
        
        # zjistíme diskname
        disk=getDiskByPartition(dev)
        diskName:str=""
        if disk is None:
            # může se jednat o lopop device bez disku
            disk = getDiskyByName(dev)
            if disk is None:
                ret.err=f"Nenalezen disk pro partition {dev}"
                return ret
        diskName=disk.name
        
        # voláme přímo umount na zadaný device
        try:
            devPath=normalizeDiskPath(dev,False)
            print(f"umount {devPath}")
            o,r,e = runRet(["sudo", "umount", devPath],False)
        except Exception as ex:
            print(f"Chyba errCode: {r}, stderr: {e}")
            ret.err=f"Chyba při umountování {devPath}: {ex}"
            return ret
        if r != 0:
            print(f"Chyba errCode: {r}, stderr: {e}")
            ret.err=f"Chyba při umountování {devPath}: {e}"
            return ret
        
        # zjistíme jestli existuje disk, u img přestane existovat
        di=getDiskyByName(diskName)
        if di is None:
            ret.ok="Partition umountnuta. Disk již neexistuje. Vracím se do předchozího menu."
            ret.endMenu=True
            return ret
        
        ret.ok=f"Partition {devPath} umountnuta."
        return ret
     

# ****************************************************
# ******************* MAIN MENU **********************
# ****************************************************


class menu(c_menu):
    """Menu pro utilitiy disku.
    """
    
    _VERSION_:str="3.0.0"
    
    # choiceBack=None
    # ESC_is_quit=False
    minMenuWidth=80
    
    curDir:Path|None
    
    def onEnterMenu(self) -> None:
        self.curDir=disk_settings.BKP_DIR
    
    def onShowMenu(self) -> None:

        self.title=c_other.basicTitle(dir=self.curDir)

        self.menu=[]
        self.menu.append( c_menu_title_label("Image Menu") )        
        self.menu.append( c_menu_item("Změň backup adresář", "b", self.changeBkpDir) )
        self.menu.append( c_menu_item("Změň mount adresář", "m", self.changeMntDir) )
        self.menu.append( c_menu_item("Connect .img file as loop device", "+", self.addImg) )
        self.menu.append( c_menu_item("SWAP manager", "-", m_swap_manager()) )
        
        ls=lsblk_list_disks(True)
        choice=0
        self.menu.append( c_menu_title_label( text_color("Select Disk", color=en_color.BRIGHT_CYAN)) )
        tit=f"{'Name':<15} | {'Size':>10} | {'Type':>8} | {'Partitions':>12} | {'Mountpoints':>12}"
        self.menu.append( c_menu_item(text_color(tit, color=en_color.BRIGHT_BLACK)) )
        self.menu.append( c_menu_item(text_color("-" * len(tit), color=en_color.BRIGHT_BLACK)) )
        for d in ls:
            di=ls[d]
            if di.type=="disk" and not di.children:
                continue
            
            part=len(di.children)
            if di.type=="loop" and di.mountpoints:
                # pokud je loop device a má mountpointy, tak se jedná o připojený image jako partition
                part="<img:>" + di.mountpoints[0] # stačí jen první mountpoint
            
            mps=len(di.mountpoints)
            if di.children:
                for p in di.children:
                    if p.mountpoints:
                        mps+=len(p.mountpoints)
            self.menu.append( c_menu_item(
                f"{di.name:<15} | {bytesTx(di.size):>10} | {di.type:>8} | {part:>12} | {mps if mps>0 else '-':>12}",
                f"{choice:02}",
                m_disk_oper(),
                data=di
            ))
            choice+=1
        
    def changeBkpDir(self,selItem:c_menu_item) -> None|onSelReturn:
        ret = onSelReturn()
        p=selectDir(
            disk_settings.BKP_DIR,
            minMenuWidth=self.minMenuWidth,
        )
        if p is None:
            ret.err="Zrušeno uživatelem."
            return ret
        self.curDir=p.resolve()
        disk_settings.BKP_DIR=self.curDir
        disk_settings.save()
        ret.ok=f"Aktuální adresář změněn na: {str(self.curDir)}"
        return ret
    
    def changeMntDir(self,selItem:c_menu_item) -> None|onSelReturn:
        ret = onSelReturn()
        p=selectDir(
            disk_settings.MNT_DIR,
            minMenuWidth=self.minMenuWidth,
        )
        if p is None:
            ret.err="Zrušeno uživatelem."
            return ret
        disk_settings.MNT_DIR=Path(p).resolve()
        disk_settings.save()
        ret.ok=f"Mount adresář změněn na: {str(disk_settings.MNT_DIR)}"
        return ret
    
    def addImg(self,selItem:c_menu_item) -> None|onSelReturn:
        ret = onSelReturn()
        fl=selectFile(
            str(self.curDir) if self.curDir else None,
            filterList=r".*\.img$",
            minMenuWidth=self.minMenuWidth,
        )
        if fl is None:
            ret.err="Zrušeno uživatelem."
            return ret
        fl=Path(fl).resolve()
        
        chk=chkImgFlUsed(fl)
        if chk.used:
            ret.err=f".img {str(fl)} soubor je již připojen nebo použit: {chk.device}"
            return ret

        m_image_oper(
            minMenuWidth=self.minMenuWidth,            
        ).run(c_menu_item(data=fl))
        
        return onSelReturn()

# ****************************************************
# ******************* DISK MENU **********************
# ****************************************************
    
class m_disk_oper(c_menu):
    """Menu pro vybraný disk.    
    """
    
    _mData:lsblkDiskInfo=None
    
    minMenuWidth=80
    
    diskName:str=""
    
    diskInfo:lsblkDiskInfo=None
    
    __loopPath:Path|None=None
    
    def onEnterMenu(self) -> None:
        self.diskName=self._mData.name
        nm=normalizeDiskPath(self.diskName,False)
        ls=getLoopImgInfo()
        if ls is not None:
            if nm in ls:
                self.__loopPath=ls[nm]
            else:
                self.__loopPath=None
        else:
            self.__loopPath=None
        
    def onShowMenu(self) -> None:
        
        self.diskInfo=getDiskyByName(self.diskName)
        disk=self.diskInfo
        if disk is None:
            raise ValueError(f"Nenalezen disk s názvem {self.diskName}")
        
        loopDev=disk.type=="loop"
        loopIsPartAndMounted=loopDev and disk.mountpoints

        self.title=c_other.basicTitle()
        self.subTitle=c_menu_block_items([
            (f"Disk",f"{disk.name}"),
            (f"Size",f"{bytesTx(disk.size)}"),
            (f"Type",f"{disk.type}"),
            (f"Image Path",f"{str(self.__loopPath) if self.__loopPath else '-'}"),
        ])
        self.menu=[]
                
        self.menu.append( c_menu_title_label(f"Disk Menu: {self.diskName}") )
        
        if loopDev:
            if not loopIsPartAndMounted:
                self.menu.append( c_menu_item("Odpoj celý loop dev", "d", self.detach_loop_device) )
            else:
                self.menu.append( c_menu_item("Připojeno jako partition, umount image", "u", self.umonunt_partition,data=disk.name) )                
        
        # záloha smart backup, parmagic, naše smart a raw zálohy atd.
        if not loopDev or (loopDev and not loopIsPartAndMounted):
            self.menu.append( c_menu_item("Zálohovat disk", "b", self.backup_disk) )
            self.menu.append( c_menu_item("Obnovit disk ze zálohy", "r", self.restore_disk) )
        
        if disk.children:
            self.menu.append( c_menu_title_label(text_color("Partitions", color=en_color.BRIGHT_CYAN)) )
            tit = f"{'Name':<15} | {'Size':>10} | {'Type':>8} | {'Filesystem':>12} | {'Mountpoint':>12}"
            self.menu.append( c_menu_item(text_color(tit, color=en_color.BRIGHT_BLACK)))
            self.menu.append( c_menu_item(text_color("-" * len(tit), color=en_color.BRIGHT_BLACK)))
            
            choice=0
            for part in disk.children:
                mp=len(part.mountpoints) if part.haveMountPoints else (part.mountpoints[0] if part.mountpoints else "-")
                fs_type=part.fstype if part.fstype else "-"
                imn=c_menu_item(f"{part.name:<15} | {bytesTx(part.size):>10} | {part.type:>8} | {fs_type:>12} | {mp:>12}")
                if part.type=="part" and part.fstype in ["ext4","ext3","ext2"] and not part.isSystemDisk:
                    imn.choice=f"{choice:02}"
                    imn.onSelect=m_disk_part()
                    imn.data=part
                    choice+=1
                    imn.atRight="menu"
                else:
                    imn.label=text_color(imn.label, color=en_color.BRIGHT_BLACK)
                    if part.isSystemDisk:
                        imn.atRight="systémová partition"
                    else:
                        imn.atRight="nelze spravovat"
                
                self.menu.append( imn )
        else:
            self.menu.append( c_menu_item("Disk neobsahuje žádné použitelné partitiony.") )
                         
    def umonunt_partition(self,selItem:c_menu_item) -> None|onSelReturn:
        """Umountne připojený image jako partition.
        """
        dev:lsblkDiskInfo=self.diskInfo
        if dev.type!="loop":
            return onSelReturn(err="Vybraný device není loop device.")
        
        pathImg:Path|None=self.__loopPath
        if pathImg is None:
            return onSelReturn(err="Cesta k .img souboru není známa.")
        if not pathImg.is_file():
            return onSelReturn(err=f".img soubor neexistuje: {str(pathImg)}")
        
        from libs.JBLibs.fs_smart_bkp import c_bkp_hlp
        print(f"Umounting loop device {dev.name} mounted as partition...")
        ret=c_partOper.umonunt_partition(dev.name)
        if ret is None:
            return onSelReturn(err="Neznámá chyba při umountování partition.")
        if not ret.ok:
            return ret
        print(text_color(f"Updating SHA256 sidecar for image {str(pathImg)}...", color=en_color.BRIGHT_YELLOW))
        c_bkp_hlp.update_sha256_sidecar(Path(pathImg), throwOnMissing=False )
        ret.endMenu=True # vracíme se o úroveň výš
        return ret        
                                
    def detach_loop_device(self,selItem:c_menu_item) -> None|onSelReturn:
        """Odpojí loop device a všechny jeho partitiony.
        """
        dev:lsblkDiskInfo=self.diskInfo
        if dev.type!="loop":
            return onSelReturn(err="Vybraný device není loop device.")
        
        print(f"Detaching loop device {dev.name} and its partitions...")
        loop=dev.name
        if dev and dev.children:
            for part in dev.children:
                if part.mountpoints:
                    mnt = normalizeDiskPath(part.name,False)
                    try:
                        print(f"umount {mnt}")
                        run(f"sudo umount {mnt}")
                    except Exception as e:
                        return onSelReturn(err=f"Chyba při umountování {mnt}: {e}")                        
        try:
            loop=normalizeDiskPath(loop,False)
            print(f"Detach {loop}")
            run(f"sudo losetup -d {loop}")
        except Exception as e:
            return onSelReturn(err=f"Chyba při odpojování {loop}: {e}")
        
        anyKey()
        return onSelReturn(endMenu=True) # je odpojen není možná další akce
    
    def backup_disk(self,selItem:c_menu_item) -> None|onSelReturn:
        """Zálohuje celý disk.
        """
        x=c_other.selectBkType(disk=True,minMenuWidth=self.minMenuWidth)
        if x is None:
            return onSelReturn(err="Zrušeno uživatelem.")
        l=c_other.selectCompressionLevel(minMenuWidth=self.minMenuWidth)
        if l is None:
            return onSelReturn(err="Zrušeno uživatelem.")
        typ, zkratka, popis, detail = x
        
        o_dir=c_other.get_bkp_dir(
            self.diskName,
            typZalohyChoice=zkratka,
            create=True,
            relative=False,
            addTimestamp=False
        )        
        print(f"Zálohuji disk {self.diskName} typem zálohy: {popis}")
        if zkratka=="s":
            return bkp.smart_backup(
                disk=self.diskName,
                outdir=o_dir,
                autoprefix=True,
                compression=bool(l>0),
                cLevel=l
            )
            
        elif zkratka=="j":
            return bkp.smart_backup(
                disk=self.diskName,
                outdir=o_dir,
                autoprefix=True,
                compression=bool(l>0),
                cLevel=l,
                ddOnly=True
            )
        elif zkratka=="r":
            return bkp.raw_backup(
                disk=self.diskName,
                outdir=o_dir,
                autoprefix=True,
                compression=bool(l>0),
                cLevel=l
            )
                    
        else:
            return onSelReturn(err="Zrušeno uživatelem.")
        
    @staticmethod        
    def restore_disk_onShowMenuItem(itm:c_fs_itm,lText:str,rText:str) -> tuple[str,str]:
        """Funkce pro úpravu zobrazení položky v menu výběru zálohy disku.
        """
        p=Path(itm.path)
        # pokud obsahuje manifest tak jej lze vybrat, tak změníme rText
        manifestFile=p / "manifest.json"
        if manifestFile.is_file():
            rText=text_color("<BKP>", en_color.BRIGHT_GREEN)
        return (lText, rText)
    
    @staticmethod
    def restore_disk_onShowMenuItem2(pth:Path) -> Union[onSelReturn|None|bool]:
        """Funkce pro ověření výběru položky v menu výběru zálohy disku.
        """
        manifestFile=pth / "manifest.json"
        if not manifestFile.is_file():
            return onSelReturn(err="Vybraný adresář neobsahuje platnou zálohu disku (chybí manifest.json).")
        return True # vše ok výběr je platný
                
    def restore_disk(self,selItem:c_menu_item) -> None|onSelReturn:
        """Obnoví celý disk ze zálohy.
        """
        # select adresář se zálohou
        bkpDir=selectDir(
            str(disk_settings.BKP_DIR),
            minMenuWidth=self.minMenuWidth,
            message=["-",("Vyberte adresář se zálohou disku","c"),"-"],
            onShowMenuItem=self.restore_disk_onShowMenuItem,
            onSelectItem=self.restore_disk_onShowMenuItem2
        )
        if bkpDir is None:
            return onSelReturn(err="Zrušeno uživatelem.")
        bkpDir=Path(bkpDir).resolve()
        x=bkp.restore_disk(
            disk=self.diskName,
            bkpdir=bkpDir
        )
        if not x.ok:
            print(text_color(f"Chyba při obnově disku: {x.err}", color=en_color.BRIGHT_RED))
            anyKey()
        return x

# ****************************************************
# ******************* IMAGE MENU *********************
# ****************************************************
# rozšiřuje funkčnost na image soubory které může připojit, testovat sidecar, opravit/vytvořit sidecar
# bere .img a img.7z na 7z není možnost připojit jako loop device jako u img

class image_nfo:
    file:Path
    used:bool
    device:str
    size:bytesTx
    mtime:datetime|None
    def __init__(self,file:Path) -> None:
        if not isinstance(file, Path):
            raise ValueError("file musí být Path")
        self.file=file.resolve()
        if not self.file.is_file():
            raise ValueError(f"file musí být existující soubor: {str(self.file)}")
        if not self.file.suffix.lower() in [".img"]:
            raise ValueError("file musí být .img")
        self.size=bytesTx(self.file.stat().st_size)
        self.mtime=datetime.fromtimestamp(self.file.stat().st_mtime)
        x=chkImgFlUsed(self.file)
        self.used=x.used
        self.device=normalizeDiskPath(x.device,True) if x.device else ""

class m_image_oper(c_menu):
    """Menu pro vybraný image soubor.
    """
    
    selectedImage:Path=None
    nfoImage:image_nfo=None
    minMenuWidth=80
    
    def onEnterMenu(self) -> None:
        x:Path=self._mData
        self.selectedImage=x.resolve()
        if not self.selectedImage.is_file():
            raise ValueError(f"Vybraný image soubor neexistuje: {str(self.selectedImage)}")
        
    def onShowMenu(self) -> None:
        self.nfoImage=image_nfo(self.selectedImage)        
        
        cesta=Path(self.selectedImage).parent.resolve()
        
        self.title=c_other.basicTitle()
        self.title.append( ("Image Utility",'c') )
        self.subTitle=c_menu_block_items([
            (f"Image File",f"{self.selectedImage.name}"),
            (f"Cesta",f"{str(cesta)}"),
            (f"Velikost",f"{self.nfoImage.size}"),
            (f"Poslední změna",f"{self.nfoImage.mtime.strftime('%Y-%m-%d %H:%M:%S')}"),
            (f"Použitý",f"{'Ano, ' + self.nfoImage.device if self.nfoImage.used else 'Ne'}"),
        ])
        
        self.menu=[]
        
        self.menu.append( c_menu_title_label(f"Image Menu: {self.selectedImage.name}") )
        self.menu.append( c_menu_item("Připojit .img soubor jako loop device", "m", self.mount_image) )
        self.menu.append( c_menu_item("Ověřit sidecar soubor", "t", self.test_sidecar) )
        self.menu.append( c_menu_item("Vytvořit/opravit sidecar soubor", "c", self.create_sidecar) )
        
    def mount_image(self,selItem:c_menu_item) -> None|onSelReturn:
        """Mountne image soubor jako loop device
        """
        ret = onSelReturn()
        fl=self.selectedImage.resolve()
        chk=chkImgFlUsed(fl)
        if chk.used:
            ret.err=f".img {str(fl)} soubor je již připojen nebo použit: {chk.device}"
            return ret
        
        print(f"Připojuji .img soubor jako loop device: {str(fl)}")
        try:
            mps=c_mountpointSelector(disk_settings.MNT_DIR, self.minMenuWidth)
            loopDev=mountImageAsLoopDevice(fl, mps.run)
            ret.ok=f".img soubor připojen jako loop device: {loopDev}"
        except Exception as e:
            ret.err=f".img soubor se nepodařilo připojit: {e}"

        ret.endMenu=True # po připojení se vracíme o úroveň výš
        return ret
    
    def test_sidecar(self,selItem:c_menu_item) -> None|onSelReturn:
        """Ověří sidecar soubor pro image.
        """
        ret = onSelReturn()
        from libs.JBLibs.fs_smart_bkp import c_bkp_hlp
        try:
            chk=c_bkp_hlp.verify_sha256_sidecar(self.selectedImage)
        except Exception as e:
            ret.err=f"Chyba při ověřování sidecar souboru: {e}"
            return ret
        if chk is True:
            ret.ok="Sidecar soubor je platný."
        else:
            print(text_color(f"Sidecar soubor není platný: {chk.err}", color=en_color.BRIGHT_RED,inverse=True,bold=True))
            if confirm("Přejete si opravit sidecar soubor nyní?"):
                try:
                    c_bkp_hlp.update_sha256_sidecar(self.selectedImage, throwOnMissing=False )
                    ret.ok="Sidecar soubor byl opraven."
                except Exception as e:
                    ret.err=f"Chyba při opravě sidecar souboru: {e}"
            else:
                ret.err="Sidecar soubor není platný."
        return ret
    
    def create_sidecar(self,selItem:c_menu_item) -> None|onSelReturn:
        """Vytvoří nebo opraví sidecar soubor pro image.
        """
        ret = onSelReturn()
        from libs.JBLibs.fs_smart_bkp import c_bkp_hlp
        
        sidecarPath=self.selectedImage.with_suffix(self.selectedImage.suffix + ".sha256")
        if sidecarPath.is_file():
            print(f"Sidecar soubor již existuje: {str(sidecarPath)}. Bude přepsán.")
            if not confirm("Pokračovat?"):
                ret.err="Zrušeno uživatelem."
                return ret
            # remove existing sidecar
            sidecarPath.unlink()
        try:
            c_bkp_hlp.write_sha256_sidecar(self.selectedImage)
            ret.ok=f"Sidecar soubor byl vytvořen nebo opraven."
        except Exception as e:
            ret.err=f"Chyba při vytváření/opravě sidecar souboru: {e}"
        return ret


# ****************************************************
# ******************* PARTITION MENU *****************
# ****************************************************

class m_disk_part(c_menu):
    """Menu pro vybranou partition disku.    
    """    
    
    selectedPartition:str=None
    minMenuWidth=80
    partInfo:lsblkDiskInfo=None
    diskInfo:lsblkDiskInfo=None
    fsInfo:fsInfo_ret|None=None
        
    def onEnterMenu(self) -> None:
        x:lsblkDiskInfo=self._mData
        self.selectedPartition=x.name
        if x.type != "part":
            raise ValueError(f"Vybraná partition není typu 'part', ale '{x.type}'")
    
    def onShowMenu(self) -> None:
        partNfo=getPartitionInfo(self.selectedPartition)
        if partNfo is None:
            raise ValueError(f"Nenalezena partition s názvem {self.selectedPartition}")
        
        self.diskInfo=getDiskByPartition(self.selectedPartition)        
        self.partInfo=partNfo
        self.fsInfo=getFsInfo(self.selectedPartition)
        
        self.title=c_other.basicTitle()
        self.subTitle=c_menu_block_items([
            (f"Partition",f"{partNfo.name}"),
            (f"Label",f"{partNfo.label}"),
        ])
        
        isMounted=bool(partNfo.mountpoints)
        
        self.menu=[]
        
        self.menu.append( c_menu_title_label(f"Partition Menu: {partNfo.name}") )
        if isMounted:        
            self.menu.append( c_menu_item("Umount Partition", "u", self.umonunt_partition) )
        else:
            self.menu.append( c_menu_item("Mount Partition", "m", self.mount_partition) )
        
        self.menu.append( c_menu_title_label("Disk Utilities") )
        if not isMounted:
            if partNfo.fstype in ["ext4","ext3","ext2"]:
                self.menu.append( c_menu_item(f"Zkontroluj partition {partNfo.fstype}", "c", self.check_partition) )
            else:
                self.menu.append( c_menu_item("Kontrola disku není podporována pro tento filesystem.",atRight=f"{partNfo.fstype}") )
            self.menu.append( c_menu_item("Shrink Disk", "s", self.shrink_disk) )
            self.menu.append( c_menu_item("Expand Disk", "e", self.expand_disk) )
            self.menu.append( c_menu_item("-" ) )
            self.menu.append( c_menu_item("Zálohovat partition", "b", self.backup_partition) )
            self.menu.append( c_menu_item("Obnovit partition ze zálohy", "r", self.restore_partition) )
        else:
            self.menu.append( c_menu_item("Nelze provést operaci na připojené partition.") )
            
        partIsLAst:bool=False
        if self.diskInfo and self.diskInfo.children:
            if self.diskInfo.children[-1].name == partNfo.name:
                partIsLAst=True
        aTit=c_menu_block_items()
        aTit.append( ("Disk",f"{self.diskInfo.name}, size {bytesTx(self.diskInfo.size)} počet partition: {len(self.diskInfo.children) if self.diskInfo.children else 0}" ) )
        aTit.append( ("Partition",f"{partNfo.name}, size {bytesTx(partNfo.size)}, type: {partNfo.type}, fstype: {partNfo.fstype if partNfo.fstype else '-'}" ) )
        aTit.append( ("Filesystem",f"{self.fsInfo.fsType if self.fsInfo else '-'}, size: {bytesTx(self.fsInfo.total) if self.fsInfo else '-'} , used: {bytesTx(self.fsInfo.used) if self.fsInfo else '-'}" ) )
        aTit.append( ("Mount status",f"{'připojena' if isMounted else 'nepřipojena'}" ) )
        aTit.append( ("Poslední na disku",f"{'ano' if partIsLAst else 'ne'}" ) )
        
        # přidáme afterMenu seznam mountpountů
        if partNfo.mountpoints:
            aTit.append( "." )
            aTit.append( ("Mountpoints:", "") )
            for mp in partNfo.mountpoints:
                aTit.append( (f"- {mp}", "") )
            aTit.append( "." )
        self.afterTitle=aTit
    
    def mount_partition(self,selItem:c_menu_item) -> None|onSelReturn:
        """Mountne partition disku nebo loop
        """
        return c_partOper.mount_partition(
            self.selectedPartition,
            minMenuWidth=self.minMenuWidth
        )
        
    def umonunt_partition(self,selItem:c_menu_item) -> None|onSelReturn:
        """Umountne mountpoint disku nebo loop
        """
        return c_partOper.umonunt_partition(
            self.selectedPartition,
        )

    def check_partition(self,selItem:c_menu_item) -> None|onSelReturn:
        """Zkontroluje partition disku nebo loop
        """
        ret = onSelReturn()
        try:
            err=checkExt4(self.selectedPartition)
            if err is not None:
                ret.err=err
                return ret
            ret.ok=f"Kontrola partition {self.selectedPartition} proběhla úspěšně."
            anyKey() # má to výstup tak počkáme na uživatele ať si to může přečíst
        except Exception as e:
            ret.err=f"Chyba při kontrole partition {self.selectedPartition}: {e}"
            return ret
        
    def shrink_disk(self,selItem:c_menu_item) -> None|onSelReturn:
        """Shrink disk
        """
        ret = onSelReturn()
        if confirm(f"Opravdu chcete shrinknout partition {self.selectedPartition}?","c"):            
            try:
                ret = shrink_disk(self.selectedPartition,spaceSizeQuestion=True)
                if ret.endMenu:
                    ret.endMenu=False
                else:
                    print(ret.ok if ret.ok else ret.err)
                    anyKey()
            except Exception as e:
                ret.err=f"Chyba při shrinkování partition {self.selectedPartition}: {e}"
                print(ret.err)                
            anyKey()
        else:
            ret.err="Zrušeno uživatelem."
        return ret
    
    def expand_disk(self,selItem:c_menu_item) -> None|onSelReturn:
        """Expand disk
        """
        ret = onSelReturn()
        if confirm(f"Opravdu chcete expandnout partition {self.selectedPartition}?","c"):
            try:
                ret = expand_disk(self.selectedPartition)
                if ret.endMenu:
                    ret.endMenu=False
                else:
                    print(ret.ok if ret.ok else ret.err)
                    anyKey()
            except Exception as e:
                ret.err=f"Chyba při expandování partition {self.selectedPartition}: {e}"
                print(ret.err)                
                anyKey()
        else:
            ret.err="Zrušeno uživatelem."
        return ret
    
    def backup_partition(self,selItem:c_menu_item) -> None|onSelReturn:
        """Zálohuje partition disku.                
        """
        # vybereme typ zálohy
        x=c_other.selectBkType(disk=False,minMenuWidth=self.minMenuWidth)
        if x is None:
            return onSelReturn(err="Zrušeno uživatelem.")
        l=c_other.selectCompressionLevel(minMenuWidth=self.minMenuWidth)
        if l is None:
            return onSelReturn(err="Zrušeno uživatelem.")
        
        typ, zkratka, popis, detail = x
        o_dir=Path(c_other.get_bkp_dir(
            self.selectedPartition,
            typZalohyChoice=zkratka,
            create=True,
            relative=False,
            addTimestamp=False
        ))
        prefix=datetime.now().strftime("%Y-%m-%d_%H%M%S_bkptp-{}")
        print(text_color(f"Zálohuji partition {self.selectedPartition} typem zálohy: {popis}", color=en_color.BRIGHT_CYAN))
        if zkratka=="s":
            bkp.c_bkp.backup_partition_image(
                devName=self.selectedPartition,
                folder=o_dir,
                prefix=prefix,
                compression=bool(l>0),
                cLevel=l
            )            
        elif zkratka=="r":
            bkp.c_bkp.backup_partition_image(
                devName=self.selectedPartition,
                folder=o_dir,
                prefix=prefix,
                compression=bool(l>0),
                cLevel=l,
                ddOnly=True
            )            
        else:
            return onSelReturn(err="Zrušeno uživatelem.")
        
        return onSelReturn(ok=f"Partition {self.selectedPartition} byla úspěšně zálohována.")

    
    def restore_partition(self,selItem:c_menu_item) -> None|onSelReturn:
        """Obnoví partition disku ze zálohy.
        """
        # select image souboru se zálohou
        bkpImg=selectFile(
            str(disk_settings.BKP_DIR),
            filterList=r".*\.(img|7z)$",
            minMenuWidth=self.minMenuWidth,
            message=["-",("Vyberte .img soubor se zálohou partition","c"),"-"],
        )
        if bkpImg is None:
            return onSelReturn(err="Zrušeno uživatelem.")
        
        print(text_color(f" Všechna data na této {self.selectedPartition} partition budou ztracena! ", color=en_color.BRIGHT_RED, inverse=True,bold=True))
        if not confirm(f"Opravdu chcete obnovit partition {self.selectedPartition} ze zálohy {bkpImg}?"):
            return onSelReturn(err="Zrušeno uživatelem.")
        
        print(text_color(f"Obnovuji partition {self.selectedPartition} ze zálohy: {bkpImg}", color=en_color.BRIGHT_CYAN))
        bkpImg=Path(bkpImg)
        # otestujeme jestli má soubor sha256 sidecar
        sha256Sidecar=bkpImg.with_suffix(bkpImg.suffix + ".sha256")
        if not sha256Sidecar.is_file():
            if not confirm(f"Nenalezena sha256 sidecar pro zálohu {str(bkpImg)}. Pokračovat i přesto?","c"):
                return onSelReturn(err="Zrušeno uživatelem.")
        else:
            try:
                if not bkp.c_bkp_hlp.verify_sha256_sidecar(bkpImg):
                    return onSelReturn(err=f"Chyba ověření sha256 sidecar pro zálohu {str(bkpImg)}: kontrolní součet neodpovídá.")
            except Exception as e:
                return onSelReturn(err=f"Chyba při ověřování sha256 sidecar pro zálohu {str(bkpImg)}: {e}")
        
        print(text_color(f"Obnovuji partition {self.selectedPartition} ze zálohy: {bkpImg}", color=en_color.BRIGHT_YELLOW))
        try:
            bkp.c_bkp.restore_partition_image(
                part_dev=self.selectedPartition,
                image_file=bkpImg.resolve()
            )
        except Exception as e:
            return onSelReturn(err=f"Chyba při obnově partition {self.selectedPartition}: {e}")
        return onSelReturn(ok=f"Partition {self.selectedPartition} byla úspěšně obnovena ze zálohy.")

from libs.JBLibs import fs_swap as swp

class m_swap_manager(c_menu):
    """Menu pro správu SWAP souborů
    """
    
    minMenuWidth=80
    
    def onShowMenu(self) -> None:
        self.title=c_other.basicTitle()
        self.title.append( ("SWAP Manager",'c') )
        
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
                s:fs_swap.swap_info
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
         
        return fs_swap.swap_mng.create_swap_img(
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
        self.title=c_other.basicTitle()
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
        return fs_swap.swap_mng.modifySizeSwapFile(
            self.selectedImage.file,
            x.inBytes
        )
    
    def remove_swap(self,selItem:c_menu_item) -> None|onSelReturn:
        if not confirm(text_color(f" Opravdu chcete odebrat SWAP image {self.selectedImage.file}? ", color=en_color.BRIGHT_RED,inverse=True,bold=True)):
            return onSelReturn(err="Zrušeno uživatelem.")
        
        print(f"Odebírám SWAP image {self.selectedImage.file}...")
        x=fs_swap.swap_mng.remove_swap_img(self.selectedImage.file)
        x:onSelReturn
        x.endMenu=True # po odebrání se vracíme o úroveň výš
        return x
