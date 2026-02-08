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
