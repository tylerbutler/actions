#!/usr/bin/env bash
set -euo pipefail

workflow=".github/workflows/release.yml"

if [[ ! -f "$workflow" ]]; then
  echo "missing $workflow" >&2
  exit 1
fi

python3 - <<'PY'
from pathlib import Path
import re

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
    "marocchino/sticky-pull-request-comment",
    "header: changie-check",
    "steps.check.outputs.needs-entry == 'true'",
    "post-batch-command: ${{ inputs.post-batch-command }}",
    "tag:",
    "contains(github.event.pull_request.labels.*.name, inputs.release-label)",
    "publish-hex:",
    "HEX_API_KEY: ${{ secrets.hex-api-key }}",
    "packages: ${{ steps.packages.outputs.packages }}",
    "publish-homebrew:",
    "APP_ID: ${{ secrets.homebrew-app-id }}",
    "PLAN: ${{ inputs.homebrew-dist-plan }}",
    "plan: ${{ inputs.homebrew-dist-plan }}",
]

missing = [item for item in required if item not in text]
if missing:
    raise SystemExit("release workflow missing expected content:\n" + "\n".join(missing))

self_actions = [
    "changie-check",
    "changie-release",
    "changie-auto-tag",
    "gleam-publish",
    "publish-homebrew-formula",
]
missing_pinned_actions = []
for action in self_actions:
    pattern = re.compile(
        rf"uses:\s+tylerbutler/actions/{re.escape(action)}@[0-9a-f]{{40}}\s+"
        rf"#\s+ratchet:tylerbutler/actions/{re.escape(action)}@main"
    )
    if not pattern.search(text):
        missing_pinned_actions.append(f"tylerbutler/actions/{action}@<40-char-sha> # ratchet:...@main")

if missing_pinned_actions:
    raise SystemExit(
        "release workflow missing pinned self-action references:\n"
        + "\n".join(missing_pinned_actions)
    )

for forbidden in ["homebrew-formula-path", "publish-to: crates", "publish-to: npm"]:
    if forbidden in text:
        raise SystemExit(f"release workflow contains forbidden stale content: {forbidden}")
PY

python3 - <<'PY'
from pathlib import Path

readme = Path("README.md").read_text()
claude = Path("CLAUDE.md").read_text()

readme_required = [
    "### release",
    "tylerbutler/actions/.github/workflows/release.yml@main",
    "publish-to: hex",
    "publish-to: hex,homebrew",
    "homebrew-dist-plan:",
    "workspace-file: workspace.toml",
    "auto-tag.yml remains available",
]
missing = [item for item in readme_required if item not in readme]
if missing:
    raise SystemExit("README missing release workflow docs:\n" + "\n".join(missing))

claude_required = [
    "| `release.yml` | High-level release orchestrator",
    "`release.yml` is the high-level release orchestrator",
]
missing = [item for item in claude_required if item not in claude]
if missing:
    raise SystemExit("CLAUDE.md missing release workflow notes:\n" + "\n".join(missing))
PY
