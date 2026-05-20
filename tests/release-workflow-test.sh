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
    "check-changelog:",
    "create-release-pr:",
    "tylerbutler/actions/changie-check@434af6fb683e908d5a2fab1b53849c2d54a86566",
    "marocchino/sticky-pull-request-comment@v2",
    "header: changie-check",
    "steps.check.outputs.needs-entry == 'true'",
    "tylerbutler/actions/changie-release@434af6fb683e908d5a2fab1b53849c2d54a86566",
    "post-batch-command: ${{ inputs.post-batch-command }}",
    "tag:",
    "contains(github.event.pull_request.labels.*.name, inputs.release-label)",
    "tylerbutler/actions/changie-auto-tag@434af6fb683e908d5a2fab1b53849c2d54a86566",
    "publish-hex:",
    "HEX_API_KEY: ${{ secrets.hex-api-key }}",
    "tylerbutler/actions/gleam-publish@434af6fb683e908d5a2fab1b53849c2d54a86566",
    "packages: ${{ steps.packages.outputs.packages }}",
    "publish-homebrew:",
    "APP_ID: ${{ secrets.homebrew-app-id }}",
    "PLAN: ${{ inputs.homebrew-dist-plan }}",
    "tylerbutler/actions/publish-homebrew-formula@434af6fb683e908d5a2fab1b53849c2d54a86566",
    "plan: ${{ inputs.homebrew-dist-plan }}",
]

missing = [item for item in required if item not in text]
if missing:
    raise SystemExit("release workflow missing expected content:\n" + "\n".join(missing))

for forbidden in ["homebrew-formula-path", "publish-to: crates", "publish-to: npm"]:
    if forbidden in text:
        raise SystemExit(f"release workflow contains forbidden stale content: {forbidden}")
PY
