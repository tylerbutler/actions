import importlib.util
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location("trellis_workspace", Path(__file__).with_name("workspace.py"))
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)


def result(stdout, code=0):
    return subprocess.CompletedProcess([], code, stdout, "")


@pytest.mark.parametrize("entries", [[], [{"name": "a", "path": ".", "version": "1.0.0"}]])
def test_shapes_and_selection(tmp_path, monkeypatch, entries):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    monkeypatch.setenv("SINCE", "base;not shell")
    monkeypatch.setenv("RELEASABLE", "true")
    matrix = json.dumps({"include": entries})
    facts = "\n".join(f'{key}=["a"]' for key in workspace.FACTS)
    with patch.object(workspace, "invoke", side_effect=[result(matrix), result(facts)]) as run:
        workspace.workspace()
    assert run.call_args_list[0].args == (["ci", "matrix", "--since", "base;not shell", "--releasable"],)
    outputs = workspace.records((tmp_path / "out").read_text())
    assert outputs["matrix"] == matrix
    assert outputs["has_packages"] == str(bool(entries)).lower()
    assert all(outputs[key] == '["a"]' for key in workspace.FACTS)


@pytest.mark.parametrize("matrix", ["null", "[]", "{}", '{"include":[{}]}'])
def test_bad_matrix(matrix):
    with patch.object(workspace, "invoke", return_value=result(matrix)):
        with pytest.raises(ValueError):
            workspace.workspace()


def test_cli_failure():
    with patch.object(workspace, "invoke", return_value=result("{}", 3)):
        with pytest.raises(subprocess.CalledProcessError):
            workspace.workspace()


@pytest.mark.skipif(not os.environ.get("TRELLIS_TEST_BIN"), reason="controlled trellis integration")
def test_real_affected_lifecycle_and_subdirectory(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True)
    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    root = tmp_path / "sub"
    root.mkdir()
    (root / "gleam.toml").write_text(
        '[tools.trellis]\nmembers=["packages/*"]\n'
        '[tools.trellis.publish.lifecycle]\npackages={"packages/private"="workspace"}\n'
    )
    for name in ("core", "app", "private"):
        pkg = root / "packages" / name
        (pkg / "src").mkdir(parents=True)
        (pkg / "gleam.toml").write_text(f'name="{name}"\nversion="1.0.0"\n' +
                                      ('[dependencies]\ncore={path="../core"}\n' if name == "app" else ""))
        (pkg / "src" / f"{name}.gleam").write_text("pub fn demo() { 1 }\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD").stdout.strip()
    (root / "packages/core/src/core.gleam").write_text("pub fn demo() { 2 }\n")
    git("commit", "-qam", "change")
    monkeypatch.setenv("WORKING_DIRECTORY", str(root))
    binary = os.environ["TRELLIS_TEST_BIN"]
    def invoke(args):
        return subprocess.run([binary, *args], cwd=root, text=True, capture_output=True,
                              env={**os.environ, "CI": "true"})
    monkeypatch.setenv("SINCE", base)
    monkeypatch.setenv("RELEASABLE", "true")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    with patch.object(workspace, "invoke", side_effect=invoke):
        workspace.workspace()
    data = workspace.records((tmp_path / "out").read_text())
    assert {p["name"] for p in json.loads(data["matrix"])["include"]} == {"core", "app"}
    assert "private" in json.loads(data["packages"])
    monkeypatch.setenv("SINCE", "HEAD")
    (tmp_path / "out").write_text("")
    with patch.object(workspace, "invoke", side_effect=invoke):
        workspace.workspace()
    assert workspace.records((tmp_path / "out").read_text())["has_packages"] == "false"
