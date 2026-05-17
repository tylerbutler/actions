"""Tests for changie_auto_tag.

Run:
    uv run --with pytest pytest changie-auto-tag/test_changie_auto_tag.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import changie_auto_tag  # noqa: E402
from changie_auto_tag import (  # noqa: E402
    cmd_read_config,
    cmd_release,
    cmd_tag,
    parse_changie_config,
    resolve_notes_file,
    wait_for_publish,
)


# --- parse_changie_config (same shape as changie-release) ---


class TestParseChangieConfig:
    def test_defaults(self):
        c = parse_changie_config("")
        assert c["changesDir"] == ".changie.d"
        assert c["projectsVersionSeparator"] == "-"

    def test_reads_quoted(self):
        c = parse_changie_config(
            'changesDir: ".changes"\nprojectsVersionSeparator: "_"\n'
        )
        assert c["changesDir"] == ".changes"
        assert c["projectsVersionSeparator"] == "_"


# --- resolve_notes_file ---


class TestResolveNotesFile:
    def test_single_project(self):
        path = resolve_notes_file(
            project=None,
            version="v1.0.0",
            changes_dir=Path(".changes"),
            separator="-",
        )
        assert path == Path(".changes/v1.0.0.md")

    def test_multi_project(self):
        path = resolve_notes_file(
            project="pkg-a",
            version="pkg-a-v1.0.0",
            changes_dir=Path(".changes"),
            separator="-",
        )
        assert path == Path(".changes/pkg-a/v1.0.0.md")

    def test_multi_project_custom_separator(self):
        path = resolve_notes_file(
            project="pkg",
            version="pkg_v0.4.1",
            changes_dir=Path(".changes"),
            separator="_",
        )
        assert path == Path(".changes/pkg/v0.4.1.md")


# --- wait_for_publish state machine ---


class FakeClock:
    """Monotonic clock + sleep recorder for deterministic polling tests."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, secs: float) -> None:
        self.sleeps.append(secs)
        self.t += secs


class TestWaitForPublish:
    def test_disabled_returns_immediately(self):
        clock = FakeClock()
        ok, _ = wait_for_publish(
            tag="v1.0.0",
            enabled=False,
            workflow_name="Publish",
            timeout=60,
            poll=5,
            list_runs=lambda tag: [],
            get_run=lambda run_id: {"status": "completed", "conclusion": "success"},
            now=clock.now,
            sleep=clock.sleep,
        )
        assert ok is True
        assert clock.sleeps == []

    def test_immediate_success(self):
        clock = FakeClock()
        ok, msg = wait_for_publish(
            tag="v1.0.0",
            enabled=True,
            workflow_name="Publish",
            timeout=60,
            poll=5,
            list_runs=lambda tag: [{"databaseId": 42}],
            get_run=lambda run_id: {"status": "completed", "conclusion": "success"},
            now=clock.now,
            sleep=clock.sleep,
        )
        assert ok is True
        assert "42" in msg
        assert clock.sleeps == []

    def test_polls_until_run_appears(self):
        clock = FakeClock()
        calls = {"n": 0}

        def list_runs(tag):
            calls["n"] += 1
            return [{"databaseId": 7}] if calls["n"] >= 3 else []

        ok, _ = wait_for_publish(
            tag="v1",
            enabled=True,
            workflow_name="Publish",
            timeout=60,
            poll=5,
            list_runs=list_runs,
            get_run=lambda run_id: {"status": "completed", "conclusion": "success"},
            now=clock.now,
            sleep=clock.sleep,
        )
        assert ok is True
        assert clock.sleeps == [5, 5]  # slept twice before the run appeared

    def test_polls_until_run_completes(self):
        clock = FakeClock()
        states = iter(
            [
                {"status": "queued", "conclusion": None},
                {"status": "in_progress", "conclusion": None},
                {"status": "completed", "conclusion": "success"},
            ]
        )
        ok, _ = wait_for_publish(
            tag="v1",
            enabled=True,
            workflow_name="Publish",
            timeout=60,
            poll=5,
            list_runs=lambda tag: [{"databaseId": 7}],
            get_run=lambda run_id: next(states),
            now=clock.now,
            sleep=clock.sleep,
        )
        assert ok is True
        assert clock.sleeps == [5, 5]

    def test_completed_failure_returns_false(self):
        clock = FakeClock()
        ok, msg = wait_for_publish(
            tag="v1",
            enabled=True,
            workflow_name="Publish",
            timeout=60,
            poll=5,
            list_runs=lambda tag: [{"databaseId": 7}],
            get_run=lambda run_id: {"status": "completed", "conclusion": "failure"},
            now=clock.now,
            sleep=clock.sleep,
        )
        assert ok is False
        assert "failure" in msg.lower()

    def test_timeout_finding_run(self):
        clock = FakeClock()
        ok, msg = wait_for_publish(
            tag="v1",
            enabled=True,
            workflow_name="Publish",
            timeout=10,
            poll=5,
            list_runs=lambda tag: [],
            get_run=lambda run_id: {"status": "queued", "conclusion": None},
            now=clock.now,
            sleep=clock.sleep,
        )
        assert ok is False
        assert "timed out" in msg.lower()

    def test_timeout_waiting_for_completion(self):
        clock = FakeClock()
        ok, msg = wait_for_publish(
            tag="v1",
            enabled=True,
            workflow_name="Publish",
            timeout=10,
            poll=5,
            list_runs=lambda tag: [{"databaseId": 7}],
            get_run=lambda run_id: {"status": "in_progress", "conclusion": None},
            now=clock.now,
            sleep=clock.sleep,
        )
        assert ok is False
        assert "timed out" in msg.lower()


