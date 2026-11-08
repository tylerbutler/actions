import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
from gha import append_summary  # noqa: E402
from trellis import authenticated_env, boolean, invoke, main, require_success  # noqa: E402


def tag() -> None:
    args = ["tag", "create"]
    push = boolean("PUSH")
    release = boolean("GITHUB_RELEASE")
    dry_run = boolean("DRY_RUN")
    for enabled, flag in ((push, "--push"), (release, "--github-release"), (dry_run, "--dry-run")):
        if enabled:
            args.append(flag)
    env = authenticated_env(os.environ.get("TOKEN", "")) if push or release else None
    result = invoke(args, env=env)
    if result.stdout:
        sys.stdout.write(result.stdout)
    require_success(result)
    append_summary("Tag dry-run completed." if dry_run else "Tag reconciliation completed.")


if __name__ == "__main__":
    main("Trellis tag", tag)
