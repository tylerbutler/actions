# Shared GitHub Actions

Reusable composite actions for CI/CD workflows across repositories.

## Available Actions

### setup-gleam

Setup Gleam/BEAM environment with caching and optional JavaScript target support.

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
| `version-file` | `.tool-versions` | Path to version file |
| `version-type` | `strict` | Version matching: strict or loose |
| `node` | `false` | Setup Node.js for JavaScript target |
| `node-version` | `22` | Node.js version |
| `cache` | `true` | Cache Gleam dependencies |
| `working-directory` | `.` | Working directory |
| `install-just` | `true` | Install just task runner |
| `run-deps` | `true` | Run dependency download |

**Example:**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/setup-gleam@v1
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
| `install-just` | `true` | Install just task runner |

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
| `tag-prefix` | `v` | Prefix for the git tag |
| `token` | `${{ github.token }}` | GitHub token for pushing the tag |

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
