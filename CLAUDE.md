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
| `changie-release` | Batch changie entries and create release PR |
| `changie-auto-tag` | Create version tag from latest changie release |

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

## Changie Action Gotchas

- `changie latest` returns versions with `v` prefix - `changie-auto-tag` default `tag-prefix` is empty to avoid `vv` tags. The `tag-prefix` input exists for monorepo/multi-package repos where tags need a package prefix (e.g. `mypackage/v1.0.0`)
- `changie batch auto` exits non-zero when no unreleased fragments exist - `changie-release` pre-checks the unreleased directory before calling batch
- `changie-release` reads `.changie.yaml` to find the unreleased directory path (`changesDir`/`unreleasedDir`)
- PR body template supports `{version}` and `{changelog}` variables resolved via bash substitution
- `changie-release` supports `version-files` input for bumping version in TOML files (only TOML is supported). Format: `path:key` per line, e.g. `gleam.toml:version`. Only top-level keys are supported. Changes are included in the same commit as the changelog update via `peter-evans/create-pull-request`
- `changie-auto-tag` supports optional `create-release` input to create a GitHub Release with changie version notes. Uses `.changes/{version}.md` as release notes if available, falls back to `--generate-notes`

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
