"""Execute workflow snippets with controlled inputs and fake task processes."""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

text = Path(".github/workflows/gleam-workspace-ci.yml").read_text()
defaults = dict(TRELLIS_VERSION="", SINCE="", TASK="", WITH_CHECKS="false", CHECK="false",
                CHANGELOG="false", BASE="", HEAD="", WORKSPACE_FILE="workspace.toml", CUSTOM_COMMAND="")


def script(name):
    section = re.search(rf"# script: {name}\n(.*?)# end-script", text, re.S)[1]
    return re.search(r"python3 - <<'PY'\n(.*?)^\s+PY\s*$", section, re.S | re.M)[1]


def run(name, env):
    import textwrap
    return subprocess.run([sys.executable, "-c", textwrap.dedent(script(name))],
                          env={**os.environ, **defaults, **env}, text=True, capture_output=True)


assert run("validate-mode", {}).returncode == 0
assert run("validate-mode", {"TRELLIS_VERSION": "1.3.0", "TASK": "ci", "WORKSPACE_FILE": ""}).returncode == 0
for env in ({"TASK": "ci"}, {"SINCE": "base"}, {"TRELLIS_VERSION": "1.3.0", "WORKSPACE_FILE": "other.toml"},
            {"TRELLIS_VERSION": "1.3.0", "TASK": "ci", "CUSTOM_COMMAND": "echo other"},
            {"TRELLIS_VERSION": "1.3.0", "CHANGELOG": "true"}):
    assert run("validate-mode", env).returncode != 0
assert run("validate-mode", {"TRELLIS_VERSION": "1.3.0", "CHECK": "true", "CHANGELOG": "true",
                              "BASE": "base", "HEAD": "head"}).returncode == 0
package = {"name": "demo", "path": "packages/demo", "version": "1.0.0"}
with tempfile.TemporaryDirectory() as directory:
    out = Path(directory) / "out"
    for mode, packages, task, both in (("", [package], "", "false"), ("1.3.0", [package], "", "false"),
                                      ("1.3.0", [], "", "false"), ("1.3.0", [package], "ci", "false"),
                                      ("1.3.0", [package], "ci", "true")):
        out.write_text("")
        result = run("select-matrix", dict(TRELLIS_VERSION=mode, TASK=task, WITH_CHECKS=both,
            LEGACY_PACKAGES=json.dumps(packages), TRELLIS_MATRIX=json.dumps({"include": packages}),
            GITHUB_OUTPUT=str(out)))
        assert result.returncode == 0, result.stderr
        outputs = dict(line.split("=", 1) for line in out.read_text().splitlines())
        assert json.loads(outputs["matrix"]) == {"package": packages}
        assert outputs["has_packages"] == str(bool(packages)).lower()
        assert outputs["run_checks"] == str(not task or both == "true").lower()
    binary = Path(directory) / "trellis"
    binary.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$TASK_LOG\"\nexit 7\n")
    binary.chmod(0o755)
    result = run("run-task", {"PATH": directory + os.pathsep + os.environ["PATH"], "TASK": "custom;data",
                             "PACKAGE": "demo", "TASK_LOG": str(Path(directory) / "log")})
    assert result.returncode != 0
    assert (Path(directory) / "log").read_text().splitlines() == ["run", "custom;data", "demo"]
assert "if: needs.discover.outputs.has-packages == 'true'" in text
assert "working-directory: ${{ inputs.working-directory }}" in text
assert text.count("version: ${{ inputs.trellis_version }}") == 3
assert "permissions:\n  contents: read" in text
for option in ("format-check", "check", "build-strict", "test", "test-js", "docs"):
    assert f"if: needs.discover.outputs.run-checks == 'true' && inputs.{option}" in text
print("Gleam workspace CI: legacy, trellis, empty/task selection, and failure checks passed")
