import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from gha import (
    append_summary,
    fail,
    parse_colon_entries,
    update_toml_file_key,
    update_toml_top_level_key,
    validate_toml_string_key_path,
    write_output,
)


def test_write_output_simple(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    write_output("version", "1.2.3")
    assert out.read_text() == "version=1.2.3\n"


def test_write_output_appends(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    out.write_text("existing=yes\n")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    write_output("version", "1.2.3")
    assert out.read_text() == "existing=yes\nversion=1.2.3\n"


def test_write_output_multiline_uses_heredoc(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    write_output("changelog", "line one\nline two")
    text = out.read_text()
    assert text.startswith("changelog<<EOF_CHANGELOG\n")
    assert "line one\nline two\n" in text
    assert text.endswith("EOF_CHANGELOG\n")


def test_write_output_no_env_writes_stdout(capsys, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    write_output("version", "1.2.3")
    assert capsys.readouterr().out == "version=1.2.3\n"


def test_write_output_key_sanitised_for_sentinel(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    write_output("pr-url", "a\nb")
    assert "pr-url<<EOF_PR_URL\n" in out.read_text()


def test_fail_exits_one_by_default(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        fail("kaboom")
    assert exc.value.code == 1
    assert "::error::kaboom" in capsys.readouterr().err


def test_fail_custom_code(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        fail("nope", code=2)
    assert exc.value.code == 2


def test_append_summary_writes_with_newline(tmp_path: Path, monkeypatch) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    append_summary("## Heading")
    append_summary("body line")
    assert summary.read_text() == "## Heading\nbody line\n"


def test_append_summary_no_env_is_noop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    append_summary("ignored")  # must not raise


def test_update_toml_top_level_string_value() -> None:
    content = 'name = "pkg"\nversion = "1.0.0"\n\n[dependencies]\nfoo = "0.1"\n'
    out = update_toml_top_level_key(content, "version", "2.0.0")
    assert 'version = "2.0.0"' in out
    assert out.endswith('[dependencies]\nfoo = "0.1"\n')


def test_update_toml_preserves_quoting_style() -> None:
    content = 'version    =    "1.0.0"\n'
    out = update_toml_top_level_key(content, "version", "1.1.0")
    assert out == 'version    =    "1.1.0"\n'


def test_update_toml_only_touches_top_level() -> None:
    content = (
        'version = "1.0.0"\n'
        "\n"
        "[dependencies]\n"
        'other = "1.0.0"\n'
    )
    out = update_toml_top_level_key(content, "version", "2.0.0")
    assert out.count('"2.0.0"') == 1
    assert 'other = "1.0.0"' in out


def test_update_toml_missing_key_raises() -> None:
    with pytest.raises(KeyError):
        update_toml_top_level_key('name = "pkg"\n', "version", "1.0.0")


def test_update_toml_non_string_value_raises() -> None:
    with pytest.raises(TypeError):
        update_toml_top_level_key("version = 1\n", "version", "2")


def test_update_toml_invalid_input_raises() -> None:
    with pytest.raises(tomllib.TOMLDecodeError):
        update_toml_top_level_key("not = valid = toml", "x", "y")


def test_validate_toml_string_key_path_top_level() -> None:
    validate_toml_string_key_path('version = "1.0.0"\n', "version")


def test_validate_toml_string_key_path_nested() -> None:
    content = '[package]\nversion = "1.0.0"\n'
    validate_toml_string_key_path(content, "package.version")


def test_validate_toml_string_key_path_deeply_nested() -> None:
    content = '[tool.poetry]\nversion = "1.0.0"\n'
    validate_toml_string_key_path(content, "tool.poetry.version")


def test_validate_toml_string_key_path_missing_raises() -> None:
    with pytest.raises(KeyError):
        validate_toml_string_key_path('[package]\nname = "pkg"\n', "package.version")


def test_validate_toml_string_key_path_non_string_raises() -> None:
    with pytest.raises(TypeError):
        validate_toml_string_key_path("[package]\nversion = 1\n", "package.version")


def test_validate_toml_string_key_path_empty_component_raises() -> None:
    with pytest.raises(ValueError):
        validate_toml_string_key_path('[package]\nversion = "1.0.0"\n', "package.")


def test_update_toml_file_key_invokes_toml_cli(tmp_path: Path, monkeypatch) -> None:
    toml = tmp_path / "Cargo.toml"
    toml.write_text('[package]\nversion = "0.1.0"\n', encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(cmd, *, capture_output, text, check):
        calls.append(cmd)
        assert capture_output is True
        assert text is True
        assert check is True
        toml.write_text('[package]\nversion = "1.2.3"\n', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    update_toml_file_key(toml, "package.version", "1.2.3")

    assert calls == [["toml", "set", "package.version", "1.2.3", "--toml-path", str(toml)]]


def test_update_toml_file_key_preserves_missing_key_failure(tmp_path: Path, monkeypatch) -> None:
    toml = tmp_path / "Cargo.toml"
    toml.write_text('[package]\nname = "pkg"\n', encoding="utf-8")

    def fake_run(*args, **kwargs):
        raise AssertionError("toml-cli should not run when validation fails")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(KeyError):
        update_toml_file_key(toml, "package.version", "1.2.3")


def test_update_toml_file_key_surfaces_toml_cli_failure(tmp_path: Path, monkeypatch) -> None:
    toml = tmp_path / "Cargo.toml"
    toml.write_text('[package]\nversion = "0.1.0"\n', encoding="utf-8")

    def fake_run(cmd, *, capture_output, text, check):
        raise subprocess.CalledProcessError(1, cmd, stderr="bad key")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="bad key"):
        update_toml_file_key(toml, "package.version", "1.2.3")


def test_parse_colon_entries_two_fields() -> None:
    text = "gleam.toml:version\npackages/foo/gleam.toml:version\n"
    result = parse_colon_entries(text, fields=2)
    assert result == [
        ("gleam.toml", "version"),
        ("packages/foo/gleam.toml", "version"),
    ]


def test_parse_colon_entries_three_fields() -> None:
    text = "vestibule:gleam.toml:version\n"
    result = parse_colon_entries(text, fields=3)
    assert result == [("vestibule", "gleam.toml", "version")]


def test_parse_colon_entries_skips_blank_and_comments() -> None:
    text = "\n# a comment\n  \nfoo:bar\n"
    assert parse_colon_entries(text, fields=2) == [("foo", "bar")]


def test_parse_colon_entries_strips_whitespace() -> None:
    text = "  foo  :  bar  \n"
    assert parse_colon_entries(text, fields=2) == [("foo", "bar")]


def test_parse_colon_entries_wrong_field_count_raises() -> None:
    with pytest.raises(ValueError, match="expected 2 fields"):
        parse_colon_entries("a:b:c\n", fields=2)
