# Shared GitHub Actions

Reusable composite actions for CI/CD workflows across repositories.

## Step summaries

Every action in this repo contributes a section to `$GITHUB_STEP_SUMMARY` using a consistent shape:

```markdown
## <Action Name>

<one-sentence outcome>

<optional Markdown body: tables for tabular data, bullet lists otherwise>
```

Skipped or no-op runs still emit a section so the summary is a faithful record of what ran. Python-backed actions use `_common/gha.append_summary`; inline-bash actions append directly to `$GITHUB_STEP_SUMMARY`.

## Available Actions

### setup-trellis

Install an exact prebuilt trellis release, verify its checksum and version, and
add its directory to the next step's `PATH`. `version` is required; `1.3.0` and
`v1.3.0` select the same release. Outputs are `version` (without `v`) and `path`
(the absolute binary path). Installation uses runner temporary storage, outside
your checkout. There is no latest-version or source-build fallback.

```yaml
- uses: tylerbutler/actions/setup-trellis@main
  with:
    version: '1.3.0'
- run: trellis doctor --format github
```

Supported binaries: Linux GNU x86_64/aarch64, macOS x86_64/aarch64, and Windows
x86_64. Unsupported platforms and unavailable releases fail. You own checkout
and Gleam/BEAM/Node setup; this action installs only trellis.

### trellis-workspace

Read an installed trellis workspace with `trellis ci matrix` and `trellis ci
outputs`. Inputs: `working_directory` (`.`), `since` (empty, full workspace),
and `releasable` (`false`, matrix selection only). Outputs: `matrix` (strategy
object), `has_packages`, and JSON arrays `packages`, `releasable`,
`version_files`, `tags`, `series_tags`. Workspace facts cover all members even
when the matrix selects fewer. Package arrays contain names, not paths.

```yaml
jobs:
  discover:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.workspace.outputs.matrix }}
      has_packages: ${{ steps.workspace.outputs.has_packages }}
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # ratchet:actions/checkout@v6
        with:
          fetch-depth: 0
      - uses: tylerbutler/actions/setup-trellis@40890c0
        with:
          version: '1.3.0'
      - uses: tylerbutler/actions/trellis-workspace@main
        id: workspace
        # Omit since for full selection. For affected-only PR checks use:
        # with:
        #   since: ${{ github.event.pull_request.base.sha }}
  test:
    needs: discover
    if: needs.discover.outputs.has_packages == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJSON(needs.discover.outputs.matrix) }}
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # ratchet:actions/checkout@v6
      # Install trellis and the package runtime here; jobs do not share binaries.
      - run: echo "Selected $PACKAGE"
        env:
          PACKAGE: ${{ matrix.name }}
```

`since` includes changed packages and their dependents. Fetch the comparison
ref/SHA and full history; invalid refs, missing history, malformed outputs, and
CLI errors fail instead of returning an empty successful selection.

### trellis-release-pr

Prepare a release with an installed trellis and a clean caller-owned checkout.
Inputs: `working_directory` (`.`), `base` (`main`), `branch` (`release/pending`),
`pre`, multiline `set` and `bump`, and required `token`. Each nonblank override
line is one CLI argument. Empty `pre` leaves the CLI default; `pre: none`
requests promotion. Trellis owns planning, candidate notes, stable rollup,
commits, branch updates, and PR creation. The summary uses its structured
outcome; this action exposes no scraped PR outputs.

```yaml
- uses: tylerbutler/actions/trellis-release-pr@main
  with:
    token: ${{ steps.app.outputs.token }}
    pre: rc
    set: |
      my_package=1.3.0
```

Omit `pre` and overrides for stable preparation. After the first candidate
merges and publishes, use `pre: rc` for the next candidate, then `pre: none`
to promote. Serialize calls to this action: trellis force-updates the designated
remote branch with a lease. It rejects caller changes instead of removing them.
Use a repository-scoped App token with Contents and Pull requests read/write
when pushes and PR creation must trigger ordinary CI. The action configures
both authenticated git and API operations for its process without persisting
credentials. Caller workflows own approval, concurrency, and prior-release gates.

