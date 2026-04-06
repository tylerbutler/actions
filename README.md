# Shared GitHub Actions

Reusable composite actions for CI/CD workflows across repositories.

## Available Actions

### setup-gleam

Setup Gleam/BEAM environment with caching, optional Elixir, and optional JavaScript target support.

```yaml
- uses: tylerbutler/actions/setup-gleam@v1
  with:
    node: 'true'  # Enable for JavaScript target
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `erlang-version` | `''` | Erlang/OTP version (ignored if version-file set) |
| `gleam-version` | `''` | Gleam version (ignored if version-file set) |
| `elixir-version` | `''` | Elixir version (enables Mix support) |
| `rebar-version` | `''` | Rebar3 version (used with Elixir) |
| `version-file` | `.tool-versions` | Path to version file |
| `version-type` | `strict` | Version matching: strict or loose |
| `node` | `false` | Setup Node.js for JavaScript target |
| `node-version` | `22` | Node.js version |
| `cache` | `true` | Cache Gleam dependencies (and Mix deps when Elixir enabled) |
| `working-directory` | `.` | Working directory |
| `install-just` | `true` | Install just task runner |
| `run-deps` | `true` | Run dependency download |

**Example (Gleam only):**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-gleam@v1
      - run: just test
```

**Example (Gleam + Elixir):**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-gleam@v1
        with:
          erlang-version: '28.3'
          gleam-version: '1.14.0'
          elixir-version: '1.18.4'
          working-directory: server
      - run: just test-server
```

**Example (Gleam monorepo with multiple packages):**

For monorepos, disable the built-in cache and add your own `actions/cache` step with the correct `hashFiles()` patterns. If the root directory is also a publishable package, include its `gleam.toml` and `manifest.toml` in the hash:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: tylerbutler/actions/setup-gleam@v1
        with:
          cache: 'false'

      - uses: actions/cache@v4
        with:
          path: |
            build/packages
            ~/.cache/gleam
          key: gleam-${{ runner.os }}-${{ hashFiles('gleam.toml', 'manifest.toml', 'packages/*/gleam.toml', 'packages/*/manifest.toml') }}
          restore-keys: gleam-${{ runner.os }}-

      - run: just test
```

### setup-rust

Setup Rust toolchain with caching.

```yaml
- uses: tylerbutler/actions/setup-rust@v1
  with:
    components: 'rustfmt,clippy'
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `toolchain` | `stable` | Rust toolchain version |
| `components` | `''` | Components to install (comma-separated) |
| `targets` | `''` | Compilation targets (comma-separated) |
| `cache` | `true` | Cache Rust artifacts |
| `cache-key` | `rust` | Custom cache key prefix |
| `cache-targets` | `true` | Cache target directories |
| `cache-on-failure` | `true` | Cache even on failure |
| `tools` | `just` | Tools to install via taiki-e/install-action (comma-separated) |

**Example:**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-rust@v1
        with:
          components: 'rustfmt,clippy'
      - run: cargo test
```

### setup-node

Setup Node.js with package manager (pnpm, npm, yarn, or bun) and caching.

```yaml
- uses: tylerbutler/actions/setup-node@v1
  with:
    package-manager: 'pnpm'
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `node-version` | `22` | Node.js version |
| `package-manager` | `pnpm` | Package manager: npm, pnpm, yarn, bun |
| `pnpm-version` | `latest` | pnpm version |
| `cache` | `true` | Cache dependencies |
| `working-directory` | `.` | Working directory |
| `install-just` | `true` | Install just task runner |
| `run-install` | `true` | Run package install |

**Example:**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-node@v1
      - run: pnpm test
```

### setup-go

