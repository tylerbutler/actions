# Handoff: Clusters B and C

**Date:** 2026-05-19
**Purpose:** Pick up the actions repo improvement work in a fresh session without re-doing the brainstorm.

## Context (read this first)

The actions repo got brainstormed for improvements on 2026-05-18. The full idea list was triaged into three clusters with a deliberate ordering: A → B → C, where each cluster is "internal" enough to ship independently but each later cluster benefits from earlier ones landing.

**Cluster A — DONE.** Shipped via PR #43 (branch `agents`, ready to merge).
- Spec: `docs/superpowers/specs/2026-05-18-actions-internal-cohesion-design.md`
- Plan: `docs/superpowers/plans/2026-05-18-actions-internal-cohesion.md`
- What landed: `_common/gha.py` (write_output, fail, append_summary, update_toml_top_level_key, parse_colon_entries) with 20 tests; 7 action helpers migrated off duplicated copies; uniform `$GITHUB_STEP_SUMMARY` convention documented and adopted across most actions; `setup-gleam` auto-detects Mix from `mix.exs` and resolves Elixir from `.tool-versions` with a `1.17` fallback; new `.github/workflows/test.yml` runs pytest matrix + bash integration tests + smoke matrix for `setup-*` actions on Ubuntu + macOS. All 12 CI jobs green.

**Cluster B — NOT STARTED.** This document.

**Cluster C — NOT STARTED.** This document.

## Cluster B — new small actions

### Goal
Add two small, independent primitives the rest of the repo can build on. Each is a standalone composite action.

### B.1 — `pr-sticky-comment` action

**Intent.** A generic "post or update a single sticky PR comment" helper. Today, both `changie-check` and `binary-size` each implement their own version of "find my comment by marker, edit it if it exists, otherwise create it." Extracting this gives:
- A reusable primitive for future actions (release-PR previews, diff renders, etc.).
- A refactor target so the two existing duplicators can drop their inline logic.

**Inputs (proposed; confirm during brainstorm):**
- `pr-number` (required) — PR to comment on.
- `marker` (required) — hidden HTML comment used to find and re-edit the comment (e.g., `<!-- changie-preview -->`).
- `body` (required) — the comment markdown.
- `mode` — `upsert` (default) or `append`. Append concatenates rather than replacing.
- `github-token` — default `${{ github.token }}`.

**Implementation sketch.** Python helper at `pr-sticky-comment/sticky_comment.py`. Uses `gh api` (already on every runner) or direct REST. Sourced via the established `_common/gha` pattern.

**Dependencies.** None for landing. After it lands, follow-up: migrate `changie-check` and `binary-size` to consume it. That follow-up could be part of the same PR or a separate one.

**Open questions for brainstorm:**
- `gh api` (rely on the GitHub CLI being present) vs raw `curl + REST` (no tool dependency)? gh is on every GH runner; curl is more portable but more code.
- Should `mode: append` exist on day one, or YAGNI it?
- Behavior when the PR is closed / lacks write permission? Fail or warn?

### B.2 — standalone `mise-setup` action

**Intent.** Lift the `Install mise and tools` step out of `setup-go/action.yml` into its own action. Today it's coupled to setup-go; it should be a standalone primitive any language setup can use.

**Inputs (proposed; confirm during brainstorm):**
- `working-directory` — default `.`. Where the `.mise.toml` / `.tool-versions` lives.
- `experimental` — default `true` (matches current setup-go usage).
- Possibly a `tools` input for ad-hoc additions.

**Implementation sketch.** Thin wrapper around `jdx/mise-action`. Composite action, ~10 lines. The existing setup-go step gets refactored to call `./mise-setup` instead of inlining mise — backward-compatible since `setup-go`'s `install-mise` input keeps the same semantics.

**Dependencies.** None.

**Open questions for brainstorm:**
- Keep `install-mise` input on `setup-go` for backward compatibility, or deprecate it?
- Should `setup-gleam` and `setup-rust` also gain optional mise hooks via this new primitive, or hold off?

### Suggested cluster scope

One spec covering both B.1 and B.2 is fine — they're independent but small. Land each as its own commit chain inside one PR. Estimated 1 working session for spec + plan + execute.

## Cluster C — release reusable workflow

### Goal
One entry-point reusable workflow that composes the existing release pieces into an end-to-end pipeline. Today, every consumer repo writes its own boilerplate wiring `changie-release` → merge → `auto-tag` → publish; this collapses that into a single `uses:` line with knobs.

### Sketch

```yaml
# In a consumer repo
jobs:
  release:
    uses: tylerbutler/actions/.github/workflows/release.yml@main
    with:
      publish-to: hex,homebrew    # or any combination of: hex, homebrew, crates, npm
      projects: my-pkg,my-pkg-plugin   # optional; for changie multi-project
      version-files: |
        my-pkg:Cargo.toml:version
        my-pkg-plugin:packages/my-pkg-plugin/Cargo.toml:version
    secrets:
      HEX_API_KEY: ${{ secrets.HEX_API_KEY }}
      HOMEBREW_APP_PRIVATE_KEY: ${{ secrets.HOMEBREW_APP_PRIVATE_KEY }}
```

