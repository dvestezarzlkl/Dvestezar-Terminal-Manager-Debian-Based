from __future__ import annotations

import os

from .lng.default import *
from libs.JBLibs.helper import getLogger, loadLng

loadLng()

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
    set_mountpoint_path,
    get_printable_keys,
    get_admin_mail,
    set_admin_mail,
    get_user_mail,
    set_user_mail,
    send_key_by_mail,
)

_MENU_NAME_: str = TXT_SFTP_MENU_NAME

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

    _VERSION_: str = "1.2.10"
    __VERSION__ = _VERSION_

    def basicTitle(self, add:str|list=None, username:str|None=TXT_SFTP_MENU_NOT_SELECTED) -> c_menu_block_items:
        """Vytvoří základní titulní blok pro menu.
        
        Returns:
            c_menu_block_items: titulní blok menu
        """
        menuname=_MENU_NAME_
        menuVer=self._VERSION_
        
        header=c_menu_block_items(blockColor=en_color.BRIGHT_CYAN )
        header.append( (menuname,'c') )
        header.append("-")
        header.append(TXT_SFTP_MENU_VERSION.format(version=menuVer))
        if username is not None:
            header.append((TXT_SFTP_MENU_SELECTED_USER, username))
        
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
            print(text_color(TXT_SFTP_MENU_WARNING.format(message=msg), en_color.BRIGHT_RED))
            anyKey()
        self.cfg = cfg
        self.users = list_users(self.cfg)
        self.changed = False

    def onExitMenu(self):
        if not self.changed:
            return None
        if confirm(TXT_SFTP_MENU_EXIT_UNSAVED_CONFIRM):
            return None
        return False

    def onShowMenu(self) -> None:
        # Compose the menu dynamically.  The header shows how many
        # users are configured.
        self.title = self.basicTitle()
        
        title = TXT_SFTP_MENU_USERS_COUNT.format(name=_MENU_NAME_, count=len(self.users))
        self.menu = [
            c_menu_title_label(text_color(title,en_color.CYAN)),
        ]
        if not cifs_exists():
            self.menu.append(
                c_menu_title_label(
                    text_color(TXT_SFTP_MENU_CIFS_MISSING, en_color.BRIGHT_RED)
                )
            )
        self.menu.extend([
            c_menu_item(text_color(TXT_SFTP_MENU_CREATE_USER, en_color.BRIGHT_GREEN), "n", self.create_user),
            c_menu_item(
                text_color(TXT_SFTP_MENU_ADMIN_MAIL, en_color.BRIGHT_YELLOW),
                "e",
                self.edit_admin_mail,
                atRight=mail_hlp.get_effective_admin_mail(get_admin_mail(self.cfg)) or TXT_SFTP_MENU_NOT_SET,
            ),
            None
        ])
        # Enumerate users; assign numeric selection keys for ease of use.
        # FIXME jako u disku zobrazovat ve sloupcích
        for idx, usr in enumerate(self.users, start=1):
            name = usr.get("sftpuser") or TXT_SFTP_MENU_USER_FALLBACK.format(index=idx)
            mp_count = len(usr.get("sftpmounts", {}))
            key_count = len(usr.get("sftpcerts", []))
            mail = usr.get("mail") or TXT_SFTP_MENU_NOT_SET
            label = text_color(f"{name}",en_color.YELLOW)
            atR = TXT_SFTP_MENU_USER_SUMMARY.format(mounts=mp_count, keys=key_count, mail=mail)
            # Create a submenu instance carrying the username.  The
            # c_menu framework will detect it as a submenu.
            self.menu.append(
                c_menu_item(label, str(idx), m_user(name, self),atRight=atR)
            )
            
        self.menu.append(None)
        if self.changed:
            self.menu.append(c_menu_item(text_color(TXT_SFTP_MENU_SAVE_APPLY, en_color.BRIGHT_RED), "a", self.apply_changes))
            self.menu.append(c_menu_item(text_color(TXT_SFTP_MENU_DISCARD_UNSAVED, en_color.BRIGHT_YELLOW), "d", self.cancel_changes))
        else:
            # apply changes = install update active sftp users according to curent config, dáme mgentu
            self.menu.append(c_menu_item(text_color(TXT_SFTP_MENU_APPLY_CURRENT, en_color.MAGENTA), "a", self.apply_changes))
            
        # kompletně smazat všechny aktivní uživatele - clean state, run sftpmanager delete all users
        self.menu.append(c_menu_item(text_color(TXT_SFTP_MENU_UNINSTALL_ALL, en_color.BRIGHT_RED), "u", self.uninstall_all_users))

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
        if not confirm(TXT_SFTP_MENU_UNINSTALL_CONFIRM):
            return onSelReturn().errRet(TXT_SFTP_MENU_CANCELLED)

        ok, msg = uninstall_all_users()
        if not ok:
            return onSelReturn().errRet(msg)
        return onSelReturn(ok=TXT_SFTP_MENU_ALL_USERS_UNINSTALLED)

    def create_user(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Prompt for a new user name and append it to the config."""
        ret = onSelReturn()
        name = get_input(TXT_SFTP_MENU_ENTER_NEW_USER)
        if not name:
            return ret.errRet(TXT_SFTP_MENU_OPERATION_CANCELLED)
        # Prevent duplicate names
        if find_user(self.cfg, name):
            return ret.errRet(TXT_SFTP_MENU_USER_EXISTS.format(username=name))
        hlp_add_user(self.cfg, name)
        self.changed = True
        return ret.okRet(TXT_SFTP_MENU_USER_CREATED.format(username=name))

    def edit_admin_mail(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Set or update the admin email address stored in the config."""
        ret = onSelReturn()
        current = get_admin_mail(self.cfg)
        prompt = TXT_SFTP_MENU_ENTER_ADMIN_MAIL
        if current:
            prompt = TXT_SFTP_MENU_ENTER_ADMIN_MAIL_CURRENT.format(mail=current)
        mail = get_input(
            prompt,
            accept_empty=False,
            rgx=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$",
            maxLen=254,
            errTx=TXT_SFTP_MENU_INVALID_EMAIL
        )
        if not mail:
            return ret.errRet(TXT_SFTP_MENU_OPERATION_CANCELLED)
        ok, msg = set_admin_mail(self.cfg, mail)
        if not ok:
            return ret.errRet(msg)
        self.changed = True
        return ret.okRet(TXT_SFTP_MENU_ADMIN_MAIL_SET.format(mail=mail))

    def apply_changes(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Invoke the SFTP manager script to apply changes to the system."""
        ok, msg = apply_changes(cfg=self.cfg, save=True)
        if not ok:
            log.error(f"Failed to apply changes: {msg}")
            print(text_color(TXT_SFTP_MENU_ERROR.format(message=msg), en_color.BRIGHT_RED))
            anyKey()
            return onSelReturn().errRet(TXT_SFTP_MENU_APPLY_FAILED.format(message=msg))
        # Apply is a transaction boundary: reload the persisted configuration so
        # subsequent edits in the same process use fresh config/user objects.
        self.onEnterMenu()
        anyKey()
        return onSelReturn(ok=TXT_SFTP_MENU_CHANGES_APPLIED)
    
    def cancel_changes(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Discard unsaved changes by reloading the configuration."""
        if not confirm(TXT_SFTP_MENU_DISCARD_CONFIRM):
            return onSelReturn().errRet(TXT_SFTP_MENU_CANCELLED)
        self.onEnterMenu()  # Reload config and reset state
        return onSelReturn(ok=TXT_SFTP_MENU_CHANGES_DISCARDED)


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
        self.title = self.mainMenu.basicTitle(add=TXT_SFTP_MENU_SECTION_USER_DETAILS, username=self.username)

        title = TXT_SFTP_MENU_USER_TITLE.format(username=self.username)
        usr = self.user or {}
        current_mail = get_user_mail(self.mainMenu.cfg, self.username) or TXT_SFTP_MENU_NOT_SET
        self.menu = [
            c_menu_title_label(text_color(title,en_color.CYAN)),
            c_menu_item(
                text_color(TXT_SFTP_MENU_MAIL, en_color.BRIGHT_YELLOW),
                "e",
                self.edit_mail,
                atRight=current_mail,
            ),
            c_menu_item(text_color(TXT_SFTP_MENU_DELETE_USER, en_color.BRIGHT_RED), "d", self.delete_user),
            None,
            c_menu_item(TXT_SFTP_MENU_MANAGE_MOUNTPOINTS, "m", m_user_mountpoints(self.username, self.mainMenu, self.user), atRight=TXT_SFTP_MENU_QTY.format(count=len(usr.get("sftpmounts", {})))),
            c_menu_item(TXT_SFTP_MENU_MANAGE_KEYS, "k", m_user_keys(self.username, self.mainMenu, self.user), atRight=TXT_SFTP_MENU_QTY.format(count=len(usr.get("sftpcerts", [])))),
        ]

    def delete_user(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Remove this user from the configuration after confirmation."""
        ret = onSelReturn()
        if not confirm(TXT_SFTP_MENU_DELETE_USER_CONFIRM.format(username=self.username)):
            return ret.errRet(TXT_SFTP_MENU_CANCELLED)
        if not hlp_delete_user(self.mainMenu.cfg, self.username):
            return ret.errRet(TXT_SFTP_MENU_USER_NOT_FOUND.format(username=self.username))
        
        self.mainMenu.changed=True
        # End this menu so that the parent list refreshes without the user
        return onSelReturn(endMenu=True)

    def edit_mail(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        """Set, update, or clear the optional mail address for this user."""
        ret = onSelReturn()
        current = get_user_mail(self.mainMenu.cfg, self.username)
        prompt = TXT_SFTP_MENU_ENTER_USER_MAIL
        if current:
            prompt = TXT_SFTP_MENU_ENTER_USER_MAIL_CURRENT.format(mail=current)
        mail = get_input(
            prompt,
            accept_empty=True,
            rgx=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$",
            maxLen=254,
            errTx=TXT_SFTP_MENU_INVALID_EMAIL
        )
        if mail is None:
            return ret.errRet(TXT_SFTP_MENU_OPERATION_CANCELLED)
        if not mail:
            if current and not confirm(TXT_SFTP_MENU_CLEAR_USER_MAIL_CONFIRM.format(username=self.username)):
                return ret.errRet(TXT_SFTP_MENU_CANCELLED)
            ok, msg = set_user_mail(self.mainMenu.cfg, self.username, None)
        else:
            ok, msg = set_user_mail(self.mainMenu.cfg, self.username, mail)
        if not ok:
            return ret.errRet(msg)
        self.mainMenu.changed=True
        return ret.okRet(TXT_SFTP_MENU_USER_MAIL_UPDATED)


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
        self.title = self.mainMenu.basicTitle(add=TXT_SFTP_MENU_SECTION_MOUNTPOINTS, username=self.username)
        
        self.mounts: List[Tuple[str, str]] = hlp_list_mountpoints(self.cfg, self.username)
        
        self.menu = [
            c_menu_title_label(text_color(TXT_SFTP_MENU_MOUNTPOINTS_FOR.format(username=self.username), en_color.CYAN)),
            c_menu_item(text_color(TXT_SFTP_MENU_ADD_MOUNTPOINT, en_color.BRIGHT_GREEN), "a", self.add_mountpoint),
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
        label = TXT_SFTP_MENU_NOT_SET
        target = TXT_SFTP_MENU_NOT_SET
        
        #pomocná funkce na zobrazení hlavičky pro zadávání mountpointu
        def show_header():
            cls()
            print(TXT_SFTP_MENU_MOUNTPOINT_HEADER.format(username=self.username))
            print(TXT_SFTP_MENU_MOUNTPOINT_NAME.format(label=label))
            print(TXT_SFTP_MENU_MOUNTPOINT_TARGET.format(target=target))
            print(("*"*40) + "\n")
        
        while True:
            show_header()
            label = get_input(
                TXT_SFTP_MENU_ENTER_MOUNTPOINT_NAME,
                rgx=r"^[a-zA-Z0-9_\-]+$",
                maxLen=32,
                errTx=TXT_SFTP_MENU_INVALID_MOUNTPOINT_NAME
            )        
            if not label:
                return ret.errRet(TXT_SFTP_MENU_NO_MOUNTPOINT_NAME)
            if checkMountpointExists(self.cfg, self.username, label):
                print(text_color(TXT_SFTP_MENU_MOUNTPOINT_EXISTS.format(label=label, username=self.username), en_color.BRIGHT_RED))
                anyKey()
                continue
            break
        
        while True:
            show_header()
            target = selectDir("/", TXT_SFTP_MENU_SELECT_MOUNTPOINT_PATH)
            if not target:
                return ret.errRet(TXT_SFTP_MENU_NO_MOUNTPOINT_PATH)
            existing_label = checkMountPointPathExists(self.cfg, self.username, target)
            if existing_label:
                print(text_color(TXT_SFTP_MENU_MOUNTPOINT_PATH_USED.format(path=target, label=existing_label), en_color.BRIGHT_RED))
                anyKey()
                continue
            break
        
        # vybereme z možností R/RW
        opts=[
            select_item(TXT_SFTP_MENU_READ_ONLY, "R", "R"),
            select_item(TXT_SFTP_MENU_READ_WRITE, "RW", "RW")
        ]
        show_header()
        x = select(TXT_SFTP_MENU_SELECT_ACCESS_MODE, opts)
        if not x or x.item is None:
            return ret.errRet(TXT_SFTP_MENU_NO_ACCESS_MODE)

        access_mode = x.item.data
        if not hlp_add_mountpoint(self.cfg, self.username, label, target, readOnly=(access_mode=="R")):
            return ret.errRet(TXT_SFTP_MENU_USER_NOT_FOUND.format(username=self.username))
        
        self.mainMenu.changed=True
        return ret.okRet(TXT_SFTP_MENU_MOUNTPOINT_ADDED)

    def modify_mountpoint(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        from .sftp_manager_hlp import checkMountPointPathExists

        opt=[]
        rTx=get_mountpointReadOnlyStatus(self.cfg, self.username, selItem.data)
        if rTx:
            opt.append(select_item(TXT_SFTP_MENU_SET_READ_WRITE, "W", "W"))
        else:
            opt.append(select_item(TXT_SFTP_MENU_SET_READ_ONLY, "R", "R"))
        opt.append(select_item(TXT_SFTP_MENU_CHANGE_MOUNTPOINT_PATH, "P", "P"))
        opt.append(select_item(text_color(TXT_SFTP_MENU_DELETE_MOUNTPOINT, en_color.BRIGHT_RED), "D", "D"))
        x = select(TXT_SFTP_MENU_SELECT_MOUNTPOINT_ACTION.format(label=selItem.data), opt)
        if not x or x.item is None:
            return onSelReturn().errRet(TXT_SFTP_MENU_NO_ACTION)
        x=x.item.data

        if x == "D":
            if not confirm(TXT_SFTP_MENU_REMOVE_MOUNTPOINT_CONFIRM.format(label=selItem.data)):
                return onSelReturn().errRet(TXT_SFTP_MENU_CANCELLED)
            if not hlp_delete_mountpoint(self.cfg, self.username, selItem.data):
                return onSelReturn().errRet(TXT_SFTP_MENU_MOUNTPOINT_NOT_FOUND)
            self.mainMenu.changed=True
            return onSelReturn(ok=TXT_SFTP_MENU_MOUNTPOINT_REMOVED)

        if x == "P":
            usr = find_user(self.cfg, self.username)
            mounts = usr.get("sftpmounts", {}) if usr else {}
            current_target = mounts.get(selItem.data)
            if not isinstance(current_target, str):
                return onSelReturn().errRet(TXT_SFTP_MENU_MOUNTPOINT_NOT_FOUND)

            start_path = current_target if os.path.isdir(current_target) else "/"
            while True:
                target = selectDir(
                    start_path,
                    TXT_SFTP_MENU_SELECT_NEW_MOUNTPOINT_PATH.format(path=current_target),
                )
                if not target:
                    return onSelReturn().errRet(TXT_SFTP_MENU_NO_MOUNTPOINT_PATH)
                if target == current_target:
                    return onSelReturn(ok=TXT_SFTP_MENU_MOUNTPOINT_PATH_UNCHANGED)
                existing_label = checkMountPointPathExists(self.cfg, self.username, target)
                if existing_label and existing_label != selItem.data:
                    print(text_color(TXT_SFTP_MENU_MOUNTPOINT_PATH_USED.format(path=target, label=existing_label), en_color.BRIGHT_RED))
                    anyKey()
                    continue
                break

            if not set_mountpoint_path(self.cfg, self.username, selItem.data, target):
                return onSelReturn().errRet(TXT_SFTP_MENU_MOUNTPOINT_UPDATE_FAILED)
            self.mainMenu.changed=True
            return onSelReturn(ok=TXT_SFTP_MENU_MOUNTPOINT_PATH_UPDATED.format(path=target))

        if not set_mountpoint_readonly(self.cfg, self.username, selItem.data, readOnly=(x=="R")):
            return onSelReturn().errRet(TXT_SFTP_MENU_MOUNTPOINT_UPDATE_FAILED)
        self.mainMenu.changed=True
        return onSelReturn(ok=TXT_SFTP_MENU_MOUNTPOINT_UPDATED)

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
        self.title = self.mainMenu.basicTitle(add=TXT_SFTP_MENU_SECTION_KEY_ACTION, username=self.username)
        self.menu = [
            c_menu_title_label(text_color(TXT_SFTP_MENU_KEY_TITLE.format(name=self.display_name), en_color.CYAN)),
            c_menu_item(
                text_color(TXT_SFTP_MENU_SHOW_PUBLIC_KEY, en_color.BRIGHT_CYAN),
                "p",
                self.show_public_key,
            ),
        ]

        if self.has_private:
            self.menu.extend([
                c_menu_item(
                    text_color(TXT_SFTP_MENU_SHOW_PRIVATE_KEY, en_color.BRIGHT_MAGENTA),
                    "s",
                    self.show_private_key,
                ),
                c_menu_item(
                    text_color(TXT_SFTP_MENU_SEND_BY_MAIL, en_color.BRIGHT_GREEN),
                    "m",
                    self.send_by_mail,
                    atRight=mail_hlp.get_effective_admin_mail(get_admin_mail(self.cfg)) or TXT_SFTP_MENU_ADMIN_MAIL_NOT_SET,
                    enabled=bool(mail_hlp.get_effective_admin_mail(get_admin_mail(self.cfg))),
                ),
                c_menu_item(
                    text_color(TXT_SFTP_MENU_DELETE_CERTIFICATE, en_color.BRIGHT_RED),
                    "d",
                    self.delete_entry,
                ),
            ])
        else:
            self.menu.extend([
                c_menu_item(
                    text_color(TXT_SFTP_MENU_SEND_BY_MAIL, en_color.BRIGHT_GREEN),
                    "m",
                    self.send_by_mail,
                    atRight=mail_hlp.get_effective_admin_mail(get_admin_mail(self.cfg)) or TXT_SFTP_MENU_ADMIN_MAIL_NOT_SET,
                    enabled=bool(mail_hlp.get_effective_admin_mail(get_admin_mail(self.cfg))),
                ),
                c_menu_item(
                    text_color(TXT_SFTP_MENU_DELETE_KEY, en_color.BRIGHT_RED),
                    "d",
                    self.delete_entry,
                ),
            ])

    def show_public_key(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        ret = onSelReturn()
        print(text_color(TXT_SFTP_MENU_PUBLIC_KEY, en_color.BRIGHT_CYAN))
        print(self.pub_key)
        anyKey()
        return ret.okRet(TXT_SFTP_MENU_PUBLIC_KEY_DISPLAYED)

    def show_private_key(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        ret = onSelReturn()
        if not self.has_private:
            return ret.errRet(TXT_SFTP_MENU_NO_PRIVATE_KEY)
        print(text_color(TXT_SFTP_MENU_PRIVATE_KEY, en_color.BRIGHT_MAGENTA))
        print(self.priv_key)
        anyKey()
        return ret.okRet(TXT_SFTP_MENU_PRIVATE_KEY_DISPLAYED)

    def send_by_mail(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        ret = onSelReturn()
        if not mail_hlp.isConfigured():
            return ret.errRet(TXT_SFTP_MENU_MAIL_NOT_CONFIGURED)
        ok, msg = send_key_by_mail(self.cfg, self.username, self.keystr)
        if not ok:
            return ret.errRet(msg)
        anyKey()
        return ret.okRet(TXT_SFTP_MENU_KEY_SENT)

    def delete_entry(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        ret = onSelReturn()
        if self.has_private:
            prompt = TXT_SFTP_MENU_REMOVE_CERTIFICATE_CONFIRM
            success_msg = TXT_SFTP_MENU_CERTIFICATE_REMOVED
        else:
            prompt = TXT_SFTP_MENU_REMOVE_KEY_CONFIRM
            success_msg = TXT_SFTP_MENU_KEY_REMOVED
        if not confirm(prompt):
            return ret.errRet(TXT_SFTP_MENU_CANCELLED)
        if not hlp_delete_key(self.cfg, self.username, self.keystr):
            return ret.errRet(TXT_SFTP_MENU_KEY_NOT_FOUND)
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
        self.title = self.mainMenu.basicTitle(add=TXT_SFTP_MENU_SECTION_KEYS, username=self.username)
        
        self.keys: List[Tuple[str,str]] = hlp_list_keys(self.cfg, self.username)
        
        self.menu = [
            c_menu_title_label(text_color(TXT_SFTP_MENU_KEYS_FOR.format(username=self.username), en_color.CYAN)),
            c_menu_item(TXT_SFTP_MENU_ADD_KEY, "a", self.add_key),
            c_menu_item(TXT_SFTP_MENU_GENERATE_PAIR, "g", self.generate),
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
                    atRight=mail_hlp.get_effective_admin_mail(get_admin_mail(self.mainMenu.cfg)) or TXT_SFTP_MENU_ADMIN_MAIL_NOT_SET,
                )
            )

    def add_key(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        ret = onSelReturn()
        keystr = get_input(TXT_SFTP_MENU_PASTE_KEY)
        if not keystr:
            return ret.errRet(TXT_SFTP_MENU_NO_KEY)
        ok,msg = hlp_add_key(self.cfg, self.username, keystr)
        if not ok:
            return ret.errRet(msg)
        
        self.mainMenu.changed=True
        return ret.okRet(TXT_SFTP_MENU_KEY_ADDED)

    def generate(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        if not confirm(TXT_SFTP_MENU_GENERATE_CONFIRM):
            return onSelReturn().errRet(TXT_SFTP_MENU_CANCELLED)
        
        from .sftp_manager_hlp import add_new_key_pair
        
        ret = onSelReturn()
        ok, msg = add_new_key_pair(self.cfg, self.username)
        if not ok:
            return ret.errRet(msg)
        
        self.mainMenu.changed=True
        return ret.okRet(TXT_SFTP_MENU_KEY_PAIR_ADDED)
