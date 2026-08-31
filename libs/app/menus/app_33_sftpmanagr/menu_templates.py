from __future__ import annotations

import os
from typing import Optional

from .lng.default import *
from libs.JBLibs.helper import loadLng

loadLng()

from libs.JBLibs.c_menu import c_menu, c_menu_item, c_menu_title_label, onSelReturn
from libs.JBLibs.input import anyKey, confirm, get_input, select, selectDir, select_item
from libs.JBLibs.term import text_color, en_color

from .sftp_template_hlp import (
    add_template_mountpoint,
    assign_template,
    assigned_templates,
    create_template,
    create_template_from_user,
    delete_template,
    delete_template_mountpoint,
    find_template,
    list_template_mounts,
    list_templates,
    set_template_mountpoint_label,
    set_template_mountpoint_path,
    unassign_template,
)


class m_mountpoint_templates(c_menu):
    ESC_is_quit = True

    def __init__(self, mainMenu) -> None:
        super().__init__()
        self.mainMenu = mainMenu
        self.cfg = mainMenu.cfg

    def onEnterMenu(self) -> None:
        self.cfg = self.mainMenu.cfg

    def onShowMenu(self) -> None:
        templates = list_templates(self.cfg)
        self.title = self.mainMenu.basicTitle(
            add=TXT_SFTP_MENU_SECTION_TEMPLATES,
            username=None,
        )
        self.menu = [
            c_menu_title_label(text_color(TXT_SFTP_MENU_TEMPLATES_TITLE, en_color.CYAN)),
            c_menu_item(
                text_color(TXT_SFTP_MENU_TEMPLATE_CREATE, en_color.BRIGHT_GREEN),
                "n",
                self.create_empty,
            ),
            c_menu_item(
                text_color(TXT_SFTP_MENU_TEMPLATE_CREATE_FROM_USER, en_color.BRIGHT_GREEN),
                "c",
                self.create_from_user,
            ),
            None,
        ]
        for idx, (name, template) in enumerate(templates, start=1):
            mounts = template.get("mounts", {}) if isinstance(template, dict) else {}
            count = len(mounts) if isinstance(mounts, dict) else 0
            self.menu.append(
                c_menu_item(
                    text_color(name, en_color.YELLOW),
                    str(idx),
                    m_mountpoint_template(name, self.mainMenu),
                    atRight=TXT_SFTP_MENU_QTY.format(count=count),
                )
            )

    def _read_template_name(self, prompt: str) -> Optional[str]:
        return get_input(
            prompt,
            rgx=r"^[a-zA-Z0-9._\-]+$",
            maxLen=64,
            errTx=TXT_SFTP_MENU_TEMPLATE_INVALID_NAME,
        )

    def create_empty(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        name = self._read_template_name(TXT_SFTP_MENU_TEMPLATE_ENTER_NAME)
        if not name:
            return onSelReturn().errRet(TXT_SFTP_MENU_OPERATION_CANCELLED)
        if not create_template(self.cfg, name):
            return onSelReturn().errRet(TXT_SFTP_MENU_TEMPLATE_CREATE_FAILED.format(name=name))
        self.mainMenu.changed = True
        return onSelReturn(ok=TXT_SFTP_MENU_TEMPLATE_CREATED.format(name=name))

    def create_from_user(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        users = [
            user.get("sftpuser")
            for user in self.cfg.get("users", [])
            if isinstance(user, dict) and isinstance(user.get("sftpuser"), str)
        ]
        if not users:
            return onSelReturn().errRet(TXT_SFTP_MENU_TEMPLATE_NO_USERS)
        options = [
            select_item(username, str(idx), username)
            for idx, username in enumerate(users, start=1)
        ]
        selected = select(TXT_SFTP_MENU_TEMPLATE_SELECT_SOURCE_USER, options)
        if not selected or selected.item is None:
            return onSelReturn().errRet(TXT_SFTP_MENU_OPERATION_CANCELLED)
        username = selected.item.data
        name = self._read_template_name(
            TXT_SFTP_MENU_TEMPLATE_ENTER_NAME_FROM_USER.format(username=username)
        )
        if not name:
            return onSelReturn().errRet(TXT_SFTP_MENU_OPERATION_CANCELLED)
        ok, count = create_template_from_user(self.cfg, name, username)
        if not ok:
            return onSelReturn().errRet(
                TXT_SFTP_MENU_TEMPLATE_CREATE_FROM_USER_FAILED.format(username=username)
            )
        self.mainMenu.changed = True
        return onSelReturn(
            ok=TXT_SFTP_MENU_TEMPLATE_CREATED_FROM_USER.format(
                name=name,
                username=username,
                count=count,
            )
        )


class m_mountpoint_template(c_menu):
    ESC_is_quit = True

    def __init__(self, template_name: str, mainMenu) -> None:
        super().__init__()
        self.template_name = template_name
        self.mainMenu = mainMenu
        self.cfg = mainMenu.cfg

    def onEnterMenu(self) -> None:
        self.cfg = self.mainMenu.cfg

    def onShowMenu(self) -> None:
        template = find_template(self.cfg, self.template_name)
        if template is None:
            self.menu = [c_menu_title_label(text_color(TXT_SFTP_MENU_TEMPLATE_NOT_FOUND, en_color.BRIGHT_RED))]
            return
        self.title = self.mainMenu.basicTitle(
            add=TXT_SFTP_MENU_SECTION_TEMPLATE_DETAIL.format(name=self.template_name),
            username=None,
        )
        self.menu = [
            c_menu_title_label(
                text_color(
                    TXT_SFTP_MENU_TEMPLATE_DETAIL_TITLE.format(name=self.template_name),
                    en_color.CYAN,
                )
            ),
            c_menu_item(
                text_color(TXT_SFTP_MENU_TEMPLATE_ADD_MOUNTPOINT, en_color.BRIGHT_GREEN),
                "a",
                self.add_mountpoint,
            ),
            c_menu_item(
                text_color(TXT_SFTP_MENU_TEMPLATE_DELETE, en_color.BRIGHT_RED),
                "d",
                self.delete_this_template,
            ),
            None,
        ]
        for idx, (mount_id, row) in enumerate(list_template_mounts(self.cfg, self.template_name), start=1):
            label = str(row.get("label", mount_id))
            path = str(row.get("path", ""))
            item = c_menu_item(
                text_color(label, en_color.YELLOW) + " → " + text_color(path, en_color.MAGENTA),
                str(idx),
                self.modify_mountpoint,
                atRight=mount_id,
            )
            item.data = mount_id
            self.menu.append(item)

    def _header(self, label: str, target: str) -> None:
        print(TXT_SFTP_MENU_TEMPLATE_MOUNTPOINT_HEADER.format(name=self.template_name))
        print(TXT_SFTP_MENU_MOUNTPOINT_NAME.format(label=label))
        print(TXT_SFTP_MENU_MOUNTPOINT_TARGET.format(target=target))
        print("*" * 40)
        print()

    def add_mountpoint(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        label = get_input(
            TXT_SFTP_MENU_ENTER_MOUNTPOINT_NAME,
            rgx=r"^[a-zA-Z0-9_\-]+$",
            maxLen=32,
            errTx=TXT_SFTP_MENU_INVALID_MOUNTPOINT_NAME,
        )
        if not label:
            return onSelReturn().errRet(TXT_SFTP_MENU_NO_MOUNTPOINT_NAME)
        target = selectDir("/", TXT_SFTP_MENU_SELECT_MOUNTPOINT_PATH)
        if not target:
            return onSelReturn().errRet(TXT_SFTP_MENU_NO_MOUNTPOINT_PATH)
        target = str(target)
        mount_id = add_template_mountpoint(self.cfg, self.template_name, label, target)
        if mount_id is None:
            return onSelReturn().errRet(TXT_SFTP_MENU_TEMPLATE_MOUNTPOINT_ADD_FAILED)
        self.mainMenu.changed = True
        return onSelReturn(ok=TXT_SFTP_MENU_TEMPLATE_MOUNTPOINT_ADDED)

    def modify_mountpoint(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        mount_id = selItem.data
        row = dict(list_template_mounts(self.cfg, self.template_name)).get(mount_id)
        if not isinstance(row, dict):
            return onSelReturn().errRet(TXT_SFTP_MENU_MOUNTPOINT_NOT_FOUND)
        label = str(row.get("label", mount_id))
        path = str(row.get("path", ""))
        options = [
            select_item(TXT_SFTP_MENU_TEMPLATE_CHANGE_LABEL, "L", "L"),
            select_item(TXT_SFTP_MENU_CHANGE_MOUNTPOINT_PATH, "P", "P"),
            select_item(text_color(TXT_SFTP_MENU_DELETE_MOUNTPOINT, en_color.BRIGHT_RED), "D", "D"),
        ]
        selected = select(TXT_SFTP_MENU_SELECT_MOUNTPOINT_ACTION.format(label=label), options)
        if not selected or selected.item is None:
            return onSelReturn().errRet(TXT_SFTP_MENU_NO_ACTION)
        action = selected.item.data
        if action == "D":
            if not confirm(TXT_SFTP_MENU_REMOVE_MOUNTPOINT_CONFIRM.format(label=label)):
                return onSelReturn().errRet(TXT_SFTP_MENU_CANCELLED)
            if not delete_template_mountpoint(self.cfg, self.template_name, mount_id):
                return onSelReturn().errRet(TXT_SFTP_MENU_MOUNTPOINT_NOT_FOUND)
            self.mainMenu.changed = True
            return onSelReturn(ok=TXT_SFTP_MENU_MOUNTPOINT_REMOVED)
        if action == "L":
            new_label = get_input(
                TXT_SFTP_MENU_TEMPLATE_ENTER_NEW_LABEL.format(label=label),
                rgx=r"^[a-zA-Z0-9_\-]+$",
                maxLen=32,
                errTx=TXT_SFTP_MENU_INVALID_MOUNTPOINT_NAME,
            )
            if not new_label:
                return onSelReturn().errRet(TXT_SFTP_MENU_OPERATION_CANCELLED)
            if not set_template_mountpoint_label(self.cfg, self.template_name, mount_id, new_label):
                return onSelReturn().errRet(TXT_SFTP_MENU_TEMPLATE_MOUNTPOINT_UPDATE_FAILED)
            self.mainMenu.changed = True
            return onSelReturn(ok=TXT_SFTP_MENU_TEMPLATE_LABEL_UPDATED.format(label=new_label))
        start_path = path if os.path.isdir(path) else "/"
        target = selectDir(
            start_path,
            TXT_SFTP_MENU_SELECT_NEW_MOUNTPOINT_PATH.format(path=path),
        )
        if not target:
            return onSelReturn().errRet(TXT_SFTP_MENU_NO_MOUNTPOINT_PATH)
        target = str(target)
        if target == path:
            return onSelReturn(ok=TXT_SFTP_MENU_MOUNTPOINT_PATH_UNCHANGED)
        if not set_template_mountpoint_path(self.cfg, self.template_name, mount_id, target):
            return onSelReturn().errRet(TXT_SFTP_MENU_TEMPLATE_MOUNTPOINT_UPDATE_FAILED)
        self.mainMenu.changed = True
        return onSelReturn(ok=TXT_SFTP_MENU_MOUNTPOINT_PATH_UPDATED.format(path=target))

    def delete_this_template(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        if not confirm(TXT_SFTP_MENU_TEMPLATE_DELETE_CONFIRM.format(name=self.template_name)):
            return onSelReturn().errRet(TXT_SFTP_MENU_CANCELLED)
        if not delete_template(self.cfg, self.template_name):
            return onSelReturn().errRet(TXT_SFTP_MENU_TEMPLATE_NOT_FOUND)
        self.mainMenu.changed = True
        return onSelReturn(ok=TXT_SFTP_MENU_TEMPLATE_DELETED.format(name=self.template_name), endMenu=True)


class m_user_templates(c_menu):
    ESC_is_quit = True

    def __init__(self, username: str, mainMenu) -> None:
        super().__init__()
        self.username = username
        self.mainMenu = mainMenu
        self.cfg = mainMenu.cfg

    def onEnterMenu(self) -> None:
        self.cfg = self.mainMenu.cfg

    def onShowMenu(self) -> None:
        assigned = set(assigned_templates(self.cfg, self.username))
        self.title = self.mainMenu.basicTitle(
            add=TXT_SFTP_MENU_SECTION_USER_TEMPLATES,
            username=self.username,
        )
        self.menu = [
            c_menu_title_label(
                text_color(
                    TXT_SFTP_MENU_USER_TEMPLATES_TITLE.format(username=self.username),
                    en_color.CYAN,
                )
            )
        ]
        templates = list_templates(self.cfg)
        if not templates:
            self.menu.append(c_menu_title_label(TXT_SFTP_MENU_TEMPLATE_NONE))
            return
        for idx, (name, _) in enumerate(templates, start=1):
            is_assigned = name in assigned
            item = c_menu_item(
                text_color(name, en_color.YELLOW),
                str(idx),
                self.toggle_template,
                atRight=(
                    TXT_SFTP_MENU_TEMPLATE_ASSIGNED
                    if is_assigned
                    else TXT_SFTP_MENU_TEMPLATE_NOT_ASSIGNED
                ),
            )
            item.data = name
            self.menu.append(item)

    def toggle_template(self, selItem: c_menu_item) -> Optional[onSelReturn]:
        name = selItem.data
        assigned = name in assigned_templates(self.cfg, self.username)
        if assigned:
            if not confirm(
                TXT_SFTP_MENU_TEMPLATE_UNASSIGN_CONFIRM.format(
                    template=name,
                    username=self.username,
                )
            ):
                return onSelReturn().errRet(TXT_SFTP_MENU_CANCELLED)
            if not unassign_template(self.cfg, self.username, name):
                return onSelReturn().errRet(TXT_SFTP_MENU_TEMPLATE_ASSIGN_FAILED)
            self.mainMenu.changed = True
            return onSelReturn(ok=TXT_SFTP_MENU_TEMPLATE_UNASSIGNED.format(name=name))
        if not assign_template(self.cfg, self.username, name):
            return onSelReturn().errRet(TXT_SFTP_MENU_TEMPLATE_ASSIGN_FAILED)
        self.mainMenu.changed = True
        return onSelReturn(ok=TXT_SFTP_MENU_TEMPLATE_ASSIGNED_OK.format(name=name))
