# Shared GitHub Actions

## Overview

Reusable composite actions for CI/CD workflows. Used across multiple repositories to standardize setup procedures.

## Actions

| Action | Purpose |
|--------|---------|
| `setup-gleam` | Gleam/BEAM environment with caching |
| `setup-go` | Go environment with optional mise tool management |
| `setup-rust` | Rust toolchain with caching |
| `setup-node` | Node.js with pnpm/npm/yarn/bun |
| `install-tools` | Install dev tools via taiki-e |
| `changie-release` | Batch changie entries and create release PR (single or multi-project) |
| `changie-auto-tag` | Create version tag(s) from latest changie release (single or multi-project) |
| `changie-check` | Detect PR-added changie fragments and render preview |
| `gleam-publish` | Publish Gleam packages to Hex.pm in dependency order, with optional path dep rewriting |
| `read-gleam-workspace` | Parse workspace.toml with glob support, output structured package metadata for other actions |
| `run-gleam-workspace` | Escape hatch: run a shell command in each package from `packages` |
| `binary-size` | Measure binary file sizes and report deltas vs baseline |
| `download-ccl-tests` | Download CCL test data from CatConfLang/ccl-test-data releases |
| `publish-homebrew-formula` | Custom dist `publish-jobs` action that commits the dist-generated .rb formula to a tap using a GitHub App token instead of a PAT |

## Usage Pattern

From any repository:
```yaml
- uses: tylerbutler/actions/setup-gleam@v1
- uses: tylerbutler/actions/setup-rust@v1
- uses: tylerbutler/actions/setup-node@v1
```

## Structure

```
actions/
├── setup-gleam/
│   └── action.yml      # Gleam/BEAM setup
├── setup-go/
│   └── action.yml      # Go setup with optional mise
├── setup-rust/
│   └── action.yml      # Rust toolchain setup
├── setup-node/
│   └── action.yml      # Node.js setup
├── install-tools/
│   └── action.yml      # Generic tool installer
├── changie-release/
│   └── action.yml      # Changie release PR automation
├── changie-auto-tag/
│   └── action.yml      # Version tag from changie
├── changie-check/
│   └── action.yml      # PR changelog detection
├── gleam-publish/
│   └── action.yml      # Publish Gleam packages to Hex.pm
├── read-gleam-workspace/
│   └── action.yml      # Parse workspace.toml, expand globs, output package metadata
├── binary-size/
│   └── action.yml      # Binary file size reporting
├── download-ccl-tests/
│   └── action.yml      # CCL test data download
├── publish-homebrew-formula/
│   └── action.yml      # Commit dist .rb formula to a tap via GitHub App token
├── README.md           # User documentation
└── LICENSE
```

## Key Design Decisions

1. **Version file support**: `setup-gleam` reads from `.tool-versions` by default
2. **Caching by default**: All setup actions cache dependencies
3. **just integration**: All actions install `just` task runner by default
4. **Flexible inputs**: Can override defaults for any use case

## Reusable Workflows

Reusable workflows live in `.github/workflows/` and are called with `uses:` from other repos:

| Workflow | Purpose |
|----------|---------|
| `auto-tag.yml` | Tags releases when release PRs merge (wraps `changie-auto-tag` action) |
| `gleam-workspace-ci.yml` | Matrix CI for Gleam monorepos using `read-gleam-workspace` |

## Multi-Project Support

Both `changie-release` and `changie-auto-tag` support changie's built-in `projects` feature for monorepos with independently-versioned packages.

### Prerequisites

The consuming repo's `.changie.yaml` must have `projects` configured:
```yaml
projectsVersionSeparator: "-"
projects:
  - label: my-package
    key: my-package
    changelog: CHANGELOG.md
  - label: my-package-plugin
    key: my-package-plugin
    changelog: packages/my-package-plugin/CHANGELOG.md
```

### changie-release with projects

```yaml
- uses: tylerbutler/actions/changie-release@main
  with:
    projects: my-package,my-package-plugin
    version-files: |
      my-package:Cargo.toml:version
      my-package-plugin:packages/my-package-plugin/Cargo.toml:version
```

