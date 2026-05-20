# Cluster C Release Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `.github/workflows/release.yml`, a reusable release orchestrator that checks changie entries on PRs, creates changie release PRs, auto-tags merged release PRs, and publishes tag releases to Hex/Homebrew.

**Architecture:** The new workflow is a thin orchestrator around existing actions: `changie-check`, `changie-release`, `changie-auto-tag`, `read-gleam-workspace`, `gleam-publish`, and `publish-homebrew-formula`. It gates jobs from caller event context, validates requested publish targets up front, and keeps `.github/workflows/auto-tag.yml` available as the lower-level reusable workflow. Tests use existing bash integration infrastructure and textual workflow assertions rather than adding a new YAML lint dependency.

**Tech Stack:** GitHub Actions reusable workflows, bash, Python 3 stdlib for test assertions, changie composite actions, Gleam Hex publish action, cargo-dist Homebrew publish action.

**Spec:** `docs/superpowers/specs/2026-05-20-cluster-c-release-workflow-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `.github/workflows/release.yml` | New reusable workflow with validation, PR changelog check/comment, release PR creation, auto-tag, Hex publish, and Homebrew publish jobs. |
| `tests/release-workflow-test.sh` | Bash/Python integration test that asserts the workflow contract, target validation script, gated jobs, and action wiring are present. |
| `.github/workflows/test.yml` | No structural change needed if the new script matches `tests/*-test.sh`; CI will pick it up automatically. |
| `README.md` | User-facing documentation for `release.yml` examples and inputs. |
| `CLAUDE.md` | Internal repo overview update adding `release.yml` as the high-level release workflow. |

---

## Task 1: Add release workflow shell and validation job

**Files:**
- Create: `.github/workflows/release.yml`
- Create: `tests/release-workflow-test.sh`

- [ ] **Step 1: Write the failing test**

Create `tests/release-workflow-test.sh`:

```bash
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash tests/release-workflow-test.sh`

Expected: FAIL with `missing .github/workflows/release.yml`.

- [ ] **Step 3: Add the workflow shell and validation job**

Create `.github/workflows/release.yml`:

```yaml
name: Release

on:
  workflow_call:
    inputs:
      publish-to:
        description: 'Comma-separated publish targets. Supported: hex, homebrew.'
        required: false
        type: string
        default: ''
      working-directory:
        description: 'Directory containing .changie.yaml and release metadata'
        required: false
        type: string
        default: '.'
      changie-version:
        description: 'Changie CLI version to install'
        required: false
        type: string
        default: 'latest'
      projects:
        description: 'Comma-separated changie project keys'
        required: false
        type: string
        default: ''
      workspace-file:
        description: 'Path to workspace.toml, relative to working-directory. Overrides projects when set.'
        required: false
        type: string
        default: ''
      version:
        description: 'Version to batch: auto, major, minor, patch, or explicit semver. Ignored when projects is set.'
        required: false
        type: string
        default: 'auto'
      version-files:
        description: 'Version files forwarded to changie-release'
        required: false
        type: string
        default: ''
      post-batch-command:
        description: 'Command to run after changie batch and version bumps'
        required: false
        type: string
        default: ''
      release-label:
        description: 'Label identifying release PRs for tag creation'
        required: false
        type: string
        default: 'release'
      labels:
        description: 'Labels applied to release PRs created by changie-release'
        required: false
        type: string
        default: 'release'
      pr-title-template:
        description: 'Release PR title template'
        required: false
        type: string
        default: 'Release {version}'
      branch-template:
        description: 'Release PR branch template'
        required: false
        type: string
        default: 'release/next'
      commit-message-template:
        description: 'Release commit message template'
        required: false
        type: string
        default: 'chore(release): {version}'
      pr-body-template:
        description: 'Release PR body template'
        required: false
        type: string
        default: '{changelog}'
      check-changelog:
        description: 'Run changie-check on pull requests'
        required: false
        type: boolean
        default: true
      require-for-types:
        description: 'Comma-separated conventional commit types that require a changelog entry'
        required: false
        type: string
        default: 'feat,fix,refactor,security'
      create-release:
        description: 'Create GitHub Releases from created tags'
        required: false
        type: boolean
        default: false
      wait-for-publish:
        description: 'Wait for downstream publish workflow after each pushed tag'
        required: false
        type: boolean
        default: false
      publish-workflow-name:
        description: 'Workflow name to wait for when wait-for-publish is true'
        required: false
        type: string
        default: 'Publish'
      hex-packages:
        description: 'Space-separated package paths for gleam-publish. workspace-file output is used when this is empty.'
        required: false
        type: string
        default: ''
      hex-replace-path-deps:
        description: 'replace-path-deps forwarded to gleam-publish'
        required: false
        type: string
        default: ''
      hex-skip-already-published:
        description: 'Skip Hex versions that are already published'
        required: false
        type: boolean
        default: true
      homebrew-tap-repo:
        description: 'Homebrew tap repo in owner/repo form'
        required: false
        type: string
        default: ''
      homebrew-dist-plan:
        description: 'cargo-dist plan JSON for publish-homebrew-formula'
        required: false
        type: string
        default: ''
      homebrew-artifact-pattern:
        description: 'Artifact pattern forwarded to publish-homebrew-formula'
        required: false
        type: string
        default: 'artifacts-*'
      homebrew-install-linuxbrew:
        description: 'Install Linuxbrew and run brew style --fix before committing formula files'
        required: false
        type: boolean
        default: true
    outputs:
      version:
        description: 'Version(s) resolved by changie-auto-tag'
        value: ${{ jobs.tag.outputs.version }}
      tag:
        description: 'Tag(s) resolved by changie-auto-tag'
        value: ${{ jobs.tag.outputs.tag }}
      created-tags:
        description: 'Space-separated tags created by changie-auto-tag'
        value: ${{ jobs.tag.outputs.created-tags }}
    secrets:
      hex-api-key:
        description: 'Hex.pm API key'
        required: false
      app-id:
        description: 'GitHub App ID for release PR/tag token generation'
        required: false
      app-private-key:
        description: 'GitHub App private key for release PR/tag token generation'
        required: false
      homebrew-app-id:
        description: 'GitHub App ID for Homebrew tap publishing'
        required: false
      homebrew-app-private-key:
        description: 'GitHub App private key for Homebrew tap publishing'
        required: false

permissions:
  contents: write
  pull-requests: write
  actions: read

jobs:
  validate:
    runs-on: ubuntu-latest
    outputs:
      publish-hex: ${{ steps.validate.outputs.publish-hex }}
      publish-homebrew: ${{ steps.validate.outputs.publish-homebrew }}
      publish-targets: ${{ steps.validate.outputs.publish-targets }}
    steps:
      - name: Validate release workflow inputs
        id: validate
        shell: bash
        env:
          PUBLISH_TO: ${{ inputs.publish-to }}
        run: |
          set -euo pipefail

          publish_hex=false
          publish_homebrew=false
          normalized=""

          IFS=',' read -ra targets <<< "$PUBLISH_TO"
          for raw_target in "${targets[@]}"; do
            target="$(echo "$raw_target" | xargs)"
            if [[ -z "$target" ]]; then
              continue
            fi

            case "$target" in
              hex)
                publish_hex=true
                ;;
              homebrew)
                publish_homebrew=true
                ;;
              *)
                echo "::error::unknown publish target '$target'. Supported targets: hex, homebrew"
                exit 1
                ;;
            esac

            normalized="${normalized:+$normalized,}$target"
          done

          {
            echo "publish-hex=$publish_hex"
            echo "publish-homebrew=$publish_homebrew"
            echo "publish-targets=$normalized"
          } >> "$GITHUB_OUTPUT"

          {
            echo "## Release workflow"
            echo
            if [[ -n "$normalized" ]]; then
              echo "Validated publish targets: $normalized."
            else
              echo "No publish targets requested."
            fi
          } >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash tests/release-workflow-test.sh`

Expected: PASS with no output.

- [ ] **Step 5: Commit**

```bash
chmod +x tests/release-workflow-test.sh
git add .github/workflows/release.yml tests/release-workflow-test.sh
git commit -m "feat: add release workflow validation"
```

---

## Task 2: Add PR changelog check/comment and release PR creation jobs

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `tests/release-workflow-test.sh`

- [ ] **Step 1: Extend the failing test**

Add these strings to the Python `required = [...]` list in `tests/release-workflow-test.sh`:

```python
    "check-changelog:",
    "create-release-pr:",
    "tylerbutler/actions/changie-check@434af6fb683e908d5a2fab1b53849c2d54a86566",
    "marocchino/sticky-pull-request-comment@v2",
    "header: changie-check",
    "steps.check.outputs.needs-entry == 'true'",
    "tylerbutler/actions/changie-release@434af6fb683e908d5a2fab1b53849c2d54a86566",
    "post-batch-command: ${{ inputs.post-batch-command }}",
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash tests/release-workflow-test.sh`

Expected: FAIL listing missing `create-release-pr`, `changie-check`, sticky comment, and `changie-release` content.

- [ ] **Step 3: Add `create-release-pr` input**

In `.github/workflows/release.yml`, add this input after `check-changelog`:

```yaml
      create-release-pr:
        description: 'Create or update the changie release PR on default-branch pushes'
        required: false
        type: boolean
        default: true
```

- [ ] **Step 4: Add PR check job**

Append this job after `validate`:

```yaml
  check:
    needs: validate
    if: github.event_name == 'pull_request' && github.event.action != 'closed' && inputs.check-changelog
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # ratchet:actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Read workspace
        if: inputs.workspace-file != ''
        id: workspace
        uses: tylerbutler/actions/read-gleam-workspace@434af6fb683e908d5a2fab1b53849c2d54a86566 # ratchet:tylerbutler/actions/read-gleam-workspace@main
        with:
          working-directory: ${{ inputs.working-directory }}
          workspace-file: ${{ inputs.workspace-file }}

      - name: Check changie entries
        id: check
        uses: tylerbutler/actions/changie-check@434af6fb683e908d5a2fab1b53849c2d54a86566 # ratchet:tylerbutler/actions/changie-check@main
        with:
          changie-version: ${{ inputs.changie-version }}
          working-directory: ${{ inputs.working-directory }}
          base-sha: ${{ github.event.pull_request.base.sha }}
          head-sha: ${{ github.event.pull_request.head.sha }}
          projects: ${{ steps.workspace.outputs.projects || inputs.projects }}
          require-for-types: ${{ inputs.require-for-types }}

      - name: Build changie comment
        id: comment
        if: steps.check.outputs.has-entries == 'true' || steps.check.outputs.needs-entry == 'true'
        shell: bash
        env:
          HAS_ENTRIES: ${{ steps.check.outputs.has-entries }}
          PREVIEW: ${{ steps.check.outputs.preview }}
          NEEDS_ENTRY: ${{ steps.check.outputs.needs-entry }}
          COMMIT_TYPES_FOUND: ${{ steps.check.outputs.commit-types-found }}
        run: |
          set -euo pipefail

          if [[ "$HAS_ENTRIES" == "true" ]]; then
            message="$PREVIEW"
          elif [[ "$NEEDS_ENTRY" == "true" ]]; then
            message="This PR appears to need a changelog entry. Commit types found: ${COMMIT_TYPES_FOUND:-unknown}."
          else
            message=""
          fi

          {
            echo "message<<EOF_MESSAGE"
            echo "$message"
            echo "EOF_MESSAGE"
          } >> "$GITHUB_OUTPUT"

      - name: Comment on PR
        if: steps.comment.outputs.message != ''
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          header: changie-check
          message: ${{ steps.comment.outputs.message }}

      - name: Fail when changelog entry is required
        if: steps.check.outputs.needs-entry == 'true'
        shell: bash
        run: |
          echo "::error::This PR needs a changelog entry."
          exit 1

      - name: Summarize changie check
        if: always()
        shell: bash
        env:
          HAS_ENTRIES: ${{ steps.check.outputs.has-entries }}
          NEEDS_ENTRY: ${{ steps.check.outputs.needs-entry }}
        run: |
          {
            echo "## Release workflow"
            echo
            if [[ "$HAS_ENTRIES" == "true" ]]; then
              echo "Checked changie entries and posted a preview comment."
            elif [[ "$NEEDS_ENTRY" == "true" ]]; then
              echo "Checked changie entries and found a required missing entry."
            else
              echo "Checked changie entries; no changelog entry required."
            fi
          } >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 5: Add release PR creation job**

Append this job after `check`:

```yaml
  create-release-pr:
    needs: validate
    if: github.event_name == 'push' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch) && inputs.create-release-pr
    runs-on: ubuntu-latest
    env:
      HAS_APP_SECRETS: ${{ secrets.app-id != '' && secrets.app-private-key != '' }}
    steps:
      - name: Generate app token
        if: env.HAS_APP_SECRETS == 'true'
        id: app-token
        uses: actions/create-github-app-token@f8d387b68d61c58ab83c6c016672934102569859 # ratchet:actions/create-github-app-token@v3
        with:
          app-id: ${{ secrets.app-id }}
          private-key: ${{ secrets.app-private-key }}

      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # ratchet:actions/checkout@v4
        with:
          token: ${{ steps.app-token.outputs.token || github.token }}

      - name: Read workspace
        if: inputs.workspace-file != ''
        id: workspace
        uses: tylerbutler/actions/read-gleam-workspace@434af6fb683e908d5a2fab1b53849c2d54a86566 # ratchet:tylerbutler/actions/read-gleam-workspace@main
        with:
          working-directory: ${{ inputs.working-directory }}
          workspace-file: ${{ inputs.workspace-file }}

      - name: Create release pull request
        id: release-pr
        uses: tylerbutler/actions/changie-release@434af6fb683e908d5a2fab1b53849c2d54a86566 # ratchet:tylerbutler/actions/changie-release@main
        with:
          version: ${{ inputs.version }}
          projects: ${{ steps.workspace.outputs.projects || inputs.projects }}
          changie-version: ${{ inputs.changie-version }}
          working-directory: ${{ inputs.working-directory }}
          pr-title-template: ${{ inputs.pr-title-template }}
          branch-template: ${{ inputs.branch-template }}
          commit-message-template: ${{ inputs.commit-message-template }}
          pr-body-template: ${{ inputs.pr-body-template }}
          labels: ${{ inputs.labels }}
          token: ${{ steps.app-token.outputs.token || github.token }}
          version-files: ${{ steps.workspace.outputs.version-files || inputs.version-files }}
          post-batch-command: ${{ inputs.post-batch-command }}

      - name: Summarize release PR
        shell: bash
        env:
          SKIPPED: ${{ steps.release-pr.outputs.skipped }}
          PR_NUMBER: ${{ steps.release-pr.outputs.pr-number }}
          VERSION: ${{ steps.release-pr.outputs.version }}
        run: |
          {
            echo "## Release workflow"
            echo
            if [[ "$SKIPPED" == "true" ]]; then
              echo "No unreleased changie fragments found; release PR creation skipped."
            else
              echo "Created or updated release PR #${PR_NUMBER} for ${VERSION}."
            fi
          } >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `bash tests/release-workflow-test.sh`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/release.yml tests/release-workflow-test.sh
git commit -m "feat: add release workflow PR phases"
```

---

## Task 3: Add auto-tag, Hex publish, and Homebrew publish jobs

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `tests/release-workflow-test.sh`

- [ ] **Step 1: Extend the failing test**

Add these strings to the Python `required` list in `tests/release-workflow-test.sh`:

```python
    "tag:",
    "contains(github.event.pull_request.labels.*.name, inputs.release-label)",
    "tylerbutler/actions/changie-auto-tag@434af6fb683e908d5a2fab1b53849c2d54a86566",
    "publish-hex:",
    "HEX_API_KEY: ${{ secrets.hex-api-key }}",
    "tylerbutler/actions/gleam-publish@434af6fb683e908d5a2fab1b53849c2d54a86566",
    "packages: ${{ steps.packages.outputs.packages }}",
    "publish-homebrew:",
    "APP_ID: ${{ secrets.homebrew-app-id }}",
    "inputs.homebrew-dist-plan == ''",
    "tylerbutler/actions/publish-homebrew-formula@434af6fb683e908d5a2fab1b53849c2d54a86566",
    "plan: ${{ inputs.homebrew-dist-plan }}",
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash tests/release-workflow-test.sh`

Expected: FAIL listing missing tag and publish job strings.

- [ ] **Step 3: Add auto-tag job**

Append this job after `create-release-pr`:

```yaml
  tag:
    needs: validate
    if: github.event_name == 'pull_request' && github.event.pull_request.merged && contains(github.event.pull_request.labels.*.name, inputs.release-label)
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.auto-tag.outputs.version }}
      tag: ${{ steps.auto-tag.outputs.tag }}
      created-tags: ${{ steps.auto-tag.outputs.created-tags }}
    env:
      HAS_APP_SECRETS: ${{ secrets.app-id != '' && secrets.app-private-key != '' }}
    steps:
      - name: Generate app token
        if: env.HAS_APP_SECRETS == 'true'
        id: app-token
        uses: actions/create-github-app-token@f8d387b68d61c58ab83c6c016672934102569859 # ratchet:actions/create-github-app-token@v3
        with:
          app-id: ${{ secrets.app-id }}
          private-key: ${{ secrets.app-private-key }}

      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # ratchet:actions/checkout@v4
        with:
          token: ${{ steps.app-token.outputs.token || github.token }}

      - name: Read workspace
        if: inputs.workspace-file != ''
        id: workspace
        uses: tylerbutler/actions/read-gleam-workspace@434af6fb683e908d5a2fab1b53849c2d54a86566 # ratchet:tylerbutler/actions/read-gleam-workspace@main
        with:
          working-directory: ${{ inputs.working-directory }}
          workspace-file: ${{ inputs.workspace-file }}

      - name: Auto-tag release
        id: auto-tag
        uses: tylerbutler/actions/changie-auto-tag@434af6fb683e908d5a2fab1b53849c2d54a86566 # ratchet:tylerbutler/actions/changie-auto-tag@main
        with:
          changie-version: ${{ inputs.changie-version }}
          working-directory: ${{ inputs.working-directory }}
          projects: ${{ steps.workspace.outputs.projects || inputs.projects }}
          create-release: ${{ inputs.create-release }}
          wait-for-publish: ${{ inputs.wait-for-publish }}
          publish-workflow-name: ${{ inputs.publish-workflow-name }}
          token: ${{ steps.app-token.outputs.token || github.token }}

      - name: Summarize tags
        shell: bash
        env:
          CREATED_TAGS: ${{ steps.auto-tag.outputs.created-tags }}
        run: |
          {
            echo "## Release workflow"
            echo
            if [[ -n "$CREATED_TAGS" ]]; then
              echo "Created tags: $CREATED_TAGS."
            else
              echo "No new tags created."
            fi
          } >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 4: Add Hex publish job**

Append this job after `tag`:

```yaml
  publish-hex:
    needs: validate
    if: startsWith(github.ref, 'refs/tags/') && needs.validate.outputs.publish-hex == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Validate Hex inputs
        shell: bash
        env:
          HEX_API_KEY: ${{ secrets.hex-api-key }}
        run: |
          if [[ -n "$HEX_API_KEY" ]]; then
            exit 0
          fi
          echo "::error::publish-to includes 'hex', but secret hex-api-key is missing"
          exit 1

      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # ratchet:actions/checkout@v4

      - name: Read workspace
        if: inputs.workspace-file != ''
        id: workspace
        uses: tylerbutler/actions/read-gleam-workspace@434af6fb683e908d5a2fab1b53849c2d54a86566 # ratchet:tylerbutler/actions/read-gleam-workspace@main
        with:
          working-directory: ${{ inputs.working-directory }}
          workspace-file: ${{ inputs.workspace-file }}
          tag: ${{ github.ref_name }}

      - name: Resolve Hex packages
        id: packages
        shell: bash
        env:
          WORKSPACE_PACKAGES: ${{ steps.workspace.outputs.packages }}
          INPUT_PACKAGES: ${{ inputs.hex-packages }}
        run: |
          set -euo pipefail
          packages="${WORKSPACE_PACKAGES:-$INPUT_PACKAGES}"
          if [[ -z "$packages" ]]; then
            echo "::error::publish-to includes 'hex', but no packages were resolved. Set workspace-file or hex-packages."
            exit 1
          fi
          echo "packages=$packages" >> "$GITHUB_OUTPUT"

      - name: Publish to Hex
        id: publish
        uses: tylerbutler/actions/gleam-publish@434af6fb683e908d5a2fab1b53849c2d54a86566 # ratchet:tylerbutler/actions/gleam-publish@main
        with:
          packages: ${{ steps.packages.outputs.packages }}
          working-directory: ${{ inputs.working-directory }}
          hex-api-key: ${{ secrets.hex-api-key }}
          skip-already-published: ${{ inputs.hex-skip-already-published }}
          replace-path-deps: ${{ inputs.hex-replace-path-deps }}

      - name: Summarize Hex publish
        shell: bash
        env:
          PUBLISHED: ${{ steps.publish.outputs.published }}
          SKIPPED: ${{ steps.publish.outputs.skipped }}
        run: |
          {
            echo "## Release workflow"
            echo
            echo "Published Hex packages: ${PUBLISHED:-none}; skipped: ${SKIPPED:-none}."
          } >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 5: Add Homebrew publish job**

Append this job after `publish-hex`:

```yaml
  publish-homebrew:
    needs: validate
    if: startsWith(github.ref, 'refs/tags/') && needs.validate.outputs.publish-homebrew == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Validate Homebrew inputs
        shell: bash
        env:
          APP_ID: ${{ secrets.homebrew-app-id }}
          PRIVATE_KEY: ${{ secrets.homebrew-app-private-key }}
          TAP_REPO: ${{ inputs.homebrew-tap-repo }}
          PLAN: ${{ inputs.homebrew-dist-plan }}
        run: |
          set -euo pipefail
          missing=()
          [[ -n "$APP_ID" ]] || missing+=("secret homebrew-app-id")
          [[ -n "$PRIVATE_KEY" ]] || missing+=("secret homebrew-app-private-key")
          [[ -n "$TAP_REPO" ]] || missing+=("input homebrew-tap-repo")
          [[ -n "$PLAN" ]] || missing+=("input homebrew-dist-plan")
          if [[ "${#missing[@]}" -gt 0 ]]; then
            printf '::error::publish-to includes homebrew, but these values are missing: %s\n' "${missing[*]}"
            exit 1
          fi

      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # ratchet:actions/checkout@v4

      - name: Publish Homebrew formula
        uses: tylerbutler/actions/publish-homebrew-formula@434af6fb683e908d5a2fab1b53849c2d54a86566 # ratchet:tylerbutler/actions/publish-homebrew-formula@main
        with:
          app-id: ${{ secrets.homebrew-app-id }}
          private-key: ${{ secrets.homebrew-app-private-key }}
          tap-repo: ${{ inputs.homebrew-tap-repo }}
          plan: ${{ inputs.homebrew-dist-plan }}
          artifact-pattern: ${{ inputs.homebrew-artifact-pattern }}
          install-linuxbrew: ${{ inputs.homebrew-install-linuxbrew }}

      - name: Summarize Homebrew publish
        shell: bash
        run: |
          {
            echo "## Release workflow"
            echo
            echo "Published Homebrew formula artifacts to ${{ inputs.homebrew-tap-repo }}."
          } >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `bash tests/release-workflow-test.sh`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/release.yml tests/release-workflow-test.sh
git commit -m "feat: add release workflow publish phases"
```

---

## Task 4: Document release workflow usage

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `tests/release-workflow-test.sh`

- [ ] **Step 1: Extend the failing test**

Append this shell/Python block to `tests/release-workflow-test.sh` after the workflow checks:

```bash
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash tests/release-workflow-test.sh`

Expected: FAIL listing missing README and CLAUDE.md docs.

- [ ] **Step 3: Update `README.md` reusable workflow docs**

Insert this section after the existing `auto-tag` reusable workflow section:

````markdown
### release

High-level reusable workflow for the standard changie release lifecycle. It can:

1. check PR changelog entries with `changie-check` and post a sticky preview comment,
2. create or update a changie release PR with `changie-release`,
3. create tags when release PRs merge with `changie-auto-tag`,
4. publish tag releases to Hex.pm and/or a Homebrew tap.

The consuming repository still owns its `on:` triggers. The same reusable workflow can be called from PR, push, and tag workflows; jobs inside `release.yml` gate themselves from the caller event context.

```yaml
jobs:
  release:
    uses: tylerbutler/actions/.github/workflows/release.yml@main
```

**Example (Gleam package publishing to Hex):**

```yaml
name: Release

on:
  pull_request:
    types: [opened, synchronize, reopened, closed]
    branches: [main]
  push:
    branches: [main]
    tags: ['v*']

jobs:
  release:
    uses: tylerbutler/actions/.github/workflows/release.yml@main
    with:
      publish-to: hex
      hex-packages: .
    secrets:
      hex-api-key: ${{ secrets.HEX_API_KEY }}
      app-id: ${{ secrets.RELEASE_APP_ID }}
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}
```

**Example (Hex + Homebrew with cargo-dist plan):**

```yaml
jobs:
  dist:
    if: startsWith(github.ref, 'refs/tags/')
    uses: axodotdev/cargo-dist/.github/workflows/release.yml@v0.28

  release:
    needs: [dist]
    uses: tylerbutler/actions/.github/workflows/release.yml@main
    with:
      publish-to: hex,homebrew
      hex-packages: .
      homebrew-tap-repo: owner/homebrew-tap
      homebrew-dist-plan: ${{ needs.dist.outputs.plan }}
    secrets:
      hex-api-key: ${{ secrets.HEX_API_KEY }}
      homebrew-app-id: ${{ secrets.HOMEBREW_TAP_APP_ID }}
      homebrew-app-private-key: ${{ secrets.HOMEBREW_TAP_APP_PRIVATE_KEY }}
```

**Example (Gleam workspace / changie projects):**

```yaml
jobs:
  release:
    uses: tylerbutler/actions/.github/workflows/release.yml@main
    with:
      workspace-file: workspace.toml
      publish-to: hex
      hex-replace-path-deps: |
        my-package:gleam.toml
    secrets:
      hex-api-key: ${{ secrets.HEX_API_KEY }}
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `publish-to` | `''` | Comma-separated publish targets: `hex`, `homebrew` |
| `working-directory` | `.` | Directory containing `.changie.yaml` |
| `changie-version` | `latest` | Changie CLI version |
| `projects` | `''` | Comma-separated changie project keys |
| `workspace-file` | `''` | Optional `workspace.toml`; overrides `projects` and can provide Hex package order |
| `version-files` | `''` | Version files forwarded to `changie-release` |
| `post-batch-command` | `''` | Command run after changie batch/version bumps |
| `release-label` | `release` | Label required for merge-to-tag behavior |
| `check-changelog` | `true` | Run PR changelog validation/commenting |
| `create-release-pr` | `true` | Create/update release PRs on default-branch pushes |
| `hex-packages` | `''` | Space-separated package paths for Hex publishing |
| `hex-replace-path-deps` | `''` | Forwarded to `gleam-publish` |
| `homebrew-tap-repo` | `''` | Tap repo in `owner/repo` form |
| `homebrew-dist-plan` | `''` | cargo-dist plan JSON passed to `publish-homebrew-formula` |
| `homebrew-artifact-pattern` | `artifacts-*` | Formula artifact pattern |

**Secrets:**

| Secret | Required when |
|--------|---------------|
| `hex-api-key` | `publish-to` contains `hex` |
| `app-id` / `app-private-key` | Optional; use when release PR/tag pushes should trigger downstream workflows |
| `homebrew-app-id` / `homebrew-app-private-key` | `publish-to` contains `homebrew` |

`auto-tag.yml` remains available for consumers that only need release-PR merge to tag behavior.
````

- [ ] **Step 4: Update `CLAUDE.md`**

In the reusable workflows table, add:

```markdown
| `release.yml` | High-level release orchestrator: PR changie check/comment, changie release PR creation, release PR auto-tagging, and Hex/Homebrew tag publishing |
```

In the Changie/release gotchas area, add:

```markdown
- `release.yml` is the high-level release orchestrator. Keep `auto-tag.yml` as the lower-level primitive for consumers that only want merge-to-tag behavior. Homebrew publishing goes through the existing dist-plan based `publish-homebrew-formula` action (`homebrew-dist-plan`, `homebrew-artifact-pattern`), not a direct formula-path input.
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `bash tests/release-workflow-test.sh`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md tests/release-workflow-test.sh
git commit -m "docs: document release workflow"
```

---

## Task 5: Run full validation

**Files:**
- No edits expected unless validation finds a bug.

- [ ] **Step 1: Run the new focused test**

Run: `bash tests/release-workflow-test.sh`

Expected: PASS.

- [ ] **Step 2: Run all bash integration tests**

Run: `for script in tests/*-test.sh; do echo "=== $script ==="; bash "$script"; done`

Expected: every script exits 0.

- [ ] **Step 3: Run pytest**

Run: `pytest -v`

Expected: all Python tests pass.

- [ ] **Step 4: Inspect final diff**

Run: `git --no-pager diff --stat HEAD~4..HEAD && git --no-pager status --short`

Expected: committed changes cover only `.github/workflows/release.yml`, `tests/release-workflow-test.sh`, `README.md`, and `CLAUDE.md`; status is clean.

- [ ] **Step 5: Commit validation fixes if needed**

If any validation command required fixes, commit them:

```bash
git add .github/workflows/release.yml tests/release-workflow-test.sh README.md CLAUDE.md
git commit -m "fix: finalize release workflow validation"
```

Expected: skip this step when Task 5 produces no edits.

---

## Self-review notes

- Spec coverage: validation, PR changelog check/comment, release PR creation, release PR merge tagging, Hex publish, Homebrew dist-plan publish, summaries, errors, tests, and docs each have at least one task.
- Placeholder scan: every code-edit step includes concrete content, commands, and expected results.
- Type/name consistency: Homebrew uses `homebrew-dist-plan`, `homebrew-artifact-pattern`, and `homebrew-install-linuxbrew` consistently with `publish-homebrew-formula`; the removed formula-path interface is checked only as forbidden test content.