Setup Go environment with caching and optional [mise](https://mise.jdx.dev/) tool management.

```yaml
- uses: tylerbutler/actions/setup-go@v1
  with:
    install-mise: 'true'  # Install tools from mise.toml
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `go-version` | `''` | Go version (ignored if go-version-file set) |
| `go-version-file` | `go.mod` | Path to go.mod or version file |
| `cache` | `true` | Cache Go modules |
| `working-directory` | `.` | Working directory |
| `install-just` | `true` | Install just task runner |
| `install-mise` | `false` | Install mise and run mise install for project tools |
| `run-deps` | `true` | Run go mod download |

**Example:**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-go@v1
      - run: just test
```

**Example with mise (installs tools from mise.toml):**

```yaml
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-go@v1
        with:
          install-mise: 'true'
      - run: just ci
```

### install-tools

Install development tools via [taiki-e/install-action](https://github.com/taiki-e/install-action).

```yaml
- uses: tylerbutler/actions/install-tools@v1
  with:
    tools: 'just,cargo-nextest'
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `tools` | `just` | Comma-separated list of tools |

**Supported tools:** See [taiki-e/install-action](https://github.com/taiki-e/install-action#supported-tools)

### changie-release

Batch [changie](https://changie.dev/) changelog entries and create a release pull request. Useful for automating releases in projects that use changie for changelog management.

```yaml
- uses: tylerbutler/actions/changie-release@v1
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `version` | `auto` | Version to batch: auto, major, minor, patch, or explicit semver |
| `changie-version` | `latest` | Changie CLI version to install |
| `working-directory` | `.` | Directory containing `.changie.yaml` |
| `skip-if-no-changes` | `true` | Skip gracefully when no unreleased fragments exist |
| `pr-title-template` | `Release {version}` | PR title (`{version}` replaced at runtime) |
| `branch-template` | `release/{version}` | Branch name template |
| `commit-message-template` | `chore(release): {version}` | Commit message template |
| `pr-body` | *(default text)* | Pull request body text |
| `labels` | `release` | Comma-separated PR labels |
| `draft` | `false` | Create as draft PR |
| `token` | `${{ github.token }}` | GitHub token for PR creation |
| `base` | *(checked-out branch)* | Base branch for the PR |
| `delete-branch` | `true` | Delete branch after merge |
| `version-files` | `''` | TOML files to bump with the release version (see below) |
| `post-batch-command` | `''` | Shell command to run after version bumps, before PR creation (see below) |

**Version file bumping:**

The `version-files` input accepts a newline-separated list of `path:key` pairs pointing to TOML files that should be updated with the release version (without `v` prefix). Only top-level TOML keys are supported.

```yaml
- uses: tylerbutler/actions/changie-release@main
  with:
    version-files: |
      gleam.toml:version
```

This replaces `version = "..."` in `gleam.toml` with the new version. The change is included in the same commit as the changelog update — no extra git operations needed.

**Post-batch command:**

The `post-batch-command` input runs a shell command after changelog batching and version file bumping, but before the release PR commit is created. Any file changes made by this command are included in the release PR. This is useful for refreshing lockfiles or running code generation that depends on the new version.

```yaml
- uses: tylerbutler/actions/changie-release@main
  with:
    version-files: |
      gleam.toml:version
    post-batch-command: 'gleam deps download'
```

**Example (Gleam monorepo with lockfile refresh):**

```yaml
- uses: tylerbutler/actions/changie-release@main
  with:
    projects: my_lib,my_lib_plugin
    version-files: |
      my_lib:gleam.toml:version
      my_lib_plugin:packages/my_lib_plugin/gleam.toml:version
    post-batch-command: |
      gleam deps download
      for d in packages/*/; do (cd "$d" && gleam deps download); done
```

**Outputs:**

| Output | Description |
|--------|-------------|
| `version` | Resolved release version |
| `pr-number` | Pull request number |
| `pr-url` | Pull request URL |
| `pr-operation` | Operation performed: created, updated, closed, or noop |
| `skipped` | Whether the action was skipped (no unreleased changes) |

**Example:**

```yaml
jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/changie-release@v1
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
```

**Example with custom templates:**

```yaml
- uses: tylerbutler/actions/changie-release@v1
  with:
    version: minor
    pr-title-template: 'chore: release {version}'
    branch-template: 'chore/release-{version}'
    labels: 'release,automated'
    draft: 'true'
```

### changie-auto-tag

Create a version tag from the latest [changie](https://changie.dev/) release. Designed to run when a release PR merges, triggering downstream tag-based workflows (e.g., GoReleaser).

```yaml
- uses: tylerbutler/actions/changie-auto-tag@v1
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `changie-version` | `latest` | Changie CLI version to install |
| `working-directory` | `.` | Directory containing `.changie.yaml` |
| `tag-prefix` | `''` | Prefix for the git tag (`changie latest` already includes `v`) |
| `token` | `${{ github.token }}` | GitHub token for pushing the tag |
| `create-release` | `false` | Create a GitHub Release with changie version notes |

**Outputs:**

| Output | Description |
|--------|-------------|
| `version` | Version from `changie latest` |
| `tag` | Full tag that was created (e.g., `v1.2.3`) |

**Example (auto-tag on release PR merge):**

```yaml
name: Auto-tag release
on:
  pull_request:
    types: [closed]
    branches: [main]
permissions:
  contents: write
jobs:
  tag:
    if: github.event.pull_request.merged && contains(github.event.pull_request.labels.*.name, 'release')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/changie-auto-tag@v1
```

### changie-check

Check PRs for [changie](https://changie.dev/) changelog entries. Detects PR-added fragments, renders a preview using `changie batch --dry-run`, and reports whether a changelog entry is required based on conventional commit types.

```yaml
- uses: tylerbutler/actions/changie-check@v1
  with:
    base-sha: ${{ github.event.pull_request.base.sha }}
    head-sha: ${{ github.event.pull_request.head.sha }}
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `changie-version` | `latest` | Changie CLI version to install |
| `working-directory` | `.` | Directory containing `.changie.yaml` |
| `base-sha` | *(required)* | Base commit SHA to diff against |
| `head-sha` | *(required)* | Head commit SHA |
| `require-for-types` | `feat,fix,refactor,security` | Conventional commit types that require a changelog entry |

**Outputs:**

| Output | Description |
|--------|-------------|
| `has-entries` | Whether the PR adds changie fragments |
| `preview` | Rendered markdown preview of PR-added entries |
| `needs-entry` | Whether the PR should have a changelog entry but doesn't |
| `commit-types-found` | Conventional commit types found in PR commits |

**Example (PR validation with sticky comments):**

```yaml
jobs:
  changelog:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - uses: tylerbutler/actions/changie-check@v1
        id: changelog
        with:
          base-sha: ${{ github.event.pull_request.base.sha }}
          head-sha: ${{ github.event.pull_request.head.sha }}
      - name: Comment with changelog preview
        if: steps.changelog.outputs.has-entries == 'true'
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          header: changelog
          message: |
            ## Changelog Preview
            ${{ steps.changelog.outputs.preview }}
      - name: Warn about missing changelog
        if: steps.changelog.outputs.needs-entry == 'true'
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          header: changelog
          message: |
            ## Missing Changelog Entry
            This PR has commits (`${{ steps.changelog.outputs.commit-types-found }}`) that typically require a changelog entry. Run `changie new` to add one.
```

### read-gleam-workspace

Parse a `workspace.toml` file and output structured package metadata for other actions. Designed as a "pre-step" that generates inputs for `gleam-publish`, `changie-release`, and `auto-tag` from a single source of truth.

```yaml
- uses: tylerbutler/actions/read-gleam-workspace@v1
  id: ws
```

**Workspace file format (`workspace.toml`):**

```toml
[workspace]
members = [".", "packages/my_lib_*"]
exclude = ["packages/my_lib_experimental"]
```

- **members** — Glob patterns or literal paths to package directories. Order is preserved: literal paths stay in declared order, glob matches are sorted alphabetically. Each matched directory must contain a `gleam.toml`.
- **exclude** — Patterns to remove from the expanded member list (optional). Supports globs.

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `working-directory` | `.` | Repository root directory |
| `workspace-file` | `workspace.toml` | Path to workspace config (relative to working-directory) |

**Outputs:**

| Output | Description |
|--------|-------------|
| `packages` | Space-separated package paths in order (for `gleam-publish`) |
| `projects` | Comma-separated package names (for `changie-release`, `auto-tag`) |
| `version-files` | Newline-separated `name:path/gleam.toml:version` entries (for `changie-release`) |
| `packages-json` | JSON array of `{name, path, version}` objects |
| `cache-hash-globs` | Comma-separated paths for `hashFiles()` in cache keys |

**Example (full publish workflow using workspace):**

```yaml
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/read-gleam-workspace@v1
        id: ws
      - uses: tylerbutler/actions/setup-gleam@v1
        with:
          cache: 'false'
      - uses: actions/cache@v4
        with:
          path: |
            build/packages
            ~/.cache/gleam
          key: gleam-${{ runner.os }}-${{ hashFiles(steps.ws.outputs.cache-hash-globs) }}
          restore-keys: gleam-${{ runner.os }}-
      - uses: tylerbutler/actions/gleam-publish@v1
        with:
          packages: ${{ steps.ws.outputs.packages }}
          replace-path-deps: |
            my_lib:gleam.toml
          hex-api-key: ${{ secrets.HEXPM_API_KEY }}
```

**Example (release workflow using workspace):**

```yaml
- uses: tylerbutler/actions/read-gleam-workspace@v1
  id: ws
- uses: tylerbutler/actions/changie-release@v1
  with:
    projects: ${{ steps.ws.outputs.projects }}
    version-files: ${{ steps.ws.outputs.version-files }}
```

**How it works:**

1. Parses `workspace.toml` using Python's `tomllib` (stdlib, zero dependencies)
2. Expands glob patterns in `members`, filters to directories containing `gleam.toml`
3. Applies `exclude` patterns
4. Reads `name`, `version`, and `dependencies` from each package's `gleam.toml`
5. Topologically sorts packages by intra-workspace dependencies (dependencies come before dependents), so `packages` output is always in safe publish order
6. Outputs structured data for downstream action consumption

### run-gleam-workspace

Run a shell command sequentially in each package returned by `read-gleam-workspace`.

This is intended as an **escape hatch** for workspace-wide tasks that do not justify a dedicated action or reusable workflow. For standard Gleam CI, prefer `gleam-workspace-ci.yml`.

```yaml
- uses: tylerbutler/actions/read-gleam-workspace@v1
  id: ws

- uses: tylerbutler/actions/run-gleam-workspace@v1
  with:
    packages-json: ${{ steps.ws.outputs.packages-json }}
    command: gleam deps download
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `packages-json` | *(required)* | JSON array from `read-gleam-workspace` |
| `command` | *(required)* | Shell command to run in each package directory |
| `working-directory` | `.` | Repository root directory |
| `allow-empty` | `false` | Succeed when `packages-json` is empty |

**Outputs:**

| Output | Description |
|--------|-------------|
| `package-count` | Number of packages the command ran in |
| `package-names` | Space-separated package names |
| `package-paths` | Space-separated package paths |

**Example (refresh lockfiles in every package):**

```yaml
- uses: tylerbutler/actions/read-gleam-workspace@v1
  id: ws

- uses: tylerbutler/actions/run-gleam-workspace@v1
  with:
    packages-json: ${{ steps.ws.outputs.packages-json }}
    command: gleam deps download
```

### gleam-publish

Publish Gleam packages to [Hex.pm](https://hex.pm/) in dependency order. Designed for monorepos with multiple Gleam packages — publishes each package sequentially and gracefully skips versions that are already on Hex.

```yaml
- uses: tylerbutler/actions/gleam-publish@v1
  with:
    packages: 'packages/core packages/utils packages/main'
    hex-api-key: ${{ secrets.HEXPM_API_KEY }}
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `packages` | *(required)* | Space-separated package directories in dependency (publish) order. Use `.` for the root package. |
| `working-directory` | `.` | Root directory of the repository |
| `hex-api-key` | *(required)* | Hex.pm API key for authentication |
| `skip-already-published` | `true` | Skip (instead of fail) when a version is already on Hex |
| `replace-path-deps` | `''` | Rewrite path deps to Hex version ranges before publishing (see below) |

**Path dependency rewriting:**

In Gleam monorepos, sub-packages often depend on a root or sibling package via `path` dependencies (e.g., `my_lib = { path = "../.." }`). Hex.pm rejects path dependencies, so they must be rewritten to version ranges before publishing.

The `replace-path-deps` input automates this. It accepts newline-separated entries in the format `dep-name:version-toml-path`:

```yaml
- uses: tylerbutler/actions/gleam-publish@v1
  with:
    packages: >-
      .
      packages/my_lib_apple
      packages/my_lib_google
    replace-path-deps: |
      my_lib:gleam.toml
    hex-api-key: ${{ secrets.HEXPM_API_KEY }}
```

This reads `my_lib`'s version from the root `gleam.toml`, then rewrites any `my_lib = { path = "..." }` entries in sub-packages to a semver-compatible Hex version range before publishing:
- **Pre-1.0** (e.g., `0.3.0`): `my_lib = ">= 0.3.0 and < 0.4.0"`
- **Post-1.0** (e.g., `2.1.0`): `my_lib = ">= 2.1.0 and < 3.0.0"`

**Outputs:**

| Output | Description |
|--------|-------------|
| `published` | Space-separated list of packages that were successfully published |
| `skipped` | Space-separated list of packages skipped (already published) |

**Example (monorepo with root package and path dep rewriting using workspace):**

```yaml
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/read-gleam-workspace@v1
        id: ws
      - uses: tylerbutler/actions/setup-gleam@v1
      - uses: tylerbutler/actions/gleam-publish@v1
        with:
          packages: ${{ steps.ws.outputs.packages }}
          replace-path-deps: |
            my_lib:gleam.toml
          hex-api-key: ${{ secrets.HEXPM_API_KEY }}
```

**Example (monorepo with ordered sub-packages only):**

```yaml
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-gleam@v1
      - uses: tylerbutler/actions/gleam-publish@v1
        with:
          packages: >-
            packages/core
            packages/counters
            packages/sets
            packages/registers
            packages/maps
            packages/umbrella
          hex-api-key: ${{ secrets.HEXPM_API_KEY }}
```

**Example (single package):**

```yaml
- uses: tylerbutler/actions/gleam-publish@v1
  with:
    packages: '.'
    hex-api-key: ${{ secrets.HEXPM_API_KEY }}
```

**How it works:**

1. If `replace-path-deps` is set, rewrites path dependencies to Hex version ranges in all listed packages
2. Iterates through packages in the specified order (dependency order matters!)
3. Reads package name and version from each `gleam.toml`
4. Runs `gleam publish --yes` in each package directory
5. If a version is already on Hex and `skip-already-published` is true, skips gracefully
6. Writes a summary of published/skipped/failed packages to the GitHub Step Summary

## Reusable Workflows

### gleam-workspace-ci

Reusable workflow for Gleam monorepos. It discovers packages from `workspace.toml`, then runs the standard Gleam CI commands in a per-package matrix:

- `gleam format --check src test`
- `gleam check`
- `gleam build --warnings-as-errors`
- `gleam test`
- `gleam docs build` (optional)

```yaml
jobs:
  ci:
    uses: tylerbutler/actions/.github/workflows/gleam-workspace-ci.yml@v1
    with:
      docs: true
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `runs-on` | `ubuntu-latest` | Runner label for all jobs |
| `working-directory` | `.` | Repository root directory |
| `workspace-file` | `workspace.toml` | Path to workspace config |
| `version-file` | `.tool-versions` | Path to version file relative to repo root |
| `version-type` | `strict` | Version matching mode for `setup-gleam` |
| `erlang-version` | `''` | Explicit Erlang version override |
| `gleam-version` | `''` | Explicit Gleam version override |
| `elixir-version` | `''` | Optional Elixir version |
| `rebar-version` | `''` | Optional Rebar3 version |
| `node` | `false` | Setup Node.js for JavaScript target |
| `node-version` | `22` | Node.js version |
| `install-just` | `true` | Install `just` via `setup-gleam` |
| `run-deps` | `true` | Run dependency installation in each package |
| `cache` | `false` | Enable workspace-aware dependency caching for each package job |
| `fail-fast` | `false` | Stop the package matrix on first failure |
| `format-check` | `true` | Run `gleam format --check src test` |
| `check` | `true` | Run `gleam check` |
| `build-strict` | `true` | Run `gleam build --warnings-as-errors` |
| `test` | `true` | Run `gleam test` |
| `docs` | `false` | Run `gleam docs build` |

When `cache` is enabled, the workflow uses an explicit workspace-aware `actions/cache` step keyed by `read-gleam-workspace`'s `cache-hash-globs` output, plus the package name. `setup-gleam`'s built-in cache is disabled here so the reusable workflow controls monorepo invalidation behavior directly.

**Example (full Gleam workspace CI):**

```yaml
jobs:
  ci:
    uses: tylerbutler/actions/.github/workflows/gleam-workspace-ci.yml@v1
    with:
      docs: true
```

**Example (tests only):**

```yaml
jobs:
  ci:
    uses: tylerbutler/actions/.github/workflows/gleam-workspace-ci.yml@v1
    with:
      format-check: false
      check: false
      build-strict: false
      docs: false
```

### auto-tag

Reusable workflow that creates a version tag when a release PR (labeled `release`) is merged. Wraps the `changie-auto-tag` composite action with the standard trigger logic, so consuming repos don't need their own workflow file.

```yaml
name: Auto-tag release

on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  auto-tag:
    uses: tylerbutler/actions/.github/workflows/auto-tag.yml@main
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `changie-version` | `latest` | Changie CLI version to install |
| `working-directory` | `.` | Directory containing `.changie.yaml` |
| `tag-prefix` | `''` | Prefix for the git tag (`changie latest` already includes `v`) |
| `create-release` | `false` | Create a GitHub Release with changie version notes |

**Outputs:**

| Output | Description |
|--------|-------------|
| `version` | Version from `changie latest` |
| `tag` | Full tag that was created |

### binary-size

Measure binary file sizes, compare against a cached baseline from the base branch, and output a markdown report. Language-agnostic — works with any build system that produces files.

```yaml
- uses: tylerbutler/actions/binary-size@v1
  id: size
  with:
    paths: |
      target/release/myapp
      target/release/cli
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `paths` | *(required)* | Newline-separated list of file paths to measure |
| `base-branch` | `main` | Branch to load baseline sizes from for comparison |
| `cache-key-prefix` | `binary-size` | Prefix for cache keys (use different values for independent trackers) |
| `working-directory` | `.` | Working directory for resolving relative paths |

**Outputs:**

| Output | Description |
|--------|-------------|
| `report` | Markdown-formatted size report with deltas |
| `sizes-json` | JSON object mapping file paths to sizes in bytes |
| `total-size` | Total size of all measured files in bytes |
| `total-delta` | Total change vs baseline in bytes (signed integer, 0 when no baseline) |
| `has-baseline` | Whether a baseline was found for comparison |

**Example (Rust project with PR comment):**

```yaml
jobs:
  binary-size:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-rust@v1
      - run: cargo build --release
      - uses: tylerbutler/actions/binary-size@v1
        id: size
        with:
          paths: |
            target/release/myapp
      - name: Comment on PR
        if: github.event_name == 'pull_request'
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          header: binary-size
          message: ${{ steps.size.outputs.report }}
```

**Example (Go project, multiple binaries):**

```yaml
- run: go build -o build/ ./cmd/...
- uses: tylerbutler/actions/binary-size@v1
  id: size
  with:
    paths: |
      build/server
      build/cli
      build/worker
    working-directory: '.'
```

**How it works:**

1. Restores baseline sizes from the GitHub Actions cache (keyed by base branch)
2. Measures current file sizes using `stat`
3. Computes deltas and generates a markdown report table
4. Saves current sizes to cache for future comparisons

The first run on a branch has no baseline, so the report shows sizes only. Once that run's cache is saved, subsequent PRs targeting that branch get delta comparisons.

### download-ccl-tests

Download test data JSON files from [CatConfLang/ccl-test-data](https://github.com/CatConfLang/ccl-test-data) GitHub releases with version tracking to skip unnecessary re-downloads.

```yaml
- uses: tylerbutler/actions/download-ccl-tests@main
  with:
    output-dir: crates/sickle/tests/test_data
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `version` | `latest` | Release version to download (e.g. `v0.6.2`) |
| `force` | `false` | Force re-download even if already at target version |
| `output-dir` | `test_data` | Directory to download test data JSON files into |

**Example (pin to specific version):**

```yaml
- uses: tylerbutler/actions/download-ccl-tests@main
  with:
    version: v0.6.2
    output-dir: tests/test_data
```

## Versioning

Use semantic versioning tags:

```yaml
# Pin to major version (recommended)
- uses: tylerbutler/actions/setup-gleam@v1

# Pin to specific version
- uses: tylerbutler/actions/setup-gleam@v1.0.0

# Latest (not recommended for production)
- uses: tylerbutler/actions/setup-gleam@main
```

## Contributing

1. Make changes to action files
2. Test locally using [act](https://github.com/nektos/act)
3. Create PR with conventional commit message
4. After merge, create a new release tag

## License

MIT
