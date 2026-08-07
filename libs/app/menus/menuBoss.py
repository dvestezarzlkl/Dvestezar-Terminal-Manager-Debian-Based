from libs.JBLibs.c_menu import c_menu,c_menu_item,c_menu_title_label,c_menu_block_items,onSelReturn
from libs.app.appHelper import menu
from typing import List
from libs.app import cfg
from libs.app import mail_hlp
from libs.JBLibs.input import anyKey,confirm,get_input,get_pwd,select,select_item
from libs.JBLibs.helper import getInterfaces,getMainScriptDir
from libs.app.plugin_manager import PluginRegistry
from libs.app.plugin_settings import PluginSettingsMenu
from libs.app.hub.menu import HubSettingsMenu
from libs.app.hub.models import HubState
from libs.app.hub.runtime import hub_runtime
from libs.app.settings_menu import SettingsPackageMenu
from libs.app.settings_package import startup_settings_update
from libs.app.service_host import configured_service_host, validate_service_host
import os,string
from libs.JBLibs import __version__ as libsVersion
from libs.JBLibs.term import cls, text_color,en_color

_items_:List[c_menu_item]=[]

def _global_host_title() -> c_menu_block_items:
    """Return the current machine identity shown in every SysApps submenu."""
    machine_info = getattr(cfg, "machineInfo", None)
    host = ""
    if machine_info is not None:
        host = str(
            getattr(machine_info, "hostname_full", "")
            or getattr(machine_info, "static_hostname", "")
            or ""
        ).strip()
    if not host:
        return c_menu_block_items()
    return c_menu_block_items([("Host", host)])

def _configure_global_menu_context() -> None:
    c_menu.globalTitle = _global_host_title

def _get_menu_version(menu_class: type) -> str:
    """Return the component version declared by a dynamic app menu."""
    for attr_name in ("_VERSION_", "__VERSION__", "__version__"):
        value = getattr(menu_class, attr_name, None)
        if value is None:
            continue
        version = str(value).strip()
        if version:
            return version
    return ""

def _format_menu_version(version: str) -> str:
    """Format a component version for the main menu."""
    version = str(version).strip()
    return f"v. {version}" if version else "?"

