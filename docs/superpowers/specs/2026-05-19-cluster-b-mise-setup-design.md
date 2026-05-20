# Cluster B Design — `mise-setup` standalone action

**Date:** 2026-05-19
**Status:** Approved for planning
**Prior cluster:** `2026-05-18-actions-internal-cohesion-design.md` (Cluster A — merged in PR #43)
**Handoff context:** `docs/superpowers/handoffs/2026-05-19-clusters-b-and-c-handoff.md`

## Scope revision from handoff

The handoff proposed two primitives under Cluster B: `pr-sticky-comment` and `mise-setup`.

`pr-sticky-comment` is **dropped**. The handoff's stated rationale ("lift duplicated sticky-comment logic out of `changie-check` and `binary-size`") does not hold on inspection: neither action contains sticky-comment logic. Both emit markdown outputs (`preview`, `report`) that consumer workflows pass into `marocchino/sticky-pull-request-comment@v2`. No duplication exists to lift. If a real need surfaces later (e.g. Cluster C's release pipeline), revisit.

Cluster B therefore ships **only** `mise-setup`.

## Goal

Lift the `Install mise and tools` step out of `setup-go/action.yml` into a standalone composite action that any setup-* action or consumer workflow can call. Preserve full backward compatibility for `setup-go` consumers.

## Non-goals

- Adding mise hooks to `setup-gleam` or `setup-rust`. They have no current need; add later when a concrete consumer asks.
- Replacing `jdx/mise-action`. This action wraps it; it does not reimplement it.
- Removing or deprecating `setup-go`'s `install-mise` input. It continues to work via internal delegation.

## Action contract

### File layout

```
mise-setup/
└── action.yml
```

No Python helper. No fixture data ships with the action itself (fixtures live under `tests/fixtures/mise-setup/`).

### Inputs

| Input | Default | Notes |
|-------|---------|-------|
| `working-directory` | `.` | Directory containing `.mise.toml` / `.tool-versions`. Passed to `jdx/mise-action`'s `working_directory`. |
| `experimental` | `'true'` | Forwarded as `jdx/mise-action`'s `experimental` input. Matches current `setup-go` usage. |
| `tools` | `''` | Newline-separated ad-hoc tool versions (e.g. `node@22\njq@latest`). Forwarded as `jdx/mise-action`'s `tool_versions`. Useful when no `.mise.toml` exists. |

Newline (not comma) separation chosen because `tool_versions` strings already use `@` and may include other punctuation; commas would force shell-escaping in workflow YAML.

### Outputs

None. `jdx/mise-action` exposes installed tools on `PATH`; consumers invoke them in subsequent steps.

### Steps

1. **Setup mise.** `uses: jdx/mise-action@<ratchet-pinned SHA>` with the three inputs mapped above.
2. **Write step summary.** Inline bash appends to `$GITHUB_STEP_SUMMARY` following the convention documented in `README.md`:
   ```
   ## mise-setup

   Installed: <output of `mise list --current` first line, or "unknown">
   ```

## `setup-go` refactor

Replace the existing inline step at `setup-go/action.yml:57-62` with a delegation to the sibling action:

```yaml
- name: Install mise and tools
  if: inputs.install-mise == 'true'
  uses: ./mise-setup
  with:
    working-directory: ${{ inputs.working-directory }}
```

`experimental` is omitted (matches mise-setup's `'true'` default).

### Cross-action reference notes

`uses: ./mise-setup` inside a composite action resolves relative to the **repository root**, not to the calling action's directory. GitHub fetches the actions repo at the ref that the consumer pinned (e.g. `tylerbutler/actions/setup-go@<sha>`), and the relative path resolves within that fetched tree at the same ref. Both actions therefore move together — no version skew risk.

This pattern is not used elsewhere in the repo today; this design introduces it. The CI smoke matrix (see Testing) verifies the delegation works end-to-end for consumers.

### Backward compatibility

The `install-mise` input on `setup-go` is unchanged. Consumers continue to opt in with `install-mise: true`. Internal implementation change is invisible to them.

## Error handling

No custom validation. If `.mise.toml` is absent and `tools` is empty, `jdx/mise-action` no-ops by design — propagate that behavior. Failures bubble up from the upstream action.

## Testing

### Smoke fixture

`tests/fixtures/mise-setup/.mise.toml`:
```toml
[tools]
jq = "1.7.1"
```

`jq` chosen as a small, fast-installing tool that mise can resolve quickly on both Ubuntu and macOS. Avoid runtime-heavy tools (Node, Python, Erlang) — too slow for smoke.

### CI matrix

Extend `.github/workflows/test.yml` smoke matrix:

- Add `mise-setup` to the `action:` matrix list. Run on `ubuntu-latest` + `macos-latest` (no upstream Apple Silicon issue applies).
- Add steps:
  ```yaml
  - name: mise-setup smoke
    if: matrix.action == 'mise-setup'
    uses: ./mise-setup
    with:
      working-directory: tests/fixtures/mise-setup
  - name: mise-setup assertion
    if: matrix.action == 'mise-setup'
    shell: bash
    run: mise exec -- jq --version
  ```

### setup-go delegation regression

Extend `tests/fixtures/setup-go/` with a `.mise.toml` (same `jq = "1.7.1"` content) and add `install-mise: true` to the existing setup-go smoke step. One cell covers both the legacy input contract and the delegation path. No separate matrix entry needed.

Add an assertion line after the existing setup-go smoke step that confirms `jq` is available, gated by the same matrix condition.

### Out of scope for CI

- **No pytest.** No Python helper exists.
- **No bash integration test under `tests/*-test.sh`.** Composite action is trivial; the smoke matrix is sufficient coverage.

## Documentation

- `README.md`: add `mise-setup` section under "Actions" with an example. Use the established section shape (heading, what it does, inputs table, usage example).
- `CLAUDE.md`: add `mise-setup` row to the "Actions" table in the project overview.

No new internal convention to document — the action follows the step-summary convention introduced in Cluster A.

## Files touched

| File | Change |
|------|--------|
| `mise-setup/action.yml` | NEW — composite action |
| `tests/fixtures/mise-setup/.mise.toml` | NEW — smoke fixture |
| `tests/fixtures/setup-go/.mise.toml` | NEW — delegation regression fixture |
| `setup-go/action.yml` | MODIFIED — replace inline mise step with `./mise-setup` delegation |
| `.github/workflows/test.yml` | MODIFIED — add `mise-setup` to smoke matrix; add `install-mise: true` + assertion to setup-go smoke |
| `README.md` | MODIFIED — add `mise-setup` section and table row |
| `CLAUDE.md` | MODIFIED — add `mise-setup` to actions table |

## Risks

1. **Composite-action `./` resolution under remote consumption.** This pattern is new to the repo. Mitigation: smoke matrix exercises `./setup-go` (which delegates to `./mise-setup`) under CI; once that passes, behavior is verified for the remote-consumption case because `./` resolves identically in both modes.
2. **`jq = "1.7.1"` becoming unavailable upstream.** Low risk — `jq` versions are stable. If it occurs, swap to another small tool in the fixture.

## Out-of-scope follow-ups

- Adding `install-mise` (delegating to `mise-setup`) to `setup-gleam` and `setup-rust` — defer until a real workspace needs it.
- Replacing `marocchino/sticky-pull-request-comment@v2` with an owned action — defer to future cluster; tracked in handoff under "What was NOT discussed (Cluster D+)" for supply-chain hardening.
