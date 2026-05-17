#!/usr/bin/env python3
"""gleam-publish composite action helper.

Subcommands:
    rewrite-path-deps   Rewrite intra-workspace path deps to Hex version ranges.
    publish             Run `gleam publish --yes` for each package; classify.

The bash version used grep+sed for both TOML reads and dep rewrites, which
broke on minor formatting variations. This version parses with tomllib and
restricts rewrites to a regex anchored at line-start in a verified region.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import NoReturn


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def hex_range(version: str) -> str:
    """Compute Hex version range matching semver compatibility.

    Pre-1.0 (0.x.y): minor bump is breaking -> `>= 0.x.y and < 0.(x+1).0`
    Post-1.0 (x.y.z): major bump is breaking -> `>= x.y.z and < (x+1).0.0`
    """
    match = _SEMVER_RE.fullmatch(version)
    if not match:
        raise ValueError(f"Not a semver string: {version!r}")
    major, minor, patch = (int(g) for g in match.groups())
    if major == 0:
        return f">= {version} and < 0.{minor + 1}.0"
    return f">= {version} and < {major + 1}.0.0"


def parse_replace_path_deps(text: str) -> list[tuple[str, str]]:
    """Parse `dep-name:version-toml-path` entries, ignoring blank lines."""
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Invalid entry {raw!r}: expected 'dep-name:version-toml-path'")
        dep, path = line.split(":", 1)
        dep, path = dep.strip(), path.strip()
        if not dep or not path:
            raise ValueError(f"Invalid entry {raw!r}: empty field")
        out.append((dep, path))
    return out


def read_gleam_meta(content: str) -> tuple[str, str]:
    """Return (name, version) from a gleam.toml's top-level fields."""
    data = tomllib.loads(content)
    if "name" not in data:
        raise KeyError("No top-level 'name' in gleam.toml")
    if "version" not in data:
        raise KeyError("No top-level 'version' in gleam.toml")
    return str(data["name"]), str(data["version"])


def rewrite_path_dep(content: str, dep_name: str, hex_version: str) -> str:
    """Rewrite `dep_name = { path = "..." }` to `dep_name = "<hex_version>"`.

    Leaves non-path deps and unrelated lines alone.
    """
    pattern = re.compile(
        rf'^([ \t]*){re.escape(dep_name)}([ \t]*)=([ \t]*)\{{[ \t]*path[ \t]*=[ \t]*"[^"]*"[ \t]*\}}',
        re.MULTILINE,
    )
    return pattern.sub(
        lambda m: f'{m.group(1)}{dep_name}{m.group(2)}={m.group(3)}"{hex_version}"',
        content,
    )


def is_already_published(output: str) -> bool:
    """Heuristic match for 'already published on Hex' across `gleam publish` variants."""
    lower = output.lower()
    return any(n in lower for n in ("already published", "already exists", "version already"))


def _is_safe_pkg_path(p: str) -> bool:
    if p == ".":
        return True
    if p.startswith("/"):
        return False
    parts = p.split("/")
    return ".." not in parts


# ---------------------------------------------------------------------------
# IO glue
# ---------------------------------------------------------------------------


def _write_output(key: str, value: str) -> None:
    out_file = os.environ.get("GITHUB_OUTPUT")
    block = f"{key}={value}\n"
    if out_file:
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(block)
    else:
        sys.stdout.write(block)


