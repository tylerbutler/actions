import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location("trellis_publish", Path(__file__).with_name("publish.py"))
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
import trellis_support as support


@pytest.mark.parametrize("package,tag,all_,valid", [
    ("a", "", "false", True), ("", "a-v1.0.0", "false", True), ("", "", "true", True),
    ("", "", "false", False), ("a", "a-v1.0.0", "false", False),
    ("a", "", "true", False), ("--bad", "", "false", False),
])
def test_selectors(monkeypatch, package, tag, all_, valid):
    for key, value in (("PACKAGE", package), ("TAG", tag), ("ALL_UNTAGGED", all_),
                       ("DRY_RUN", "true")):
        monkeypatch.setenv(key, value)
    with patch.object(publish, "invoke", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
        if valid:
            publish.publish()
            assert run.call_args.args[0][-1] == "--dry-run"
        else:
            with pytest.raises(ValueError):
                publish.publish()
            run.assert_not_called()


def test_key_and_failure(monkeypatch):
    monkeypatch.setenv("PACKAGE", "app")
    monkeypatch.delenv("HEXPM_API_KEY", raising=False)
    with pytest.raises(ValueError):
        publish.publish()
    monkeypatch.setenv("HEXPM_API_KEY", "test-key")
    with patch.object(publish, "invoke", return_value=subprocess.CompletedProcess([], 3, "", "")):
        with pytest.raises(subprocess.CalledProcessError):
            publish.publish()


@pytest.mark.skipif(not os.environ.get("TRELLIS_TEST_BIN"), reason="controlled trellis integration")
@pytest.mark.parametrize("bundle", [False, True])
def test_real_partial_retry_and_bundle(tmp_path, monkeypatch, bundle):
    support.workspace(tmp_path, bundle=bundle)
    fake = tmp_path / "fake-gleam"
    shutil.copyfile(Path(__file__).resolve().parent.parent / "tests/fixtures/trellis/fake_gleam.py", fake)
    fake.chmod(0o755)
    originals = {p: p.read_text() for p in tmp_path.glob("packages/*/gleam.toml")}
    monkeypatch.setenv("PACKAGE", "")
    monkeypatch.setenv("TAG", "")
    monkeypatch.setenv("ALL_UNTAGGED", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("HEXPM_API_KEY", "test-key")
    with support.api() as (url, versions, _):
        env = {"TRELLIS_GLEAM_BIN": str(fake), "TRELLIS_HEX_API_URL": url,
               "FAKE_HEX_URL": url, "FAKE_GLEAM_ROOT": str(tmp_path), "FAIL_PACKAGE": "app"}
        with patch.object(publish, "invoke", side_effect=lambda args: support.invoke(tmp_path, args, env)):
            with pytest.raises(subprocess.CalledProcessError):
                publish.publish()
            assert versions == {"core": ["1.0.0"]}
            assert all(p.read_text() == text for p, text in originals.items())
            publish.publish()
            assert versions == {"core": ["1.0.0"], "app": ["1.0.0"]}
            assert all(p.read_text() == text for p, text in originals.items())
            log = [json.loads(line) for line in (tmp_path / "gleam-log").read_text().splitlines()]
            assert len([item for item in log if item["name"] == "core" and item["args"][0] == "publish"]) == 1
            assert not any(item["name"] in ("tool", "private") for item in log)
            if bundle:
                assert any("src/private.gleam" in item["sources"] for item in log if item["name"] == "app")
            else:
                assert tomllib.loads((tmp_path / "published-app.toml").read_text())["dependencies"]["core"] == ">= 1.0.0 and < 2.0.0"
            before = (tmp_path / "gleam-log").read_text()
            monkeypatch.setenv("DRY_RUN", "true")
            publish.publish()
            assert (tmp_path / "gleam-log").read_text() == before
        for name in ("tool", "private"):
            invalid = support.invoke(tmp_path, ["publish", name, "--dry-run"], env)
            assert invalid.returncode != 0
