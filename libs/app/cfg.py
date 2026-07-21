import sys

# from .c_service_node import c_service_node

from libs.JBLibs.machine_info import c_machine_info
from ..app import g_def as defs

# cspell:ignore fullchain
VERSION = "1.9.7"
MAIN_TITLE: str = f"Dvestezar Terminal Manager (Debian Based) - version: {VERSION}"

# **** následují proměnné které budou přepsány z config.ini který je v root-u hlavního skriptu, tzn jak je app.py ****

MIN_WIDTH: int            = 0
LANGUAGE: str             = "en-US"                         # jazyk aplikace
SERVER_URL:str            = "moje.domena.fake