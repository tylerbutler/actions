# Cluster B `mise-setup` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a standalone `mise-setup` composite action and refactor `setup-go` to delegate to it internally, preserving its `install-mise` input contract.

**Architecture:** Thin composite-action wrapper around `jdx/mise-action@v4`. `setup-go/action.yml`'s existing inline mise step becomes `uses: ./mise-setup`. GitHub resolves the sibling-action path within the actions repo at the same ref a consumer pinned, so the two move together. No Python helper; inline-bash step summary follows the established convention.

**Tech Stack:** GitHub Actions composite syntax, `jdx/mise-action@v4`, inline bash for step summary, smoke matrix in `.github/workflows/test.yml` for verification.

**Spec:** `docs/superpowers/specs/2026-05-19-cluster-b-mise-setup-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `mise-setup/action.yml` | NEW | Composite action wrapping `jdx/mise-action@v4` |
| `tests/fixtures/mise-setup/.mise.toml` | NEW | Smoke fixture (installs `jq`) |
| `tests/fixtures/setup-go/.mise.toml` | NEW | Delegation regression fixture (same `jq`) |
| `setup-go/action.yml` | MODIFY | Replace inline `jdx/mise-action` step with `uses: ./mise-setup` |
| `.github/workflows/test.yml` | MODIFY | Add `mise-setup` to smoke matrix; extend `setup-go` smoke with `install-mise: true` + `jq` assertion |
| `README.md` | MODIFY | Add `mise-setup` section under "Available Actions" |
| `CLAUDE.md` | MODIFY | Add `mise-setup` row to Actions table |

---

## Task 1: Add mise-setup smoke matrix entry (red — action does not exist yet)

**Files:**
- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: Add `mise-setup` to the matrix `action:` list**

Open `.github/workflows/test.yml`. Find the `smoke` job's matrix (around line 47):

```yaml
matrix:
  action: [setup-gleam, setup-go, setup-rust, setup-node]
  os: [ubuntu-latest, macos-latest]
```

Add `mise-setup` to the list:

```yaml
matrix:
  action: [setup-gleam, setup-go, setup-rust, setup-node, mise-setup]
  os: [ubuntu-latest, macos-latest]
```

- [ ] **Step 2: Add smoke + assertion steps for mise-setup**

After the `install-tools assertion` step (around line 112), and before `run-gleam-workspace smoke`, insert:

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

- [ ] **Step 3: Do NOT commit yet — this change introduces a reference to a not-yet-created action. Proceed to Task 2.**

---

## Task 2: Create mise-setup action + fixture (green)

**Files:**
- Create: `mise-setup/action.yml`
- Create: `tests/fixtures/mise-setup/.mise.toml`

- [ ] **Step 1: Create the fixture directory and file**

```bash
mkdir -p tests/fixtures/mise-setup
```

Create `tests/fixtures/mise-setup/.mise.toml`:

```toml
[tools]
jq = "1.7.1"
```

- [ ] **Step 2: Create `mise-setup/action.yml`**

```yaml
name: 'Setup mise and tools'
description: 'Install mise and project-declared tools (.mise.toml / .tool-versions) or ad-hoc tools'

inputs:
  working-directory:
    description: 'Directory containing .mise.toml or .tool-versions'
    required: false
    default: '.'
  experimental:
    description: 'Enable mise experimental features (newer plugins, etc.)'
    required: false
    default: 'true'
  tools:
    description: |
      Newline-separated ad-hoc tool versions, e.g.
        node@22
        jq@latest
      Forwarded to jdx/mise-action as `tool_versions`. Useful when no .mise.toml exists.
    required: false
    default: ''

runs:
  using: composite
  steps:
    - name: Setup mise
      uses: jdx/mise-action@1648a7812b9aeae629881980618f079932869151 # ratchet:jdx/mise-action@v4
      with:
        experimental: ${{ inputs.experimental }}
        working_directory: ${{ inputs.working-directory }}
        tool_versions: ${{ inputs.tools }}

    - name: Write step summary
      shell: bash
      run: |
        installed=$(mise list --current 2>/dev/null | head -1 || echo "unknown")
        {
          echo "## mise-setup"
          echo
          echo "Installed: ${installed}"
        } >> "$GITHUB_STEP_SUMMARY"
```

Note: the `jdx/mise-action@v4` SHA `1648a7812b9aeae629881980618f079932869151` is reused from `setup-go/action.yml:59`. Keep them in sync.

- [ ] **Step 3: Validate YAML locally**

```bash
python3 -c "import yaml; yaml.safe_load(open('mise-setup/action.yml'))"
python3 -c "import yaml; yaml.safe_load(open('tests/fixtures/mise-setup/.mise.toml')) if False else None"
# .mise.toml is TOML — validate separately:
python3 -c "import tomllib; tomllib.load(open('tests/fixtures/mise-setup/.mise.toml','rb'))"
```

Both should exit 0.

- [ ] **Step 4: Commit Task 1 + Task 2 together**

```bash
git add mise-setup/action.yml tests/fixtures/mise-setup/.mise.toml .github/workflows/test.yml
git commit -m "feat(mise-setup): add standalone action wrapping jdx/mise-action

