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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import fail, update_toml_top_level_key  # noqa: E402


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
            content = toml_path.read_text(encoding="utf-8")
            new_content = update_toml_top_level_key(content, key, version)
        except (
            KeyError,
            TypeError,
            ValueError,
            tomllib.TOMLDecodeError,
        ) as e:
            fail(f"Failed to update {path_str}: {e}")
            return

        if new_content != content:
            toml_path.write_text(new_content, encoding="utf-8")
        print(f'Updated {path_str}: {key} = "{version}" (from {pkg_json})')


if __name__ == "__main__":
    main()
