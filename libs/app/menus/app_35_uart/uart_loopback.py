from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from typing import Callable, Iterable

import serial

from libs.JBLibs.term import restoreAndClearDown, savePos

BAUDRATES = (9600, 19200, 38400, 57600, 115200, 230400, 460800,
             500000, 576000, 921