**Behavior when `projects` is set:**
- Each project is batched independently with `changie batch auto --project X`
- Projects with no unreleased changes are skipped
- `version` output contains comma-separated versions: `my-package-v1.0.0, my-package-plugin-v0.2.0`
- `version-files` uses `project:path:key` format (three colon-separated fields)
- Only projects that were actually batched have their version files bumped
- Branch name uses `release/next` (since multiple versions don't make valid branch names)
- `batched-projects` output lists which projects had changes
- `version` input is ignored (auto is always used per-project)

### changie-auto-tag with projects

```yaml
- uses: tylerbutler/actions/changie-auto-tag@main
  with:
    projects: my-package,my-package-plugin
    create-release: true
```

**Behavior when `projects` is set:**
- Loops over all projects, gets latest version for each
- Skips tags that already exist (handles partial releases gracefully)
- Creates a GitHub Release per new tag (when `create-release` is true)
- Release notes sourced from `.changes/{project}/{version}.md`
- `created-tags` output lists only the tags that were actually created
- Tags are pushed individually to ensure each generates a GitHub push event (batch pushes of >3 tags do not trigger workflow events)

### auto-tag.yml reusable workflow with projects

```yaml
jobs:
  auto-tag:
    uses: tylerbutler/actions/.github/workflows/auto-tag.yml@main
    with:
      projects: my-package,my-package-plugin
      create-release: true
```

### Multi-Project Directory Structure

With projects configured, changie organizes files as:
```
.changes/
├── header.md
├── unreleased/            # All fragments, prefixed by project
│   ├── my-package-Added-20260228-....yaml
│   └── my-package-plugin-Fixed-20260228-....yaml
├── my-package/            # Per-project version files
│   └── v1.0.0.md
└── my-package-plugin/
    └── v0.2.0.md
```

### Backward Compatibility

Both actions are fully backward compatible:
- When `projects` input is empty (default), all behavior is identical to before
- Single-project `version-files` format (`path:key`) is unchanged
- All existing outputs work the same way for single-project repos

## Changie Action Gotchas

- `changie latest` returns versions with `v` prefix - `changie-auto-tag` default `tag-prefix` is empty to avoid `vv` tags. The `tag-prefix` input exists for monorepo/multi-package repos where tags need a package prefix (e.g. `mypackage/v1.0.0`)
- `changie batch auto` exits non-zero when no unreleased fragments exist - `changie-release` pre-checks the unreleased directory before calling batch
- `changie-release` reads `.changie.yaml` to find the unreleased directory path (`changesDir`/`unreleasedDir`)
- PR body template supports `{version}` and `{changelog}` variables resolved via bash substitution
- `changie-release` supports `version-files` input for bumping version in TOML files (only TOML is supported). Single-project format: `path:key` per line. Multi-project format: `project:path:key` per line. Only top-level keys are supported. Changes are included in the same commit as the changelog update via `peter-evans/create-pull-request`
- `changie-release` supports `post-batch-command` input to run a shell command after version bumps but before the PR commit. Useful for refreshing lockfiles (e.g., `gleam deps download`) so the release PR includes up-to-date manifests
- `changie-auto-tag` supports optional `create-release` input to create a GitHub Release with changie version notes. Uses `.changes/{version}.md` (or `.changes/{project}/{version}.md` for multi-project) as release notes if available, falls back to `--generate-notes`
- In multi-project mode, `changie-release` reads `projectsVersionSeparator` from `.changie.yaml` (defaults to `-`) to correctly parse version strings like `my-package-v1.0.0`
- In multi-project mode, the branch name template replaces `{version}` with `next` instead of the version string, since comma-separated versions aren't valid branch names

- `gleam-publish` supports `replace-path-deps` input to rewrite path dependencies to Hex version ranges before publishing. Format: `dep-name:version-toml-path` per line. Reads version from the specified TOML file and generates a `">= X.Y.Z and < (X+1).0.0"` range (or `< 0.(Y+1).0` for pre-1.0). Essential for monorepos where sub-packages use `{ path = "..." }` deps during development
- `read-gleam-workspace` parses `workspace.toml` with `[workspace]` section containing `members` (glob-enabled) and `exclude` arrays. Uses Python `tomllib` (stdlib). Topologically sorts packages by intra-workspace dependencies so output order is safe for publishing. Outputs: `packages` (space-separated paths), `projects` (comma-separated names), `version-files` (changie format), `packages-json` (JSON), `cache-hash-globs` (for hashFiles)
- `run-gleam-workspace` is a minimal bash escape hatch for sequential workspace-wide tasks. It consumes `read-gleam-workspace`'s `packages` output and runs a caller-provided shell command in each package directory. Prefer dedicated actions/reusable workflows for common cases; use this when the repo needs one-off workspace iteration.
- `gleam-workspace-ci.yml` is a reusable workflow for Gleam monorepos. It discovers packages from `workspace.toml`, then runs the standard Gleam CI steps (`format --check`, `check`, `build --warnings-as-errors`, `test`, optional docs) in a per-package matrix after calling `setup-gleam`.
- `publish-homebrew-formula` is a composite action used as a custom dist `publish-jobs` step. **Not invoked directly by dist** — dist requires custom publish jobs to be local reusable workflows (`./my-job.yml` in `.github/workflows/`), so the consumer repo defines a ~20-line shim reusable workflow that calls this action. Replaces dist's built-in homebrew publish to use a GitHub App installation token instead of `HOMEBREW_TAP_TOKEN` PAT. `installers = ["homebrew"]` still drives .rb generation; `publish-jobs = ["./publish-homebrew-tap"]` swaps only the publish step. The tap-repo input is split into owner/repo in a small bash step so `actions/create-github-app-token` can scope the token to just that repo. Why App token over PAT: tokens are 1-hour scoped installation tokens, not tied to a user, and do not need manual rotation.

## Workspace File Format

Repos can define a `workspace.toml` to centralize monorepo package layout:
```toml
[workspace]
members = [".", "packages/my_lib_*"]
exclude = ["packages/my_lib_experimental"]
```
- `members`: Glob patterns or literal paths. Order preserved for literals, sorted for globs. Each dir must have a `gleam.toml`.
- `exclude`: Patterns to remove from expanded members. Supports globs.
- The `read-gleam-workspace` action expands this into outputs consumed by `gleam-publish`, `changie-release`, and `auto-tag`.

## Adding New Actions

1. Create new directory: `new-action/action.yml`
2. Follow composite action pattern
3. Add inputs with sensible defaults
4. Include caching where applicable
5. Update README.md with documentation

## Versioning

- Use semantic versioning tags (v1, v1.0.0)
- Major version tags (v1) should be updated to point to latest minor/patch
- Breaking changes require major version bump
