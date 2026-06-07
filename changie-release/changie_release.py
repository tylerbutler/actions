#!/usr/bin/env python3
"""changie-release composite action helper.

Implements the bash steps that were too fragile to keep in sed/grep/awk:

    check-config        Read .changie.yaml and detect unreleased fragments.
    bump-files          Rewrite TOML key paths with the released version.
    read-changelog      Build the changelog body (multi-project aggregation).
    resolve-templates   Apply {version}/{changelog} substitutions to PR templates.

Other steps in action.yml (batching, calling `changie latest`, the PR-create
step itself) remain in bash because they are thin wrappers over external CLIs.

Each subcommand reads its inputs from environment variables and writes results
to GITHUB_OUTPUT (or stdout when GITHUB_OUTPUT is unset, for local debugging).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import append_summary, fail, parse_colon_entries, update_toml_file_key, write_output  # noqa: E402


# ---------------------------------------------------------------------------
# Pure helpers (covered by unit tests)
# ---------------------------------------------------------------------------


_CHANGIE_DEFAULTS: dict[str, str] = {
    "changesDir": ".changie.d",
    "unreleasedDir": "unreleased",
    "projectsVersionSeparator": "-",
}


def parse_changie_config(yaml_text: str) -> dict[str, str]:
    """Extract the three top-level scalar fields we need from .changie.yaml.

    A real YAML parser would be more robust, but adding a dependency for three
    scalar reads is overkill — and matches the behavior of the bash grep/awk
    implementation. Only unindented top-level keys are recognized.
    """
    config = dict(_CHANGIE_DEFAULTS)
    pattern = re.compile(
        r'^(?P<key>changesDir|unreleasedDir|projectsVersionSeparator)\s*:\s*'
        r'["\']?(?P<value>[^"\'\n#]*?)["\']?\s*(?:#.*)?$',
        re.MULTILINE,
    )
    for match in pattern.finditer(yaml_text):
        value = match.group("value").strip()
        if value:
            config[match.group("key")] = value
    return config


def strip_version_prefix(version: str, project: str = "", separator: str = "") -> str:
    """Strip the leading 'v' (and project prefix in multi-project mode) from a version."""
    if project:
        prefix = f"{project}{separator}v"
        if version.startswith(prefix):
            return version[len(prefix):]
    return version.removeprefix("v")


def parse_version_files(text: str, multi_project: bool) -> list[dict[str, str | None]]:
    """Parse the `version-files` input.

    Single-project format: `path:key-path` per line.
    Multi-project format:  `project:path:key-path` per line.
    """
    expected = 3 if multi_project else 2
    label = "project:path:key-path" if multi_project else "path:key-path"
    try:
        raw_entries = parse_colon_entries(text, fields=expected)
    except ValueError as e:
        raise ValueError(f"Invalid entry: expected {label!r} ({e})") from e

    entries: list[dict[str, str | None]] = []
    for parts in raw_entries:
        if not all(parts):
            raise ValueError(f"Invalid entry {':'.join(parts)!r}: empty field, expected {label!r}")
        if multi_project:
            entries.append({"project": parts[0], "path": parts[1], "key": parts[2]})
        else:
            entries.append({"project": None, "path": parts[0], "key": parts[1]})
    return entries


def resolve_template(template: str, **substitutions: str) -> str:
    """Replace `{var}` placeholders in `template` with substitution values."""
    result = template
    for var, value in substitutions.items():
        result = result.replace(f"{{{var}}}", value)
    return result


def aggregate_changelog(
    versions_by_project: dict[str, str],
    project_order: list[str],
    changes_dir: str,
    separator: str,
) -> str:
    """Build a combined markdown changelog from per-project version files."""
    sections: list[str] = []
    for project in project_order:
        full_version = versions_by_project.get(project)
        if not full_version:
            continue
        ver_suffix = full_version.removeprefix(f"{project}{separator}")
        ver_file = Path(changes_dir) / project / f"{ver_suffix}.md"
        if ver_file.is_file():
            sections.append(
                f"### {project} {ver_suffix}\n\n"
                f"{ver_file.read_text(encoding='utf-8').rstrip()}\n"
            )
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# IO glue
# ---------------------------------------------------------------------------


def _load_changie_config(working_dir: Path) -> dict[str, str]:
    path = working_dir / ".changie.yaml"
    if path.is_file():
        return parse_changie_config(path.read_text(encoding="utf-8"))
    return dict(_CHANGIE_DEFAULTS)


def _split_csv(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_check_config() -> None:
    """Detect unreleased fragments and emit the resolved changie config."""
    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    projects = os.environ.get("PROJECTS", "").strip()
    config = _load_changie_config(cwd)

    write_output("changes-dir", config["changesDir"])
    write_output("separator", config["projectsVersionSeparator"] if projects else "")
    write_output("has-projects", "true" if projects else "false")

    unreleased_path = cwd / config["changesDir"] / config["unreleasedDir"]
    fragments = (
        list(unreleased_path.glob("*.yaml")) if unreleased_path.is_dir() else []
    )
    if fragments:
        print(f"Found {len(fragments)} unreleased change fragment(s)")
        write_output("skipped", "false")
    else:
        print(f"No unreleased change fragments found in {unreleased_path}")
        write_output("skipped", "true")


def _changie_latest(project: str | None, cwd: Path) -> str:
    """Run `changie latest [--project X]`; return the trimmed stdout or '' on failure."""
    cmd = ["changie", "latest"]
    if project:
        cmd += ["--project", project]
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return result.stdout.strip()


def cmd_resolve_versions() -> None:
    """Resolve the released version per batched project and emit version + JSON map."""
    projects = os.environ.get("PROJECTS", "").strip()
    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))

    if projects:
        batched = _split_csv(os.environ.get("BATCHED", ""))
        if not batched:
            write_output("version", "")
            write_output("versions-json", "{}")
            return
        versions: dict[str, str] = {}
        for project in batched:
            ver = _changie_latest(project, cwd)
            if ver:
                versions[project] = ver
        ordered = [versions[p] for p in batched if p in versions]
        write_output("version", ", ".join(ordered))
        write_output("versions-json", json.dumps(versions))
    else:
        write_output("version", _changie_latest(None, cwd))
        write_output("versions-json", "{}")


def cmd_bump_files() -> None:
    """Rewrite TOML version key paths for each batched project (or single-project mode)."""
    projects = os.environ.get("PROJECTS", "").strip()
    version_files_text = os.environ.get("VERSION_FILES", "")
    if not version_files_text.strip():
        return

    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    multi = bool(projects)

    try:
        entries = parse_version_files(version_files_text, multi_project=multi)
    except ValueError as e:
        fail(str(e))

    if multi:
        batched = set(_split_csv(os.environ.get("BATCHED", "")))
        try:
            versions = json.loads(os.environ.get("VERSIONS_JSON") or "{}")
        except json.JSONDecodeError as e:
            fail(f"Invalid VERSIONS_JSON: {e}")
        separator = os.environ.get("SEPARATOR", "-")

        for entry in entries:
            project = entry["project"] or ""
            if project not in batched:
                print(f"Skipping {project} (not batched)")
                continue
            full_version = versions.get(project)
            if not full_version:
                print(f"No version resolved for {project}, skipping")
                continue
            semver = strip_version_prefix(full_version, project, separator)
            _apply_bump(cwd / (entry["path"] or ""), entry["key"] or "", semver)
    else:
        semver = strip_version_prefix(os.environ.get("VERSION", ""))
        for entry in entries:
            _apply_bump(cwd / (entry["path"] or ""), entry["key"] or "", semver)


def _apply_bump(path: Path, key: str, value: str) -> None:
    if not path.is_file():
        fail(f"Version file not found: {path}")
    try:
        update_toml_file_key(path, key, value)
    except (KeyError, TypeError, ValueError, RuntimeError, tomllib.TOMLDecodeError) as e:
        fail(f"Failed to update {path}: {e}")
    print(f'Updated {path}: {key} = "{value}"')


def cmd_read_changelog() -> None:
    """Build the changelog content (multi-project: aggregate per-project files)."""
    projects = os.environ.get("PROJECTS", "").strip()
    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    changes_dir = os.environ.get("CHANGES_DIR", ".changes")
    changes_path = cwd / changes_dir

    if projects:
        batched = _split_csv(os.environ.get("BATCHED", ""))
        try:
            versions = json.loads(os.environ.get("VERSIONS_JSON") or "{}")
        except json.JSONDecodeError:
            versions = {}
        separator = os.environ.get("SEPARATOR", "-")
        content = aggregate_changelog(versions, batched, str(changes_path), separator)
    else:
        version = os.environ.get("VERSION", "")
        ver_file = changes_path / f"{version}.md"
        content = ver_file.read_text(encoding="utf-8") if ver_file.is_file() else ""

    write_output("content", content)


def cmd_resolve_templates() -> None:
    """Apply {version}/{changelog} substitutions to the PR templates."""
    version = os.environ.get("VERSION", "")
    has_projects = os.environ.get("HAS_PROJECTS", "false") == "true"
    branch_version = "next" if has_projects else version
    changelog = os.environ.get("CHANGELOG", "")

    write_output(
        "pr-title",
        resolve_template(os.environ.get("TITLE_TPL", ""), version=version),
    )
    write_output(
        "commit-message",
        resolve_template(os.environ.get("COMMIT_TPL", ""), version=version),
    )
    write_output(
        "branch",
        resolve_template(os.environ.get("BRANCH_TPL", ""), version=branch_version),
    )
    write_output(
        "pr-body",
        resolve_template(
            os.environ.get("BODY_TPL", ""), version=version, changelog=changelog
        ),
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


_HANDLERS = {
    "check-config": cmd_check_config,
    "resolve-versions": cmd_resolve_versions,
    "bump-files": cmd_bump_files,
    "read-changelog": cmd_read_changelog,
    "resolve-templates": cmd_resolve_templates,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(_HANDLERS))
    args = parser.parse_args()
    _HANDLERS[args.command]()


if __name__ == "__main__":
    main()
