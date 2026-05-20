#!/usr/bin/env bash
set -euo pipefail

workflow=".github/workflows/release.yml"

if [[ ! -f "$workflow" ]]; then
  echo "missing $workflow" >&2
  exit 1
fi

python3 - <<'PY'
from pathlib import Path

text = Path(".github/workflows/release.yml").read_text()

required = [
    "name: Release",
    "workflow_call:",
    "publish-to:",
    "homebrew-dist-plan:",
    "homebrew-artifact-pattern:",
    "homebrew-install-linuxbrew:",
    "hex-api-key:",
    "homebrew-app-id:",
    "homebrew-app-private-key:",
    "jobs:",
    "validate:",
    "publish-hex: ${{ steps.validate.outputs.publish-hex }}",
    "publish-homebrew: ${{ steps.validate.outputs.publish-homebrew }}",
    "unknown publish target",
    "case \"$target\" in",
    "hex)",
    "homebrew)",
]

missing = [item for item in required if item not in text]
if missing:
    raise SystemExit("release workflow missing expected content:\n" + "\n".join(missing))

for forbidden in ["homebrew-formula-path", "publish-to: crates", "publish-to: npm"]:
    if forbidden in text:
        raise SystemExit(f"release workflow contains forbidden stale content: {forbidden}")
PY