def _append_summary(line: str) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _fail(message: str) -> NoReturn:
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_rewrite_path_deps() -> None:
    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    replace_text = os.environ.get("REPLACE_PATH_DEPS", "")
    packages_text = os.environ.get("PACKAGES", "")
    if not replace_text.strip():
        return

    try:
        entries = parse_replace_path_deps(replace_text)
    except ValueError as e:
        _fail(str(e))

    pkg_dirs = [p for p in packages_text.split() if p]

    # Validate package paths up-front
    for p in pkg_dirs:
        if not _is_safe_pkg_path(p):
            _fail(f"Invalid package path: {p}")

    for dep_name, version_toml_rel in entries:
        version_toml = cwd / version_toml_rel
        if not version_toml.is_file():
            _fail(f"Version source file not found: {version_toml}")
        try:
            _, dep_version = read_gleam_meta(version_toml.read_text(encoding="utf-8"))
        except (KeyError, tomllib.TOMLDecodeError) as e:
            _fail(f"Failed to read {version_toml}: {e}")

        try:
            rng = hex_range(dep_version)
        except ValueError as e:
            _fail(f"Cannot compute Hex range for {dep_name}@{dep_version}: {e}")

        print(f'Dependency {dep_name}: version {dep_version} → "{rng}"')

        for pkg_dir in pkg_dirs:
            pkg_path = cwd / pkg_dir
            toml = pkg_path / "gleam.toml"
            manifest = pkg_path / "manifest.toml"
            build_dir = pkg_path / "build"
            if not toml.is_file():
                continue
            if manifest.is_file():
                manifest.unlink()
                print(f"  Removed stale {manifest}")
            if build_dir.is_dir():
                shutil.rmtree(build_dir)
                print(f"  Removed stale {build_dir}")

            content = toml.read_text(encoding="utf-8")
            new_content = rewrite_path_dep(content, dep_name, rng)
            if new_content != content:
                toml.write_text(new_content, encoding="utf-8")
                print(f"  Rewrote {toml}")


def _run_gleam_publish(pkg_dir: Path) -> tuple[int, str]:
    """Run `gleam publish --yes` in pkg_dir; return (returncode, combined output)."""
    result = subprocess.run(
        ["gleam", "publish", "--yes"],
        cwd=pkg_dir,
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def cmd_publish() -> None:
    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    packages_text = os.environ.get("PACKAGES", "")
    skip_published = os.environ.get("SKIP_PUBLISHED", "true").lower() == "true"

    pkg_dirs = [p for p in packages_text.split() if p]
    published: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for pkg_dir_str in pkg_dirs:
        pkg_dir = cwd / pkg_dir_str
        if not pkg_dir.is_dir():
            print(f"::error::Package directory not found: {pkg_dir}", file=sys.stderr)
            failed.append(pkg_dir_str)
            continue

        toml = pkg_dir / "gleam.toml"
        try:
            name, version = read_gleam_meta(toml.read_text(encoding="utf-8"))
        except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError) as e:
            print(f"::error::Failed to read {toml}: {e}", file=sys.stderr)
            failed.append(pkg_dir_str)
            continue

        print(f"::group::{name}@{version} ({pkg_dir_str})")
        code, output = _run_gleam_publish(pkg_dir)
        sys.stdout.write(output)
        if code == 0:
            print(f"✓ Published {name}@{version}")
            published.append(pkg_dir_str)
        elif is_already_published(output):
            if skip_published:
                print(f"· Skipped {name}@{version} (already published)")
                skipped.append(pkg_dir_str)
            else:
                print(f"::error::{name}@{version} is already published", file=sys.stderr)
                failed.append(pkg_dir_str)
        else:
            print(f"::error::Failed to publish {name}@{version}", file=sys.stderr)
            failed.append(pkg_dir_str)
        print("::endgroup::")

    _write_output("published", " ".join(published))
    _write_output("skipped", " ".join(skipped))

    _append_summary("### Publish Results")
    if published:
        _append_summary(f"- **Published:** {' '.join(published)}")
    if skipped:
        _append_summary(f"- **Skipped:** {' '.join(skipped)}")
    if failed:
        _append_summary(f"- **Failed:** {' '.join(failed)}")

    if failed:
        _fail(f"Some packages failed to publish: {' '.join(failed)}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


_HANDLERS = {
    "rewrite-path-deps": cmd_rewrite_path_deps,
    "publish": cmd_publish,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(_HANDLERS))
    args = parser.parse_args()
    _HANDLERS[args.command]()


if __name__ == "__main__":
    main()
