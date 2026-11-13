"""Read-only PHP runtime inventory for sys_apps.

No package installation, configuration changes or service control is performed.
"""

from .discovery import discover_php

__all__ = ["discover_php"]
