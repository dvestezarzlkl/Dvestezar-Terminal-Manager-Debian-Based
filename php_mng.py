#!/usr/bin/env python3
"""CLI entrypoint for the read-only phase of sys_apps PHP Manager."""

import argparse
from libs.app.php_manager.discovery import as_json, discover_php


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PHP Manager (read-only inventory)")
    parser.add_argument("--json", action="store_true", help="structured inventory")
    options = parser.parse_args(argv)
    inventory = discover_php()
    if options.json:
        print(as_json(inventory))
    else:
        for item in inventory["installations"]:
            print(f'{item["binary"]}: {item.get("version", item.get("error", "unknown"))}')
        if not inventory["installations"]:
            print("No PHP CLI installations discovered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
