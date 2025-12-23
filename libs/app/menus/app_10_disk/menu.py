from pathlib import Path
from datetime import datetime
from libs.JBLibs import fs_smart_bkp as bkp
from libs.JBLibs.c_menu import c_menu,c_menu_title_label,c_menu_item,c_menu_block_items,onSelReturn
from libs.JBLibs.disk_shrink import shrink_disk,extend_disk_part_max as expand_disk
from libs.JBLibs.format import bytesTx
from libs.JBLibs.fs_utils import *
from libs.JBLibs.fs_helper import c_fs_itm
from libs.JBLibs.helper import run
from libs.JBLibs.input import anyKey,selectDir,selectFile,text_color,en_color,get_input,confirm
from libs.app.disk_hlp import disk_settings,c_other
from libs.JBLibs.helper import getLogger
log = getLogger("disk_mng")

_MENU_NAME_:str = "Disk manager"

def basicTitle(add:str|list=None, dir:str|Path|None=None) -> c_menu_block_items:
    return c_other.basicTitle(
        menuName=_MENU_NAME_,
        menuVer=menu._VERSION_,
        add=add,
        dir=dir
    )

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
    
    _VERSION_:str="3.5.0"
    
    # choiceBack=None
    # ESC_is_quit=False
    minMenuWidth=80
    
    curDir:Path|None
    
    def onEnterMenu(self) -> None:
        try:
            disk_settings.init()
            self.curDir=disk_settings.BKP_DIR
        except Exception as e:
            log.error(f"Chyba při inicializaci disk settings: {e}")
            log.exception(e)
            raise e
    
    def onShowMenu(self) -> None:
        try:
            self.title=basicTitle(dir=self.curDir)

            self.menu=[]
            self.menu.append( c_menu_title_label("Image Menu") )        
            self.menu.append( c_menu_item("Změň backup adresář", "b", self.changeBkpDir) )
            self.menu.append( c_menu_item("Změň mount adresář", "m", self.changeMntDir) )
            self.menu.append( c_menu_item("Connect .img file as loop device", "+", self.addImg) )
            # self.menu.append( c_menu_item("SWAP manager", "-", m_swap_manager()) )
            
            ls=lsblk_list_disks(True)
            if ls:
                choice=0
                self.menu.append( c_menu_title_label( text_color("Select Disk", color=en_color.BRIGHT_CYAN)) )
                tit=f"{'Name':<30} | {'Size':>10} | {'Type':>8} | {'Partitions':>12} | {'Mountpoints':>12}"
                self.menu.append( c_menu_item(text_color(tit, color=en_color.BRIGHT_BLACK)) )
                self.menu.append( c_menu_item(text_color("-" * len(tit), color=en_color.BRIGHT_BLACK)) )
                for d in ls:
                    di=ls[d]
                    if di.type=="disk" and not di.children:
                        continue
                    
                    disk_name_display = c_other.getDiskDisplayName(di)
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
                        f"{disk_name_display:<30} | {bytesTx(di.size):>10} | {di.type:>8} | {part:>12} | {mps if mps>0 else '-':>12}",
                        f"{choice:02}",
                        m_disk_oper(),
                        data=di
                    ))
                    choice+=1
            else:
                self.menu.append( c_menu_item("Žádné použitelné disky k manažování.") )
        except Exception as e:
            log.error(f"Chyba při zobrazení menu disk manager: {e}")
            log.exception(e)
            raise e
        
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

        self.title=basicTitle()
        disk_name_display = c_other.getDiskDisplayName(disk)
        self.subTitle=c_menu_block_items([
            ("Disk",f"{disk_name_display}"),
            ("Size",f"{bytesTx(disk.size)}"),
            ("Type",f"{disk.type}"),
            ("Image Path",f"{str(self.__loopPath) if self.__loopPath else '-'}"),
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
            self.menu.append( c_menu_item("Přejmenovat disk", "n", self.rename_disk) )
        
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
    
    def rename_disk(self,selItem:c_menu_item) -> None|onSelReturn:
        """Přejmenuje disk podle jeho PUUID na uživatelské jméno.
        """
        ret = onSelReturn()
        
        disk=self.diskInfo
        if disk is None:
            return ret.errRet("Neznámý disk.")
        ptuuid=disk.ptuuid
        if ptuuid is None:
            return ret.errRet("Nelze zjistit PUUID disku.")
        curName=disk_settings.find_disk_name(ptuuid)
        print(text_color(f"Aktuální jméno disku: {curName if curName else '<žádné>'}", color=en_color.YELLOW))
        print(text_color("Poznámka: Jméno disku může obsahovat pouze znaky a-Z, 0-9, podtržítko a pomlčku.", color=en_color.CYAN))
        newName=get_input(
            f"Zadejte nové jméno disku (PUUID: {ptuuid}): ",
            rgx=r'^[a-zA-Z0-9_-]{1,25}$',
            maxLen=25,
            accept_empty=False,
            minMessageWidth=self.minMenuWidth,
            errTx="Jméno disku může obsahovat pouze znaky a-Z, 0-9, podtržítko a pomlčku v rozsahu 1-16 znaků."
        )
        if newName is None:
            return ret.errRet("Zrušeno uživatelem.")        
        # povolené znaky, musí být safe pro filename, takže jen a-Z 0-9 a podtržítko
        disk_settings.set_disk_name(ptuuid, newName)
        return ret.okRet(f"Disk přejmenován na: {newName}")
    
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
        
        self.title=basicTitle()
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
        
        self.title=basicTitle()
        self.subTitle=c_menu_block_items([
            (f"Disk",f"{self.diskInfo.name} {disk_settings.find_disk_name(self.diskInfo.ptuuid)}"),
            (f"Partition",f"{partNfo.name}"),
            (f"Label",f"{partNfo.label}"),
        ],blockColor=en_color.BRIGHT_CYAN)
        
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
