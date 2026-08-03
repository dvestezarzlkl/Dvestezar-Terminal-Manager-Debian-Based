#!/usr/bin/env python3
"""Apply exact repository text replacements described by JSON manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path.cwd().resolve()
CHANGE_DIR = ROOT / ".github" / "changes"


def fail(message: str) -> None:
    raise SystemExit(message)


def resolve_repo_file(raw_path: str) -> Path:
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        fail(f"Unsafe repository path: {raw_path}")

    target = (ROOT / relative).resolve()
    if target == ROOT or ROOT not in target.parents:
        fail(f"Path escapes repository: {raw_path}")
    if not target.is_file():
        fail(f"Target file does not exist: {raw_path}")
    return target


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or value == "":
        fail(f"Manifest field '{field}' must be a non-empty string")
    return value


def validate_new_text(value: str, context: str) -> None:
    for line_number, line in enumerate(value.split("\n"), start=1):
        if line.endswith((" ", "\t")):
            fail(f"{context}: trailing space or tab in new text on line {line_number}")


def replacement_bytes(old: str, new: str, source: bytes, expected: int) -> tuple[bytes, bytes, str]:
    old_lf = old.encode("utf-8")
    new_lf = new.encode("utf-8")
    candidates = [(old_lf, new_lf, "LF/exact")]

    if b"\n" in old_lf and b"\r\n" not in old_lf:
        candidates.append(
            (
                old_lf.replace(b"\n", b"\r\n"),
                new_lf.replace(b"\n", b"\r\n"),
                "CRLF",
            )
        )

    matches = [candidate for candidate in candidates if source.count(candidate[0]) == expected]
    if len(matches) != 1:
        counts = ", ".join(f"{label}={source.count(old_bytes)}" for old_bytes, _, label in candidates)
        fail(f"Expected exactly one newline mode with {expected} occurrence(s); found {counts}")

    return matches[0]


def load_manifest(manifest_path: Path) -> tuple[str, list[dict[str, Any]]]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Cannot read {manifest_path}: {exc}")

    if manifest.get("version") != 1:
        fail(f"Unsupported manifest version in {manifest_path}")

    commit_message = require_string(manifest.get("commit_message"), "commit_message")
    replacements = manifest.get("replacements")
    if not isinstance(replacements, list) or not replacements:
        fail(f"Manifest {manifest_path} must contain replacements")
    return commit_message, replacements


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message-file", required=True)
    args = parser.parse_args()

    manifests = sorted(CHANGE_DIR.glob("*.json"))
    if not manifests:
        fail(f"No JSON change manifests found in {CHANGE_DIR.relative_to(ROOT)}")

    buffers: dict[Path, bytes] = {}
    messages: list[str] = []

    for manifest_path in manifests:
        commit_message, replacements = load_manifest(manifest_path)
        messages.append(commit_message)

        for index, replacement in enumerate(replacements, start=1):
            if not isinstance(replacement, dict):
                fail(f"Replacement {index} in {manifest_path} must be an object")

            raw_path = require_string(replacement.get("path"), "path")
            old = require_string(replacement.get("old"), "old")
            new = replacement.get("new")
            if not isinstance(new, str):
                fail(f"Replacement {index} field 'new' must be a string")
            validate_new_text(new, f"Replacement {index} in {raw_path}")

            expected = replacement.get("expected", 1)
            if not isinstance(expected, int) or expected < 1:
                fail(f"Replacement {index} field 'expected' must be a positive integer")

            target = resolve_repo_file(raw_path)
            source = buffers.get(target, target.read_bytes())
            try:
                old_bytes, new_bytes, newline_mode = replacement_bytes(old, new, source, expected)
            except SystemExit as exc:
                fail(f"Replacement {index} in {raw_path}: {exc}")

            buffers[target] = source.replace(old_bytes, new_bytes, expected)
            print(f"Validated replacement {index}: {raw_path} ({newline_mode})")

    for target, content in buffers.items():
        target.write_bytes(content)
        print(f"Updated: {target.relative_to(ROOT)}")

    for manifest_path in manifests:
        manifest_path.unlink()
        print(f"Removed manifest: {manifest_path.relative_to(ROOT)}")

    Path(args.message_file).write_text("; ".join(messages) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
