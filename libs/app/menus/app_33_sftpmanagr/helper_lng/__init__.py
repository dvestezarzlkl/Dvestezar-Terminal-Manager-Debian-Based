from .lng.default import *
from libs.JBLibs.helper import loadLng

loadLng()

__all__ = [name for name in globals() if name.startswith(("TXT_", "TX_"))]