New composite action lifts mise installation into a reusable
primitive. Smoke matrix entry installs jq via fixture .mise.toml
and asserts \`mise exec -- jq --version\` works on Ubuntu + macOS."
```

- [ ] **Step 5: Push and verify CI green for the new smoke matrix cells**

```bash
git push
```

Watch the `smoke (mise-setup on ubuntu-latest)` and `smoke (mise-setup on macos-latest)` jobs. Both must pass before continuing.

If either fails, do NOT proceed to Task 3. Investigate and fix the action.yml or fixture.

---

## Task 3: Extend setup-go smoke with install-mise (still green via inline step)

**Files:**
- Create: `tests/fixtures/setup-go/.mise.toml`
- Modify: `.github/workflows/test.yml`

This task adds the regression coverage that will catch breakage when we refactor `setup-go` in Task 4. It must stay green now (inline mise step still works) and after Task 4 (delegated mise step works).

- [ ] **Step 1: Create the setup-go mise fixture**

Create `tests/fixtures/setup-go/.mise.toml`:

```toml
[tools]
jq = "1.7.1"
```

- [ ] **Step 2: Update the setup-go smoke step to enable mise**

In `.github/workflows/test.yml`, find the `setup-go smoke` step (around line 75):

```yaml
      - name: setup-go smoke
        if: matrix.action == 'setup-go'
        uses: ./setup-go
        with:
          working-directory: tests/fixtures/setup-go
          go-version-file: tests/fixtures/setup-go/go.mod
          run-deps: 'false'
          cache: 'false'
```

Add `install-mise: 'true'`:

```yaml
      - name: setup-go smoke
        if: matrix.action == 'setup-go'
        uses: ./setup-go
        with:
          working-directory: tests/fixtures/setup-go
          go-version-file: tests/fixtures/setup-go/go.mod
          run-deps: 'false'
          cache: 'false'
          install-mise: 'true'
```

- [ ] **Step 3: Add a jq assertion after the existing go assertion**

Below the existing setup-go assertion:

```yaml
      - name: setup-go assertion
        if: matrix.action == 'setup-go'
        run: go version
```

Append:

```yaml
      - name: setup-go mise assertion
        if: matrix.action == 'setup-go'
        shell: bash
        working-directory: tests/fixtures/setup-go
        run: mise exec -- jq --version
```

`working-directory` is required because mise resolves `.mise.toml` from the current directory.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/setup-go/.mise.toml .github/workflows/test.yml
git commit -m "test(setup-go): cover install-mise path in smoke matrix

Adds .mise.toml fixture and asserts \`mise exec -- jq --version\`
works after setup-go runs with install-mise: true. This locks in
the current inline mise behavior before refactoring to delegate
to mise-setup."
```

- [ ] **Step 5: Push and verify**

```bash
git push
```

Both `smoke (setup-go on ubuntu-latest)` and `smoke (setup-go on macos-latest)` must pass. If either fails, the inline mise step is broken — fix before continuing.

---

## Task 4: Refactor setup-go to delegate to mise-setup

**Files:**
- Modify: `setup-go/action.yml`

This is the meaningful change. The smoke from Task 3 will catch any regression — if it stays green after this commit, delegation works.

- [ ] **Step 1: Replace the inline mise step**

In `setup-go/action.yml`, find lines 57-62:

```yaml
    - name: Install mise and tools
      if: inputs.install-mise == 'true'
      uses: jdx/mise-action@1648a7812b9aeae629881980618f079932869151 # ratchet:jdx/mise-action@v4
      with:
        experimental: true
        working_directory: ${{ inputs.working-directory }}
```

Replace with:

```yaml
    - name: Install mise and tools
      if: inputs.install-mise == 'true'
      uses: ./mise-setup
      with:
        working-directory: ${{ inputs.working-directory }}
```

`experimental` is omitted because `mise-setup`'s default is `'true'` — same effective behavior.

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('setup-go/action.yml'))"
```

Exit 0.

- [ ] **Step 3: Commit**

```bash
git add setup-go/action.yml
git commit -m "refactor(setup-go): delegate mise installation to mise-setup

Replaces the inline jdx/mise-action step with \`uses: ./mise-setup\`.
The \`install-mise\` input is unchanged — consumers keep the same
contract. The smoke matrix cell added in the prior commit verifies
the delegation works on Ubuntu and macOS."
```

