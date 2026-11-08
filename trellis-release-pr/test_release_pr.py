import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location("release_pr", Path(__file__).with_name("release_pr.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize("pre", ["", "rc", "none"])
@pytest.mark.parametrize("outcome", ["prepared", "unchanged", "no_changes"])
def test_overrides_and_noop(monkeypatch, pre, outcome):
    monkeypatch.setenv("PRE", pre)
    monkeypatch.setenv("SET", "a=1.3.0\n\nb=$(touch bad)\n")
    monkeypatch.setenv("BUMP", "a=minor\n")
    monkeypatch.setenv("TOKEN", "secret")
    with patch.object(release, "authenticated_env", return_value={"GITHUB_TOKEN": "secret"}) as auth, \
         patch.object(release, "invoke", return_value=subprocess.CompletedProcess(
             [], 0, f"outcome={outcome}\n", "")) as run:
        release.prepare()
    args = run.call_args.args[0]
    assert args[-6:] == ["--set", "a=1.3.0", "--set", "b=$(touch bad)", "--bump", "a=minor"]
    assert ("--pre" in args) == bool(pre)
    if pre:
        assert args[args.index("--pre") + 1] == pre
    auth.assert_called_once_with("secret")


@pytest.mark.parametrize("code,output", [(3, ""), (1, ""), (0, ""), (0, "outcome=bad")])
def test_failure(code, output):
    with patch.object(release, "authenticated_env", return_value={}), \
         patch.object(release, "invoke", return_value=subprocess.CompletedProcess([], code, output, "")):
        with pytest.raises((ValueError, subprocess.CalledProcessError)):
            release.prepare()