# --- helpers for integration tests ---


def _read_outputs(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
    return out


# --- cmd_read_config ---


class TestCmdReadConfig:
    def test_no_projects_emits_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        cmd_read_config()
        # No output emitted in single-project mode (matches bash)
        assert _read_outputs(outputs) == {}

    def test_with_projects_emits_dirs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".changie.yaml").write_text(
            "changesDir: .changes\nprojectsVersionSeparator: _\n"
        )
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "a,b")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        cmd_read_config()
        result = _read_outputs(outputs)
        assert result["changes-dir"] == ".changes"
        assert result["separator"] == "_"


# --- cmd_tag ---


class FakeGit:
    """Records git invocations; configurable responses for tag existence checks."""

    def __init__(
        self,
        local_existing: set[str] | None = None,
        remote_existing: set[str] | None = None,
    ) -> None:
        self.local_existing = local_existing or set()
        self.remote_existing = remote_existing or set()
        self.created: list[str] = []
        self.pushed: list[str] = []

    def tag_exists_local(self, tag: str, cwd: Path) -> bool:
        return tag in self.local_existing

    def tag_exists_remote(self, tag: str, cwd: Path) -> bool:
        return tag in self.remote_existing

    def create_tag(self, tag: str, cwd: Path) -> None:
        self.created.append(tag)

    def push_tag(self, tag: str, cwd: Path) -> None:
        self.pushed.append(tag)


