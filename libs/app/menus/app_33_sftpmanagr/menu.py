from __future__ import annotations

from typing import List, Optional, Tuple, Dict

from libs.JBLibs.c_menu import (
    c_menu,
    c_menu_block_items,
    c_menu_item,
    c_menu_title_label,
    onSelReturn,
)
from libs.JBLibs.input import anyKey,selectDir,text_color,en_color,get_input,confirm,select,select_item
from libs.JBLibs.term import cls
from libs.JBLibs.helper import getLogger
from libs.app import mail_hlp
log = getLogger("sftpmng")

from .sftp_manager_hlp import (
    load_config,
    find_user,
    list_users,
    add_user as hlp_add_user,
    delete_user as hlp_delete_user,
    list_mountpoints as hlp_list_mountpoints,
    add_mountpoint as hlp_add_mountpoint,
    delete_mountpoint as hlp_delete_mountpoint,
    list_keys as hlp_list_keys,
    add_key as hlp_add_key,
    delete_key as hlp_delete_key,
    apply_changes,
    cifs_exists,
    get_mountpointReadOnlyStatus,
    set_mountpoint_readonly,
    get_printable_keys,
    get_admin_mail,
    set_admin_mail,
    get_user_mail,
    set_user_mail,
    send_key_by_mail,
)

_MENU_NAME_: str = "SFTP Manager"