- [ ] **Step 4: Push and verify**

```bash
git push
```

`smoke (setup-go on ubuntu-latest)` and `smoke (setup-go on macos-latest)` must remain green. This proves the `./mise-setup` cross-action reference resolves correctly.

If either fails, the delegation is broken. Most likely cause: GitHub's composite-action path resolution differs from expectations. Investigate before continuing.

---

## Task 5: Document mise-setup in README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Insert a `### mise-setup` section after `### install-tools`**

In `README.md`, find the `### install-tools` section (starts around line 224). After its closing example block and before the next `###` heading, insert:

```markdown
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
| `working-directory` | `.` | Directory containing `.mise.toml` / `.tool-versions` |
| `experimental` | `true` | Enable mise experimental features (newer plugins) |
| `tools` | `''` | Newline-separated ad-hoc tools (e.g. `node@22`). Forwarded as `tool_versions` |

**Example (project-declared tools):**

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/mise-setup@main
      - run: mise exec -- jq --version
```

**Example (ad-hoc tools, no .mise.toml needed):**

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: tylerbutler/actions/mise-setup@main
        with:
          tools: |
            jq@1.7.1
            yq@4
      - run: mise exec -- jq --version
```

**Note on `setup-go`:** `setup-go` already integrates mise via its `install-mise: true` input — internally it calls `mise-setup`. Consumers of `setup-go` do not need to add `mise-setup` separately.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): document mise-setup action"
```

- [ ] **Step 3: Push**

```bash
git push
```

No CI gate needed — docs-only change.

---

## Task 6: Update CLAUDE.md actions table

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add `mise-setup` row**

In `CLAUDE.md`, find the actions table (header at line 9, `| Action | Purpose |`). Add a new row after the `setup-node` row and before `install-tools`:

```markdown
| `mise-setup` | Install mise and project-declared tools (delegated to from `setup-go`'s `install-mise`) |
```

- [ ] **Step 2: Add `mise-setup` to the Structure tree diagram**

Find the `## Structure` section's tree diagram. Add a `mise-setup/` entry near the other setup-* directories:

```
├── mise-setup/
│   └── action.yml      # mise installation (used standalone or via setup-go's install-mise)
```

Insertion point: after the `setup-node/` block, before `install-tools/`.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): add mise-setup to actions table and structure tree"
```

- [ ] **Step 4: Push**

```bash
git push
```

---

## Task 7: Final verification

- [ ] **Step 1: Confirm full smoke matrix is green**

Open the latest CI run for the `agents` branch (or whatever branch this work landed on). All matrix cells must pass:
- `smoke (mise-setup on ubuntu-latest)`
- `smoke (mise-setup on macos-latest)`
- `smoke (setup-go on ubuntu-latest)`
- `smoke (setup-go on macos-latest)`

Plus the pre-existing cells (`setup-gleam`, `setup-rust`, `setup-node`, `install-tools`, `run-gleam-workspace`) must remain green.

- [ ] **Step 2: Confirm pytest + bash-tests jobs still green**

These jobs should be untouched by this work, but verify they pass on the latest commit. If either is red, this work introduced an unintended regression — investigate.

- [ ] **Step 3: Sanity-check the diff**

```bash
git log --oneline main..HEAD
```

Expected five commits (Tasks 1+2 share a commit; Tasks 3-6 commit independently):
1. `feat(mise-setup): add standalone action wrapping jdx/mise-action`
2. `test(setup-go): cover install-mise path in smoke matrix`
3. `refactor(setup-go): delegate mise installation to mise-setup`
4. `docs(readme): document mise-setup action`
5. `docs(claude): add mise-setup to actions table and structure tree`

(The earlier spec commit `63fdf69` is separate and predates this plan.)

- [ ] **Step 4: Open the PR (if not already open)**

Use the existing branch's PR if one is open. Otherwise:

```bash
gh pr create --title "feat: mise-setup standalone action" --body "$(cat <<'EOF'
## Summary

- New `mise-setup` composite action wrapping `jdx/mise-action@v4`
- `setup-go` refactored to delegate to `mise-setup` internally; `install-mise` input contract preserved
- Smoke matrix coverage for `mise-setup` (Ubuntu + macOS) and for the `setup-go` delegation path
- README + CLAUDE.md updated

Spec: `docs/superpowers/specs/2026-05-19-cluster-b-mise-setup-design.md`

## Test plan
- [ ] `smoke (mise-setup on ubuntu-latest)` green
- [ ] `smoke (mise-setup on macos-latest)` green
- [ ] `smoke (setup-go on ubuntu-latest)` green
- [ ] `smoke (setup-go on macos-latest)` green
- [ ] pytest + bash-tests jobs unchanged and green
EOF
)"
```
