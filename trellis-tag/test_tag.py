import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location("trellis_tag", Path(__file__).with_name("tag.py"))
tag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tag)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
import trellis_support as support


@pytest.mark.parametrize("push,release,dry", [("false","false","false"), ("true","false","true"),
                                           ("false","true","false")])
def test_flags(monkeypatch, push, release, dry):
    for key, value in (("PUSH", push), ("GITHUB_RELEASE", release), ("DRY_RUN", dry)):
        monkeypatch.setenv(key, value)
    with patch.object(tag, "authenticated_env", return_value={}) as auth, \
         patch.object(tag, "invoke", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
        tag.tag()
    args = run.call_args.args[0]
    assert ("--push" in args) == (push == "true")
    assert ("--github-release" in args) == (release == "true")
    assert ("--dry-run" in args) == (dry == "true")
    assert bool(auth.call_count) == (push == "true" or release == "true")


def test_failure():
    with patch.object(tag, "invoke", return_value=subprocess.CompletedProcess([], 3, "", "")):
        with pytest.raises(subprocess.CalledProcessError):
            tag.tag()


@pytest.mark.skipif(not os.environ.get("TRELLIS_TEST_BIN"), reason="controlled trellis integration")
def test_candidate_promotion_and_remote_retry(tmp_path, monkeypatch):
    support.workspace(tmp_path)
    remote = tmp_path / "origin.git"
    support.git(tmp_path, "init", "--bare", "-q", str(remote))
    support.git(tmp_path, "remote", "add", "origin", str(remote))
    support.git(tmp_path, "push", "-q", "origin", "main")
    monkeypatch.setenv("PUSH", "true")
    monkeypatch.setenv("GITHUB_RELEASE", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    with support.api() as (url, _, requests):
        env = {"TRELLIS_GITHUB_API_URL": url, "TRELLIS_GITHUB_REPO": "example/repo",
               "GITHUB_TOKEN": "test-token"}
        with patch.object(tag, "authenticated_env", return_value=env), \
             patch.object(tag, "invoke", side_effect=lambda args, env=None: support.invoke(tmp_path, args, env)):
            tag.tag()
            stable = support.git(tmp_path, "rev-parse", "core-v1.0")
            manifest = tmp_path / "packages/core/gleam.toml"
            manifest.write_text(manifest.read_text().replace("1.0.0", "1.1.0-rc.0"))
            (manifest.parent / "CHANGELOG.md").write_text("## v1.1.0-rc.0\n\n- candidate\n")
            support.git(tmp_path, "commit", "-qam", "candidate")
            tag.tag()
            tag.tag()
            assert support.git(tmp_path, "rev-parse", "core-v1.0") == stable
            assert [r for r in requests if r["tag_name"] == "core-v1.1.0-rc.0"] == [{
                "tag_name": "core-v1.1.0-rc.0", "name": "core-v1.1.0-rc.0",
                "body": "- candidate", "prerelease": True
            }]
            manifest.write_text(manifest.read_text().replace("1.1.0-rc.0", "1.1.0"))
            (manifest.parent / "CHANGELOG.md").write_text("## v1.1.0\n\n- stable\n")
            support.git(tmp_path, "commit", "-qam", "promotion")
            tag.tag()
            assert support.git(tmp_path, "rev-parse", "core-v1.1^{}") == support.git(tmp_path, "rev-parse", "HEAD")
            assert requests[-1]["prerelease"] is False
            assert not any(r["tag_name"].startswith("private-") for r in requests)
