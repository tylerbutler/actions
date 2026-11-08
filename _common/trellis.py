"""Process and output helpers for thin trellis actions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from gha import append_summary, fail


def boolean(name: str, default: str = "false") -> bool:
    value = os.environ.get(name, default)
    if value not in ("true", "false"):
        raise ValueError(f"{name.lower()} must be true or false")
    return value == "true"


def invoke(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["trellis", *args], cwd=os.environ.get("WORKING_DIRECTORY", "."),
        env=env, text=True, capture_output=True,
    )
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result


def require_success(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode:
        if result.stdout:
            sys.stdout.write(result.stdout)
        raise subprocess.CalledProcessError(result.returncode, "trellis")


def records(text: str) -> dict[str, str]:
    """Read CLI GitHub-format records, including its collision-safe heredocs."""
    result: dict[str, str] = {}
    lines = iter(text.splitlines())
    for line in lines:
        if "<<" in line and ("=" not in line or line.index("<<") < line.index("=")):
            key, delimiter = line.split("<<", 1)
            if not delimiter:
                raise ValueError("empty output delimiter")
            value: list[str] = []
            for entry in lines:
                if entry == delimiter:
                    break
                value.append(entry)
            else:
                raise ValueError("unterminated output block")
            parsed = "\n".join(value)
        elif "=" in line:
            key, parsed = line.split("=", 1)
        else:
            raise ValueError("malformed trellis output record")
        if not key or key in result:
            raise ValueError("missing or duplicate trellis output key")
        result[key] = parsed
    return result


def json_array(value: str) -> list[str]:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise ValueError("workspace output must be a JSON array of strings")
    return parsed


def main(name: str, action: Callable[[], None]) -> None:
    append_summary(f"## {name}\n")
    try:
        action()
    except subprocess.CalledProcessError as error:
        append_summary(f"Failed (trellis exit {error.returncode}).")
        fail(f"{name} failed (trellis exit {error.returncode})", error.returncode)
    except (OSError, ValueError, KeyError) as error:
        append_summary(f"Failed: {error}")
        fail(str(error))