### trellis-tag

Run `trellis tag create` on the caller's approved release checkout. Inputs:
`working_directory` (`.`), `push`, `github_release`, and `dry_run` (all false),
plus `token` for remote operations. `github_release` implies push. Dry-run
performs remote checks when requested but writes no tags/releases.

Trellis reconciles immutable exact tags, moving package/repository series,
release bodies, and retries. Conflicting immutable tags fail. Existing releases
skip; candidate exact tags create GitHub prereleases without moving series
tags, while stable promotion advances the configured series. The action does
not require Hex publication; callers own ordering and concurrency.

```yaml
- uses: tylerbutler/actions/trellis-tag@main
  with:
    push: 'true'
    github_release: 'true'
    token: ${{ github.token }}
```

Use Contents read/write for tags/releases. Git-only bundles retain their
repository paths: trellis validates coverage, but this action does not assemble
or attach an archive. Include required workspace dependency paths in custom
release artifacts. Never retry a completed old release to move series backward;
the reusable release workflow guards that case.

### trellis-check

Run doctor annotations and a branch-scoped changelog check, finish both reports,
then fail if either command fails. Inputs: `working_directory` (`.`),
`check_changelog` (`true`), and required explicit `base`/`head` refs when enabled.
Install trellis and fetch the required history before calling.

```yaml
- uses: tylerbutler/actions/trellis-check@main
  with:
    base: ${{ github.event.pull_request.base.sha }}
    head: ${{ github.event.pull_request.head.sha }}
```

Outputs match trellis 1.3.0: `ok`, `strictness`, `has_entries`, `needs_entry`,
`needs_entry_packages`, `invalid_fragments`, and `preview`. Arrays stay JSON.
`ok` is the changelog verdict; it does not override a failed doctor. Missing
verdicts fail. The summary includes the preview and command outcomes.
`check_changelog: 'false'` runs doctor alone.

Trellis owns fragment attribution and strictness (`error`, `warn`, `off`);
invalid fragments fail under all policies. The action never runs doctor fixes
and works on ordinary fork PRs with Contents read-only. A sticky comment is an
optional caller step that needs its own Pull requests write permission.

### trellis-publish

Publish with installed trellis and caller-provided Gleam/runtime tools.
Inputs: `working_directory` (`.`), exactly one of `package`, `tag`, or
`all_untagged` (`false`), `dry_run` (`false`), and `hex_api_key` for real
publication or authenticated queries. The key is scoped to this step.
The summary reports the CLI outcome; there are no log-derived per-package outputs.

```yaml
- uses: tylerbutler/actions/trellis-publish@main
  with:
    all_untagged: 'true'
    hex_api_key: ${{ secrets.HEXPM_API_KEY }}
```

Trellis owns dependency order, already-published checks, lifecycle selection,
path-dependency requirements, source bundles, build/test validation, retry policy,
and manifest restoration. Named Git-only/workspace packages fail; all-untagged
publishes only Hex lifecycle members. Retry at the same approved release SHA
after partial failure.

`tag` must name an immutable exact package tag, with the matching manifest
version and approved commit checked out. Moving series and repository tags are
not publish selectors. Dry-run still queries Hex and prepares rewrites/bundles;
it does not build/test the combined package or publish it. Callers own commit
approval, serialization, and tagging.

### trellis-release (reusable workflow)

Call `.github/workflows/trellis-release.yml` from your trigger workflow. Require
trellis 1.3.0, an explicit `release_mode` (`hex`, `git_only`, or `mixed`), and
preparation App credentials. Optional inputs: `working_directory`, `base`
(`main`), `release_branch` (`release/pending`), `pre`, multiline `set`/`bump`.
Hex/mixed publication also requires pinned `gleam_version`, `erlang_version`,
and `hex_api_key`. Git-only needs no Hex key or runtime installation.

