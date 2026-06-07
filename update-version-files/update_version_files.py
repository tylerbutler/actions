#!/usr/bin/env python3
"""Update TOML version key paths from the nearest ancestor package.json.

Uses toml-cli for TOML mutation while validating requested key paths first, so
missing keys fail instead of being created implicitly.

Input is read from the `VERSION_FILES` environment variable: newline-separated
`path:key-path` entries. For each entry, the script walks up from the TOML
file's directory to find the nearest `package.json`, reads its `version` field,
and rewrites the existing string TOML key path.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import append_summary, fail, parse_colon_entries, update_toml_file_key  # noqa: E402


def parse_entries(text: str) -> list[tuple[str, str]]:
    """Parse newline-separated `path:key-path` entries, ignoring blank lines."""
    try:
        raw_entries = parse_colon_entries(text, fields=2)
    except ValueError as e:
        raise ValueError(f"Invalid entry: expected 'path:key-path' ({e})") from e
    entries: list[tuple[str, str]] = []
    for path, key in raw_entries:
        if not path or not key:
            raise ValueError(f"Invalid entry {path!r}:{key!r}: empty path or key")
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


def main() -> None:
    text = os.environ.get("VERSION_FILES", "")
    try:
        entries = parse_entries(text)
    except ValueError as e:
        fail(str(e))
        return

    for path_str, key in entries:
        toml_path = Path(path_str)
        if not toml_path.is_file():
            fail(f"TOML file not found: {path_str}")

        pkg_json = find_ancestor_package_json(toml_path)
        if pkg_json is None:
            fail(f"No package.json found in ancestor directories of {path_str}")
            return  # for type-checkers; _fail exits

        try:
            pkg_data = json.loads(pkg_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            fail(f"Failed to parse {pkg_json}: {e}")
            return

        version = pkg_data.get("version")
        if not version or not isinstance(version, str):
            fail(f"No string `version` field in {pkg_json}")
            return

        try:
            update_toml_file_key(toml_path, key, version)
        except (
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
            tomllib.TOMLDecodeError,
        ) as e:
            fail(f"Failed to update {path_str}: {e}")
            return

        print(f'Updated {path_str}: {key} = "{version}" (from {pkg_json})')

    append_summary("## Update Version Files")
    if entries:
        append_summary(f"Updated {len(entries)} TOML file(s) from package.json.")
    else:
        append_summary("No entries to update; skipped.")


if __name__ == "__main__":
    main()
