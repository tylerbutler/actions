import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
from gha import append_summary  # noqa: E402
from trellis import boolean, invoke, main, require_success  # noqa: E402


def publish() -> None:
    package = os.environ.get("PACKAGE", "")
    tag = os.environ.get("TAG", "")
    all_untagged = boolean("ALL_UNTAGGED")
    dry_run = boolean("DRY_RUN")
    if sum((bool(package), bool(tag), all_untagged)) != 1:
        raise ValueError("exactly one of package, tag, or all_untagged is required")
    if package.startswith("-") or tag.startswith("-"):
        raise ValueError("package and tag selectors must not start with '-'")
    if not dry_run and not os.environ.get("HEXPM_API_KEY"):
        raise ValueError("hex_api_key is required for publication")
    args = ["publish"]
    if package:
        args.append(package)
    elif tag:
        args += ["--tag", tag]
    else:
        args.append("--all-untagged")
    if dry_run:
        args.append("--dry-run")
    result = invoke(args)
    if result.stdout:
        sys.stdout.write(result.stdout)
    require_success(result)
    append_summary("Publication dry-run completed." if dry_run else "Hex publication completed.")


if __name__ == "__main__":
    main("Trellis publish", publish)
