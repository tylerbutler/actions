#!/usr/bin/env python3
"""changie-check composite action helper.

Subcommands:
    detect-fragments  Find changie YAML fragments added in this PR.
    render-preview    Strip non-PR fragments + render `changie batch --dry-run`.
    check-required    Decide whether a PR needs a changelog entry from its commits.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import fail, write_output  # noqa: E402


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


_CHANGIE_DEFAULTS = {
    "changesDir": ".changie.d",
    "unreleasedDir": "unreleased",
}


def parse_changie_config(yaml_text: str) -> dict[str, str]:
    config = dict(_CHANGIE_DEFAULTS)
    pattern = re.compile(
        r'^(?P<key>changesDir|unreleasedDir)\s*:\s*'
        r'["\']?(?P<value>[^"\'\n#]*?)["\']?\s*(?:#.*)?$',
        re.MULTILINE,
    )
    for m in pattern.finditer(yaml_text):
        value = m.group("value").strip()
        if value:
            config[m.group("key")] = value
    return config


_SUBJECT_RE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?!?:")
_BREAKING_RE = re.compile(r"^[a-z]+(?:\([^)]*\))?!:")


def parse_conventional_types(log_text: str) -> set[str]:
    """Return the set of conventional-commit types found in log subjects."""
    out: set[str] = set()
    for line in log_text.splitlines():
        m = _SUBJECT_RE.match(line)
        if m:
            out.add(m.group("type"))
    return out


def has_breaking_marker(log_text: str) -> bool:
    return any(_BREAKING_RE.match(line) for line in log_text.splitlines())


def needs_changelog_entry(types: set[str], required: list[str]) -> bool:
    return bool(types & set(required))


# ---------------------------------------------------------------------------
# Subprocess wrappers (mockable)
# ---------------------------------------------------------------------------


def _git_diff_added(base: str, head: str, path_glob: str, cwd: Path) -> list[str]:
    r = subprocess.run(
        [
            "git", "diff", "--name-only", "--diff-filter=A",
            f"{base}...{head}", "--", path_glob,
        ],
        cwd=cwd, capture_output=True, text=True,
    )
    if r.returncode != 0:
        return []
    return [line for line in r.stdout.splitlines() if line.strip()]


def _git_log_subjects(base: str, head: str, cwd: Path) -> str:
    r = subprocess.run(
        ["git", "log", "--format=%s", f"{base}..{head}"],
        cwd=cwd, capture_output=True, text=True,
    )
    if r.returncode != 0:
        return ""
    return r.stdout


def _changie_batch_dry_run(project: str | None, cwd: Path) -> str:
    cmd = ["changie", "batch", "auto", "--dry-run"]
    if project:
        cmd += ["--project", project]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    # Mirror bash: dry-run failures are non-fatal here
    return (r.stdout or "") + (r.stderr or "")


# ---------------------------------------------------------------------------
# IO glue
# ---------------------------------------------------------------------------


def _split_csv(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


def _load_changie_config(working_dir: Path) -> dict[str, str]:
    path = working_dir / ".changie.yaml"
    if path.is_file():
        return parse_changie_config(path.read_text(encoding="utf-8"))
    return dict(_CHANGIE_DEFAULTS)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_detect_fragments() -> None:
    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    base = os.environ.get("BASE_SHA", "")
    head = os.environ.get("HEAD_SHA", "")
    config = _load_changie_config(cwd)
    unreleased_path = f"{config['changesDir']}/{config['unreleasedDir']}"
    write_output("unreleased-path", unreleased_path)

    # Match any added file in the unreleased dir regardless of extension —
    # changie writes fragments using the configured versionExt (e.g. .yaml,
    # .md), so a hardcoded extension misses repos that don't use .yaml.
    # Dotfiles like .gitkeep are ignored.
    added = _git_diff_added(base, head, unreleased_path, cwd)
    fragments = [f for f in added if not Path(f).name.startswith(".")]
    if fragments:
        print(f"Found {len(fragments)} changie fragment(s) added in this PR")
        write_output("has-entries", "true")
        write_output("fragments", "\n".join(fragments))
    else:
        print("No changie fragments added in this PR")
        write_output("has-entries", "false")
        write_output("fragments", "")


def cmd_render_preview() -> None:
    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    fragments_text = os.environ.get("FRAGMENTS", "")
    unreleased_path = os.environ.get("UNRELEASED_PATH", "")
    projects = os.environ.get("PROJECTS", "").strip()

    pr_fragments = {line.strip() for line in fragments_text.splitlines() if line.strip()}
    unreleased_dir = cwd / unreleased_path

    # Strip non-PR fragments so changie's dry-run renders only PR additions.
    # The checkout is disposable. We only touch regular, non-dotfile files so
    # any fragment extension is handled while .gitkeep is preserved.
    if unreleased_dir.is_dir():
        for path in unreleased_dir.glob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            rel = str(path.relative_to(cwd))
            if rel not in pr_fragments:
                path.unlink()

    if projects:
        sections: list[str] = []
        for project in _split_csv(projects):
            out = _changie_batch_dry_run(project, cwd).strip()
            if out:
                sections.append(f"#### {project}\n\n{out}\n")
        preview = "\n".join(sections)
    else:
        preview = _changie_batch_dry_run(None, cwd)

    write_output("preview", preview)


def cmd_check_required() -> None:
    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    base = os.environ.get("BASE_SHA", "")
    head = os.environ.get("HEAD_SHA", "")
    required = _split_csv(os.environ.get("REQUIRE_FOR_TYPES", ""))

    log = _git_log_subjects(base, head, cwd)
    types = parse_conventional_types(log)
    if not types:
        print("No conventional commit types found")
        write_output("needs-entry", "false")
        write_output("commit-types-found", "")
        return

    types_csv = ",".join(sorted(types))
    write_output("commit-types-found", types_csv)
    print(f"Conventional commit types found: {types_csv}")

    if has_breaking_marker(log):
        print("Breaking change detected — changelog entry required")
        write_output("needs-entry", "true")
        return

    if needs_changelog_entry(types, required):
        match = next(t for t in types if t in set(required))
        print(f"Commit type {match!r} requires a changelog entry")
        write_output("needs-entry", "true")
    else:
        write_output("needs-entry", "false")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


_HANDLERS = {
    "detect-fragments": cmd_detect_fragments,
    "render-preview": cmd_render_preview,
    "check-required": cmd_check_required,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(_HANDLERS))
    args = parser.parse_args()
    _HANDLERS[args.command]()


if __name__ == "__main__":
    main()