```yaml
name: Release
on:
  push:
    branches: [main]
  pull_request:
    types: [closed]
    branches: [main]
  workflow_dispatch:
    inputs:
      pre:
        description: Candidate label, none for promotion, or empty for stable
        type: string
        default: ''
      set:
        description: Exact package=version targets, one per line
        type: string
        default: ''
      bump:
        description: Bump overrides, one per line
        type: string
        default: ''
permissions:
  contents: write
  pull-requests: read
  statuses: write
jobs:
  release:
    uses: tylerbutler/actions/.github/workflows/trellis-release.yml@main
    with:
      trellis_version: '1.3.0'
      release_mode: mixed
      gleam_version: '1.13.0'
      erlang_version: '28'
      pre: ${{ inputs.pre }}
      set: ${{ inputs.set }}
      bump: ${{ inputs.bump }}
    secrets:
      app_id: ${{ secrets.RELEASE_APP_ID }}
      app_private_key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}
      hex_api_key: ${{ secrets.HEXPM_API_KEY }}
```

For Git-only, use `release_mode: git_only` and omit the runtime inputs and Hex
secret. Hex and mixed modes publish Hex members first, then tag all releasable
members; workspace-only members have no release. Assemble Git-only artifacts in
your own workflow. Do not add a second tag-triggered publisher to this recipe.

The App needs Contents, Pull requests, and Commit statuses read/write on this
repository. Preparation uses its installation token to trigger ordinary CI.
Publication uses a separate optional `publication_token`, or the workflow token,
with Contents write, Pull requests read, and Commit statuses write. Hex credentials
appear only in the publishing step. Protect the configured base with reviews and
required checks; restrict release-branch pushes and release dispatch access.

#### Approval, ownership, and recovery

The workflow trusts only merged PRs from this repository's designated release
branch to its configured base. It re-reads GitHub state and publishes the
immutable approved merge SHA, never the unmerged branch or current base.
All callers share repository-wide concurrency, no in-progress cancellation, and
`queue: max` (up to 100 pending runs; excess runs cancel). Queue order follows
waiting order, not dispatch order. Dispatch the next candidate after the previous
one merges and completes publication.

Dispatch on the configured base. First candidate: `pre: rc`, `set:
my_package=1.3.0`; next candidate: `pre: rc`; promotion: `pre: none`.
Automatic pushes prepare stable releases but pause for candidates or a reserved
manual request. The workflow writes a pending `trellis/release_request` status
before manual preparation, including promotion and failures before PR creation.
Unrelated pushes cannot replace that request. A successful no-op clears its
reservation; a subsequent release merge ends ownership of earlier requests.

To abandon a manual request, close its PR, then clear the reservation on the
recorded base SHA with a deliberate status update. Fix failures and rerun the
manual preparation or dispatch the intended request again. Do not clear a
reservation to bypass unfinished work.

Publication writes `trellis/release: pending`, then success only after both
publication and tagging finish. Missing, pending, or failed status on the latest
merged release blocks new preparation. Recover by rerunning that merge-event run
at its approved SHA. Partial retries skip Hex versions and reconcile remote tags
and releases. Completed old runs skip publication/tagging, so they cannot move
series tags backward; they retry preparation from current base instead.

During adoption, verify publication, tags, and releases for the latest historical
matching release PR before recording success on its merge SHA:

```sh
gh api --method POST "repos/OWNER/REPO/statuses/$RELEASE_SHA" \
  -f context=trellis/release -f state=success \
  -f description='Historical publication and tagging verified'
```

Do not mark partial or unknown releases successful. With no historical matching
PR, no status seed is needed. Before that first merge the ownership scan reads
full base history; API/rate-limit failures stop preparation. A stable-only
alternative can publish from exact package-tag events using `trellis-publish`
with `tag`; it requires matching approved checkouts and does not use this
publish-then-tag coordinator.

### Gleam workspace CI with trellis

The existing `gleam-workspace-ci.yml` retains its kebab-case inputs and legacy
workspace.toml path when `trellis_version` is empty. An exact version enables
trellis discovery; no workspace.toml is required. A nondefault `workspace-file`
override in trellis mode fails instead of guessing which format you intended.

