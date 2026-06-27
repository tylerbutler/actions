"""Tests for changie_check.

Run:
    uv run --with pytest pytest changie-check/test_changie_check.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import changie_check  # noqa: E402
from changie_check import (  # noqa: E402
    cmd_check_required,
    cmd_detect_fragments,
    cmd_render_preview,
    has_breaking_marker,
    needs_changelog_entry,
    parse_changie_config,
    parse_conventional_types,
)


# --- parse_changie_config ---


class TestParseChangieConfig:
    def test_defaults(self):
        c = parse_changie_config("")
        assert c["changesDir"] == ".changie.d"
        assert c["unreleasedDir"] == "unreleased"

    def test_custom(self):
        c = parse_changie_config(
            "changesDir: .changes\nunreleasedDir: pending\n"
        )
        assert c["changesDir"] == ".changes"
        assert c["unreleasedDir"] == "pending"


# --- parse_conventional_types ---


class TestParseConventionalTypes:
    def test_simple(self):
        log = "feat: add foo\nfix: bar\n"
        assert parse_conventional_types(log) == {"feat", "fix"}

    def test_with_scope(self):
        log = "feat(api): add\nfix(ui): patch\n"
        assert parse_conventional_types(log) == {"feat", "fix"}

    def test_with_breaking_marker(self):
        log = "feat!: drop deprecated api\n"
        assert parse_conventional_types(log) == {"feat"}

    def test_with_scope_and_breaking(self):
        log = "feat(api)!: rewrite\n"
        assert parse_conventional_types(log) == {"feat"}

    def test_ignores_non_conventional(self):
        log = "random subject\nfeat: x\n   indented: nope\n"
        assert parse_conventional_types(log) == {"feat"}

    def test_empty(self):
        assert parse_conventional_types("") == set()

    def test_deduplicates(self):
        log = "feat: a\nfeat: b\nfeat(api): c\n"
        assert parse_conventional_types(log) == {"feat"}


# --- has_breaking_marker ---


class TestHasBreakingMarker:
    def test_with_bang(self):
        assert has_breaking_marker("feat!: break\n")

    def test_with_scope_and_bang(self):
        assert has_breaking_marker("feat(api)!: break\n")

    def test_no_bang(self):
        assert not has_breaking_marker("feat: nope\nfix: nope\n")

    def test_bang_only_in_body(self):
        # Has to be in subject prefix, not anywhere
        assert not has_breaking_marker("feat: foo with ! mark\n")


# --- needs_changelog_entry ---


class TestNeedsChangelogEntry:
    def test_required_type_present(self):
        assert needs_changelog_entry({"feat", "chore"}, ["feat", "fix"])

    def test_only_non_required_types(self):
        assert not needs_changelog_entry({"docs", "chore"}, ["feat", "fix"])

    def test_empty_types(self):
        assert not needs_changelog_entry(set(), ["feat", "fix"])


# --- IO helpers ---


def _read_outputs(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    lines = path.read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if "<<" in line and "=" not in line.split("<<", 1)[0]:
            key, sentinel = line.split("<<", 1)
            buf = []
            i += 1
            while i < len(lines) and lines[i] != sentinel:
                buf.append(lines[i])
                i += 1
            out[key] = "\n".join(buf)
        elif "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
        i += 1
    return out


# --- cmd_detect_fragments ---


class TestCmdDetectFragments:
    def test_no_fragments(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("BASE_SHA", "base")
        monkeypatch.setenv("HEAD_SHA", "head")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setattr(
            changie_check, "_git_diff_added", lambda base, head, glob, cwd: []
        )
        cmd_detect_fragments()
        result = _read_outputs(outputs)
        assert result["has-entries"] == "false"
        assert result["fragments"] == ""

    def test_fragments_detected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".changie.yaml").write_text(
            "changesDir: .changes\nunreleasedDir: unreleased\n"
        )
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("BASE_SHA", "base")
        monkeypatch.setenv("HEAD_SHA", "head")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")

        captured_glob: list[str] = []

        def fake_diff(base, head, glob, cwd):
            captured_glob.append(glob)
            return [
                ".changes/unreleased/Added-1.yaml",
                ".changes/unreleased/Fixed-2.md",
                ".changes/unreleased/.gitkeep",
            ]

        monkeypatch.setattr(changie_check, "_git_diff_added", fake_diff)
        cmd_detect_fragments()

        result = _read_outputs(outputs)
        assert result["has-entries"] == "true"
        # The unreleased dir itself is the pathspec so any extension matches.
        assert captured_glob == [".changes/unreleased"]
        assert "Added-1.yaml" in result["fragments"]
        # Non-.yaml fragments (e.g. versionExt: md) are detected too.
        assert "Fixed-2.md" in result["fragments"]
        # Dotfiles like .gitkeep are not counted as fragments.
        assert ".gitkeep" not in result["fragments"]
        assert result["unreleased-path"] == ".changes/unreleased"

    def test_only_gitkeep_added_is_not_a_fragment(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("BASE_SHA", "base")
        monkeypatch.setenv("HEAD_SHA", "head")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setattr(
            changie_check,
            "_git_diff_added",
            lambda base, head, glob, cwd: [".changes/unreleased/.gitkeep"],
        )
        cmd_detect_fragments()
        result = _read_outputs(outputs)
        assert result["has-entries"] == "false"
        assert result["fragments"] == ""


# --- cmd_render_preview ---


class TestCmdRenderPreview:
    def test_removes_non_pr_fragments_and_calls_changie(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        unreleased = tmp_path / ".changes" / "unreleased"
        unreleased.mkdir(parents=True)
        (unreleased / "pr-added.yaml").write_text("kind: Added\n")
        (unreleased / "from-main.yaml").write_text("kind: Added\n")
        (unreleased / "from-main.md").write_text("kind: Added\n")
        (unreleased / ".gitkeep").touch()  # dotfile, should be left alone

        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv(
            "FRAGMENTS", ".changes/unreleased/pr-added.yaml"
        )
        monkeypatch.setenv("UNRELEASED_PATH", ".changes/unreleased")
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setattr(
            changie_check,
            "_changie_batch_dry_run",
            lambda project, cwd: "## Added\n- pr-only content\n",
        )

        cmd_render_preview()

        # Non-PR fragment removed, PR fragment preserved, .gitkeep untouched
        assert (unreleased / "pr-added.yaml").exists()
        assert not (unreleased / "from-main.yaml").exists()
        assert not (unreleased / "from-main.md").exists()
        assert (unreleased / ".gitkeep").exists()

        result = _read_outputs(outputs)
        assert "- pr-only content" in result["preview"]

    def test_multi_project_prefixes_per_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        unreleased = tmp_path / ".changes" / "unreleased"
        unreleased.mkdir(parents=True)
        (unreleased / "x.yaml").write_text("kind: Added\n")

        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("FRAGMENTS", ".changes/unreleased/x.yaml")
        monkeypatch.setenv("UNRELEASED_PATH", ".changes/unreleased")
        monkeypatch.setenv("PROJECTS", "pkg-a,pkg-b")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")

        previews = {"pkg-a": "- a stuff", "pkg-b": "- b stuff"}
        monkeypatch.setattr(
            changie_check,
            "_changie_batch_dry_run",
            lambda project, cwd: previews[project],
        )

        cmd_render_preview()

        result = _read_outputs(outputs)
        assert "#### pkg-a" in result["preview"]
        assert "- a stuff" in result["preview"]
        assert "#### pkg-b" in result["preview"]
        assert "- b stuff" in result["preview"]
        assert result["preview"].index("pkg-a") < result["preview"].index("pkg-b")


# --- cmd_check_required ---


class TestCmdCheckRequired:
    def test_no_commit_types(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("BASE_SHA", "base")
        monkeypatch.setenv("HEAD_SHA", "head")
        monkeypatch.setenv("REQUIRE_FOR_TYPES", "feat,fix")
        monkeypatch.setattr(
            changie_check, "_git_log_subjects", lambda base, head, cwd: ""
        )
        cmd_check_required()
        result = _read_outputs(outputs)
        assert result["needs-entry"] == "false"
        assert result["commit-types-found"] == ""

    def test_breaking_change_requires(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("BASE_SHA", "base")
        monkeypatch.setenv("HEAD_SHA", "head")
        monkeypatch.setenv("REQUIRE_FOR_TYPES", "feat,fix")
        monkeypatch.setattr(
            changie_check,
            "_git_log_subjects",
            lambda base, head, cwd: "chore!: drop old api\n",
        )
        cmd_check_required()
        result = _read_outputs(outputs)
        assert result["needs-entry"] == "true"
        assert result["commit-types-found"] == "chore"

    def test_required_type_match(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("BASE_SHA", "base")
        monkeypatch.setenv("HEAD_SHA", "head")
        monkeypatch.setenv("REQUIRE_FOR_TYPES", "feat,fix")
        monkeypatch.setattr(
            changie_check,
            "_git_log_subjects",
            lambda base, head, cwd: "feat: add thing\ndocs: typo\n",
        )
        cmd_check_required()
        result = _read_outputs(outputs)
        assert result["needs-entry"] == "true"
        # types sorted for stable output
        assert set(result["commit-types-found"].split(",")) == {"feat", "docs"}

    def test_only_non_required(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("BASE_SHA", "base")
        monkeypatch.setenv("HEAD_SHA", "head")
        monkeypatch.setenv("REQUIRE_FOR_TYPES", "feat,fix")
        monkeypatch.setattr(
            changie_check,
            "_git_log_subjects",
            lambda base, head, cwd: "docs: typo\nchore: deps\n",
        )
        cmd_check_required()
        result = _read_outputs(outputs)
        assert result["needs-entry"] == "false"
