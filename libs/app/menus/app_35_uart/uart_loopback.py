from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Iterable

import serial


BAUDRATES: tuple[int, ...] = (
    9_600,
    19_200,
    38_400,
    57_600,
    115_200,
    230_400,
    460_800,
    500_000,
    576_000,
    921_600,
    1_000_000,
    1_500_000,
    2_000_000,
)

TEST_SECONDS_PER_BAUD = 4.0
READ_TIMEOUT = 0.10
FRAME_TIMEOUT =