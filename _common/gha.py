"""Shared utilities for actions repo Python helpers.

Consumed via sys.path injection from each action's script:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
    from gha import write_output, fail, append_summary  # noqa: E402
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from typing import NoReturn


def write_output(key: str, value: str) -> None:
    """Append `key=value` (or heredoc block for multi-line) to GITHUB_OUTPUT.

    Falls back to stdout when GITHUB_OUTPUT is unset (local runs).
    """
    if "\n" in value:
        sentinel = f"EOF_{re.sub(r'[^A-Z0-9]', '_', key.upper())}"
        block = f"{key}<<{sentinel}\n{value}\n{sentinel}\n"
    else:
        block = f"{key}={value}\n"

    out_file = os.environ.get("GITHUB_OUTPUT")
    if out_file:
        with open(out_file, "a", encoding="utf-8") as fh:
            fh.write(block)
    else:
        sys.stdout.write(block)


def fail(message: str, code: int = 1) -> NoReturn:
    """Emit a GitHub Actions error annotation and exit."""
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(code)


def append_summary(markdown: str) -> None:
    """Append a line of Markdown to GITHUB_STEP_SUMMARY. No-op if unset."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return
    with open(summary_file, "a", encoding="utf-8") as fh:
        fh.write(markdown + "\n")


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
            f"Expected exactly one top-level assignment for {key!r}, found {count}"
        )
    return new_head + tail
