# Cluster C Design — release reusable workflow

**Date:** 2026-05-20
**Status:** Draft for review
**Prior clusters:**
- `2026-05-18-actions-internal-cohesion-design.md` (Cluster A)
- `2026-05-19-cluster-b-mise-setup-design.md` (Cluster B)
**Handoff context:** `docs/superpowers/handoffs/2026-05-19-clusters-b-and-c-handoff.md`

## Goal

Add one high-level reusable workflow, `.github/workflows/release.yml`, that lets consumer repositories wire the standard changie release lifecycle with one `uses:` target:

1. PRs get changelog validation and a rendered preview comment.
2. Default-branch pushes create or update the changie release PR.
3. Merged release PRs create version tag(s) through the existing auto-tag behavior.
4. Tag pushes publish to selected v1 targets: Hex.pm and Homebrew.

The workflow is an orchestrator. It composes existing actions and reusable workflows instead of replacing them.

## Non-goals

- Replacing or removing `.github/workflows/auto-tag.yml`. Existing consumers keep using it directly if they only need tag creation.
- Implementing crates.io or npm publishing in v1. The `publish-to` contract reserves space for future targets, but unknown values fail explicitly.
- Creating a new owned sticky-comment action. `changie-check` already emits markdown; v1 posts it with `marocchino/sticky-pull-request-comment@v2`, matching existing consumer practice.
- Reworking changie internals, version-file mutation, or `gleam-publish` path-dependency rewriting.

## Workflow contract

### File layout

```
.github/workflows/
├── auto-tag.yml
├── gleam-workspace-ci.yml
└── release.yml          # new
```

### Caller shape

Consumer repositories call the same reusable workflow from their own event workflows. The caller owns `on:` triggers because reusable workflows cannot declare `pull_request`, `pull_request.closed`, and `push.tags` behavior for another repository.

```yaml
jobs:
  release:
    uses: tylerbutler/actions/.github/workflows/release.yml@main
    with:
      publish-to: hex,homebrew
      workspace-file: workspace.toml
      projects: my-pkg,my-pkg-plugin
      version-files: |
        my-pkg:gleam.toml:version
        my-pkg-plugin:packages/plugin/gleam.toml:version
      hex-packages: . packages/plugin
      homebrew-tap-repo: owner/homebrew-tap
      homebrew-dist-plan: ${{ needs.dist.outputs.plan }}
    secrets:
      hex-api-key: ${{ secrets.HEX_API_KEY }}
      app-id: ${{ secrets.RELEASE_APP_ID }}
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}
      homebrew-app-id: ${{ secrets.HOMEBREW_APP_ID }}
      homebrew-app-private-key: ${{ secrets.HOMEBREW_APP_PRIVATE_KEY }}
```

### Inputs

| Input | Default | Notes |
|-------|---------|-------|
| `publish-to` | `''` | Comma-separated targets. v1 accepts `hex` and `homebrew`; empty means no publish jobs. |
| `working-directory` | `'.'` | Directory containing `.changie.yaml` and release metadata. |
| `changie-version` | `'latest'` | Forwarded to changie actions. |
| `projects` | `''` | Comma-separated changie project keys. |
| `workspace-file` | `''` | When set, read projects/packages through `read-gleam-workspace`; overrides `projects` for changie project discovery. |
| `version` | `'auto'` | Forwarded to `changie-release`; ignored when projects are set. |
| `version-files` | `''` | Forwarded to `changie-release`. Supports existing single-project and multi-project formats. |
| `post-batch-command` | `''` | Forwarded to `changie-release`. |
| `release-label` | `'release'` | Label identifying release PRs for tag creation. |
| `labels` | `'release'` | Labels applied to release PRs created by `changie-release`. |
| `pr-title-template` | `'Release {version}'` | Forwarded to `changie-release`. |
| `branch-template` | `'release/next'` | Forwarded to `changie-release`. |
| `commit-message-template` | `'chore(release): {version}'` | Forwarded to `changie-release`. |
| `pr-body-template` | `'{changelog}'` | Forwarded to `changie-release`. |
| `check-changelog` | `true` | Enables PR changelog validation/commenting. |
| `require-for-types` | `'feat,fix,refactor,security'` | Forwarded to `changie-check`. |
| `create-release` | `false` | Forwarded to auto-tag GitHub Release creation. |
| `wait-for-publish` | `false` | Forwarded to auto-tag publish waiting. |
| `publish-workflow-name` | `'Publish'` | Forwarded to auto-tag publish waiting. |
| `hex-packages` | `''` | Space-separated packages for `gleam-publish`. Required when `publish-to` contains `hex` unless `workspace-file` provides packages. |
| `hex-replace-path-deps` | `''` | Forwarded to `gleam-publish`. |
| `hex-skip-already-published` | `true` | Forwarded to `gleam-publish`. |
| `homebrew-tap-repo` | `''` | Required when `publish-to` contains `homebrew`. |
| `homebrew-dist-plan` | `''` | dist plan JSON. Required when `publish-to` contains `homebrew`. |
| `homebrew-artifact-pattern` | `'artifacts-*'` | Forwarded to `publish-homebrew-formula`. |
| `homebrew-install-linuxbrew` | `true` | Forwarded to `publish-homebrew-formula`. |

