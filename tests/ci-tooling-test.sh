#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from pathlib import Path

mise = Path(".mise.toml")
workflow = Path(".github/workflows/test.yml").read_text()

if not mise.exists():
    raise SystemExit("missing root .mise.toml")

mise_text = mise.read_text()
required_mise = [
    "[tools]",
    'uv = "latest"',
]
missing = [item for item in required_mise if item not in mise_text]
if missing:
    raise SystemExit(".mise.toml missing expected tool config:\n" + "\n".join(missing))

required_workflow = [
    "uses: ./mise-setup",
    "working-directory: .",
    "mise exec -- uvx pytest -v",
]
missing = [item for item in required_workflow if item not in workflow]
if missing:
    raise SystemExit("test workflow missing uvx/mise pytest wiring:\n" + "\n".join(missing))

for forbidden in ["pip install pytest", "run: pytest -v"]:
    if forbidden in workflow:
        raise SystemExit(f"test workflow still uses old pytest wiring: {forbidden}")
PY
