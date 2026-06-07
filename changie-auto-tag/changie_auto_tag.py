#!/usr/bin/env python3
"""changie-auto-tag composite action helper.

Subcommands:
    read-config   Parse .changie.yaml for multi-project mode.
    tag           Resolve versions, create + push new tags, optionally wait.
    release       Create GitHub Releases for newly-created tags.

The wait_for_publish helper is a pure state machine with injected callbacks
so the polling logic is unit-testable without subprocess or real time.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import fail, write_output  # noqa: E402


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


_CHANGIE_DEFAULTS: dict[str, str] = {
    "changesDir": ".changie.d",
    "projectsVersionSeparator": "-",
}


def parse_changie_config(yaml_text: str) -> dict[str, str]:
    config = dict(_CHANGIE_DEFAULTS)
    pattern = re.compile(
        r'^(?P<key>changesDir|projectsVersionSeparator)\s*:\s*'
        r'["\']?(?P<value>[^"\'\n#]*?)["\']?\s*(?:#.*)?$',
        re.MULTILINE,
    )
    for m in pattern.finditer(yaml_text):
        value = m.group("value").strip()
        if value:
            config[m.group("key")] = value
    return config


def resolve_notes_file(
    project: str | None,
    version: str,
    changes_dir: Path,
    separator: str,
) -> Path:
    """Path to the changie-generated release notes for `version`."""
    if project:
        suffix = version.removeprefix(f"{project}{separator}")
        return changes_dir / project / f"{suffix}.md"
    return changes_dir / f"{version}.md"


def wait_for_publish(
    *,
    tag: str,
    enabled: bool,
    workflow_name: str,
    timeout: float,
    poll: float,
    list_runs: Callable[[str], list[dict]],
    get_run: Callable[[int], dict],
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bool, str]:
    """Wait for the publish workflow for `tag` to complete successfully.

    `list_runs(tag) -> [{"databaseId": int, ...}, ...]` (most-recent first)
    `get_run(run_id) -> {"status": str, "conclusion": str | None}`

    Returns (success, message). Success is True when disabled, when the
    matching run completes with conclusion=success, or when polling never
    needs to occur. False on timeout, completion with non-success conclusion,
    or unrecoverable errors raised from the callbacks.
    """
    if not enabled:
        return True, "wait disabled"

    print(f"Waiting for publish workflow '{workflow_name}' for tag {tag}")
    start = now()
    run_id: int | None = None

    while run_id is None:
        try:
            runs = list_runs(tag)
        except Exception as e:
            print(f"Failed to list runs for {tag}; retrying: {e}", file=sys.stderr)
            runs = []
        if runs:
            run_id = int(runs[0]["databaseId"])
            print(f"Found publish workflow run {run_id} for tag {tag}")
            break
        if now() - start >= timeout:
            return False, f"Timed out waiting for workflow run for {tag}"
        sleep(poll)

    while True:
        try:
            run = get_run(run_id)
        except Exception as e:
            return False, f"Failed to read publish workflow run {run_id} for tag {tag}: {e}"
        status = run.get("status") or ""
        conclusion = run.get("conclusion") or ""
        if status == "completed":
            if conclusion == "success":
                msg = f"Publish workflow run {run_id} for tag {tag} completed successfully"
                print(msg)
                return True, msg
            return False, f"Publish workflow run {run_id} for tag {tag} completed with conclusion {conclusion}"
        if now() - start >= timeout:
            return False, f"Timed out waiting for run {run_id} for tag {tag}"
        sleep(poll)


# ---------------------------------------------------------------------------
# Subprocess wrappers (mockable in tests)
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _changie_latest(project: str | None, cwd: Path) -> str:
    cmd = ["changie", "latest"]
    if project:
        cmd += ["--project", project]
    r = _run(cmd, cwd)
    if r.returncode != 0:
        return ""
    return r.stdout.strip()


def _git_tag_exists_local(tag: str, cwd: Path) -> bool:
    r = _run(["git", "tag", "-l", tag], cwd)
    return r.returncode == 0 and r.stdout.strip() != ""


def _git_tag_exists_remote(tag: str, cwd: Path) -> bool:
    r = _run(
        ["git", "ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{tag}"],
        cwd,
    )
    if r.returncode == 0:
        return True
    if r.returncode == 2:
        return False
    raise RuntimeError(f"git ls-remote failed for {tag}: {r.stderr.strip()}")


def _git_create_tag(tag: str, cwd: Path) -> None:
    r = _run(["git", "tag", tag], cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git tag {tag} failed: {r.stderr.strip()}")


def _git_head_sha(cwd: Path) -> str:
    r = _run(["git", "rev-parse", "HEAD"], cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git rev-parse HEAD failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _git_push_tag(tag: str, cwd: Path) -> None:
    r = _run(["git", "push", "origin", tag], cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git push origin {tag} failed: {r.stderr.strip()}")


def _gh_list_runs(workflow_name: str, branch: str) -> list[dict]:
    r = subprocess.run(
        [
            "gh", "run", "list",
            "--workflow", workflow_name,
            "--branch", branch,
            "--limit", "1",
            "--json", "databaseId,status,conclusion,headBranch",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh run list failed: {r.stderr.strip()}")
    return json.loads(r.stdout or "[]")


def _gh_get_run(run_id: int) -> dict:
    r = subprocess.run(
        ["gh", "run", "view", str(run_id), "--json", "status,conclusion"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh run view failed: {r.stderr.strip()}")
    return json.loads(r.stdout or "{}")


def _gh_release_exists(tag: str, cwd: Path) -> bool:
    r = _run(["gh", "release", "view", tag], cwd)
    return r.returncode == 0


def _gh_release_create(
    tag: str,
    title: str,
    notes_file: Path | None,
    generate_notes: bool,
    cwd: Path,
    target: str | None = None,
) -> None:
    if _gh_release_exists(tag, cwd):
        print(f"Release {tag} already exists, skipping creation")
        return

    cmd = ["gh", "release", "create", tag, "--title", title]
    if target is not None:
        cmd += ["--target", target]
    if notes_file is not None:
        cmd += ["--notes-file", str(notes_file)]
    elif generate_notes:
        cmd += ["--generate-notes"]
    r = _run(cmd, cwd)
    if r.returncode != 0:
        raise RuntimeError(f"gh release create {tag} failed: {r.stderr.strip()}")


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


def cmd_read_config() -> None:
    projects = os.environ.get("PROJECTS", "").strip()
    if not projects:
        return
    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    config = _load_changie_config(cwd)
    write_output("changes-dir", config["changesDir"])
    write_output("separator", config["projectsVersionSeparator"])


def _wait(tag: str) -> None:
    """Apply the wait_for_publish env config to a single tag; exit on failure."""
    if os.environ.get("WAIT_FOR_PUBLISH", "false").lower() != "true":
        return
    ok, msg = wait_for_publish(
        tag=tag,
        enabled=True,
        workflow_name=os.environ.get("PUBLISH_WORKFLOW_NAME", "Publish"),
        timeout=float(os.environ.get("PUBLISH_WAIT_TIMEOUT_SECONDS", "1800")),
        poll=float(os.environ.get("PUBLISH_WAIT_POLL_SECONDS", "15")),
        list_runs=lambda t: _gh_list_runs(
            os.environ.get("PUBLISH_WORKFLOW_NAME", "Publish"), t
        ),
        get_run=_gh_get_run,
    )
    if not ok:
        fail(msg)


def _publish_tag(
    tag: str,
    project: str | None,
    version: str,
    cwd: Path,
    create_release: bool,
    changes_dir: Path,
    separator: str,
) -> None:
    if create_release:
        target = _git_head_sha(cwd)
        notes_file = resolve_notes_file(project, version, cwd / changes_dir, separator)
        if notes_file.is_file():
            _gh_release_create(tag, tag, notes_file, generate_notes=False, cwd=cwd, target=target)
        else:
            _gh_release_create(tag, tag, None, generate_notes=True, cwd=cwd, target=target)
    else:
        _git_push_tag(tag, cwd)


def cmd_tag() -> None:
    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    projects = os.environ.get("PROJECTS", "").strip()
    prefix = os.environ.get("PREFIX", "")
    create_release = os.environ.get("CREATE_RELEASE", "false").lower() == "true"
    changes_dir = Path(os.environ.get("CHANGES_DIR") or ".changes")
    separator = os.environ.get("SEPARATOR", "-")

    if projects:
        project_list = _split_csv(projects)
        all_versions: list[str] = []
        all_tags: list[str] = []
        created: list[tuple[str, str, str]] = []

        for project in project_list:
            version = _changie_latest(project, cwd)
            if not version:
                print(f"Could not resolve version for {project}, skipping")
                continue
            tag = f"{prefix}{version}"
            all_versions.append(version)
            all_tags.append(tag)

            if _git_tag_exists_local(tag, cwd):
                print(f"Tag {tag} already exists, skipping")
                continue
            try:
                if _git_tag_exists_remote(tag, cwd):
                    print(f"Tag {tag} already exists on origin, skipping")
                    continue
            except RuntimeError as e:
                fail(str(e))

            _git_create_tag(tag, cwd)
            created.append((project, version, tag))
            print(f"Created tag: {tag}")

        if created:
            for project, version, tag in created:
                _publish_tag(
                    tag,
                    project,
                    version,
                    cwd,
                    create_release,
                    changes_dir,
                    separator,
                )
                _wait(tag)
        else:
            print("No new tags to push")

        write_output("version", ", ".join(all_versions))
        write_output("tag", ", ".join(all_tags))
        write_output("created-tags", " ".join(tag for _, _, tag in created))
        return

    # Single-project mode
    version = _changie_latest(None, cwd)
    tag = f"{prefix}{version}"
    write_output("version", version)
    write_output("tag", tag)

    if _git_tag_exists_local(tag, cwd):
        print(f"Tag {tag} already exists, skipping")
        write_output("created-tags", "")
        return
    try:
        if _git_tag_exists_remote(tag, cwd):
            print(f"Tag {tag} already exists on origin, skipping")
            write_output("created-tags", "")
            return
    except RuntimeError as e:
        fail(str(e))

    _git_create_tag(tag, cwd)
    _publish_tag(tag, None, version, cwd, create_release, changes_dir, separator)
    write_output("created-tags", tag)
    _wait(tag)


def cmd_release() -> None:
    created_tags = os.environ.get("CREATED_TAGS", "").strip()
    if not created_tags:
        print("No newly-created tag needs a release")
        return

    cwd = Path(os.environ.get("WORKING_DIRECTORY", "."))
    projects = os.environ.get("PROJECTS", "").strip()
    prefix = os.environ.get("PREFIX", "")
    changes_dir = Path(os.environ.get("CHANGES_DIR") or ".changes")
    separator = os.environ.get("SEPARATOR", "-")
    created_set = set(created_tags.split())

    def _release(tag: str, project: str | None, version: str) -> None:
        notes_file = resolve_notes_file(project, version, cwd / changes_dir, separator)
        if notes_file.is_file():
            print(f"Creating release for {tag} with notes from {notes_file}")
            _gh_release_create(tag, tag, notes_file, generate_notes=False, cwd=cwd)
        else:
            print(f"Creating release for {tag} with --generate-notes")
            _gh_release_create(tag, tag, None, generate_notes=True, cwd=cwd)

    if projects:
        for project in _split_csv(projects):
            version = _changie_latest(project, cwd)
            if not version:
                continue
            tag = f"{prefix}{version}"
            if tag not in created_set:
                continue
            _release(tag, project, version)
    else:
        version = _changie_latest(None, cwd)
        # CREATED_TAGS in single-project mode is the single tag string
        tag = created_tags
        _release(tag, None, version)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


_HANDLERS = {
    "read-config": cmd_read_config,
    "tag": cmd_tag,
    "release": cmd_release,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(_HANDLERS))
    args = parser.parse_args()
    _HANDLERS[args.command]()


if __name__ == "__main__":
    main()