class menu(c_menu):
    """Top‑level menu listing all configured SFTP users."""

    # Allow ESC to quit back to the parent menu
    ESC_is_quit: bool = True
    
    # true pokud bylo změněno něco v konfiguraci 
    changed:bool = False
    
    # seznam uživatelů v konfigu
    users: List[Dict] = []
    
    # aktuální konfigurace
    cfg:Dict

    __VERSION__ = "1.1.1"

    def basicTitle(self, add:str|list=None, username:str|None="not selected") -> c_menu_block_items:
        """Vytvoří základní titulní blok pro menu.
        
        Returns:
            c_menu_block_items: titulní blok menu
        """
        menuname=_MENU_NAME_
        menuVer=self.__VERSION__
        
        header=c_menu_block_items(blockColor=en_color.BRIGHT_CYAN )
        header.append( (menuname,'c') )
        header.append("-")
        header.append(f"Verze: {menuVer}")
        if username is not None:
            header.append( ("Selected user", username) )
        
        if isinstance(add, str):
            header.append( add )
        elif isinstance(add, list):
            header.extend( add )
        elif add is None:
            pass
        else:
            raise ValueError("Vstup musí být str nebo list")
        
        return header

    def onEnterMenu(self) -> None:
        # Load configuration fresh each time the menu is entered so that
        # changes performed in submenus are visible here.
        ok,msg,cfg = load_config()
        if not ok:
            print(text_color(f"Warning: {msg}", en_color.BRIGHT_RED))
            anyKey()
        self.cfg = cfg
        self.users = list_users(self.cfg)
        self.changed = False

    def onShowMenu(self) -> None:
        # Compose the menu dynamically.  The header shows how many
        # users are configured.
        self.title = self.basicTitle()
        
        title = f"{_MENU_NAME_} ({len(self.users)} users)"
        self.menu = [
            c_menu_title_label(text_color(title,en_color.CYAN)),
        ]
        if not cifs_exists():
            self.menu.append(
                c_menu_title_label(
                    text_color("!! CIFS support is missing - install package cifs-utils !!", en_color.BRIGHT_RED)
                )
            )
        self.menu.extend([
            c_menu_item(text_color("Create new SFTP user", en_color.BRIGHT_GREEN), "n", self.create_user),
            c_menu_item(
                text_color("Admin mail", en_color.BRIGHT_YELLOW),
                "e",
                self.edit_admin_mail,
                atRight=mail_hlp.get_effective_admin_mail(get_admin_mail(self.cfg)) or "not set",
            ),
            None
        ])
        # Enumerate users; assign numeric selection keys for ease of use.
        # FIXME jako u disku zobrazovat ve sloupcích
        for idx, usr in enumerate(self.users, start=1):
            name = usr.get("sftpuser") or f"user{idx}"
            mp_count = len(usr.get("sftpmounts", {}))
            key_count = len(usr.get("sftpcerts", []))
            mail = usr.get("mail") or "-"
            label = text_color(f"{name}",en_color.YELLOW)
            atR=f"mounts:{mp_count}, keys:{key_count}, mail:{mail}"
            # Create a submenu instance carrying the username.  The
            # c_menu framework will detect it as a submenu.
            self.menu.append(
                c_menu_item(label, str(idx), m_user(name, self),atRight=atR)
            )
            
        self.menu.append(None)
        if self.changed:
            self.menu.append(c_menu_item(text_color("!! Save & apply changes !!",en_color.BRIGHT_RED), "a", self.apply_changes))
            self.menu.append(c_menu_item(text_color("Discard unsaved changes",en_color.BRIGHT_YELLOW), "d", self.cancel_changes))
        else:
            # apply changes = install update active sftp users according to curent config, dáme mgentu
            self.menu.append(c_menu_item(text_color("Install/update active SFTP users according to current config",en_color.MAGENTA), "a", self.apply_changes))
            
        # kompletně smazat všechny aktivní uživatele - clean state, run sftpmanager delete all users
        self.menu.append(c_menu_item(text_color("Uninstall all users", en_color.BRIGHT_RED), "u", self.uninstall_all_users))

    def uninstall_all_users(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """
        Uninstall all active SFTP users from the system.
        Prompts for confirmation before removing all active SFTP user accounts.
        This action does not modify the configuration file, allowing 'Apply changes'
        to be used afterwards to reinstall users according to the current configuration.
        Args:
            selItem: Menu item object (required by interface, not used internally).
        Returns:
            onSelReturn: Success message if uninstall completed, error message if cancelled.
        """
        from .sftp_manager_hlp import uninstall_all_users
        
        # opravdu odinstalovat všechny aktivní sftp usery? \n toto odinstaluje aktivní sftp uživatele
        # tato akce nemá nic společného s modifikací konfigu, po této akci lze použít apply changes pro aktualizaci aktivních sftp uživatelů
        # tzn tato akce + apply = reainstall sftp users podle aktuálního stavu konfigu
        if not confirm("Really uninstall all active SFTP users?\nThis will remove all SFTP user accounts currently active on the system.\nThis action does not modify the configuration, so you can use 'Apply changes'\n  afterwards to reinstall users according to the current configuration.\n\nProceed [y/N]"):
            return onSelReturn().errRet("Cancelled.")
        
        uninstall_all_users()
        return onSelReturn(ok="All users uninstalled.")

    def create_user(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Prompt for a new user name and append it to the config."""
        ret = onSelReturn()
        name = get_input("Enter new SFTP user name:")
        if not name:
            return ret.errRet("Operation cancelled.")
        # Prevent duplicate names
        if find_user(self.cfg, name):
            return ret.errRet(f"User '{name}' already exists.")
        hlp_add_user(self.cfg, name)
        self.changed = True
        return ret.okRet(f"User '{name}' created.")

    def edit_admin_mail(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Set or update the admin email address stored in the config."""
        ret = onSelReturn()
        current = get_admin_mail(self.cfg)
        prompt = "Enter admin email address:"
        if current:
            prompt = f"Enter admin email address [{current}]:"
        mail = get_input(
            prompt,
            accept_empty=False,
            rgx=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$",
            maxLen=254,
            errTx="Invalid email address."
        )
        if not mail:
            return ret.errRet("Operation cancelled.")
        ok, msg = set_admin_mail(self.cfg, mail)
        if not ok:
            return ret.errRet(msg)
        self.changed = True
        return ret.okRet(f"Admin mail set to '{mail}'.")

    def apply_changes(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Invoke the SFTP manager script to apply changes to the system."""
        ok, msg = apply_changes(cfg=self.cfg, save=True)
        if not ok:
            log.error(f"Failed to apply changes: {msg}")
            print(text_color(f"Error: {msg}", en_color.BRIGHT_RED))
            anyKey()
            return onSelReturn().errRet(f"Failed to apply changes: {msg}")
        self.changed=False
        anyKey()
        return onSelReturn(ok="Changes applied.")
    
    def cancel_changes(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Discard unsaved changes by reloading the configuration."""
        if not confirm("Discard unsaved changes?"):
            return onSelReturn().errRet("Cancelled.")
        self.onEnterMenu()  # Reload config and reset state
        return onSelReturn(ok="Changes discarded.")


class m_user(c_menu):
    """Submenu for a specific SFTP user."""

    # vybrané username
    username:str=""
    
    # instance hlavního menu akonfigu
    mainMenu:menu=None
    
    # načtený user z konfigu
    user:Optional[Dict] = None

    def __init__(
        self,
        username: str,
        mainMenu: menu
    ) -> None:
        super().__init__()
        self.username = username
        self.mainMenu=mainMenu

    def onEnterMenu(self) -> None:
        # Reload configuration so that modifications from other menus are visible.
        self.user = find_user(self.mainMenu.cfg, self.username)

    def onShowMenu(self) -> None:
        self.title=self.mainMenu.basicTitle(add=" *** User details ***", username=self.username)
        
        title = f"User: {self.username}"
        usr = self.user or {}
        current_mail = get_user_mail(self.mainMenu.cfg, self.username) or "not set"
        self.menu = [
            c_menu_title_label(text_color(title,en_color.CYAN)),
            c_menu_item(
                text_color("Mail", en_color.BRIGHT_YELLOW),
                "e",
                self.edit_mail,
                atRight=current_mail,
            ),
            c_menu_item(text_color("Delete user", en_color.BRIGHT_RED), "d", self.delete_user),
            None,
            c_menu_item("Manage mountpoints", "m", m_user_mountpoints(self.username, self.mainMenu,self.user),atRight="qty: "+str(len(usr.get("sftpmounts", {})))),
            c_menu_item("Manage keys", "k", m_user_keys(self.username, self.mainMenu,self.user),atRight="qty: "+str(len(usr.get("sftpcerts", [])))),
        ]

    def delete_user(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Remove this user from the configuration after confirmation."""
        ret = onSelReturn()
        if not confirm(f"Really delete SFTP user '{self.username}'? [y/N]"):
            return ret.errRet("Cancelled.")
        if not hlp_delete_user(self.mainMenu.cfg, self.username):
            return ret.errRet(f"User '{self.username}' not found.")
        
        self.mainMenu.changed=True
        # End this menu so that the parent list refreshes without the user
        return onSelReturn(endMenu=True)

    def edit_mail(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Set, update, or clear the optional mail address for this user."""
        ret = onSelReturn()
        current = get_user_mail(self.mainMenu.cfg, self.username)
        prompt = "Enter user email address (empty clears):"
        if current:
            prompt = f"Enter user email address [{current}] (empty clears):"
        mail = get_input(
            prompt,
            accept_empty=True,
            rgx=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$",
            maxLen=254,
            errTx="Invalid email address."
        )
        if mail is None:
            return ret.errRet("Operation cancelled.")
        if not mail:
            if current and not confirm(f"Clear mail address for user '{self.username}'?"):
                return ret.errRet("Cancelled.")
            ok, msg = set_user_mail(self.mainMenu.cfg, self.username, None)
        else:
            ok, msg = set_user_mail(self.mainMenu.cfg, self.username, mail)
        if not ok:
            return ret.errRet(msg)
        self.mainMenu.changed=True
        return ret.okRet("User mail updated.")


class m_user_mountpoints(c_menu):
    """Submenu for listing and editing a user's SFTP mountpoints."""

    # vybrané username
    username:str=""
    
    # instance hlavního menu akonfigu
    mainMenu:menu=None
    
    # načtený user z konfigu
    user:Optional[Dict] = None


    def __init__(
        self,
        username: str,
        mainMenu: menu,
        user: Optional[Dict]
    ) -> None:
        super().__init__()
        self.username = username
        self.mainMenu = mainMenu
        self.user = user

    def onEnterMenu(self) -> None:
        self.cfg = self.mainMenu.cfg

    def onShowMenu(self) -> None:
        self.title=self.mainMenu.basicTitle(add=" *** User > Mountpoints ***", username=self.username)
        
        self.mounts: List[Tuple[str, str]] = hlp_list_mountpoints(self.cfg, self.username)
        
        self.menu = [
            c_menu_title_label(text_color(f"Mountpoints for {self.username}",en_color.CYAN)),
            c_menu_item(text_color("Add mountpoint", en_color.BRIGHT_GREEN), "a", self.add_mountpoint),
            None
        ]
        # List existing mountpoints; each item can be selected for deletion.
        for idx, (label, target) in enumerate(self.mounts, start=1):
            rTx=get_mountpointReadOnlyStatus(self.cfg, self.username, label)
            atR = "RO" if rTx else "RW"
            itm = c_menu_item(text_color(label,en_color.YELLOW) + " → " + text_color(target,en_color.MAGENTA), str(idx), self.modify_mountpoint, atRight=atR)
            # Store the label of the mountpoint to delete on selection.
            itm.data = label
            self.menu.append(itm)

    def add_mountpoint(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        from .sftp_manager_hlp import checkMountpointExists, checkMountPointPathExists
        
        ret = onSelReturn()
        label = "NaN"
        target = "NaN"
        
        #pomocná funkce na zobrazení hlavičky pro zadávání mountpointu
        def show_header():
            cls()
            print(f"*********** Add mountpoint for {self.username} ***********")
            print(f"- Mountpoint name (alias): {label}")
            print(f"- Target path: {target}")
            print(("*"*40) + "\n")
        
        while True:
            show_header()
            label = get_input(
                "Enter mountpoint name (alias):",
                rgx=r"^[a-zA-Z0-9_\-]+$",
                maxLen=32,
                errTx="Invalid name. Use only letters, numbers, underscores or hyphens."
            )        
            if not label:
                return ret.errRet("No mountpoint name provided.")
            if checkMountpointExists(self.cfg, self.username, label):
                print(text_color(f"Mountpoint '{label}' already exists for user '{self.username}'.", en_color.BRIGHT_RED))
                anyKey()
                continue
            break
        
        while True:
            show_header()
            target = selectDir("/","Select absolute path to mount:")
            if not target:
                return ret.errRet("No mountpoint path provided.")
            existing_label = checkMountPointPathExists(self.cfg, self.username, target)
            if existing_label:
                print(text_color(f"Path '{target}' is already used for mountpoint '{existing_label}'.", en_color.BRIGHT_RED))
                anyKey()
                continue
            break
        
        # vybereme z možností R/RW
        opts=[
            select_item("Read-only (R)", "R", "R"),
            select_item("Read-write (RW)", "RW", "RW")
        ]
        show_header()
        x = select("Select access mode:",opts)
        if not x:
            return ret.errRet("No access mode selected.")
        
        if not hlp_add_mountpoint(self.cfg, self.username, label, target, readOnly=(x=="R")):
            return ret.errRet(f"User '{self.username}' not found.")
        
        self.mainMenu.changed=True
        return ret.okRet("Mountpoint added.")

    def modify_mountpoint(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        
        # přes sel uděláme modify, tzn set R nebo RW podle aktuální stavu a druhá močnost bude červená delete
        opt=[]
        rTx=get_mountpointReadOnlyStatus(self.cfg, self.username, selItem.data)
        if rTx:
            opt.append(select_item("Set to Read-Write", "W", "W"))
        else:
            opt.append(select_item("Set to Read-Only", "R", "R"))
        opt.append(select_item(text_color("Delete mountpoint", en_color.BRIGHT_RED), "D", "D"))
        x = select(f"Select action for mountpoint '{selItem.data}':",opt)
        if x is None:
            return onSelReturn().errRet("No action selected.")
        x=x.item.data
        
        if x == "D":
            if not confirm(f"Remove mountpoint '{selItem.data}'?"):
                return onSelReturn().errRet("Cancelled.")
            if not hlp_delete_mountpoint(self.cfg, self.username, selItem.data):
                return onSelReturn().errRet("Mountpoint not found.")
            else:
                self.mainMenu.changed=True
                return onSelReturn(ok="Mountpoint removed.")
        else:
            # nastavíme readonly nebo rw podle výběru
            if not set_mountpoint_readonly(self.cfg, self.username, selItem.data, readOnly=(x=="R")):
                return onSelReturn().errRet("Failed to update mountpoint.")
            else:
                self.mainMenu.changed=True
                return onSelReturn(ok="Mountpoint updated.")

class m_key_actions(c_menu):
    """Submenu with actions for a single SFTP key entry."""

    # vybrané username
    username: str = ""

    # instance hlavního menu akonfigu
    mainMenu: menu = None

    # celý uložený key záznam
    keystr: str = ""

    # zobrazený název položky v listu
    display_name: str = ""

    # dekódovaná veřejná / privátní část
    pub_key: str = ""
    priv_key: str = ""
    has_private: bool = False

    def __init__(
        self,
        username: str,
        mainMenu: menu,
        keystr: str,
        display_name: str,
    ) -> None:
        super().__init__()
        self.username = username
        self.mainMenu = mainMenu
        self.keystr = keystr
        self.display_name = display_name

    def onEnterMenu(self) -> None:
        self.cfg = self.mainMenu.cfg
        ok, printable = get_printable_keys(self.keystr)
        if not ok:
            raise ValueError(f"Failed to parse key: {printable}")
        self.pub_key, self.priv_key = printable
        self.has_private = bool(self.priv_key)

    def onShowMenu(self) -> None:
        self.title = self.mainMenu.basicTitle(add=" *** User > Key action ***", username=self.username)
        self.menu = [
            c_menu_title_label(text_color(f"Key: {self.display_name}", en_color.CYAN)),
            c_menu_item(
                text_color("Show public key", en_color.BRIGHT_CYAN),
                "p",
                self.show_public_key,
            ),
        ]

        if self.has_private:
            self.menu.extend([
                c_menu_item(
                    text_color("Show private key", en_color.BRIGHT_MAGENTA),
                    "s",
                    self.show_private_key,
                ),
                c_menu_item(
                    text_color("Send by mail", en_color.BRIGHT_GREEN),
                    "m",
                    self.send_by_mail,
                    atRight=mail_hlp.get_effective_admin_mail(get_admin_mail(self.cfg)) or "admin mail not set",
                    enabled=bool(mail_hlp.get_effective_admin_mail(get_admin_mail(self.cfg))),
                ),
                c_menu_item(
                    text_color("Delete entire certificate", en_color.BRIGHT_RED),
                    "d",
                    self.delete_entry,
                ),
            ])
        else:
            self.menu.extend([
                c_menu_item(
                    text_color("Send by mail", en_color.BRIGHT_GREEN),
                    "m",
                    self.send_by_mail,
                    atRight=mail_hlp.get_effective_admin_mail(get_admin_mail(self.cfg)) or "admin mail not set",
                    enabled=bool(mail_hlp.get_effective_admin_mail(get_admin_mail(self.cfg))),
                ),
                c_menu_item(
                    text_color("Delete key", en_color.BRIGHT_RED),
                    "d",
                    self.delete_entry,
                ),
            ])

    def show_public_key(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        ret = onSelReturn()
        print(text_color("Public key:", en_color.BRIGHT_CYAN))
        print(self.pub_key)
        anyKey()
        return ret.okRet("Public key displayed.")

    def show_private_key(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        ret = onSelReturn()
        if not self.has_private:
            return ret.errRet("No private key stored for this entry.")
        print(text_color("Private key:", en_color.BRIGHT_MAGENTA))
        print(self.priv_key)
        anyKey()
        return ret.okRet("Private key displayed.")

    def send_by_mail(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        ret = onSelReturn()
        if not mail_hlp.isConfigured():
            return ret.errRet("Mail transport is not configured in application settings.")
        ok, msg = send_key_by_mail(self.cfg, self.username, self.keystr)
        if not ok:
            return ret.errRet(msg)
        anyKey()
        return ret.okRet("Key sent by mail.")

    def delete_entry(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        ret = onSelReturn()
        if self.has_private:
            prompt = "Remove this certificate (public + private parts)?"
            success_msg = "Certificate removed."
        else:
            prompt = "Remove this key?"
            success_msg = "Key removed."
        if not confirm(prompt):
            return ret.errRet("Cancelled.")
        if not hlp_delete_key(self.cfg, self.username, self.keystr):
            return ret.errRet("Key not found.")
        self.mainMenu.changed = True
        return ret.okRet(success_msg, endMenu=True)

class m_user_keys(c_menu):
    """Submenu for listing and editing a user's authorised keys."""

    # vybrané username
    username:str=""
    
    # instance hlavního menu akonfigu
    mainMenu:menu=None
    
    # načtený user z konfigu
    user:Optional[Dict] = None

    def __init__(
        self,
        username: str,
        mainMenu: menu,
        user: Optional[Dict]
    ) -> None:
        super().__init__()
        self.username = username
        self.mainMenu = mainMenu
        self.user = user

    def onEnterMenu(self) -> None:
        self.cfg = self.mainMenu.cfg
        self.user = find_user(self.cfg, self.username)

    def onShowMenu(self) -> None:
        self.title=self.mainMenu.basicTitle(add=" *** User > Keys ***", username=self.username)
        
        self.keys: List[Tuple[str,str]] = hlp_list_keys(self.cfg, self.username)
        
        self.menu = [
            c_menu_title_label(text_color(f"Keys for {self.username}",en_color.CYAN)),
            c_menu_item("Add key", "a", self.add_key),
            c_menu_item("Generate new  pair", "g", self.generate),
            None
        ]
        for idx, itm in enumerate(self.keys, start=1):
            # Truncate long keys for display but carry the full string in data
            name = itm[0]
            keystr = itm[1]
            self.menu.append(
                c_menu_item(
                    text_color(name, en_color.YELLOW),
                    str(idx),
                    m_key_actions(self.username, self.mainMenu, keystr, name),
                    data=keystr,
                    atRight=mail_hlp.get_effective_admin_mail(get_admin_mail(self.mainMenu.cfg)) or "admin mail not set",
                )
            )

    def add_key(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        ret = onSelReturn()
        keystr = get_input("Paste the public key or certificate:")
        if not keystr:
            return ret.errRet("No key provided.")
        ok,msg = hlp_add_key(self.cfg, self.username, keystr)
        if not ok:
            return ret.errRet(msg)
        
        self.mainMenu.changed=True
        return ret.okRet("Key added.")

    def generate(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        if not confirm("Generate a new SSH Ed25519 key pair? The private key will be added to the config in base64 format and the public key will be added to the user's authorised keys."):
            return onSelReturn().errRet("Cancelled.")
        
        from .sftp_manager_hlp import add_new_key_pair
        
        ret = onSelReturn()
        ok, msg = add_new_key_pair(self.cfg, self.username)
        if not ok:
            return ret.errRet(msg)
        
        self.mainMenu.changed=True
        return ret.okRet("New key pair generated and added.")