class TestCmdTag:
    def test_single_project_happy_path(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("PREFIX", "")
        monkeypatch.setenv("WAIT_FOR_PUBLISH", "false")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")

        fake_git = FakeGit()
        monkeypatch.setattr(changie_auto_tag, "_git_tag_exists_local", fake_git.tag_exists_local)
        monkeypatch.setattr(changie_auto_tag, "_git_tag_exists_remote", fake_git.tag_exists_remote)
        monkeypatch.setattr(changie_auto_tag, "_git_create_tag", fake_git.create_tag)
        monkeypatch.setattr(changie_auto_tag, "_git_push_tag", fake_git.push_tag)
        monkeypatch.setattr(changie_auto_tag, "_changie_latest", lambda project, cwd: "v1.0.0")

        cmd_tag()

        result = _read_outputs(outputs)
        assert result["version"] == "v1.0.0"
        assert result["tag"] == "v1.0.0"
        assert result["created-tags"] == "v1.0.0"
        assert fake_git.created == ["v1.0.0"]
        assert fake_git.pushed == ["v1.0.0"]

    def test_skip_when_tag_exists_locally(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("PREFIX", "")
        monkeypatch.setenv("WAIT_FOR_PUBLISH", "false")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")

        fake_git = FakeGit(local_existing={"v1.0.0"})
        monkeypatch.setattr(changie_auto_tag, "_git_tag_exists_local", fake_git.tag_exists_local)
        monkeypatch.setattr(changie_auto_tag, "_git_tag_exists_remote", fake_git.tag_exists_remote)
        monkeypatch.setattr(changie_auto_tag, "_git_create_tag", fake_git.create_tag)
        monkeypatch.setattr(changie_auto_tag, "_git_push_tag", fake_git.push_tag)
        monkeypatch.setattr(changie_auto_tag, "_changie_latest", lambda project, cwd: "v1.0.0")

        cmd_tag()

        result = _read_outputs(outputs)
        assert result["created-tags"] == ""
        assert fake_git.created == []
        assert fake_git.pushed == []

    def test_multi_project_partial_creation(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "a,b,c")
        monkeypatch.setenv("PREFIX", "")
        monkeypatch.setenv("WAIT_FOR_PUBLISH", "false")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")

        # b already exists on origin; c returns no version
        fake_git = FakeGit(remote_existing={"b-v2.0.0"})
        monkeypatch.setattr(changie_auto_tag, "_git_tag_exists_local", fake_git.tag_exists_local)
        monkeypatch.setattr(changie_auto_tag, "_git_tag_exists_remote", fake_git.tag_exists_remote)
        monkeypatch.setattr(changie_auto_tag, "_git_create_tag", fake_git.create_tag)
        monkeypatch.setattr(changie_auto_tag, "_git_push_tag", fake_git.push_tag)

        versions = {"a": "a-v1.0.0", "b": "b-v2.0.0", "c": ""}
        monkeypatch.setattr(
            changie_auto_tag, "_changie_latest", lambda project, cwd: versions[project]
        )

        cmd_tag()

        result = _read_outputs(outputs)
        # versions and tag include only projects with a resolved version (a + b)
        assert result["version"] == "a-v1.0.0, b-v2.0.0"
        assert result["tag"] == "a-v1.0.0, b-v2.0.0"
        # Only a was actually created (b skipped, c had no version)
        assert result["created-tags"] == "a-v1.0.0"
        assert fake_git.created == ["a-v1.0.0"]
        assert fake_git.pushed == ["a-v1.0.0"]


# --- cmd_release ---


class TestCmdRelease:
    def test_no_created_tags_skips(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CREATED_TAGS", "")
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        cmd_release()  # should not raise
        assert "No newly-created tag" in capsys.readouterr().out

    def test_single_project_with_notes_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".changes").mkdir()
        (tmp_path / ".changes" / "v1.0.0.md").write_text("notes\n")
        monkeypatch.setenv("CREATED_TAGS", "v1.0.0")
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("PREFIX", "")
        monkeypatch.setenv("CHANGES_DIR", ".changes")
        monkeypatch.setenv("SEPARATOR", "")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")

        calls: list[list[str]] = []
        monkeypatch.setattr(
            changie_auto_tag,
            "_gh_release_create",
            lambda tag, title, notes_file, generate_notes, cwd: calls.append(
                [tag, title, str(notes_file) if notes_file else None, generate_notes]
            ),
        )
        monkeypatch.setattr(
            changie_auto_tag, "_changie_latest", lambda project, cwd: "v1.0.0"
        )

        cmd_release()

        assert len(calls) == 1
        assert calls[0][0] == "v1.0.0"
        assert calls[0][2] is not None
        assert calls[0][3] is False  # used notes file, not generate

    def test_single_project_falls_back_to_generate(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No notes file exists
        monkeypatch.setenv("CREATED_TAGS", "v1.0.0")
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("PREFIX", "")
        monkeypatch.setenv("CHANGES_DIR", ".changes")
        monkeypatch.setenv("SEPARATOR", "")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")

        calls: list[list] = []
        monkeypatch.setattr(
            changie_auto_tag,
            "_gh_release_create",
            lambda tag, title, notes_file, generate_notes, cwd: calls.append(
                [tag, generate_notes]
            ),
        )
        monkeypatch.setattr(
            changie_auto_tag, "_changie_latest", lambda project, cwd: "v1.0.0"
        )

        cmd_release()

        assert calls == [["v1.0.0", True]]

    def test_multi_project_only_for_created_tags(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ch = tmp_path / ".changes"
        (ch / "a").mkdir(parents=True)
        (ch / "a" / "v1.0.0.md").write_text("a-notes\n")
        # b notes file missing on purpose

        monkeypatch.setenv("CREATED_TAGS", "a-v1.0.0")  # only a was created; b already existed
        monkeypatch.setenv("PROJECTS", "a,b")
        monkeypatch.setenv("PREFIX", "")
        monkeypatch.setenv("CHANGES_DIR", ".changes")
        monkeypatch.setenv("SEPARATOR", "-")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")

        versions = {"a": "a-v1.0.0", "b": "b-v2.0.0"}
        monkeypatch.setattr(
            changie_auto_tag, "_changie_latest", lambda project, cwd: versions[project]
        )
        calls: list[list] = []
        monkeypatch.setattr(
            changie_auto_tag,
            "_gh_release_create",
            lambda tag, title, notes_file, generate_notes, cwd: calls.append(
                [tag, notes_file is not None]
            ),
        )

        cmd_release()

        # Only a is in CREATED_TAGS, so only a gets a release
        assert calls == [["a-v1.0.0", True]]
