from __future__ import annotations

from .lng.default import *
from libs.JBLibs.helper import getLogger, loadLng

loadLng()

from typing import Any

from libs.JBLibs import uart_tester
from libs.JBLibs.c_menu import c_menu, c_menu_block_items, c_menu_item, c_menu_title_label, onSelReturn
from libs.JBLibs.input import anyKey, get_input, select, select_item
from libs.JBLibs.term import cls, en_color, text_color

from .uart_menu_hlp import (
    BAUDRATES,
    BYTESIZES,
    MODES,
    PARITIES,
    STOPBITS,
    TIMEOUTS,
    UartSettings,
    get_config_path,
    list_serial_ports,
    load_settings,
    mode_label,
    parity_label,
    save_settings,
)

log = getLogger("uart_menu")

_MENU_NAME_: str = TXT_UART_MENU_NAME


class menu(c_menu):
    """Menu wrapper for the UART tester library."""

    _VERSION_: str = "1.0.0"
    ESC_is_quit: bool = True
    minMenuWidth: int = 80

    settings: UartSettings
    port_count: int = 0

    def onEnterMenu(self) -> None:
        self.settings = load_settings()

    def onShowMenu(self) -> None:
        ports = list_serial_ports()
        self.port_count = len(ports)
        self.title = self.basicTitle()

        port_ok = bool(self.settings.port)
        current_mode = mode_label(self.settings.mode)

        self.menu = [
            c_menu_title_label(text_color(TXT_UART_MENU_SECTION_RUN, en_color.BRIGHT_CYAN)),
            c_menu_item(
                text_color(TXT_UART_MENU_START_SELECTED, en_color.BRIGHT_GREEN),
                "s",
                self.start_selected_mode,
                atRight=current_mode,
                enabled=port_ok,
            ),
            c_menu_item(
                TXT_UART_MENU_START_TX,
                "tx",
                self.start_transmitter,
                enabled=port_ok,
            ),
            c_menu_item(
                TXT_UART_MENU_START_RX,
                "rx",
                self.start_receiver,
                enabled=port_ok,
            ),
            None,
            c_menu_title_label(text_color(TXT_UART_MENU_SECTION_SETTINGS, en_color.CYAN)),
            c_menu_item(
                TXT_UART_MENU_SET_MODE,
                "m",
                self.select_mode,
                atRight=current_mode,
            ),
            c_menu_item(
                TXT_UART_MENU_SET_PORT,
                "p",
                self.select_port,
                atRight=self.settings.port or TXT_UART_MENU_NOT_SET,
            ),
            c_menu_item(
                TXT_UART_MENU_PORT_MANUAL,
                "pm",
                self.manual_port,
            ),
            c_menu_item(
                TXT_UART_MENU_REFRESH_PORTS,
                "f",
                self.refresh_ports,
                atRight=str(self.port_count),
            ),
            c_menu_item(
                TXT_UART_MENU_SET_BAUDRATE,
                "b",
                self.select_baudrate,
                atRight=str(self.settings.baudrate),
            ),
            c_menu_item(
                TXT_UART_MENU_SET_PARITY,
                "pa",
                self.select_parity,
                atRight=parity_label(self.settings.parity),
            ),
            c_menu_item(
                TXT_UART_MENU_SET_BYTESIZE,
                "d",
                self.select_bytesize,
                atRight=str(self.settings.bytesize),
            ),
            c_menu_item(
                TXT_UART_MENU_SET_STOPBITS,
                "sb",
                self.select_stopbits,
                atRight=str(self.settings.stopbits),
            ),
            c_menu_item(
                TXT_UART_MENU_SET_TIMEOUT,
                "to",
                self.select_timeout,
                atRight=str(self.settings.timeout),
            ),
        ]

        if not port_ok:
            self.menu.insert(
                1,
                c_menu_item(text_color(TXT_UART_MENU_NO_PORT_SELECTED, en_color.BRIGHT_YELLOW)),
            )

    def basicTitle(self) -> c_menu_block_items:
        header = c_menu_block_items(blockColor=en_color.BRIGHT_CYAN)
        header.append((_MENU_NAME_, "c"))
        header.append("-")
        header.append((TXT_UART_MENU_VERSION, self._VERSION_))
        header.append((TXT_UART_MENU_CONFIG_FILE, str(get_config_path(create=False))))
        header.append((TXT_UART_MENU_PORT, self.settings.port or TXT_UART_MENU_NOT_SET))
        header.append((TXT_UART_MENU_BAUDRATE, str(self.settings.baudrate)))
        header.append((TXT_UART_MENU_PARITY, parity_label(self.settings.parity)))
        header.append((TXT_UART_MENU_BYTESIZE, str(self.settings.bytesize)))
        header.append((TXT_UART_MENU_STOPBITS, str(self.settings.stopbits)))
        header.append((TXT_UART_MENU_TIMEOUT, str(self.settings.timeout)))
        return header

    def start_selected_mode(self, selItem: c_menu_item) -> onSelReturn:
        return self._run_mode(self.settings.mode == "transmitter")

    def start_transmitter(self, selItem: c_menu_item) -> onSelReturn:
        self.settings.mode = "transmitter"
        if err := self._try_save_error():
            return onSelReturn().errRet(err)
        return self._run_mode(True)

    def start_receiver(self, selItem: c_menu_item) -> onSelReturn:
        self.settings.mode = "receiver"
        if err := self._try_save_error():
            return onSelReturn().errRet(err)
        return self._run_mode(False)

    def select_mode(self, selItem: c_menu_item) -> onSelReturn:
        options = [
            select_item(mode_label(mode), mode[:2], mode)
            for mode in MODES
        ]
        value = self._select_value(TXT_UART_MENU_SELECT_MODE, options)
        if value is None:
            return onSelReturn().errRet(TXT_UART_MENU_CANCELLED)
        self.settings.mode = str(value)
        return self._save_ok(TXT_UART_MENU_SAVED)

    def select_port(self, selItem: c_menu_item) -> onSelReturn:
        ports = list_serial_ports()
        options: list[select_item | None] = []
        known = {port.device for port in ports}

        if self.settings.port and self.settings.port not in known:
            options.append(
                select_item(
                    TXT_UART_MENU_CURRENT_PORT.format(port=self.settings.port),
                    "c",
                    self.settings.port,
                )
            )
            options.append(None)

        for idx, port in enumerate(ports, start=1):
            options.append(select_item(port.label, str(idx), port.device))

        if not options:
            return onSelReturn().errRet(TXT_UART_MENU_NO_PORTS_FOUND)

        value = self._select_value(TXT_UART_MENU_SELECT_PORT, options)
        if value is None:
            return onSelReturn().errRet(TXT_UART_MENU_CANCELLED)
        self.settings.port = str(value)
        return self._save_ok(TXT_UART_MENU_SAVED)

    def manual_port(self, selItem: c_menu_item) -> onSelReturn:
        port = get_input(TXT_UART_MENU_ENTER_PORT, minMessageWidth=self.minMenuWidth)
        if not port:
            return onSelReturn().errRet(TXT_UART_MENU_CANCELLED)
        self.settings.port = str(port).strip()
        return self._save_ok(TXT_UART_MENU_SAVED)

    def refresh_ports(self, selItem: c_menu_item) -> onSelReturn:
        self.port_count = len(list_serial_ports())
        self.menuRecycle = True
        return onSelReturn(ok=TXT_UART_MENU_PORTS_REFRESHED.format(count=self.port_count))

    def select_baudrate(self, selItem: c_menu_item) -> onSelReturn:
        options = [select_item(str(baudrate), str(baudrate), baudrate) for baudrate in BAUDRATES]
        value = self._select_value(TXT_UART_MENU_SELECT_BAUDRATE, options)
        if value is None:
            return onSelReturn().errRet(TXT_UART_MENU_CANCELLED)
        self.settings.baudrate = int(value)
        return self._save_ok(TXT_UART_MENU_SAVED)

    def select_parity(self, selItem: c_menu_item) -> onSelReturn:
        options = [
            select_item(parity_label(parity), parity.lower(), parity)
            for parity in PARITIES
        ]
        value = self._select_value(TXT_UART_MENU_SELECT_PARITY, options)
        if value is None:
            return onSelReturn().errRet(TXT_UART_MENU_CANCELLED)
        self.settings.parity = str(value)
        return self._save_ok(TXT_UART_MENU_SAVED)

    def select_bytesize(self, selItem: c_menu_item) -> onSelReturn:
        options = [select_item(str(bits), str(bits), bits) for bits in BYTESIZES]
        value = self._select_value(TXT_UART_MENU_SELECT_BYTESIZE, options)
        if value is None:
            return onSelReturn().errRet(TXT_UART_MENU_CANCELLED)
        self.settings.bytesize = int(value)
        return self._save_ok(TXT_UART_MENU_SAVED)

    def select_stopbits(self, selItem: c_menu_item) -> onSelReturn:
        options = [select_item(str(bits), str(idx), bits) for idx, bits in enumerate(STOPBITS, start=1)]
        value = self._select_value(TXT_UART_MENU_SELECT_STOPBITS, options)
        if value is None:
            return onSelReturn().errRet(TXT_UART_MENU_CANCELLED)
        self.settings.stopbits = float(value)
        return self._save_ok(TXT_UART_MENU_SAVED)

    def select_timeout(self, selItem: c_menu_item) -> onSelReturn:
        options = [
            select_item(TXT_UART_MENU_TIMEOUT_VALUE.format(timeout=timeout), str(idx), timeout)
            for idx, timeout in enumerate(TIMEOUTS, start=1)
        ]
        value = self._select_value(TXT_UART_MENU_SELECT_TIMEOUT, options)
        if value is None:
            return onSelReturn().errRet(TXT_UART_MENU_CANCELLED)
        self.settings.timeout = float(value)
        return self._save_ok(TXT_UART_MENU_SAVED)

    def _run_mode(self, transmitter: bool) -> onSelReturn:
        if not self.settings.port:
            return onSelReturn().errRet(TXT_UART_MENU_NO_PORT_SELECTED)

        mode = TXT_UART_MENU_MODE_TRANSMITTER if transmitter else TXT_UART_MENU_MODE_RECEIVER
        cls()
        print(TXT_UART_MENU_STARTING.format(mode=mode))
        print(TXT_UART_MENU_STARTING_PORT.format(
            port=self.settings.port,
            baudrate=self.settings.baudrate,
            parity=parity_label(self.settings.parity),
            bytesize=self.settings.bytesize,
            stopbits=self.settings.stopbits,
            timeout=self.settings.timeout,
        ))
        print("")

        ret = uart_tester.runAs(
            transmitter=transmitter,
            **self.settings.serial_kwargs(),
        )

        if ret:
            print(ret)
            anyKey()
            if str(ret).startswith("[ERROR]"):
                return onSelReturn().errRet(str(ret))
            return onSelReturn(ok=TXT_UART_MENU_RUN_FINISHED)

        anyKey()
        return onSelReturn(ok=TXT_UART_MENU_RUN_FINISHED)

    def _select_value(self, msg: str, options: list[select_item | None]) -> Any | None:
        result = select(
            msg,
            options,
            self.minMenuWidth,
            title=TXT_UART_MENU_NAME,
        )
        if result is None or result.item is None:
            return None
        return result.item.data

    def _save(self) -> None:
        save_settings(self.settings)
        self.menuRecycle = True

    def _try_save_error(self) -> str | None:
        try:
            self._save()
        except Exception as e:
            log.error(f"Failed to save UART settings: {e}")
            return TXT_UART_MENU_SAVE_FAILED.format(err=e)
        return None

    def _save_ok(self, message: str) -> onSelReturn:
        if err := self._try_save_error():
            return onSelReturn().errRet(err)
        return onSelReturn(ok=message)
