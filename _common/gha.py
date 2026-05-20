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