### Secrets

Secrets are explicit and optional at the workflow boundary. Jobs validate that required secrets are present only when their phase needs them.

| Secret | Used by | Required when |
|--------|---------|---------------|
| `hex-api-key` | Hex publish | `publish-to` contains `hex` |
| `app-id` | changie release PR and auto-tag token generation | Optional; falls back to `GITHUB_TOKEN` when absent |
| `app-private-key` | changie release PR and auto-tag token generation | Required only with `app-id` |
| `homebrew-app-id` | Homebrew tap publish | `publish-to` contains `homebrew` |
| `homebrew-app-private-key` | Homebrew tap publish | `publish-to` contains `homebrew` |

## Jobs and data flow

### 1. Validate configuration

First job normalizes comma-separated inputs and fails on unknown `publish-to` values. It emits booleans such as `publish-hex` and `publish-homebrew` so later `if:` expressions stay readable.

Validation is strict:

- `publish-to: crates` or `publish-to: npm` fails until those adapters exist.
- `hex` without `hex-api-key` fails on tag publish.
- `homebrew` without tap inputs, dist plan JSON, or Homebrew app secrets fails on tag publish.
- Empty `publish-to` is valid and skips publishing.

### 2. PR changelog check

Runs when the caller event is `pull_request` and `check-changelog` is true.

Steps:

1. Check out the repository with enough history for diffing.
2. Optionally read `workspace-file` to derive changie projects.
3. Run `changie-check` with the PR base/head SHAs.
4. Post a sticky PR comment with the rendered preview or missing-entry guidance.
5. Fail the job when `changie-check` reports `needs-entry=true`.

The sticky comment uses a stable hidden marker such as `<!-- tylerbutler/actions-release-changie-check -->` so reruns update the same comment.

### 3. Release PR creation

Runs on normal push events to the default branch when the caller wants automated release PR creation. It invokes `changie-release` with the changie, template, version-file, and post-batch inputs.

This phase creates or updates the release PR. It is skipped when no unreleased fragments exist, preserving `changie-release`'s existing graceful no-op behavior.

### 4. Release PR merge tagging

Runs when the caller event is `pull_request`, the PR was merged, and the PR has `release-label`.

This job does not reimplement tag logic. It mirrors `.github/workflows/auto-tag.yml` by using the same action path and inputs, including optional GitHub App token generation. Keeping `auto-tag.yml` intact avoids breaking existing consumers and prevents two independent tag implementations from drifting.

Outputs expose `version`, `tag`, and `created-tags` for caller workflows that want to chain custom jobs.

### 5. Tag publish

Runs when the caller event is a tag push and at least one publish target is requested.

Hex publishing:

1. Resolve packages from `workspace-file` when available, otherwise use `hex-packages`.
2. Call `gleam-publish` with `packages`, `working-directory`, `hex-api-key`, `hex-skip-already-published`, and `hex-replace-path-deps`.

Homebrew publishing:

