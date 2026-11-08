import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from trellis import json_array, records
from gha import write_output


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