```yaml
jobs:
  ci:
    uses: tylerbutler/actions/.github/workflows/gleam-workspace-ci.yml@main
    with:
      working-directory: gleam
      trellis_version: '1.3.0'
      trellis_task: ci
      trellis_check: true
      trellis_changelog: true
      trellis_base: ${{ github.event.pull_request.base.sha }}
      trellis_head: ${{ github.event.pull_request.head.sha }}
```

Define `ci` in your workspace tasks; the workflow does not invent a configured
task name. It runs `trellis run <task> <selected-package>` from the workspace
directory and installs trellis in each job that uses it. A task replaces standard
checks by default; set `trellis_task_with_checks: true` to run both, including any
`custom-command`. Runtime/toolchain/cache options and explicit dependency
installation retain their meaning.

Selection defaults to all packages. Set `since` to an explicit comparison ref/SHA
for affected selection with dependents. Trellis-mode checkouts fetch full history;
ensure the requested refs exist. Empty selection skips the matrix job, while
enabled diagnostics still run. `trellis_check` enables doctor; `trellis_changelog`
also requires explicit base/head. Checks use read-only permissions for fork PRs.

### setup-licence-audit

Install the released `licence_audit` escript and optionally set up Erlang/OTP.

```yaml
- uses: tylerbutler/actions/setup-licence-audit@v1
  with:
    version: v1.0.0
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `version` | Required | `licence_audit` GitHub Release tag to install. |
| `setup-beam` | `true` | Set up Erlang/OTP 28 before installing `licence_audit`. |

**Example (default Beam setup):**

```yaml
jobs:
  licence-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-licence-audit@v1
        with:
          version: v1.0.0
      - run: licence_audit check
```

**Example (Beam already installed):**

```yaml
jobs:
  licence-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: erlef/setup-beam@v1
        with:
          otp-version: '28'
      - uses: tylerbutler/actions/setup-licence-audit@v1
        with:
          version: v1.0.0
          setup-beam: 'false'
      - run: licence_audit check
```

**Example (Gleam project):**

```yaml
jobs:
  licence-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-gleam@v1
      - uses: tylerbutler/actions/setup-licence-audit@v1
        with:
          version: v1.0.0
          setup-beam: 'false'
      - run: licence_audit check
```

### setup-gleam

Setup Gleam/BEAM environment with caching, optional Elixir, and optional JavaScript target support.

```yaml
- uses: tylerbutler/actions/setup-gleam@main
  with:
    node: 'true'  # Enable for JavaScript target
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `erlang-version` | `''` | Erlang/OTP version (ignored if version-file set) |
| `gleam-version` | `''` | Gleam version (ignored if version-file set) |
| `elixir-version` | `''` | Elixir version (enables Mix support). Auto-detected from `mix.exs` when unset — see below. |
| `rebar-version` | `''` | Rebar3 version (used with Elixir) |
| `version-file` | `.tool-versions` | Path to version file |
| `version-type` | `strict` | Version matching: strict or loose |
| `node` | `false` | Setup Node.js for JavaScript target |
| `node-version` | `22` | Node.js version |
| `cache` | `true` | Cache Gleam dependencies (and Mix deps when Elixir enabled) |
| `working-directory` | `.` | Working directory |
| `tools` | `just` | Tools to install via taiki-e/install-action (comma-separated) |
| `run-deps` | `true` | Run dependency download |

**Mix auto-detection:** if `mix.exs` is present in `working-directory` and `elixir-version` is unset, Elixir is installed automatically — the version comes from `.tool-versions` if it declares `elixir`, otherwise falls back to `1.17`.

**Example (Gleam only):**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-gleam@main
      - run: just test
```

**Example (Gleam + Elixir):**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-gleam@main
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

      - uses: tylerbutler/actions/setup-gleam@main
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
- uses: tylerbutler/actions/setup-rust@main
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
      - uses: tylerbutler/actions/setup-rust@main
        with:
          components: 'rustfmt,clippy'
      - run: cargo test
```

