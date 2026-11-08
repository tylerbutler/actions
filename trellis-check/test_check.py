import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location("trellis_check", Path(__file__).with_name("check.py"))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
import trellis_support as support

HEALTHY = ("ok=true\nstrictness=error\nhas_entries=false\nneeds_entry=false\n"
           "needs_entry_packages=[]\ninvalid_fragments=[]\npreview<<END\nPreview\nEND\n")


@pytest.mark.parametrize("doctor_code,changelog_code,outputs", [
    (0, 0, HEALTHY), (1, 0, HEALTHY), (0, 1, HEALTHY.replace("ok=true", "ok=false")),
    (0, 0, ""), (0, 0, HEALTHY.replace("ok=true", "ok=unknown")),
    (0, 3, ""),
])
def test_both_reports(tmp_path, monkeypatch, doctor_code, changelog_code, outputs):
    monkeypatch.setenv("BASE", "base;data")
    monkeypatch.setenv("HEAD", "head")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    with patch.object(check, "invoke", side_effect=[
        subprocess.CompletedProcess([], doctor_code, "::warning::finding\n", ""),
        subprocess.CompletedProcess([], changelog_code, outputs, ""),
    ]) as run:
        if doctor_code or changelog_code or outputs != HEALTHY:
            with pytest.raises((ValueError, subprocess.CalledProcessError)):
                check.check()
        else:
            check.check()
    assert run.call_count == 2
    assert run.call_args.args[0][3] == "base;data"
    summary = (tmp_path / "summary").read_text()
    assert "Doctor:" in summary and "Changelog:" in summary


def test_doctor_only(monkeypatch):
    monkeypatch.setenv("CHECK_CHANGELOG", "false")
    with patch.object(check, "invoke", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
        check.check()
    run.assert_called_once_with(["doctor", "--format", "github"])


def test_startup_failure_still_reports_changelog(monkeypatch):
    monkeypatch.setenv("BASE", "main")
    monkeypatch.setenv("HEAD", "HEAD")
    with patch.object(check, "invoke", side_effect=[FileNotFoundError("trellis"),
                                                   subprocess.CompletedProcess([], 0, HEALTHY, "")]) as run:
        with pytest.raises(subprocess.CalledProcessError) as error:
            check.check()
    assert error.value.returncode == 127 and run.call_count == 2


@pytest.mark.skipif(not os.environ.get("TRELLIS_TEST_BIN"), reason="controlled trellis integration")
def test_real_missing_malformed_and_healthy(tmp_path):
    support.workspace(tmp_path)
    base = support.git(tmp_path, "rev-parse", "HEAD")
    source = tmp_path / "packages/core/src/core.gleam"
    source.write_text("pub fn demo() { 2 }\n")
    support.git(tmp_path, "commit", "-qam", "change")
    args = ["changelog", "check", "--base", base, "--head", "HEAD", "--format", "github"]
    missing = support.invoke(tmp_path, args)
    assert missing.returncode == 1 and "needs_entry=true" in missing.stdout
    fragment = tmp_path / ".changes/unreleased/change.toml"
    fragment.parent.mkdir(parents=True)
    fragment.write_text("this = [invalid\n")
    support.git(tmp_path, "add", ".changes")
    support.git(tmp_path, "commit", "-qm", "malformed")
    malformed = support.invoke(tmp_path, args)
    assert malformed.returncode == 1 and "invalid_fragments=[]" not in malformed.stdout
    fragment.write_text('package="core"\nkind="Fixed"\nbody="Fix demo"\n')
    support.git(tmp_path, "commit", "-qam", "healthy")
    healthy = support.invoke(tmp_path, args)
    assert healthy.returncode == 0 and "ok=true" in healthy.stdout, healthy.stderr
