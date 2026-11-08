import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from trellis import json_array, records
from gha import write_output
from trellis import authenticated_env
import subprocess
from unittest.mock import patch


def test_multiline_records():
    assert records("ok=true\npreview<<END\nhi=a\nhello<<world\nEND\n") == {
        "ok": "true", "preview": "hi=a\nhello<<world"
    }


@pytest.mark.parametrize("text", ["bad", "x=1\nx=2", "x<<EOF\nmissing", "x<<", "=value"])
def test_invalid_records(text):
    with pytest.raises(ValueError):
        records(text)


@pytest.mark.parametrize("value", ["{}", "null", "[1]", '["a",null]'])
def test_invalid_array(value):
    with pytest.raises(ValueError):
        json_array(value)


def test_collision_safe_output(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    write_output("preview", "a\nEOF_PREVIEW\nok=false")
    assert records((tmp_path / "out").read_text())["preview"] == "a\nEOF_PREVIEW\nok=false"


@pytest.mark.parametrize("origin", ["https://github.com/example/repo.git",
                                   "git@github.com:example/repo.git"])
def test_scoped_auth(monkeypatch, origin):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "test.existing")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "preserved")
    with patch("trellis.subprocess.run", return_value=subprocess.CompletedProcess([], 0, origin, "")):
        env = authenticated_env("secret")
    assert env["GITHUB_TOKEN"] == "secret"
    assert env["GIT_CONFIG_COUNT"] == "4"
    assert env["GIT_CONFIG_VALUE_0"] == "preserved"
    assert env["GIT_CONFIG_VALUE_2"] == ""
    assert env["GIT_CONFIG_KEY_3"] == "http.https://github.com/example/repo.git.extraheader"
    assert "secret" not in env["GIT_CONFIG_VALUE_1"]


@pytest.mark.parametrize("token", ["", "bad\nvalue", "two words"])
def test_auth_requires_token(token):
    with pytest.raises(ValueError):
        authenticated_env(token)


@pytest.mark.parametrize("origin", ["https://evil.invalid/a/b", "https://secret@github.com/a/b",
                                   "file:///tmp/repo"])
def test_auth_rejects_wrong_origin(origin):
    with patch("trellis.subprocess.run", return_value=subprocess.CompletedProcess([], 0, origin, "")):
        with pytest.raises(ValueError):
            authenticated_env("secret")
