"""Tests for changie_release helpers.

Run with:
    uv run --with pytest pytest changie-release/test_changie_release.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import changie_release  # noqa: E402
from changie_release import (  # noqa: E402
    aggregate_changelog,
    cmd_bump_files,
    cmd_check_config,
    cmd_read_changelog,
    cmd_resolve_templates,
    cmd_resolve_versions,
    parse_changie_config,
    parse_version_files,
    resolve_template,
    strip_version_prefix,
)


# --- parse_changie_config ---

class TestParseChangieConfig:
    def test_defaults_when_empty(self):
        config = parse_changie_config("")
        assert config["changesDir"] == ".changie.d"
        assert config["unreleasedDir"] == "unreleased"
        assert config["projectsVersionSeparator"] == "-"

    def test_reads_top_level_scalars(self):
        yaml = (
            "changesDir: .changes\n"
            "unreleasedDir: pending\n"
            "projectsVersionSeparator: _\n"
        )
        config = parse_changie_config(yaml)
        assert config["changesDir"] == ".changes"
        assert config["unreleasedDir"] == "pending"
        assert config["projectsVersionSeparator"] == "_"

    def test_strips_quotes(self):
        yaml = (
            'changesDir: ".changes"\n'
            "projectsVersionSeparator: '/'\n"
        )
        config = parse_changie_config(yaml)
        assert config["changesDir"] == ".changes"
        assert config["projectsVersionSeparator"] == "/"

    def test_ignores_indented_keys(self):
        # Same-named key inside a nested section must not be picked up
        yaml = "header:\n  changesDir: nested\nchangesDir: top\n"
        config = parse_changie_config(yaml)
        assert config["changesDir"] == "top"


# --- strip_version_prefix ---

class TestStripVersionPrefix:
    def test_single_project_strips_v(self):
        assert strip_version_prefix("v1.2.3") == "1.2.3"

    def test_single_project_no_v_passthrough(self):
        assert strip_version_prefix("1.2.3") == "1.2.3"

    def test_multi_project_strips_project_prefix(self):
        assert strip_version_prefix("my-pkg-v1.2.3", "my-pkg", "-") == "1.2.3"

    def test_multi_project_custom_separator(self):
        assert strip_version_prefix("pkg/v0.4.1", "pkg", "/") == "0.4.1"

    def test_multi_project_prefix_mismatch_falls_back(self):
        # If the actual version doesn't carry the expected prefix, strip only the v
        assert strip_version_prefix("v9.9.9", "my-pkg", "-") == "9.9.9"


# --- parse_version_files ---

class TestParseVersionFiles:
    def test_single_project(self):
        entries = parse_version_files("gleam.toml:version", multi_project=False)
        assert entries == [{"project": None, "path": "gleam.toml", "key": "version"}]

    def test_single_project_nested_key_path(self):
        entries = parse_version_files("Cargo.toml:package.version", multi_project=False)
        assert entries == [{"project": None, "path": "Cargo.toml", "key": "package.version"}]

    def test_multi_project(self):
        entries = parse_version_files("pkg:gleam.toml:version", multi_project=True)
        assert entries == [{"project": "pkg", "path": "gleam.toml", "key": "version"}]

    def test_multiple_lines(self):
        text = "a.toml:version\nb.toml:rev"
        entries = parse_version_files(text, multi_project=False)
        assert entries == [
            {"project": None, "path": "a.toml", "key": "version"},
            {"project": None, "path": "b.toml", "key": "rev"},
        ]

    def test_blank_lines_skipped(self):
        text = "\n\na.toml:version\n\n"
        entries = parse_version_files(text, multi_project=False)
        assert len(entries) == 1

    def test_single_rejects_three_fields(self):
        with pytest.raises(ValueError, match="path:key-path"):
            parse_version_files("a:b:c", multi_project=False)

    def test_multi_rejects_two_fields(self):
        with pytest.raises(ValueError, match="project:path:key-path"):
            parse_version_files("a:b", multi_project=True)


# --- resolve_template ---

class TestResolveTemplate:
    def test_substitutes_single_var(self):
        assert resolve_template("Release {version}", version="1.2.3") == "Release 1.2.3"

    def test_multiple_vars(self):
        out = resolve_template("{version}\n\n{changelog}", version="1.0", changelog="notes")
        assert out == "1.0\n\nnotes"

    def test_missing_var_left_alone(self):
        assert resolve_template("hello {other}", version="1.0") == "hello {other}"

    def test_repeated_var(self):
        assert resolve_template("{v}-{v}", v="x") == "x-x"


# --- aggregate_changelog ---

class TestAggregateChangelog:
    def test_combines_multiple_projects(self, tmp_path):
        (tmp_path / "pkg-a").mkdir()
        (tmp_path / "pkg-a" / "v1.0.0.md").write_text("- feature one\n")
        (tmp_path / "pkg-b").mkdir()
        (tmp_path / "pkg-b" / "v2.1.0.md").write_text("- fix something\n")

        versions = {"pkg-a": "pkg-a-v1.0.0", "pkg-b": "pkg-b-v2.1.0"}
        out = aggregate_changelog(
            versions_by_project=versions,
            project_order=["pkg-a", "pkg-b"],
            changes_dir=str(tmp_path),
            separator="-",
        )
        assert "### pkg-a v1.0.0" in out
        assert "- feature one" in out
        assert "### pkg-b v2.1.0" in out
        assert "- fix something" in out

    def test_skips_missing_files(self, tmp_path):
        # Project listed in versions but file doesn't exist
        out = aggregate_changelog(
            versions_by_project={"pkg-a": "pkg-a-v1.0.0"},
            project_order=["pkg-a"],
            changes_dir=str(tmp_path),
            separator="-",
        )
        assert out == ""

    def test_respects_order(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "v1.0.0.md").write_text("a-content\n")
        (tmp_path / "b").mkdir()
        (tmp_path / "b" / "v1.0.0.md").write_text("b-content\n")
        out = aggregate_changelog(
            {"a": "a-v1.0.0", "b": "b-v1.0.0"},
            ["b", "a"],
            str(tmp_path),
            "-",
        )
        assert out.index("b-content") < out.index("a-content")


# --- Subcommand integration tests ---

def _read_outputs(path: Path) -> dict[str, str]:
    """Parse a GITHUB_OUTPUT file (handles heredoc blocks)."""
    out: dict[str, str] = {}
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


class TestCheckConfig:
    def test_no_changie_yaml_uses_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setenv("PROJECTS", "")

        cmd_check_config()

        result = _read_outputs(outputs)
        assert result["changes-dir"] == ".changie.d"
        assert result["has-projects"] == "false"
        assert result["skipped"] == "true"

    def test_detects_fragments(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".changie.yaml").write_text("changesDir: .changes\nunreleasedDir: unreleased\n")
        frag_dir = tmp_path / ".changes" / "unreleased"
        frag_dir.mkdir(parents=True)
        (frag_dir / "Added-20260101.yaml").write_text("kind: Added\nbody: foo\n")
        (frag_dir / ".gitkeep").touch()  # must be ignored

        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setenv("PROJECTS", "")
        cmd_check_config()

        result = _read_outputs(outputs)
        assert result["changes-dir"] == ".changes"
        assert result["skipped"] == "false"

    def test_projects_mode_sets_separator(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".changie.yaml").write_text("projectsVersionSeparator: _\n")
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setenv("PROJECTS", "a,b")
        cmd_check_config()

        result = _read_outputs(outputs)
        assert result["has-projects"] == "true"
        assert result["separator"] == "_"


class TestResolveVersions:
    def test_single_project(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setattr(
            changie_release, "_changie_latest", lambda project, cwd: "v1.2.3"
        )
        cmd_resolve_versions()

        result = _read_outputs(outputs)
        assert result["version"] == "v1.2.3"
        assert result["versions-json"] == "{}"

    def test_multi_project_emits_json_map(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "a,b")
        monkeypatch.setenv("BATCHED", "a,b")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")

        fake = {"a": "a-v1.0.0", "b": "b-v2.0.0"}
        monkeypatch.setattr(
            changie_release,
            "_changie_latest",
            lambda project, cwd: fake.get(project, ""),
        )
        cmd_resolve_versions()

        result = _read_outputs(outputs)
        assert result["version"] == "a-v1.0.0, b-v2.0.0"
        assert json.loads(result["versions-json"]) == fake

    def test_multi_project_empty_batched(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "a,b")
        monkeypatch.setenv("BATCHED", "")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        cmd_resolve_versions()

        result = _read_outputs(outputs)
        assert result["version"] == ""
        assert result["versions-json"] == "{}"

    def test_multi_project_skips_failed_lookups(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "a,b")
        monkeypatch.setenv("BATCHED", "a,b")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        # b returns empty (e.g. no fragments existed)
        monkeypatch.setattr(
            changie_release,
            "_changie_latest",
            lambda project, cwd: "a-v1.0.0" if project == "a" else "",
        )
        cmd_resolve_versions()

        result = _read_outputs(outputs)
        assert result["version"] == "a-v1.0.0"
        assert json.loads(result["versions-json"]) == {"a": "a-v1.0.0"}


class TestBumpFiles:
    def test_single_project_bumps_version(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "gleam.toml").write_text('name = "x"\nversion = "0.0.0"\n')

        def fake_update(path: Path, key: str, value: str) -> None:
            assert key == "version"
            path.write_text('name = "x"\nversion = "1.2.3"\n')

        monkeypatch.setattr(changie_release, "update_toml_file_key", fake_update)
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("VERSION", "v1.2.3")
        monkeypatch.setenv("VERSION_FILES", "gleam.toml:version")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        cmd_bump_files()
        assert (tmp_path / "gleam.toml").read_text() == 'name = "x"\nversion = "1.2.3"\n'

    def test_single_project_bumps_nested_version(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "Cargo.toml").write_text('[package]\nversion = "0.0.0"\n')
        calls: list[tuple[Path, str, str]] = []

        def fake_update(path: Path, key: str, value: str) -> None:
            calls.append((path, key, value))
            path.write_text('[package]\nversion = "1.2.3"\n')

        monkeypatch.setattr(changie_release, "update_toml_file_key", fake_update)
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("VERSION", "v1.2.3")
        monkeypatch.setenv("VERSION_FILES", "Cargo.toml:package.version")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        cmd_bump_files()

        assert calls == [(Path("Cargo.toml"), "package.version", "1.2.3")]
        assert (tmp_path / "Cargo.toml").read_text() == '[package]\nversion = "1.2.3"\n'

    def test_multi_project_skips_unbatched(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pkg_a = tmp_path / "pkg-a"
        pkg_b = tmp_path / "pkg-b"
        pkg_a.mkdir()
        pkg_b.mkdir()
        (pkg_a / "gleam.toml").write_text('version = "0.0.0"\n')
        (pkg_b / "gleam.toml").write_text('version = "0.0.0"\n')

        def fake_update(path: Path, key: str, value: str) -> None:
            path.write_text(f'{key} = "{value}"\n')

        monkeypatch.setattr(changie_release, "update_toml_file_key", fake_update)
        monkeypatch.setenv("PROJECTS", "pkg-a,pkg-b")
        monkeypatch.setenv("BATCHED", "pkg-a")  # only pkg-a was batched
        monkeypatch.setenv(
            "VERSIONS_JSON",
            json.dumps({"pkg-a": "pkg-a-v1.0.0"}),
        )
        monkeypatch.setenv(
            "VERSION_FILES",
            "pkg-a:pkg-a/gleam.toml:version\npkg-b:pkg-b/gleam.toml:version",
        )
        monkeypatch.setenv("SEPARATOR", "-")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        cmd_bump_files()

        assert (pkg_a / "gleam.toml").read_text() == 'version = "1.0.0"\n'
        # pkg-b not batched → unchanged
        assert (pkg_b / "gleam.toml").read_text() == 'version = "0.0.0"\n'

    def test_missing_file_errors(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("VERSION", "1.0.0")
        monkeypatch.setenv("VERSION_FILES", "missing.toml:version")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        with pytest.raises(SystemExit):
            cmd_bump_files()


class TestReadChangelog:
    def test_single_project_reads_version_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".changes").mkdir()
        (tmp_path / ".changes" / "v1.0.0.md").write_text("- a thing\n- another\n")
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("VERSION", "v1.0.0")
        monkeypatch.setenv("CHANGES_DIR", ".changes")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        cmd_read_changelog()

        result = _read_outputs(outputs)
        assert "- a thing" in result["content"]
        assert "- another" in result["content"]

    def test_single_project_missing_file_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "")
        monkeypatch.setenv("VERSION", "v9.9.9")
        monkeypatch.setenv("CHANGES_DIR", ".changes")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        cmd_read_changelog()
        result = _read_outputs(outputs)
        assert result["content"] == ""

    def test_multi_project_aggregates(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ch = tmp_path / ".changes"
        (ch / "a").mkdir(parents=True)
        (ch / "b").mkdir(parents=True)
        (ch / "a" / "v1.0.0.md").write_text("a-notes\n")
        (ch / "b" / "v2.0.0.md").write_text("b-notes\n")

        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("PROJECTS", "a,b")
        monkeypatch.setenv("BATCHED", "a,b")
        monkeypatch.setenv(
            "VERSIONS_JSON",
            json.dumps({"a": "a-v1.0.0", "b": "b-v2.0.0"}),
        )
        monkeypatch.setenv("CHANGES_DIR", ".changes")
        monkeypatch.setenv("SEPARATOR", "-")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        cmd_read_changelog()

        result = _read_outputs(outputs)
        assert "### a v1.0.0" in result["content"]
        assert "a-notes" in result["content"]
        assert "### b v2.0.0" in result["content"]
        assert "b-notes" in result["content"]


class TestResolveTemplates:
    def test_resolves_single_project(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("VERSION", "v1.2.3")
        monkeypatch.setenv("TITLE_TPL", "Release {version}")
        monkeypatch.setenv("BRANCH_TPL", "release/{version}")
        monkeypatch.setenv("COMMIT_TPL", "chore(release): {version}")
        monkeypatch.setenv("BODY_TPL", "Version {version}\n\n{changelog}")
        monkeypatch.setenv("CHANGELOG", "- foo\n- bar")
        monkeypatch.setenv("HAS_PROJECTS", "false")
        cmd_resolve_templates()

        result = _read_outputs(outputs)
        assert result["pr-title"] == "Release v1.2.3"
        assert result["branch"] == "release/v1.2.3"
        assert result["commit-message"] == "chore(release): v1.2.3"
        assert "Version v1.2.3" in result["pr-body"]
        assert "- foo" in result["pr-body"]

    def test_multi_project_uses_next_branch(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("VERSION", "a-v1.0.0, b-v2.0.0")
        monkeypatch.setenv("TITLE_TPL", "Release {version}")
        monkeypatch.setenv("BRANCH_TPL", "release/{version}")
        monkeypatch.setenv("COMMIT_TPL", "chore(release): {version}")
        monkeypatch.setenv("BODY_TPL", "{changelog}")
        monkeypatch.setenv("CHANGELOG", "x")
        monkeypatch.setenv("HAS_PROJECTS", "true")
        cmd_resolve_templates()

        result = _read_outputs(outputs)
        assert result["branch"] == "release/next"
        assert result["pr-title"] == "Release a-v1.0.0, b-v2.0.0"