**Phases the workflow orchestrates:**
1. On PR merge (release PR closing) → `changie-auto-tag` to push tag(s).
2. On tag push → publish to each target in `publish-to` (Hex via `gleam-publish`, Homebrew via `publish-homebrew-formula`, future: crates via cargo, npm via npm publish).
3. On every PR → `changie-check` posts a sticky preview comment (uses `pr-sticky-comment` from Cluster B once landed).

**Why it benefits from A and B:**
- A's `_common/gha` and `append_summary` mean the orchestrator can write a single coherent step summary across the whole pipeline.
- B's `pr-sticky-comment` is the natural place to render the release-PR preview body.

**Open questions for brainstorm:**
- Single workflow with branching `if:` per phase, or three separate reusable workflows (one per trigger: PR / merge / tag) that compose? The repo already has `auto-tag.yml` as a reusable workflow — does this replace it or wrap it?
- How to expose secrets cleanly? The reusable workflow needs `secrets: inherit` or explicit `secrets:` declarations for each publish target.
- Should `publish-to: crates` and `publish-to: npm` be in scope for v1, or define the interface now and add adapters later?
- Concurrency policy — `concurrency: group: release-${{ github.ref }}, cancel-in-progress: false`?

### Suggested cluster scope

One spec, one plan, one PR. Bigger than B — estimate 1–2 sessions for spec + plan, then execution. Don't try to land it the same day as the spec; the design will benefit from sleeping on it.

## How to start the next session

Open the actions repo, then invoke the brainstorming skill on whichever cluster comes next:

> "Let's brainstorm Cluster B from `docs/superpowers/handoffs/2026-05-19-clusters-b-and-c-handoff.md`."

The brainstorming skill should:
1. Read this handoff and the Cluster A spec/plan for context.
2. Read the relevant action files (`changie-check/`, `binary-size/`, `setup-go/`) so its design proposals are grounded.
3. Ask the open questions above one at a time.
4. Produce a Cluster B spec at `docs/superpowers/specs/YYYY-MM-DD-cluster-b-new-primitives-design.md`.
5. Plan and execute via the same flow used for A.

## Pointers to grounding files

When starting B or C, read these first:

- `docs/superpowers/specs/2026-05-18-actions-internal-cohesion-design.md` — Cluster A spec, sets the conventions B/C build on.
- `docs/superpowers/plans/2026-05-18-actions-internal-cohesion.md` — Cluster A plan, shows the TDD/commit cadence pattern to mirror.
- `_common/gha.py` — what's already available for shared Python utilities.
- `README.md` — section "Step summaries" documents the convention every new action must follow.
- `CLAUDE.md` — section "Internal conventions" covers the `_common` import pattern, summary writes, and CI expectations.
- `.github/workflows/test.yml` — pattern for adding CI for new actions (pytest, bash integration tests, smoke).
- `.github/workflows/auto-tag.yml` — existing reusable workflow; reference for shape when designing C's release workflow.

For Cluster B's `pr-sticky-comment` specifically:
- `changie-check/changie_check.py` — has the current sticky-comment implementation worth lifting.
- `binary-size/binary_size.py` — second consumer; check it ships a similar implementation before designing the abstraction.

For Cluster B's `mise-setup` specifically:
- `setup-go/action.yml` — the existing inline mise step (around the "Install mise and tools" name).

## What was deferred during Cluster A (worth knowing)

Two follow-ups were intentionally deferred during Cluster A execution. They are NOT part of B or C but worth tracking:

1. **Per-subcommand step summaries** for the multi-subcommand Python actions: `changie-release`, `changie-auto-tag`, `changie-check`, `binary-size`. They have `gha.append_summary` available, but each subcommand's outcome line needs design work the Cluster A spec didn't pin down. Could be its own small PR, or rolled into Cluster C since C's release workflow will surface these summaries prominently.

2. **upstream `erlef/setup-beam` does not work on macos-latest (Apple Silicon)** for the Erlang/Gleam versions in our smoke fixture. The Cluster A CI workflow excludes that matrix cell with a tracking comment. Re-enable when upstream supports it.

## What was NOT discussed but could be future cluster D+

The original brainstorm included items that didn't make any of A/B/C and remain undone:

- **Supply-chain hardening pass** — audit each action for default-deny `permissions:`, per-step token scoping, OIDC for publishers that support it (Homebrew/crates/npm; Hex doesn't), Sigstore/SLSA provenance. High-value, mostly mechanical.
- **Concurrency-group conventions** — document/expose the recommended `concurrency:` pattern for release flows. Partially absorbed into Cluster C as an open question, but worth its own treatment.
- **`setup-ocaml`** — new action for OCaml/dune (workspace has `ccl-ocaml` that could use it).

These are valid future clusters but not pre-scoped. Treat as fresh brainstorm fodder if the user asks "what's next after C?"
