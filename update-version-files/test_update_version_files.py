"""Tests for update_version_files.

Run with:
    uv run --with pytest pytest update-version-files/test_update_version_files.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import update_version_files  # noqa: E402
from update_version_files import (  # noqa: E402
    find_ancestor_package_json,
    main,
    parse_entries,
)


class TestParseEntries:
    def test_simple(self):
        assert parse_entries("foo.toml:version") == [("foo.toml", "version")]

    def test_multiline(self):
        text = "a.toml:version\nb.toml:name"
        assert parse_entries(text) == [("a.toml", "version"), ("b.toml", "name")]

    def test_strips_whitespace_around_fields(self):
        assert parse_entries("  foo.toml : version  ") == [("foo.toml", "version")]

    def test_skips_blank_lines(self):
        text = "\na.toml:version\n\n  \nb.toml:name\n"
        assert parse_entries(text) == [("a.toml", "version"), ("b.toml", "name")]

    def test_rejects_missing_colon(self):
        with pytest.raises(ValueError, match="expected 'path:key-path'"):
            parse_entries("nocolon")

    def test_rejects_empty_path(self):
        with pytest.raises(ValueError):
            parse_entries(":version")

    def test_rejects_empty_key(self):
        with pytest.raises(ValueError):
            parse_entries("foo.toml:")


class TestFindAncestorPackageJson:
    def test_same_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "Cargo.toml").write_text("")
        result = find_ancestor_package_json(Path("Cargo.toml"))
        assert result == Path("package.json")

    def test_walks_up_multiple_levels(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text("{}")
        pkg_dir = tmp_path / "packages" / "core"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "Cargo.toml").write_text("")
        result = find_ancestor_package_json(Path("packages/core/Cargo.toml"))
        assert result == Path("package.json")

    def test_picks_nearest_when_multiple_exist(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text('{"name":"root"}')
        pkg_dir = tmp_path / "packages" / "core"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text('{"name":"core"}')
        (pkg_dir / "Cargo.toml").write_text("")
        result = find_ancestor_package_json(Path("packages/core/Cargo.toml"))
        assert result == Path("packages/core/package.json")

    def test_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "Cargo.toml").write_text("")
        assert find_ancestor_package_json(Path("Cargo.toml")) is None


class TestMainIntegration:
    def test_end_to_end_updates_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text(json.dumps({"version": "3.4.5"}))
        pkg_dir = tmp_path / "packages" / "core"
        pkg_dir.mkdir(parents=True)
        cargo = pkg_dir / "Cargo.toml"
        cargo.write_text('name = "core"\nversion = "0.0.0"\n')

        def fake_update(path: Path, key: str, value: str) -> None:
            assert key == "version"
            path.write_text('name = "core"\nversion = "3.4.5"\n')

        monkeypatch.setattr(update_version_files, "update_toml_file_key", fake_update)
        monkeypatch.setenv("VERSION_FILES", "packages/core/Cargo.toml:version")
        main()

        assert cargo.read_text() == 'name = "core"\nversion = "3.4.5"\n'

    def test_end_to_end_updates_nested_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text(json.dumps({"version": "3.4.5"}))
        cargo = tmp_path / "Cargo.toml"
        cargo.write_text('[package]\nversion = "0.0.0"\n')
        calls: list[tuple[Path, str, str]] = []

        def fake_update(path: Path, key: str, value: str) -> None:
            calls.append((path, key, value))
            path.write_text('[package]\nversion = "3.4.5"\n')

        monkeypatch.setattr(update_version_files, "update_toml_file_key", fake_update)
        monkeypatch.setenv("VERSION_FILES", "Cargo.toml:package.version")
        main()

        assert calls == [(Path("Cargo.toml"), "package.version", "3.4.5")]
        assert cargo.read_text() == '[package]\nversion = "3.4.5"\n'

    def test_multiple_entries(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text(json.dumps({"version": "1.2.3"}))

        a = tmp_path / "a.toml"
        b = tmp_path / "b.toml"
        a.write_text('version = "0.0.0"\n')
        b.write_text('version = "0.0.0"\n')

        def fake_update(path: Path, key: str, value: str) -> None:
            path.write_text(f'{key} = "{value}"\n')

        monkeypatch.setattr(update_version_files, "update_toml_file_key", fake_update)
        monkeypatch.setenv("VERSION_FILES", "a.toml:version\nb.toml:version")
        main()

        assert a.read_text() == 'version = "1.2.3"\n'
        assert b.read_text() == 'version = "1.2.3"\n'

    def test_missing_toml_file_errors(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("VERSION_FILES", "missing.toml:version")
        with pytest.raises(SystemExit):
            main()

    def test_missing_package_json_errors(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "Cargo.toml").write_text('version = "0.0.0"\n')
        monkeypatch.setenv("VERSION_FILES", "Cargo.toml:version")
        with pytest.raises(SystemExit):
            main()

    def test_missing_version_in_package_json_errors(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "Cargo.toml").write_text('version = "0.0.0"\n')
        monkeypatch.setenv("VERSION_FILES", "Cargo.toml:version")
        with pytest.raises(SystemExit):
            main()

    def test_empty_input_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("VERSION_FILES", "")
        main()
