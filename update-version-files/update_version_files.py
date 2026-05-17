#!/usr/bin/env python3
"""Update top-level TOML version keys from the nearest ancestor package.json.

Replaces the bash/sed implementation: more robust (won't blindly rewrite
same-named keys inside `[tables]`) and unit-testable.

Input is read from the `VERSION_FILES` environment variable: newline-separated
`path:key` entries. For each entry, the script walks up from the TOML file's
directory to find the nearest `package.json`, reads its `version` field, and
rewrites the top-level `key = "..."` assignment in the TOML file.

Only top-level string keys are updated. If the requested key only appears
inside a `[table]`, the action errors out rather than rewriting the wrong line.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path


def parse_entries(text: str) -> list[tuple[str, str]]:
    """Parse newline-separated `path:key` entries, ignoring blank lines."""
    entries: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Invalid entry {raw_line!r}: expected 'path:key'")
        path, key = line.split(":", 1)
        path = path.strip()
        key = key.strip()
        if not path or not key:
            raise ValueError(f"Invalid entry {raw_line!r}: empty path or key")
        entries.append((path, key))
    return entries


def find_ancestor_package_json(toml_path: Path) -> Path | None:
    """Walk up from `toml_path`'s directory and return the nearest package.json."""
    start = toml_path.parent if toml_path.parent != Path("") else Path(".")
    for directory in (start, *start.parents):
        candidate = directory / "package.json"
        if candidate.is_file():
            return candidate
    return None


def _top_level_region_end(content: str) -> int:
    """Return the offset of the first `[table]` header, or len(content) if none."""
    match = re.search(r"^[ \t]*\[", content, re.MULTILINE)
    return match.start() if match else len(content)


def update_toml_top_level_key(content: str, key: str, new_value: str) -> str:
    """Replace the top-level `key = "..."` string assignment in `content`.

    Raises:
        tomllib.TOMLDecodeError: if `content` is not valid TOML.
        KeyError: if `key` is not a top-level key.
        TypeError: if the top-level `key` is not a string value.
        ValueError: if exactly one matching assignment line cannot be located.
    """
    data = tomllib.loads(content)
    if key not in data:
        raise KeyError(f"Top-level key {key!r} not found")
    if not isinstance(data[key], str):
        raise TypeError(f"Top-level key {key!r} is not a string value")

    end = _top_level_region_end(content)
    head, tail = content[:end], content[end:]

    pattern = re.compile(
        rf'^({re.escape(key)}[ \t]*=[ \t]*)"[^"\n]*"',
        re.MULTILINE,
    )
    new_head, count = pattern.subn(
        lambda m: f'{m.group(1)}"{new_value}"', head
    )
    if count != 1:
        raise ValueError(
            f"Expected exactly one top-level {key!r} assignment, found {count}"
        )
    return new_head + tail


def _fail(message: str) -> "None":
    """Emit a GitHub Actions error annotation and exit non-zero."""
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    text = os.environ.get("VERSION_FILES", "")
    try:
        entries = parse_entries(text)
    except ValueError as e:
        _fail(str(e))
        return

    for path_str, key in entries:
        toml_path = Path(path_str)
        if not toml_path.is_file():
            _fail(f"TOML file not found: {path_str}")

        pkg_json = find_ancestor_package_json(toml_path)
        if pkg_json is None:
            _fail(f"No package.json found in ancestor directories of {path_str}")
            return  # for type-checkers; _fail exits

        try:
            pkg_data = json.loads(pkg_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            _fail(f"Failed to parse {pkg_json}: {e}")
            return

        version = pkg_data.get("version")
        if not version or not isinstance(version, str):
            _fail(f"No string `version` field in {pkg_json}")
            return

        try:
            content = toml_path.read_text(encoding="utf-8")
            new_content = update_toml_top_level_key(content, key, version)
        except (
            KeyError,
            TypeError,
            ValueError,
            tomllib.TOMLDecodeError,
        ) as e:
            _fail(f"Failed to update {path_str}: {e}")
            return

        if new_content != content:
            toml_path.write_text(new_content, encoding="utf-8")
        print(f'Updated {path_str}: {key} = "{version}" (from {pkg_json})')


if __name__ == "__main__":
    main()
