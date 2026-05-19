# Actions repo internal cohesion (Cluster A)

**Date:** 2026-05-18
**Status:** Draft for review
**Scope:** Internal-only changes to `tylerbutler/actions` that make the repo itself follow the discipline it provides to consumers. No changes to any action's public input/output contract.

## Motivation

The repo currently ships 14 composite actions and 2 reusable workflows, all consumed by other repos in this workspace. Recent commits show good investment in moving fragile bash to Python (`6d63f11 refactor: port fragile bash logic to python across composite actions`), but the supporting infrastructure has gaps:

1. **No CI.** Per-action `pytest` suites and `tests/*-test.sh` integration tests exist, but nothing runs them on push or PR. Regressions can land silently.
2. **Drifting helpers.** `_write_output`, `_fail`, `_append_summary`, and `update_toml_top_level_key` are duplicated verbatim across action Python scripts. The TOML-update function has *two implementations* (one in `update-version-files/`, one in `changie-release/`), which is the canonical symptom that dedup is overdue.
3. **Inconsistent observability.** Some actions write to `$GITHUB_STEP_SUMMARY`, some don't; the ones that do use different conventions.
4. **One small `setup-gleam` polish.** Mix support exists but only activates when `elixir-version` is explicitly passed, even when `mix.exs` is sitting right there.

This spec addresses all four with minimal surface change.

## Goal

Land tests in CI, extract a small shared Python utility module, document and adopt a uniform step-summary convention, and auto-detect Mix in `setup-gleam`.

Out of scope:
- Any change to action inputs, outputs, or runtime behavior visible to consumers (other than richer step summaries and Mix auto-detect, both additive).
- Repackaging the shared helpers as a pip-installable Python package.
- New actions or removal of existing ones.
- Documentation rewrites beyond what these changes require.

## Design

### 1. CI workflow

New file: `.github/workflows/test.yml`. Triggers on `push` to `main` and on `pull_request`. Three jobs run in parallel:

**Job: `pytest`**
- Matrix: Python 3.11 and 3.13 on `ubuntu-latest`.
- Uses `actions/setup-python` with pip caching.
- Discovers and runs `pytest` against the repo root; collects `*/test_*.py` across all action directories and `_common/`.
- No tests are skipped or marked xfail by default.

**Job: `bash-tests`**
- Single runner: `ubuntu-latest`.
- Runs each script in `tests/*-test.sh` in turn. Each script already provisions its own tmp fixture and cleans up via `trap`.
- Failure of any individual script fails the job.

**Job: `smoke`**
- Matrix: `ubuntu-latest` and `macos-latest` for `setup-*` actions; Linux-only for `install-tools` and `run-gleam-workspace`.
- For each composite action without a Python helper, the job runs `uses: ./<action-name>` against a minimal fixture under `tests/fixtures/<action>/`, then asserts:
  - exit code is 0,
  - the expected tool is on `PATH` (e.g., `gleam --version`, `go version`),
  - one or two key outputs are non-empty.
- Covers: `setup-gleam`, `setup-go`, `setup-rust`, `setup-node`, `install-tools`, `run-gleam-workspace`.

Any failed job blocks merge (enforced via branch protection, configured out-of-band).

### 2. Shared Python utilities (`_common/`)

New directory at repo root: `_common/`. Contains a single module today, room to grow.

```
_common/
├── gha.py
└── test_gha.py
```

`gha.py` exports:

| Function | Replaces | Notes |
|---|---|---|
| `write_output(key: str, value: str) -> None` | `_write_output` in 4+ scripts | Multi-line safe — uses random heredoc delimiter for values containing newlines. |
| `fail(message: str, code: int = 1) -> NoReturn` | `_fail` in 4+ scripts | Writes `::error::` annotation + raises `SystemExit`. |
| `append_summary(markdown: str) -> None` | `_append_summary` in `gleam-publish` | Single sink for `$GITHUB_STEP_SUMMARY`. Tolerates summary file being unset (local runs). |
| `update_toml_top_level_key(content: str, key: str, value: str) -> str` | Duplicated in `update-version-files` and `changie-release` | Single canonical implementation. Preserves comments and ordering. |
| `parse_colon_entries(text: str, fields: int) -> list[tuple[str, ...]]` | `parse_entries` / `parse_replace_path_deps` / `parse_version_files` | Splits newline-separated, colon-delimited input. Caller specifies expected field count; raises with a precise error on mismatch. |

**Consumption pattern.** Each action's Python helper begins:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import write_output, fail, append_summary  # noqa: E402
```

No pip install, no packaging. The path injection is a one-liner and matches how GitHub composite actions conventionally source helpers from sibling directories via `$GITHUB_ACTION_PATH`. The trade-off (mildly ugly import) is worth the simplicity (no install step on every action invocation).

**Testing.** `_common/test_gha.py` provides direct unit coverage. The existing per-action pytest suites continue to pass after migration — proving the refactor is behaviour-preserving.

**Migration strategy.** Per-action and incremental. Landing `_common/` does not require touching every consumer at once; this spec migrates all current consumers in one sweep, but future Python helpers adopt it from day one without coordination.

### 3. Uniform `$GITHUB_STEP_SUMMARY` convention

Documented in `README.md` and `CLAUDE.md`; not enforced syntactically.

Every action writes one section:

```markdown
## <Action Name>

