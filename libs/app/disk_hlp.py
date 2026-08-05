from pathlib import Path
from datetime import datetime, timezone
import re
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
    """Mapování normalizovaného PTUUID na uživatelské jméno disku."""

    diskNameUpdatedAt:dict[str,str]={}
    """UTC ISO timestamp poslední lokální nebo vzdálené změny názvu."""

    _NAME_RE=re.compile(r"^[a-zA-Z0-9_-]{1,25}$")

    @staticmethod
    def _config_path() -> Path:
        return getConfigPath(
            configName=defs.DISK_CFG,
            appName=defs.APP_NAME,
            fromEtc=defs.CONFIG_ETC,
            createIfNotExist=True
        )

    @staticmethod
    def normalize_ptuuid(ptuuid:str|None) -> str:
        return str(ptuuid or "").strip().lower()

    @staticmethod
    def _parse_timestamp(value:datetime|str|None) -> datetime|None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            parsed=value
        else:
            try:
                parsed=datetime.fromisoformat(str(value))
            except ValueError as exc:
                raise ValueError(f"Invalid disk name timestamp: {value}") from exc
        if parsed.tzinfo is None:
            parsed=parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _timestamp_text(value:datetime|str|None=None) -> str:
        parsed=disk_settings._parse_timestamp(value)
        if parsed is None:
            parsed=datetime.now(timezone.utc)
        return parsed.isoformat(timespec="microseconds")

    @staticmethod
    def save() -> None:
        fl=disk_settings._config_path()
        if not fl.parent.is_dir():
            fl.parent.mkdir(parents=True, exist_ok=True)

        import json
        data={
            "MNT_DIR": str(disk_settings.MNT_DIR),
            "BKP_DIR": str(disk_settings.BKP_DIR),
            "diskNames": disk_settings.diskNames,
            "diskNameUpdatedAt": disk_settings.diskNameUpdatedAt,
        }
        with fl.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, sort_keys=True)

    @staticmethod
    def load() -> None:
        fl=disk_settings._config_path()
        if not fl.is_file():
            return
        import json
        with fl.open("r", encoding="utf-8") as f:
            data=json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Disk settings must contain a JSON object.")
        if "MNT_DIR" in data:
            disk_settings.MNT_DIR=Path(data["MNT_DIR"]).resolve()
        if "BKP_DIR" in data:
            disk_settings.BKP_DIR=Path(data["BKP_DIR"]).resolve()

        raw_names=data.get("diskNames", {})
        raw_updates=data.get("diskNameUpdatedAt", {})
        if not isinstance(raw_names, dict) or not isinstance(raw_updates, dict):
            raise ValueError("Invalid disk name settings.")

        legacy_timestamp=datetime.fromtimestamp(fl.stat().st_mtime, timezone.utc)
        names:dict[str,str]={}
        updates:dict[str,str]={}
        migrated=False
        for raw_ptuuid, raw_name in raw_names.items():
            ptuuid=disk_settings.normalize_ptuuid(raw_ptuuid)
            if not ptuuid:
                continue
            name=str(raw_name or "")
            names[ptuuid]=name
            raw_updated=raw_updates.get(raw_ptuuid, raw_updates.get(ptuuid))
            parsed=disk_settings._parse_timestamp(raw_updated)
            if parsed is None:
                parsed=legacy_timestamp
                migrated=True
            updates[ptuuid]=disk_settings._timestamp_text(parsed)

        disk_settings.diskNames=names
        disk_settings.diskNameUpdatedAt=updates
        if migrated:
            disk_settings.save()

    @staticmethod
    def find_disk_name(puuid:str) -> str|None:
        key=disk_settings.normalize_ptuuid(puuid)
        return disk_settings.diskNames.get(key)

    @staticmethod
    def get_disk_name_updated_at(puuid:str) -> datetime|None:
        key=disk_settings.normalize_ptuuid(puuid)
        return disk_settings._parse_timestamp(
            disk_settings.diskNameUpdatedAt.get(key)
        )

    @staticmethod
    def set_disk_name(
        ptuuid:str,
        name:str,
        updated_at:datetime|str|None=None,
        save:bool=True,
    ) -> None:
        key=disk_settings.normalize_ptuuid(ptuuid)
        if not key:
            raise ValueError("PTUUID cannot be empty.")
        name=str(name or "")
        if name and not disk_settings._NAME_RE.fullmatch(name):
            raise ValueError(
                "Disk name may contain only letters, digits, underscore and dash."
            )
        disk_settings.diskNames[key]=name
        disk_settings.diskNameUpdatedAt[key]=disk_settings._timestamp_text(updated_at)
        if save:
            disk_settings.save()

    @staticmethod
    def apply_remote_names(updates) -> None:
        changed=False
        for update in updates:
            key=disk_settings.normalize_ptuuid(getattr(update, "ptuuid", ""))
            if not key:
                raise ValueError("Remote disk update is missing PTUUID.")
            remote_updated=disk_settings._parse_timestamp(
                getattr(update, "updated_at", None)
            )
            if remote_updated is None:
                raise ValueError(f"Remote disk update {key} has no timestamp.")
            local_updated=disk_settings.get_disk_name_updated_at(key)
            remote_name=str(getattr(update, "display_name", "") or "")
            if local_updated is not None and remote_updated < local_updated:
                continue
            if (
                disk_settings.diskNames.get(key) == remote_name
                and local_updated == remote_updated
            ):
                continue
            disk_settings.set_disk_name(
                key, remote_name, updated_at=remote_updated, save=False
            )
            changed=True
        if changed:
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
    def prepare_machine_id_for_first_boot(partInfo: lsblkDiskInfo) -> str|None:
        """Připraví offline klon systému pro vytvoření nového machine-id při prvním bootu.

        DŮLEŽITÝ KONTRAKT: tato funkce záměrně negeneruje nové machine-id okamžitě.
        Odstraní existující identity, ponechá prázdný `/etc/machine-id` a nainstaluje
        jednotku s `ConditionFirstBoot=yes`. Tím zůstane systém ve first-boot stavu a
        při prvním startu se mohou vedle vytvoření machine-id spustit také všechny další
        projektové first-boot služby. Neměnit na okamžité `systemd-machine-id-setup` nebo
        `systemd-firstboot --setup-machine-id`, pokud se vědomě nemění tento workflow.

        V cílovém systému vytvoří `generate-machine-id-firstboot.service` a relativní
        symlink v `multi-user.target.wants`.

        Args:
            partInfo (lsblkDiskInfo): připojená root partition připravovaného systému

        Returns:
            str|None: chybová hláška, nebo None při úspěšné přípravě
        """
        if not partInfo.mountpoints:
            return "Disk není připojený, nelze připravit Machine ID pro první boot"
        if len(partInfo.mountpoints)>1:
            return "Disk má více mountů, nelze připravit Machine ID pro první boot"
        mountPoint=Path(partInfo.mountpoints[0])
        if not mountPoint.is_dir():
            return "Mount point není adresář, nelze připravit Machine ID pro první boot"
        
        # Záměrně pouze připravujeme first-boot stav; nové ID zde negenerujeme.
        # Další ConditionFirstBoot jednotky musí zůstat způsobilé ke spuštění.
        # smažeme machine-id soubory
        machine_id_path = mountPoint / "etc/machine-id"
        dbus_machine_id_path = mountPoint / "var/lib/dbus/machine-id"
        if machine_id_path.is_file():
            machine_id_path.unlink()
        if dbus_machine_id_path.is_file():
            dbus_machine_id_path.unlink()
            
        # vytvoříme prázdný machine-id pro vygenerování nového
        (mountPoint / "etc/machine-id").touch()
        # vytvoříme službu, která nové machine-id vygeneruje až při prvním bootu
        service_content ="""[Unit]
Description=Generate machine-id on first boot
ConditionFirstBoot=yes

[Service]
Type=oneshot
ExecStart=/usr/bin/systemd-machine-id-setup

[Install]
WantedBy=multi-user.target
        """
        service_path = mountPoint / "etc/systemd/system/generate-machine-id-firstboot.service"
        with service_path.open("w", encoding="utf-8") as f:
            f.write(service_content)
        # povolíme službu vytvořením relativního symlinku
        wants_dir = mountPoint / "etc/systemd/system/multi-user.target.wants"
        if not wants_dir.is_dir():
            wants_dir.mkdir(parents=True, exist_ok=True)
        symlink_path = wants_dir / "generate-machine-id-firstboot.service"
        if not symlink_path.is_symlink():
            symlink_path.symlink_to("../generate-machine-id-firstboot.service")
            
        return None