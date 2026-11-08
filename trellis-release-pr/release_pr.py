import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
from gha import append_summary  # noqa: E402
from trellis import authenticated_env, invoke, main, records, require_success  # noqa: E402


def prepare() -> None:
    args = ["release", "pr", "--base", os.environ.get("BASE", "main"),
            "--branch", os.environ.get("BRANCH", "release/pending"), "--github-output"]
    pre = os.environ.get("PRE", "").strip()
    if pre:
        args += ["--pre", pre]
    for flag in ("set", "bump"):
        for value in os.environ.get(flag.upper(), "").splitlines():
            if value.strip():
                args += [f"--{flag}", value.strip()]
    result = invoke(args, env=authenticated_env(os.environ.get("TOKEN", "")))
    require_success(result)
    outputs = records(result.stdout)
    if outputs.get("outcome") not in ("prepared", "unchanged", "no_changes"):
        raise ValueError("missing or invalid trellis preparation outcome")
    append_summary(f"Preparation outcome: `{outputs['outcome']}`.")


if __name__ == "__main__":
    main("Trellis release PR", prepare)