<one-sentence result>

<optional Markdown body: tables for tabular data, bullet lists otherwise>
```

Conventions:
- The header is the action's display name (matches `name:` in its `action.yml`).
- The first body line is a single-sentence outcome — "Published 3 packages", "No unreleased changes, skipping", "Set Erlang 28, Gleam 1.13".
- Skipped or no-op runs still emit a section so the summary is a faithful record.
- The single mechanism is `gha.append_summary()`. Actions that don't currently write summaries acquire one in this sweep.

For composite actions with no Python helper (`setup-*`, `install-tools`), the summary is written from a final inline `bash` step using `echo "..." >> "$GITHUB_STEP_SUMMARY"`. Small enough to not need a helper.

### 4. Auto-detect Mix in `setup-gleam`

Today, Elixir support activates only when `elixir-version` is explicitly set. Change: if `working-directory` contains `mix.exs` and `elixir-version` is unset:

1. If `.tool-versions` is present and declares an `elixir` line, use that version.
2. Otherwise, fall back to a static workspace default: `1.17`.

Implementation: a new step before the BEAM-setup steps that reads `.tool-versions` (if present) and exports a resolved `elixir-version` to subsequent steps via `$GITHUB_OUTPUT`. Existing `if:` conditions on the BEAM-setup steps update to consume the resolved value.

The static fallback version is captured as a single constant in `setup-gleam/action.yml` so future bumps are a one-line change. Document the behaviour in the action's section of `README.md`.

## File changes

```
NEW   .github/workflows/test.yml                       # CI workflow
NEW   _common/gha.py                                   # shared utilities
NEW   _common/test_gha.py                              # pytest for shared utils
NEW   tests/fixtures/setup-gleam/                      # minimal Gleam project
NEW   tests/fixtures/setup-go/                         # minimal Go module
NEW   tests/fixtures/setup-rust/                       # minimal Cargo project
NEW   tests/fixtures/setup-node/                       # minimal package.json
NEW   tests/fixtures/install-tools/                    # placeholder + tool list
NEW   tests/fixtures/run-gleam-workspace/              # minimal workspace.toml
EDIT  changie-release/changie_release.py               # migrate to _common
EDIT  changie-auto-tag/changie_auto_tag.py             # migrate to _common
EDIT  changie-check/changie_check.py                   # migrate to _common
EDIT  gleam-publish/gleam_publish.py                   # migrate to _common
EDIT  binary-size/binary_size.py                       # migrate to _common
EDIT  update-version-files/update_version_files.py     # drop local TOML fn, use _common
EDIT  read-gleam-workspace/parse_workspace.py          # migrate to _common
EDIT  setup-gleam/action.yml                           # Mix auto-detect
EDIT  README.md                                        # document summary convention + CI
EDIT  CLAUDE.md                                        # _common, summary convention, CI
```

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Smoke tests flaky due to upstream registry latency (Hex, crates.io) | Cache aggressively (`actions/cache`); fixtures pin tiny dep sets; allow re-runs; macOS only where it matters for setup-*. |
| `_common/` sys.path injection feels hacky | One-line pattern, documented in `CLAUDE.md`. The alternatives (pip-install on every action run, symlinks) trade simplicity for marginal aesthetic gain. |
| Mix auto-detect changes behaviour for existing consumers with stray `mix.exs` files | Limited to the case where `elixir-version` is *unset* — anyone who explicitly opted out by leaving it blank keeps the old behaviour. Documented in CHANGELOG-style README note. |
| TOML-update function consolidation risks regressing one of the two existing implementations | Both have pytest coverage; reconcile by running both test suites against the canonical version, fixing any behaviour differences as discovered. |

## Test plan

Self-verification of this work:

- All pre-existing `pytest` tests pass after migration to `_common`.
- All `tests/*-test.sh` scripts pass on a fresh checkout.
- The new `test.yml` workflow runs green on a no-op PR.
- Smoke tests fail when an `action.yml` is intentionally corrupted (verify, then revert).
- A test repo consuming `setup-gleam@<this-branch>` with a `mix.exs` and no `elixir-version` input successfully installs Elixir.
- A test repo consuming `setup-gleam@<this-branch>` *without* `mix.exs` and no `elixir-version` does *not* install Elixir (behaviour preserved).

## Out of scope (future work)

This spec is Cluster A of three. Subsequent specs:

- **Cluster B**: new primitives (`pr-sticky-comment`, standalone `mise-setup`).
- **Cluster C**: end-to-end release reusable workflow composing existing actions.

Cluster A's `_common/` and summary convention are load-bearing for both.
