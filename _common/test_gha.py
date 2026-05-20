import os
from pathlib import Path

from gha import write_output


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
