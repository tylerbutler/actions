#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import re
from pathlib import Path
readme = Path("README.md").read_text()
new_docs = readme.split("### setup-trellis", 1)[1].split("### setup-licence-audit", 1)[0]
for line in new_docs.splitlines():
    if re.match(r"\s*(?:-\s*)?uses:", line):
        assert re.search(r"@[0-9a-f]{40}\s+# ratchet:", line), line
for required in ("#### Metadata and matrix: before", "**After:**",
                 "#### Tasks: before", "#### Tasks: after",
                 "#### Publishing: before", "#### Publishing: after",
                 "trellis exec --serial -- gleam check", "trellis run test",
                 "JSON arrays", "source bundles", "trellis/release_request"):
    assert required in new_docs, required
for action in ("read-gleam-workspace", "run-gleam-workspace", "gleam-publish"):
    text = Path(action, "action.yml").read_text()
    assert "Legacy" in text and "runs:" in text
    assert not re.search(r"uses: .*trellis", text), action
print("trellis documentation: pins, migration examples, and legacy entry points passed")
PY