class menuBoss(menu):
    """
    Main APPs menu
    """
    
    # override protected
    choiceBack=None
    ESC_is_quit=False
    showGlobalTitle=False  # HOME already shows FQDN in its own system summary
    
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
        other_items = [
            None,
            c_menu_item('System info','i',self.showSystemInfo),
            c_menu_item('Update me','u',self.updateMe),
        ]
        if cfg.HUB_ENABLED:
            other_items.append(
                c_menu_item(
                    text_color('Synchronize SysApps Hub', en_color.BRIGHT_GREEN),
                    'hs',
                    self.syncHub,
                    atRight=hub_runtime.status_text(),
                    enabled=hub_runtime.status.state is HubState.READY,
                )
            )
        other_items.extend([
            c_menu_item(
                text_color('App settings', en_color.BRIGHT_GREEN),
                'm',
                m_mail_settings(),
                atRight=configured_service_host() or "not set",
            ),
            c_menu_item(
                text_color('Plugin settings', en_color.BRIGHT_CYAN),
                'p',
                PluginSettingsMenu(),
            ),
        ])
        self.menu.extend(other_items)

        # return onSelReturn(err="test err",ok="ok test")
        
    def onShowMenu(self):
        """
        Show menu
        """
        # Rebuild operational items after schema/settings actions so their
        # visibility and enabled state reflect the current Hub status.
        self.onEnterMenu()
        self._setAppHeader("HOME")
        
        if cfg.machineInfo.err:
            self.menu=[
                c_menu_title_label('Error machine info'),
                c_menu_title_label(cfg.machineInfo.err)
            ]
        else:
            if hub_runtime.status.state is HubState.READY:
                hub_color = en_color.BRIGHT_GREEN
            elif hub_runtime.status.state in {HubState.DISABLED, HubState.NOT_CONFIGURED}:
                hub_color = en_color.BRIGHT_BLACK
            else:
                hub_color = en_color.BRIGHT_RED
            self.afterTitle=[
                "Distro: "+cfg.machineInfo.operating_system,
                "Kernel: "+cfg.machineInfo.kernel,
                "FQDN: "+cfg.machineInfo.hostname_full,
                "JBLibs: "+libsVersion,
                "SysApps Hub: "+text_color(hub_runtime.status_text(), hub_color),
            ]
        
    def showSystemInfo(self,selItem:c_menu_item) -> onSelReturn:
        """
        Show system info
        """
        print(cfg.machineInfo)
        anyKey()

    def syncHub(self, selItem:c_menu_item) -> onSelReturn:
        """Run a manual full Hub synchronization without changing auto-sync policy."""
        if not cfg.HUB_ENABLED:
            return onSelReturn().errRet("SysApps Hub is disabled.")
        if hub_runtime.refresh_status().state is not HubState.READY:
            return onSelReturn().errRet(hub_runtime.status_text())
        print("SysApps Hub: collecting and synchronizing inventory...")
        report = hub_runtime.sync_all()
        if report.error:
            return onSelReturn().errRet(report.error)
        for warning in report.warnings:
            print(text_color(f"SysApps Hub warning: {warning}", en_color.BRIGHT_YELLOW))
        if report.warnings:
            anyKey()
        total = sum(report.provider_counts.values())
        return onSelReturn(ok=f"SysApps Hub synchronized core and {total} provider item(s).")

    def updateMe(self,selItem:c_menu_item) -> onSelReturn:
        """Update core, mandatory libraries, enabled plugins and runtime."""
        from libs.app.self_updater import update_application

        cls()
        report = update_application(getMainScriptDir())
        report.print_summary()
        anyKey()

        if report.changed:
            raise SystemExit(0)
        if report.success:
            return onSelReturn(ok="Application is already up to date.")
        return onSelReturn().errRet(report.error or "Update failed.")


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
        self.subTitle.append(("Service host / FQDN", configured_service_host() or "not set"))
        self.subTitle.append(("SMTP", mail_hlp.get_status_text()))
        self.subTitle.append(("Fallback admin", mail_hlp.get_fallback_admin_mail() or "not set"))
        self.subTitle.append(("SysApps Hub", hub_runtime.status_text()))
        self.menu = [
            c_menu_title_label(text_color("App settings", color=en_color.CYAN)),
            c_menu_item(
                text_color("Service host / FQDN", en_color.BRIGHT_CYAN),
                "s",
                self.edit_server_url,
                atRight=configured_service_host() or "not set",
            ),
            None,
            c_menu_title_label(text_color("SysApps Hub", color=en_color.CYAN)),
            c_menu_item(
                text_color("SysApps Hub settings", en_color.BRIGHT_CYAN),
                "b",
                HubSettingsMenu(),
                atRight=hub_runtime.status_text(),
            ),
            c_menu_item(
                text_color("Centralized settings", en_color.BRIGHT_GREEN),
                "g",
                SettingsPackageMenu(),
                atRight=(
                    f"revision {cfg.SETTINGS_LAST_REVISION}"
                    if cfg.SETTINGS_LAST_REVISION
                    else (cfg.SETTINGS_URL or "not configured")
                ),
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
        current = configured_service_host()
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
            opts.append(select_item(f"Use IPv4 ({iface.name}: {ip})", data=ip))

        opts.append(select_item("Manual entry or clear", data="manual"))
        for opt in opts:
            if opt.data == current:
                opt.atRight = "current"

        sel = select("Select service host / FQDN source:", opts)
        if not sel:
            return onSelReturn().errRet("Cancelled.")

        if sel.item.data == "manual":
            value = get_input(
                "Enter service host / FQDN (empty clears):",
                accept_empty=True,
                maxLen=255,
                titleNote=(
                    "This is the hostname, FQDN or IP used to present Node-RED and other service URLs.\n"
                    "It may resolve only through VPN. Do not include scheme, port or path.\n"
                    "An empty value disables SysApps Hub synchronization until configured."
                ),
            )
            if value is None:
                return onSelReturn().errRet("Cancelled.")
            try:
                service_host = validate_service_host(value)
            except ValueError as exc:
                return onSelReturn().errRet(str(exc))
        else:
            try:
                service_host = validate_service_host(sel.item.data)
            except ValueError as exc:
                return onSelReturn().errRet(str(exc))

        cfg.SERVER_URL = service_host
        self._save()
        hub_runtime.refresh_status()
        if not service_host:
            return onSelReturn(ok="Service host cleared; Hub synchronization is disabled until it is configured.")
        return onSelReturn(ok=f"Service host / FQDN updated to {service_host}.")

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
    _items_.clear()
    hub_runtime.clear_providers()
    _configure_global_menu_context()

    # Najde všechny adresáře odpovídající vzoru 'app_*' v aktuálním adresáři
    root=os.path.dirname(__file__)
    app_dirs = os.listdir(root)
    app_dirs = [d for d in app_dirs if os.path.isdir(os.path.join(root,d)) and d.startswith('app_')]
    app_dirs = [d for d in app_dirs if os.path.isfile(os.path.join(root,d,'menu.py')) ]

    try:
        plugin_registry = PluginRegistry(getMainScriptDir())
        app_dirs = [
            d for d in app_dirs
            if plugin_registry.is_app_directory_enabled(d)
        ]
    except Exception as e:
        print(f"Plugin state warning, loading discovered menus without filtering: {e}")

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
                version = _get_menu_version(menu_class)
                _items_.append(
                    c_menu_item(
                        mod._MENU_NAME_,
                        choice,
                        menu_class(),
                        atRight=_format_menu_version(version),
                    )
                )

                provider_key = str(getattr(mod, "_HUB_PROVIDER_KEY_", "") or "").strip()
                provider_collector = getattr(mod, "hub_collect", None)
                provider_applier = getattr(mod, "hub_apply_remote", None)
                if provider_key and callable(provider_collector):
                    try:
                        hub_runtime.register_provider(
                            provider_key, provider_collector, provider_applier
                        )
                    except Exception as provider_error:
                        print(f"SysApps Hub provider warning ({provider_key}): {provider_error}")

                choice_counter += 1  # Zvýšíme počítadlo pro další volbu
                
        except Exception as e:
            print(f"Error: {e}")
            # print exception to terminal
            import traceback
            traceback.print_exc()                        
    
    if choice_counter:
        startup_settings_update()
        hub_runtime.startup()
        x=menuBoss().run()
        if x:
            if isinstance(x,str):
                print(f"Returned error: {x}")
            return False
        return True
    else:
        print("No menu items found. END")
        return False
