"""Shared Firewall Manager terminal UI helpers built only on JBLibs."""
from __future__ import annotations

import re
from typing import Any

from .lng.default import *
from libs.JBLibs.helper import getInterfaces, loadLng
loadLng()

from libs.JBLibs.c_menu import c_menu_block_items, printBlock
from libs.JBLibs.input import get_input, select, select_item
from libs.JBLibs.term import cls, en_color, text_color


_PORT_INPUT_RE = re.compile(
    r"^-$|^$|^[0-9]{1,5}(?:-[0-9]{1,5})?"
    r"(?:,[0-9]{1,5}(?:-[0-9]{1,5})?)*$"
)
_INTERFACE_RE = re.compile(r"^[a-zA-Z0-9_.+-]{1,15}$")


def color_direction(value: str) -> str:
    return text_color(value.upper(), {
        "input": en_color.RED,
        "output": en_color.GREEN,
        "forward": en_color.YELLOW,
    }.get(value, en_color.WHITE))


def color_action(value: str) -> str:
    return text_color(("DROP" if value == "deny" else value.upper()), {
        "allow": en_color.GREEN,
        "deny": en_color.YELLOW,
        "reject": en_color.RED,
    }.get(value, en_color.WHITE))


def color_protocol(value: str) -> str:
    return text_color(value.upper(), {
        "tcp": en_color.GREEN,
        "udp": en_color.CYAN,
    }.get(value, en_color.WHITE))


def context_block(
    context: dict[str, str] | None = None,
) -> c_menu_block_items:
    block = c_menu_block_items()
    if context:
        for label, value in context.items():
            block.append((label, value or "*"))
    return block


def progress_block(
    title: str,
    context: dict[str, str] | None = None,
) -> c_menu_block_items:
    block = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
    block.append((title, "c"))
    block.append("-")
    block.extend(context_block(context))
    return block


def render_progress(
    title: str,
    context: dict[str, str],
    width: int,
) -> int:
    """Redraw accepted form values like Node-RED print_newInstance()."""
    cls()
    return printBlock(
        progress_block(title, context),
        c_menu_block_items(),
        min_width=width,
    )


def pick(
    message: str,
    options: list[tuple[str, str, Any]],
    width: int,
    *,
    title: str = TXT_FW_EDITOR_TITLE,
    context: dict[str, str] | None = None,
) -> Any | None:
    result = select(
        message,
        [select_item(label, key, data) for key, label, data in options],
        width,
        title=title,
        subTitle=context_block(context),
    )
    if not result or result.item is None:
        return None
    return result.item.data


def prompt(
    message: str,
    *,
    width: int,
    current: str | int | None = None,
    required: bool = False,
    max_len: int = 255,
    rgx: Any = None,
    title: str = TXT_FW_EDITOR_TITLE,
    context: dict[str, str] | None = None,
) -> str | None:
    if context is not None:
        width = max(width, render_progress(title, context, width))
    note = ""
    if current not in (None, ""):
        note = TXT_FW_EDITOR_CURRENT.format(value=current)
        if not required:
            note += "\n" + TXT_FW_EDITOR_CLEAR
    value = get_input(
        message,
        accept_empty=(not required or current not in (None, "")),
        maxLen=max_len,
        rgx=rgx,
        titleNote=note,
        minMessageWidth=width,
    )
    if value is None:
        return None
    if not required and value == "-":
        return ""
    if value == "" and current not in (None, ""):
        return str(current)
    return value


def host_interface_options() -> list[tuple[str, str, str]]:
    """Return detected interfaces with short collision-free select choices."""
    found: list[tuple[str, str]] = []
    for iface in getInterfaces(noLoop=False):
        name = str(iface.name or "").strip()
        if not _INTERFACE_RE.fullmatch(name):
            continue
        details = ", ".join(
            str(ip) for ip in (iface.ipv4, iface.ipv6) if ip
        )
        found.append((name, f"{name} ({details})" if details else name))
    found.sort(key=lambda item: item[0])
    return [
        (str(index), label, name)
        for index, (name, label) in enumerate(found, start=1)
    ]


def pick_interface(
    *,
    width: int,
    context: dict[str, str],
    current: str = "",
    allow_any: bool = True,
    title: str = TXT_FW_EDITOR_TITLE,
) -> str | None:
    options: list[tuple[str, str, str]] = []
    if allow_any:
        options.append(("a", TXT_FW_EDITOR_IFACE_ANY, ""))
    try:
        options.extend(host_interface_options())
    except (OSError, ValueError):
        pass
    known = {item[2] for item in options}
    if current and current not in known:
        options.append((
            "old",
            TXT_FW_EDITOR_IFACE_OLD.format(name=current),
            current,
        ))
    options.append(("m", TXT_FW_EDITOR_IFACE_MANUAL, "__manual__"))
    value = pick(
        TXT_FW_EDITOR_INTERFACE_OPTIONAL,
        options,
        width,
        title=title,
        context=context,
    )
    if value is None:
        return None
    if value != "__manual__":
        return value
    return prompt(
        TXT_FW_EDITOR_INTERFACE_OPTIONAL,
        width=width,
        current=current,
        required=True,
        max_len=15,
        rgx=_INTERFACE_RE,
        title=title,
        context=context,
    )
