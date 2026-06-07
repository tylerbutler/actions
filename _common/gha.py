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
import subprocess
import sys
import tomllib
from pathlib import Path
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


def _toml_key_path_parts(key_path: str) -> list[str]:
    parts = key_path.split(".")
    if not key_path or any(not part for part in parts):
        raise ValueError(f"Invalid TOML key path {key_path!r}")
    return parts


def _toml_value_at_path(data: object, key_path: str) -> object:
    current = data
    for part in _toml_key_path_parts(key_path):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(f"TOML key path {key_path!r} not found")
        current = current[part]
    return current


def validate_toml_string_key_path(content: str, key_path: str) -> None:
    """Validate that `key_path` exists in TOML content and points to a string."""
    data = tomllib.loads(content)
    value = _toml_value_at_path(data, key_path)
    if not isinstance(value, str):
        raise TypeError(f"TOML key path {key_path!r} is not a string value")


def update_toml_file_key(
    path: Path,
    key_path: str,
    new_value: str,
    *,
    toml_bin: str = "toml",
) -> None:
    """Update an existing TOML string key path using toml-cli.

    `toml-cli` creates missing keys by default, so this validates the key path
    first to preserve the actions' existing fail-on-missing-key behavior.
    """
    content = path.read_text(encoding="utf-8")
    validate_toml_string_key_path(content, key_path)

    cmd = [toml_bin, "set", key_path, new_value, "--toml-path", str(path)]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"{toml_bin!r} executable not found; install toml-cli before updating TOML files"
        ) from e
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or str(e)).strip()
        raise RuntimeError(f"toml-cli failed updating {path}: {detail}") from e

    updated = path.read_text(encoding="utf-8")
    data = tomllib.loads(updated)
    if _toml_value_at_path(data, key_path) != new_value:
        raise ValueError(f"TOML key path {key_path!r} was not updated in {path}")


def parse_colon_entries(text: str, fields: int) -> list[tuple[str, ...]]:
    """Parse newline-separated, colon-delimited entries.

    Blank lines and lines starting with `#` are skipped. Whitespace around
    each field is stripped. Each non-empty line must split into exactly
    `fields` parts.
    """
    out: list[tuple[str, ...]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = [p.strip() for p in stripped.split(":")]
        if len(parts) != fields:
            raise ValueError(
                f"line {lineno}: expected {fields} fields, got {len(parts)}: {raw!r}"
            )
        out.append(tuple(parts))
    return out
