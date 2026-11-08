import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
from gha import append_summary, write_output  # noqa: E402
from trellis import boolean, invoke, json_array, main, records, require_success  # noqa: E402

FACTS = ("packages", "releasable", "version_files", "tags", "series_tags")


def workspace() -> None:
    args = ["ci", "matrix"]
    if os.environ.get("SINCE"):
        args += ["--since", os.environ["SINCE"]]
    if boolean("RELEASABLE"):
        args += ["--releasable"]
    selected = invoke(args)
    require_success(selected)
    matrix = json.loads(selected.stdout)
    if not isinstance(matrix, dict) or not isinstance(matrix.get("include"), list):
        raise ValueError("trellis matrix must contain an include array")
    for package in matrix["include"]:
        if not isinstance(package, dict) or any(
            not isinstance(package.get(key), str) for key in ("name", "path", "version")
        ):
            raise ValueError("invalid trellis matrix entry")
    facts_result = invoke(["ci", "outputs"])
    require_success(facts_result)
    facts = records(facts_result.stdout)
    for key in FACTS:
        json_array(facts[key])
    write_output("matrix", selected.stdout.strip())
    write_output("has_packages", str(bool(matrix["include"])).lower())
    for key in FACTS:
        write_output(key, facts[key])
    append_summary(f"Selected {len(matrix['include'])} package(s). Workspace facts cover all members.")


if __name__ == "__main__":
    main("Trellis workspace", workspace)
