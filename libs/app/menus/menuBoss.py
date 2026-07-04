from libs.JBLibs.c_menu import c_menu,c_menu_item,c_menu_title_label,c_menu_block_items,onSelReturn
from libs.app.appHelper import menu
from typing import List
from libs.app import cfg
from libs.app import mail_hlp
from libs.JBLibs.input import anyKey,confirm,get_input,get_pwd,select,select_item
from libs.JBLibs.helper import getInterfaces
import os,string
from libs.JBLibs import __version__ as libsVersion
from libs.JBLibs.term import cls, text_color,en_color

_items_:List[c_menu_item]=[]

class menuBoss(menu):
    """
    Main APPs menu
    """
    
    # override protected
    choiceBack=None
    ESC_is_quit=False
    
    # apphelper menu props protected
    titleShowMyIP=True
    titleShowTime=True
    appTitle="Apps Menu"
            
    def onEnterMenu(self):
        """
        Show menu
        """
        self.menu=[
            c_menu_title_label(text_color('Available Applications',color=en_color.BRIGHT_CYAN,bold=True))
        ]
        self.menu.extend(_items_)
        self.menu.append(c_menu_title_label(text_color('Other options',color=en_color.CYAN)))
        self.menu.extend([
            None,
            c_menu_item('System info','i',self.showSystemInfo),
            c_menu_item('Update me','u',self.updateMe),
            c_menu_item(
                text_color('App settings', en_color.BRIGHT_GREEN),
                'm',
                m_mail_settings(),
                atRight=cfg.SERVER_URL or "not set",
            ),
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
                "JBLibs: "+libsVersion,
            ]
        
    def showSystemInfo(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show system info
        """
        print(cfg.machineInfo)
        anyKey()

    def updateMe(self,selItem:c_menu_item) -> onSelReturn:
        """
        Update me
        """
        from libs.JBLibs.git import git
        from libs.JBLibs.helper import getMainScriptDir
        cls()
        print("Checking for updates ...")
        myPath=getMainScriptDir()
        g=git(None)
        if g.check(myPath,'root'):
            print("Update available, updating ...")
            err=g.update(myPath,'root')
            if err:
                print(f"Error updating: {err}")
            else:
                print("Update completed, application will exit now.")
        else:
            print("No update available")
        anyKey()
        # ukončíme program - aplikaci
        exit(0)    


class m_mail_settings(c_menu):
    """Global mailing settings for the whole application."""

    choiceBack = None
    ESC_is_quit = True

    def onEnterMenu(self) -> None:
        self.cfg = cfg

    def _save(self) -> None:
        cfg.save()

    def onShowMenu(self) -> None:
        self.title = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        self.title.append(("App settings", "c"))
        self.subTitle = c_menu_block_items()
        self.subTitle.append(("URL", cfg.SERVER_URL or "not set"))
        self.subTitle.append(("SMTP", mail_hlp.get_status_text()))
        self.subTitle.append(("Fallback admin", mail_hlp.get_fallback_admin_mail() or "not set"))
        self.menu = [
            c_menu_title_label(text_color("App settings", color=en_color.CYAN)),
            c_menu_item(
                text_color("Server URL", en_color.BRIGHT_CYAN),
                "s",
                self.edit_server_url,
                atRight=cfg.SERVER_URL or "not set",
            ),
            None,
            c_menu_title_label(text_color("Mail settings", color=en_color.CYAN)),
            c_menu_item(
                text_color("SMTP host", en_color.BRIGHT_CYAN),
                "h",
                self.edit_smtp_host,
                atRight=cfg.MAIL_SMTP_HOST or "not set",
            ),
            c_menu_item(
                text_color("SMTP port", en_color.BRIGHT_CYAN),
                "p",
                self.edit_smtp_port,
                atRight=str(cfg.MAIL_SMTP_PORT),
            ),
            c_menu_item(
                text_color("SMTP user", en_color.BRIGHT_CYAN),
                "u",
                self.edit_smtp_user,
                atRight=cfg.MAIL_SMTP_USER or "not set",
            ),
            c_menu_item(
                text_color("SMTP password", en_color.BRIGHT_CYAN),
                "w",
                self.edit_smtp_password,
                atRight="set" if cfg.MAIL_SMTP_PASSWORD else "not set",
            ),
            c_menu_item(
                text_color("SMTP mode", en_color.BRIGHT_CYAN),
                "o",
                self.edit_smtp_mode,
                atRight=cfg.MAIL_SMTP_MODE or "starttls",
            ),
            c_menu_item(
                text_color("From address", en_color.BRIGHT_CYAN),
                "f",
                self.edit_mail_from,
                atRight=cfg.MAIL_FROM or cfg.MAIL_SMTP_USER or "not set",
            ),
            c_menu_item(
                text_color("Fallback admin mail", en_color.BRIGHT_YELLOW),
                "a",
                self.edit_fallback_admin_mail,
                atRight=mail_hlp.get_fallback_admin_mail() or "not set",
            ),
            c_menu_item(
                text_color("Send test mail", en_color.BRIGHT_GREEN),
                "t",
                self.send_test_mail,
                atRight=mail_hlp.get_fallback_admin_mail() or "fallback mail not set",
                enabled=bool(mail_hlp.get_fallback_admin_mail()),
            ),
        ]

    def edit_smtp_host(self, selItem:c_menu_item) -> onSelReturn:
        current = cfg.MAIL_SMTP_HOST or ""
        prompt = "Enter SMTP host:"
        if current:
            prompt = f"Enter SMTP host [{current}]:"
        value = get_input(prompt, accept_empty=True, maxLen=255)
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        cfg.MAIL_SMTP_HOST = value.strip()
        self._save()
        return onSelReturn(ok="SMTP host updated.")

    def edit_smtp_port(self, selItem:c_menu_item) -> onSelReturn:
        current = str(cfg.MAIL_SMTP_PORT or "")
        prompt = "Enter SMTP port:"
        if current:
            prompt = f"Enter SMTP port [{current}]:"
        value = get_input(
            prompt,
            accept_empty=True,
            rgx=r"^\d+$",
            maxLen=5,
            errTx="Invalid port.",
            titleNote=mail_hlp.get_smtp_port_hint(cfg.MAIL_SMTP_MODE),
        )
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        if not value:
            return onSelReturn().errRet("SMTP port cannot be empty.")
        port = int(value)
        if port < 1 or port > 65535:
            return onSelReturn().errRet("SMTP port must be between 1 and 65535.")
        cfg.MAIL_SMTP_PORT = port
        self._save()
        return onSelReturn(ok="SMTP port updated.")

    def edit_smtp_user(self, selItem:c_menu_item) -> onSelReturn:
        current = cfg.MAIL_SMTP_USER or ""
        prompt = "Enter SMTP user:"
        if current:
            prompt = f"Enter SMTP user [{current}]:"
        value = get_input(prompt, accept_empty=True, maxLen=255)
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        cfg.MAIL_SMTP_USER = value.strip()
        self._save()
        return onSelReturn(ok="SMTP user updated.")

    def edit_smtp_password(self, selItem:c_menu_item) -> onSelReturn:
        value = get_pwd("Enter SMTP password", make_cls=False, minMessageWidth=0)
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        cfg.MAIL_SMTP_PASSWORD = value
        self._save()
        return onSelReturn(ok="SMTP password updated.")

    def edit_smtp_mode(self, selItem:c_menu_item) -> onSelReturn:
        opts = [
            select_item("Plain", "plain", "plain"),
            select_item("STARTTLS", "starttls", "starttls"),
            select_item("SSL", "ssl", "ssl"),
        ]
        current = (cfg.MAIL_SMTP_MODE or "starttls").lower()
        for opt in opts:
            if opt.data == current:
                opt.atRight = "current"
        sel = select("Select SMTP mode:", opts)
        if not sel:
            return onSelReturn().errRet("Cancelled.")
        new_mode = sel.item.data
        new_port = mail_hlp.get_default_smtp_port(new_mode)
        if cfg.MAIL_SMTP_PORT != new_port:
            msg = (
                f"Změnit aktuální port {cfg.MAIL_SMTP_PORT} "
                f"na výchozí port {new_port} pro {new_mode.upper()}?"
            )
            if confirm(msg, minMessageWidth=self.minMenuWidth):
                cfg.MAIL_SMTP_PORT = new_port
        cfg.MAIL_SMTP_MODE = new_mode
        self._save()
        return onSelReturn(ok=f"SMTP mode set to {new_mode}.")

    def edit_mail_from(self, selItem:c_menu_item) -> onSelReturn:
        current = cfg.MAIL_FROM or cfg.MAIL_SMTP_USER or ""
        prompt = "Enter from address (empty uses SMTP user):"
        if current:
            prompt = f"Enter from address [{current}] (empty uses SMTP user):"
        value = get_input(
            prompt,
            accept_empty=True,
            rgx=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$",
            maxLen=254,
            errTx="Invalid email address.",
        )
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        cfg.MAIL_FROM = value.strip().lower()
        self._save()
        return onSelReturn(ok="From address updated.")

    def edit_server_url(self, selItem:c_menu_item) -> onSelReturn:
        current = (cfg.SERVER_URL or "").strip()
        fqdn = ""
        if getattr(cfg, "machineInfo", None):
            fqdn = (cfg.machineInfo.hostname_full or cfg.machineInfo.static_hostname or "").strip()

        opts = []
        if fqdn:
            opts.append(select_item(f"Use FQDN ({fqdn})", data=fqdn))

        seen_ips = set()
        for iface in getInterfaces():
            ip = (getattr(iface, "ipv4", "") or "").strip()
            if not ip or ip.startswith(("127.", "0.", "169.254.")):
                continue
            if ip in seen_ips:
                continue
            seen_ips.add(ip)
            label = f"Use IPv4 ({iface.name}: {ip})"
            opts.append(select_item(label, data=ip))

        opts.append(select_item("Manual entry", data="manual"))
        for opt in opts:
            if opt.data == current:
                opt.atRight = "current"

        sel = select("Select SERVER_URL source:", opts)
        if not sel:
            return onSelReturn().errRet("Cancelled.")

        new_url = ""
        if sel.item.data == "manual":
            note = "\n".join([
                "SERVER_URL is used without a port.",
                "Enter only a hostname, FQDN, IP address, or path.",
                "Do not include http://, https://, or :PORT.",
            ])
            value = get_input(
                "Enter SERVER_URL:",
                accept_empty=False,
                maxLen=255,
                titleNote=note,
                rgx=r"^[^:\s]+$",
                errTx="SERVER_URL must not contain a port or spaces.",
            )
            if value is None:
                return onSelReturn().errRet("Cancelled.")
            new_url = value.strip()
        else:
            new_url = str(sel.item.data).strip()

        if not new_url:
            return onSelReturn().errRet("SERVER_URL cannot be empty.")

        cfg.SERVER_URL = new_url
        self._save()
        return onSelReturn(ok=f"SERVER_URL updated to {new_url}.")

    def edit_fallback_admin_mail(self, selItem:c_menu_item) -> onSelReturn:
        current = mail_hlp.get_fallback_admin_mail()
        prompt = "Enter fallback admin email address (empty clears):"
        if current:
            prompt = f"Enter fallback admin email address [{current}] (empty clears):"
        value = get_input(
            prompt,
            accept_empty=True,
            rgx=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$",
            maxLen=254,
            errTx="Invalid email address.",
        )
        if value is None:
            return onSelReturn().errRet("Cancelled.")
        ok, msg = mail_hlp.set_fallback_admin_mail(value)
        if not ok:
            return onSelReturn().errRet(msg)
        self._save()
        return onSelReturn(ok="Fallback admin mail updated.")

    def send_test_mail(self, selItem:c_menu_item) -> onSelReturn:
        recipient = mail_hlp.get_fallback_admin_mail()
        if not recipient:
            return onSelReturn().errRet("Fallback admin mail is not configured.")
        ok, msg = mail_hlp.send_test_mail(recipient)
        if not ok:
            return onSelReturn().errRet(msg)
        anyKey()
        return onSelReturn(ok=f"Test mail sent to {recipient}.")

def init() -> bool:
    """
    Initialize menu
    """
    global _items_
    
    # Najde všechny adresáře odpovídající vzoru 'app_*' v aktuálním adresáři
    root=os.path.dirname(__file__)
    app_dirs = os.listdir(root)
    app_dirs = [d for d in app_dirs if os.path.isdir(os.path.join(root,d)) and d.startswith('app_')]
    app_dirs = [d for d in app_dirs if os.path.isfile(os.path.join(root,d,'menu.py')) ]
    
    # sort app_dirs alphabetically
    app_dirs.sort()
    
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
