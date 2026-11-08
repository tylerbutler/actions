"""Process and output helpers for thin trellis actions."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import re
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

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


def authenticated_env(token: str) -> dict[str, str]:
    if not token or any(char.isspace() for char in token):
        raise ValueError("a nonempty token without whitespace is required")
    print(f"::add-mask::{token}")
    env = os.environ.copy()
    env["GITHUB_TOKEN"] = token
    env["GH_TOKEN"] = token
    origin = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=env.get("WORKING_DIRECTORY", "."), check=True, text=True, capture_output=True,
    ).stdout.strip()
    server = urlparse(env.get("GITHUB_SERVER_URL", "https://github.com"))
    if server.scheme != "https" or not server.hostname or server.username or server.password:
        raise ValueError("GITHUB_SERVER_URL must be an HTTPS GitHub server")
    if origin.startswith(f"git@{server.hostname}:"):
        repo = origin.split(":", 1)[1]
    else:
        parsed = urlparse(origin)
        if parsed.hostname != server.hostname or parsed.scheme not in ("https", "ssh") \
                or parsed.password or (parsed.scheme == "https" and parsed.username):
            raise ValueError("origin must use the configured GitHub server without credentials")
        repo = parsed.path.lstrip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid GitHub origin repository")
    url = f"{server.scheme}://{server.netloc}/{repo}"
    header = "AUTHORIZATION: basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode()
    print(f"::add-mask::{header}")
    count = int(env.get("GIT_CONFIG_COUNT", "0"))
    # Reset checkout's persisted header before adding this action's scoped token.
    settings = [(f"url.{url}.insteadOf", origin),
                (f"http.{url}.extraheader", ""), (f"http.{url}.extraheader", header)]
    for key, value in settings:
        env[f"GIT_CONFIG_KEY_{count}"] = key
        env[f"GIT_CONFIG_VALUE_{count}"] = value
        count += 1
    env["GIT_CONFIG_COUNT"] = str(count)
    return env


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