1. Receive the dist plan JSON through `homebrew-dist-plan`.
2. Call `publish-homebrew-formula` with `app-id`, `private-key`, `tap-repo`, `plan`, `artifact-pattern`, and `install-linuxbrew`.
3. Let `publish-homebrew-formula` mint the tap-scoped GitHub App token, download matching formula artifacts, style them when configured, and push commits to the tap.

Hex and Homebrew jobs can run independently. One failing target fails the workflow; no target is silently skipped when explicitly requested.

## Step summaries

`release.yml` should add a small orchestrator summary in each phase, while the composed actions continue writing their own summaries:

```markdown
## Release workflow

Checked changie entries for PR #123.
```

Examples:

- `Created release PR #45 for v1.2.0.`
- `Created tags: my-pkg-v1.2.0 my-pkg-plugin-v0.4.0.`
- `Published targets: hex, homebrew.`

Skipped phases still write a short line when the job runs far enough to know it is skipping. This follows the Cluster A summary convention without centralizing all child-action output.

## Error handling

- Unknown `publish-to` values fail with a clear message.
- Missing required inputs or secrets fail only in jobs where the relevant target is active.
- Changelog validation failures use `changie-check` outputs; no broad catch-all logic masks action failures.
- Tag creation remains idempotent through `changie-auto-tag`, which already skips existing tags.
- Publish behavior remains target-specific: `gleam-publish` can skip already-published Hex versions when configured; Homebrew publishing propagates commit/API failures.

## Testing

### Static workflow validation

Extend CI with a workflow syntax validation step for `.github/workflows/release.yml`. Use existing repository tooling only; no new linter dependency is introduced unless already available in CI.

### Scenario fixtures

Add lightweight tests or smoke workflows that cover:

1. `publish-to` parsing accepts `hex`, `homebrew`, and `hex,homebrew`.
2. Unknown targets fail explicitly.
3. PR check job uses `changie-check` base/head inputs and posts a sticky comment body.
4. Release PR merge gating requires both `merged == true` and the release label.
5. Tag publish gating activates Hex and Homebrew jobs independently.

Where GitHub-hosted event simulation is impractical, keep the test at the validation-script level and rely on the called actions' existing tests for behavior. Do not introduce a large mock GitHub API harness in v1.

## Documentation

Update `README.md` with a new reusable workflows section for `release.yml`:

- Basic changie release PR + auto-tag usage.
- Gleam Hex publishing.
- Hex + Homebrew publishing.
- Multi-project/workspace example.
- Notes that `auto-tag.yml` remains available for consumers that only need tag creation.

Also update `CLAUDE.md` / repo memory docs if needed so future work knows `release.yml` is the high-level orchestrator and `auto-tag.yml` is the lower-level primitive.

## Files expected in implementation

| File | Change |
|------|--------|
| `.github/workflows/release.yml` | New reusable workflow orchestrator |
| `.github/workflows/test.yml` | Add workflow validation/smoke coverage |
| `README.md` | Document release workflow examples and inputs |
| `CLAUDE.md` | Add reusable workflow summary if present in repo |
| `docs/superpowers/specs/2026-05-20-cluster-c-release-workflow-design.md` | This design |

## Risks

1. **Reusable workflows cannot own caller triggers.** Mitigation: document caller workflows clearly and keep event gating inside `release.yml` defensive.
2. **One workflow may look broad.** Mitigation: keep jobs phase-oriented and delegate actual work to existing actions.
3. **Homebrew publishing depends on dist plan/artifact plumbing.** Mitigation: expose the existing `publish-homebrew-formula` contract directly (`plan`, `artifact-pattern`, `install-linuxbrew`) instead of inventing a parallel formula-path adapter.
4. **Future publish targets could bloat the interface.** Mitigation: reject unknown targets now and add adapters one at a time with explicit inputs.

## Out-of-scope follow-ups

- Add crates.io and npm publish adapters.
- Replace third-party sticky comment posting with an owned `pr-sticky-comment` action if a concrete need appears.
- Supply-chain hardening pass for publisher permissions, OIDC, and provenance.
- More detailed per-subcommand summaries inside `changie-release`, `changie-auto-tag`, `changie-check`, and `binary-size`.
