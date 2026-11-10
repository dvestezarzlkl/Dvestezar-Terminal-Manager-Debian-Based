"""Headless Firewall Manager acknowledgement command."""
from __future__ import annotations

import sys

from .ack import FirewallAckError, acknowledge_pending
from .lng.default import *
from libs.JBLibs.helper import loadLng

loadLng()


def main(args: list[str]) -> int:
    if len(args) != 1:
        print(TXT_FW_ACK_CLI_USAGE, file=sys.stderr)
        return 2

    try:
        result = acknowledge_pending(args[0])
    except FirewallAckError as exc:
        print(TXT_FW_ACK_CLI_FAIL.format(reason=str(exc)), file=sys.stderr)
        return 1

    print(TXT_FW_ACK_CLI_OK.format(seconds=result.remaining_seconds))
    return 0
