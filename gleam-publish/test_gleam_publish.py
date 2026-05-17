"""Tests for gleam_publish.

Run:
    uv run --with pytest pytest gleam-publish/test_gleam_publish.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import gleam_publish  # noqa: E402
from gleam_publish import (  # noqa: E402
    cmd_publish,
    cmd_rewrite_path_deps,
    hex_range,
    is_already_published,
    parse_replace_path_deps,
    read_gleam_meta,
    rewrite_path_dep,
)


# --- hex_range ---


class TestHexRange:
    def test_post_1_0(self):
        # Post-1.0: major bump is breaking
        assert hex_range("1.2.3") == ">= 1.2.3 and < 2.0.0"

    def test_post_1_0_zero_patch(self):
        assert hex_range("2.0.0") == ">= 2.0.0 and < 3.0.0"

    def test_pre_1_0(self):
        # Pre-1.0: minor bump is breaking
        assert hex_range("0.4.1") == ">= 0.4.1 and < 0.5.0"

    def test_pre_1_0_zero_zero(self):
        assert hex_range("0.0.5") == ">= 0.0.5 and < 0.1.0"

    def test_pre_1_0_zero_minor(self):
        assert hex_range("0.0.0") == ">= 0.0.0 and < 0.1.0"

    def test_invalid_version_raises(self):
        with pytest.raises(ValueError):
            hex_range("not-a-version")

    def test_too_few_components_raises(self):
        with pytest.raises(ValueError):
            hex_range("1.0")


# --- parse_replace_path_deps ---


class TestParseReplacePathDeps:
    def test_single_entry(self):
        out = parse_replace_path_deps("vestibule:gleam.toml")
        assert out == [("vestibule", "gleam.toml")]

    def test_multiple(self):
        text = "a:packages/a/gleam.toml\nb:packages/b/gleam.toml"
        out = parse_replace_path_deps(text)
        assert out == [("a", "packages/a/gleam.toml"), ("b", "packages/b/gleam.toml")]

    def test_blank_lines_skipped(self):
        out = parse_replace_path_deps("\n\nfoo:bar.toml\n  \n")
        assert out == [("foo", "bar.toml")]

    def test_whitespace_trimmed(self):
        out = parse_replace_path_deps("  foo  :  bar.toml  ")
        assert out == [("foo", "bar.toml")]

    def test_invalid_no_colon(self):
        with pytest.raises(ValueError):
            parse_replace_path_deps("nocolon")

    def test_empty_field(self):
        with pytest.raises(ValueError):
            parse_replace_path_deps(":foo")
        with pytest.raises(ValueError):
            parse_replace_path_deps("foo:")


# --- read_gleam_meta ---


class TestReadGleamMeta:
    def test_basic(self):
        content = 'name = "foo"\nversion = "1.2.3"\n'
        assert read_gleam_meta(content) == ("foo", "1.2.3")

    def test_with_other_fields(self):
        content = (
            'name = "my_pkg"\n'
            'version = "0.1.0"\n'
            'description = "a thing"\n'
            "\n"
            "[dependencies]\n"
            'gleam_stdlib = ">= 0.34.0"\n'
        )
        assert read_gleam_meta(content) == ("my_pkg", "0.1.0")

    def test_missing_name_raises(self):
        with pytest.raises(KeyError):
            read_gleam_meta('version = "1.0.0"\n')

    def test_missing_version_raises(self):
        with pytest.raises(KeyError):
            read_gleam_meta('name = "foo"\n')


# --- rewrite_path_dep ---


class TestRewritePathDep:
    def test_basic(self):
        content = (
            'name = "consumer"\n'
            'version = "0.1.0"\n'
            "\n"
            "[dependencies]\n"
            'foo = { path = "../foo" }\n'
            'gleam_stdlib = ">= 0.34.0"\n'
        )
        result = rewrite_path_dep(content, "foo", ">= 1.0.0 and < 2.0.0")
        assert 'foo = ">= 1.0.0 and < 2.0.0"' in result
        assert "path =" not in result.replace('"', "")  # no path remains for foo
        # other dep untouched
        assert 'gleam_stdlib = ">= 0.34.0"' in result

    def test_no_change_when_not_path_dep(self):
        # If foo is a version range, leave it alone
        content = '[dependencies]\nfoo = ">= 1.0.0"\n'
        result = rewrite_path_dep(content, "foo", ">= 2.0.0 and < 3.0.0")
        assert result == content

    def test_no_change_when_dep_absent(self):
        content = '[dependencies]\nbar = "1.0.0"\n'
        result = rewrite_path_dep(content, "foo", ">= 1.0.0 and < 2.0.0")
        assert result == content

    def test_preserves_indentation(self):
        # Dependency lines inside [dependencies] are conventionally unindented
        # but accept leading whitespace if present
        content = '[dependencies]\n  foo = { path = "../foo" }\n'
        result = rewrite_path_dep(content, "foo", ">= 1.0.0 and < 2.0.0")
        assert '  foo = ">= 1.0.0 and < 2.0.0"' in result


# --- is_already_published ---


class TestIsAlreadyPublished:
    def test_already_published(self):
        assert is_already_published("error: foo@1.0.0 is already published")

    def test_already_exists(self):
        assert is_already_published("Package version already exists on Hex")

    def test_version_already(self):
        assert is_already_published("version already in use")

    def test_case_insensitive(self):
        assert is_already_published("ALREADY PUBLISHED")

    def test_unrelated_error(self):
        assert not is_already_published("network timeout")


# --- subcommand integration ---


def _write_toml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class TestRewritePathDepsCmd:
    def test_rewrites_across_packages(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Root version source
        _write_toml(tmp_path / "gleam.toml", 'name = "vestibule"\nversion = "0.4.1"\n')
        # Sub-packages with path deps on vestibule
        _write_toml(
            tmp_path / "packages" / "apple" / "gleam.toml",
            'name = "apple"\nversion = "0.1.0"\n\n'
            "[dependencies]\n"
            'vestibule = { path = "../.." }\n',
        )
        _write_toml(
            tmp_path / "packages" / "google" / "gleam.toml",
            'name = "google"\nversion = "0.1.0"\n\n'
            "[dependencies]\n"
            'vestibule = { path = "../.." }\n',
        )
        # Stale manifest and build dir should be removed
        (tmp_path / "packages" / "apple" / "manifest.toml").write_text("stale\n")
        (tmp_path / "packages" / "apple" / "build").mkdir()

        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setenv("REPLACE_PATH_DEPS", "vestibule:gleam.toml")
        monkeypatch.setenv("PACKAGES", ". packages/apple packages/google")
        cmd_rewrite_path_deps()

        apple = (tmp_path / "packages" / "apple" / "gleam.toml").read_text()
        google = (tmp_path / "packages" / "google" / "gleam.toml").read_text()
        assert 'vestibule = ">= 0.4.1 and < 0.5.0"' in apple
        assert 'vestibule = ">= 0.4.1 and < 0.5.0"' in google
        assert not (tmp_path / "packages" / "apple" / "manifest.toml").exists()
        assert not (tmp_path / "packages" / "apple" / "build").exists()

    def test_rejects_unsafe_package_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_toml(tmp_path / "gleam.toml", 'name = "x"\nversion = "1.0.0"\n')
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setenv("REPLACE_PATH_DEPS", "x:gleam.toml")
        monkeypatch.setenv("PACKAGES", "../escape")
        with pytest.raises(SystemExit):
            cmd_rewrite_path_deps()


class TestPublishCmd:
    def test_publishes_in_order_and_skips_already_published(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        _write_toml(tmp_path / "a" / "gleam.toml", 'name = "a"\nversion = "1.0.0"\n')
        _write_toml(tmp_path / "b" / "gleam.toml", 'name = "b"\nversion = "1.0.0"\n')
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setenv("PACKAGES", "a b")
        monkeypatch.setenv("HEXPM_API_KEY", "fake")
        monkeypatch.setenv("SKIP_PUBLISHED", "true")

        calls: list[Path] = []

        def fake_publish(pkg_dir: Path) -> tuple[int, str]:
            calls.append(pkg_dir)
            if pkg_dir.name == "a":
                return 0, "published"
            return 1, "version already in use"

        monkeypatch.setattr(gleam_publish, "_run_gleam_publish", fake_publish)

        cmd_publish()

        assert [c.name for c in calls] == ["a", "b"]
        result = _read_outputs(outputs)
        assert result["published"] == "a"
        assert result["skipped"] == "b"

    def test_fails_on_real_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_toml(tmp_path / "a" / "gleam.toml", 'name = "a"\nversion = "1.0.0"\n')
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setenv("PACKAGES", "a")
        monkeypatch.setenv("HEXPM_API_KEY", "fake")
        monkeypatch.setenv("SKIP_PUBLISHED", "true")
        monkeypatch.setattr(
            gleam_publish,
            "_run_gleam_publish",
            lambda pkg_dir: (1, "network timeout"),
        )
        with pytest.raises(SystemExit):
            cmd_publish()

    def test_already_published_fails_when_skip_disabled(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_toml(tmp_path / "a" / "gleam.toml", 'name = "a"\nversion = "1.0.0"\n')
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setenv("PACKAGES", "a")
        monkeypatch.setenv("HEXPM_API_KEY", "fake")
        monkeypatch.setenv("SKIP_PUBLISHED", "false")
        monkeypatch.setattr(
            gleam_publish,
            "_run_gleam_publish",
            lambda pkg_dir: (1, "already published"),
        )
        with pytest.raises(SystemExit):
            cmd_publish()


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