### setup-node

Setup Node.js with package manager (pnpm, npm, yarn, or bun) and caching.

```yaml
- uses: tylerbutler/actions/setup-node@main
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
| `tools` | `just` | Tools to install via taiki-e/install-action (comma-separated) |
| `run-install` | `true` | Run package install |

**Example:**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-node@main
      - run: pnpm test
```

### setup-go

Setup Go environment with caching and optional [mise](https://mise.jdx.dev/) tool management.

```yaml
- uses: tylerbutler/actions/setup-go@main
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
| `tools` | `just` | Tools to install via taiki-e/install-action (comma-separated) |
| `install-mise` | `false` | Install mise and run mise install for project tools |
| `run-deps` | `true` | Run go mod download |

**Example:**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-go@main
      - run: just test
```

**Example with mise (installs tools from mise.toml):**

```yaml
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-go@main
        with:
          install-mise: 'true'
      - run: just ci
```

### install-tools

Install development tools via [taiki-e/install-action](https://github.com/taiki-e/install-action).

```yaml
- uses: tylerbutler/actions/install-tools@main
  with:
    tools: 'just,cargo-nextest'
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `tools` | `just` | Comma-separated list of tools |

**Supported tools:** See [taiki-e/install-action](https://github.com/taiki-e/install-action#supported-tools)

### mise-setup

Install [mise](https://mise.jdx.dev/) and project-declared tools from `.mise.toml` or `.tool-versions`. Thin wrapper around `jdx/mise-action@v4`.

```yaml
- uses: tylerbutler/actions/mise-setup@main
  with:
    working-directory: server
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `working-directory` | `.` | Directory where mise should run; usually contains `.mise.toml` or `.tool-versions` for project-declared tools |
| `experimental` | `true` | Enable mise experimental features (newer plugins) |
| `tools` | `''` | .tool-versions-style ad-hoc tools (e.g. `node 22`). Forwarded as `tool_versions` |

**Example (project-declared tools):**

Declare tools in `.mise.toml` (or `.tool-versions`) before running them with `mise exec`:

```toml
[tools]
jq = "1.7.1"
```

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/mise-setup@main
      - run: mise exec -- jq --version
```

**Example (ad-hoc tools, no `.mise.toml` needed):**

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/mise-setup@main
        with:
          tools: |
            jq 1.7.1
            yq 4
      - run: mise exec -- jq --version
```

**Note on `setup-go`:** `setup-go` already integrates mise via its `install-mise: true` input — internally it calls `mise-setup`. Consumers of `setup-go` do not need to add `mise-setup` separately.

### changie-release

Batch [changie](https://changie.dev/) changelog entries and create a release pull request. Useful for automating releases in projects that use changie for changelog management.

```yaml
- uses: tylerbutler/actions/changie-release@main
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

The `version-files` input accepts a newline-separated list of `path:key-path` pairs pointing to TOML files that should be updated with the release version (without `v` prefix). TOML dotted key paths are supported, so nested values like Cargo's `[package].version` can be updated with `package.version`.

```yaml
- uses: tylerbutler/actions/changie-release@main
  with:
    version-files: |
      gleam.toml:version
      Cargo.toml:package.version
```

This replaces `version = "..."` in `gleam.toml` and `[package].version` in `Cargo.toml` with the new version. The change is included in the same commit as the changelog update — no extra git operations needed.

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
      - uses: tylerbutler/actions/changie-release@main
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
```

**Example with custom templates:**

```yaml
- uses: tylerbutler/actions/changie-release@main
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
- uses: tylerbutler/actions/changie-auto-tag@main
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `changie-version` | `latest` | Changie CLI version to install |
| `working-directory` | `.` | Directory containing `.changie.yaml` |
| `tag-prefix` | `''` | Prefix for the git tag (`changie latest` already includes `v`) |
| `projects` | `''` | Comma-separated changie project keys for multi-package repos |
| `token` | `${{ github.token }}` | GitHub token for pushing the tag |
| `create-release` | `false` | Create a GitHub Release with changie version notes |
| `wait-for-publish` | `false` | Wait for the downstream publish workflow after each pushed tag |
| `publish-workflow-name` | `Publish` | Workflow to wait for when `wait-for-publish` is `true` |
| `publish-wait-timeout-seconds` | `1800` | Maximum seconds to wait for each tag publish workflow |
| `publish-wait-poll-seconds` | `15` | Seconds between publish workflow status checks |

**Outputs:**

| Output | Description |
|--------|-------------|
| `version` | Version(s) from `changie latest` |
| `tag` | Full tag(s) that were created |
| `created-tags` | Space-separated list of tags actually created |

**Release ownership when `create-release` is `true`:**

`changie-auto-tag` is the sole owner and guaranteed creator of the GitHub Release. It creates the Release as the tag is published, before downstream tag-triggered workflows run, and re-runs skip an existing Release without duplicating or changing it. Publish workflows should only upload assets to the existing Release (for example, `gh release upload <tag> ...`), not call `gh release create`; standalone workflows that may run without this action should use an idempotent guard such as `gh release view <tag> || gh release create <tag> ...`. This ordering also lets `wait-for-publish: true` compose with `create-release: true`.

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
      - uses: tylerbutler/actions/changie-auto-tag@main
```

### changie-check

Check PRs for [changie](https://changie.dev/) changelog entries. Detects PR-added fragments, renders a preview using `changie batch --dry-run`, and reports whether a changelog entry is required based on conventional commit types.

```yaml
- uses: tylerbutler/actions/changie-check@main
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
      - uses: tylerbutler/actions/changie-check@main
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
- uses: tylerbutler/actions/read-gleam-workspace@main
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
| `tag` | `''` | Optional tag name to map to a workspace package |
| `tag-prefix` | `''` | Optional prefix to strip before matching `tag` to package name |

**Outputs:**

| Output | Description |
|--------|-------------|
| `packages` | Space-separated package paths in order (for `gleam-publish`) |
| `projects` | Comma-separated package names (for `changie-release`, `auto-tag`) |
| `version-files` | Newline-separated `name:path/gleam.toml:version` entries (for `changie-release`) |
| `packages-json` | JSON array of `{name, path, version}` objects |
| `cache-hash-globs` | Comma-separated paths for `hashFiles()` in cache keys |
| `tag-package` | Workspace package name matched by `tag` |
| `tag-package-path` | Workspace package path matched by `tag` |

**Example (full publish workflow using workspace):**

```yaml
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/read-gleam-workspace@main
        id: ws
      - uses: tylerbutler/actions/setup-gleam@main
        with:
          cache: 'false'
      - uses: actions/cache@v4
        with:
          path: |
            build/packages
            ~/.cache/gleam
          key: gleam-${{ runner.os }}-${{ hashFiles(steps.ws.outputs.cache-hash-globs) }}
          restore-keys: gleam-${{ runner.os }}-
      - uses: tylerbutler/actions/gleam-publish@main
        with:
          packages: ${{ steps.ws.outputs.packages }}
          replace-path-deps: |
            my_lib:gleam.toml
          hex-api-key: ${{ secrets.HEXPM_API_KEY }}
```

**Example (tag-scoped publish workflow):**

Use `tag` when each pushed package tag should publish only that package. For a
tag like `lattice_counters-v1.1.0`, `tag-package-path` will contain the matching
workspace path, such as `packages/lattice_counters`.

```yaml
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/read-gleam-workspace@main
        id: ws
        with:
          tag: ${{ github.ref_name }}
      - uses: tylerbutler/actions/gleam-publish@main
        with:
          packages: ${{ steps.ws.outputs.tag-package-path }}
          replace-path-deps: |
            my_lib:gleam.toml
          hex-api-key: ${{ secrets.HEXPM_API_KEY }}
```

**Example (release workflow using workspace):**

```yaml
- uses: tylerbutler/actions/read-gleam-workspace@main
  id: ws
- uses: tylerbutler/actions/changie-release@main
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
- uses: tylerbutler/actions/read-gleam-workspace@main
  id: ws

- uses: tylerbutler/actions/run-gleam-workspace@main
  with:
    packages: ${{ steps.ws.outputs.packages }}
    command: gleam deps download
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `packages` | *(required)* | Space-separated package paths from `read-gleam-workspace` |
| `command` | *(required)* | Shell command to run in each package directory |
| `working-directory` | `.` | Repository root directory |

**Example (refresh lockfiles in every package):**

```yaml
- uses: tylerbutler/actions/read-gleam-workspace@main
  id: ws

- uses: tylerbutler/actions/run-gleam-workspace@main
  with:
    packages: ${{ steps.ws.outputs.packages }}
    command: gleam deps download
```

### gleam-publish

Publish Gleam packages to [Hex.pm](https://hex.pm/) in dependency order. Designed for monorepos with multiple Gleam packages — publishes each package sequentially and gracefully skips versions that are already on Hex.

```yaml
- uses: tylerbutler/actions/gleam-publish@main
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
- uses: tylerbutler/actions/gleam-publish@main
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
      - uses: tylerbutler/actions/read-gleam-workspace@main
        id: ws
      - uses: tylerbutler/actions/setup-gleam@main
      - uses: tylerbutler/actions/gleam-publish@main
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
      - uses: tylerbutler/actions/setup-gleam@main
      - uses: tylerbutler/actions/gleam-publish@main
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
- uses: tylerbutler/actions/gleam-publish@main
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
    uses: tylerbutler/actions/.github/workflows/gleam-workspace-ci.yml@main
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
| `tools` | `''` | Tools to install via `setup-gleam` (comma-separated) |
| `run-deps` | `true` | Run dependency installation in each package |
| `cache` | `false` | Enable workspace-aware dependency caching for each package job |
| `fail-fast` | `false` | Stop the package matrix on first failure |
| `format-check` | `true` | Run `gleam format --check src test` |
| `check` | `true` | Run `gleam check` |
| `build-strict` | `true` | Run `gleam build --warnings-as-errors` |
| `test` | `true` | Run `gleam test` |
| `docs` | `false` | Run `gleam docs build` |

When `cache` is enabled, each matrix job uses an explicit workspace-aware `actions/cache` step for that package's `build/packages` directory plus `~/.cache/gleam`. The cache key includes the package name and hashes all workspace `gleam.toml` and `manifest.toml` files. `setup-gleam`'s built-in cache is disabled here so the reusable workflow controls monorepo invalidation behavior directly.

**Example (full Gleam workspace CI):**

```yaml
jobs:
  ci:
    uses: tylerbutler/actions/.github/workflows/gleam-workspace-ci.yml@main
    with:
      docs: true
```

**Example (tests only):**

```yaml
jobs:
  ci:
    uses: tylerbutler/actions/.github/workflows/gleam-workspace-ci.yml@main
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

For monorepos where each tag triggers a package publish workflow, set `wait-for-publish: true` on the reusable `auto-tag.yml` workflow. This makes auto-tag push one tag, wait for the configured publish workflow to succeed for that tag, and only then push the next tag. This preserves dependency order for packages that must be published to a registry before dependents can resolve them.

When `create-release: true` is also set, the wrapped `changie-auto-tag` action creates the GitHub Release before the publish workflow runs. Publish workflows should upload assets to that existing Release instead of creating it themselves.

**Example (workspace auto-tag with ordered package publishing):**

```yaml
jobs:
  auto-tag:
    uses: tylerbutler/actions/.github/workflows/auto-tag.yml@main
    with:
      workspace-file: workspace.toml
      create-release: true
      wait-for-publish: true
      publish-workflow-name: Publish
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `changie-version` | `latest` | Changie CLI version to install |
| `working-directory` | `.` | Directory containing `.changie.yaml` |
| `tag-prefix` | `''` | Prefix for the git tag (`changie latest` already includes `v`) |
| `projects` | `''` | Comma-separated changie project keys for multi-package repos |
| `workspace-file` | `''` | Path to `workspace.toml` relative to `working-directory`; overrides `projects` |
| `create-release` | `false` | Create a GitHub Release with changie version notes |
| `wait-for-publish` | `false` | Wait for the downstream publish workflow after each pushed tag |
| `publish-workflow-name` | `Publish` | Workflow to wait for when `wait-for-publish` is `true` |
| `publish-wait-timeout-seconds` | `1800` | Maximum seconds to wait for each tag publish workflow |
| `publish-wait-poll-seconds` | `15` | Seconds between publish workflow status checks |

**Outputs:**

| Output | Description |
|--------|-------------|
| `version` | Version(s) from `changie latest` |
| `tag` | Full tag(s) that were created |
| `created-tags` | Space-separated list of tags actually created |

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

auto-tag.yml remains available for consumers that only need release-PR merge to tag behavior.

### binary-size

Measure binary file sizes, compare against a cached baseline from the base branch, and output a markdown report. Language-agnostic — works with any build system that produces files.

```yaml
- uses: tylerbutler/actions/binary-size@main
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
      - uses: tylerbutler/actions/setup-rust@main
      - run: cargo build --release
      - uses: tylerbutler/actions/binary-size@main
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
- uses: tylerbutler/actions/binary-size@main
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

### publish-homebrew-formula

Commit a dist-generated Homebrew formula to a tap repo using a **GitHub App installation token** instead of a long-lived personal access token. Designed to be called from a thin reusable workflow registered as a [custom `publish-jobs` entry in `dist-workspace.toml`](https://github.com/axodotdev/cargo-dist/blob/main/book/src/ci/customizing.md#custom-jobs).

```yaml
# .github/workflows/publish-homebrew-tap.yml in the consuming repo
on:
  workflow_call:
    inputs:
      plan:
        required: true
        type: string

jobs:
  publish-homebrew-formula:
    runs-on: ubuntu-22.04
    if: ${{ !fromJson(inputs.plan).announcement_is_prerelease || fromJson(inputs.plan).publish_prereleases }}
    steps:
      - uses: tylerbutler/actions/publish-homebrew-formula@main
        with:
          app-id: ${{ secrets.HOMEBREW_TAP_APP_ID }}
          private-key: ${{ secrets.HOMEBREW_TAP_APP_PRIVATE_KEY }}
          tap-repo: tylerbutler/homebrew-tap
          plan: ${{ inputs.plan }}
```

Then in `dist-workspace.toml`:

```toml
publish-jobs = ["./publish-homebrew-tap"]
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `app-id` | (required) | GitHub App ID; the app must be installed on the tap repo with `contents: write` |
| `private-key` | (required) | GitHub App private key (PEM) |
| `tap-repo` | (required) | Tap repo in `owner/repo` form (e.g. `tylerbutler/homebrew-tap`) |
| `plan` | (required) | dist plan JSON (pass through from the calling reusable workflow) |
| `artifact-pattern` | `artifacts-*` | Pattern for `actions/download-artifact` |
| `commit-user` | `github-actions[bot]` | git `user.name` |
| `commit-email` | `41898282+github-actions[bot]@users.noreply.github.com` | git `user.email` |
| `install-linuxbrew` | `true` | Run `brew style --fix` on each formula before commit |

**Prerequisites:**

1. Create a GitHub App owned by the tap owner. Minimum permissions: `Contents: write`.
2. Install the app on both the source repo (doing the release) and the tap repo.
3. Store the app ID and a generated private key as repo secrets (`HOMEBREW_TAP_APP_ID`, `HOMEBREW_TAP_APP_PRIVATE_KEY`) in the source repo.

The installation token is minted per-run and expires in one hour — no rotation needed.

## Versioning

Use semantic versioning tags:

```yaml
# Pin to major version (recommended)
- uses: tylerbutler/actions/setup-gleam@main

# Pin to specific version
- uses: tylerbutler/actions/setup-gleam@main.0.0

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
