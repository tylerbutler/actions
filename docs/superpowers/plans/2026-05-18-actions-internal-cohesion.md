# Actions Repo Internal Cohesion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land CI for the actions repo, extract a shared Python helper module, adopt a uniform `$GITHUB_STEP_SUMMARY` convention, and auto-detect Mix in `setup-gleam`.

**Architecture:** A new `_common/gha.py` module is consumed by each action's Python script via a `sys.path` injection. Existing duplicated helpers (`_write_output`, `_fail`, `_append_summary`, `update_toml_top_level_key`) are deleted in favour of imports. A new `.github/workflows/test.yml` runs the existing pytest + bash-test suites and adds smoke tests for `setup-*` actions. `setup-gleam` gains a Mix-detection step that resolves `elixir-version` from `.tool-versions` with a static `1.17` fallback.

**Tech Stack:** Python 3.11+ (stdlib `tomllib`), pytest, bash, GitHub Actions composite actions and reusable workflows.

**Spec:** `docs/superpowers/specs/2026-05-18-actions-internal-cohesion-design.md`

---

## Phase 1 — Build `_common/gha.py`

### Task 1: Scaffold `_common/` and add `write_output`

**Files:**
- Create: `_common/gha.py`
- Create: `_common/test_gha.py`

(No `__init__.py` — consumers inject `_common/` itself onto `sys.path`, so `gha` is importable as a top-level module from that directory.)

- [ ] **Step 1: Write the failing test**

```python
# _common/test_gha.py
import os
from pathlib import Path

from gha import write_output


def test_write_output_simple(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    write_output("version", "1.2.3")
    assert out.read_text() == "version=1.2.3\n"


def test_write_output_appends(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    out.write_text("existing=yes\n")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    write_output("version", "1.2.3")
    assert out.read_text() == "existing=yes\nversion=1.2.3\n"


def test_write_output_multiline_uses_heredoc(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    write_output("changelog", "line one\nline two")
    text = out.read_text()
    assert text.startswith("changelog<<EOF_CHANGELOG\n")
    assert "line one\nline two\n" in text
    assert text.endswith("EOF_CHANGELOG\n")


def test_write_output_no_env_writes_stdout(capsys, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    write_output("version", "1.2.3")
    assert capsys.readouterr().out == "version=1.2.3\n"


def test_write_output_key_sanitised_for_sentinel(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    write_output("pr-url", "a\nb")
    assert "pr-url<<EOF_PR_URL\n" in out.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest _common/test_gha.py -v`
Expected: collection error or `ModuleNotFoundError: No module named 'gha'`

- [ ] **Step 3: Write minimal implementation**

```python
# _common/gha.py
"""Shared utilities for actions repo Python helpers.

Consumed via sys.path injection from each action's script:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
    from gha import write_output, fail, append_summary  # noqa: E402
"""

from __future__ import annotations

import os
import re
import sys


def write_output(key: str, value: str) -> None:
    """Append `key=value` (or heredoc block for multi-line) to GITHUB_OUTPUT.

    Falls back to stdout when GITHUB_OUTPUT is unset (local runs).
    """
    if "\n" in value:
        sentinel = f"EOF_{re.sub(r'[^A-Z0-9]', '_', key.upper())}"
        block = f"{key}<<{sentinel}\n{value}\n{sentinel}\n"
    else:
        block = f"{key}={value}\n"

    out_file = os.environ.get("GITHUB_OUTPUT")
    if out_file:
        with open(out_file, "a", encoding="utf-8") as fh:
            fh.write(block)
    else:
        sys.stdout.write(block)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest _common/test_gha.py -v`
Expected: PASS for all 5 tests.

- [ ] **Step 5: Commit**

```bash
git add _common/gha.py _common/test_gha.py
git commit -m "feat(common): add gha.write_output helper"
```

---

### Task 2: Add `fail`

**Files:**
- Modify: `_common/gha.py`
- Modify: `_common/test_gha.py`

- [ ] **Step 1: Write the failing test**

Append to `_common/test_gha.py`:

```python
import pytest

from gha import fail


def test_fail_exits_one_by_default(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        fail("kaboom")
    assert exc.value.code == 1
    assert "::error::kaboom" in capsys.readouterr().err


def test_fail_custom_code(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        fail("nope", code=2)
    assert exc.value.code == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest _common/test_gha.py::test_fail_exits_one_by_default -v`
Expected: `ImportError: cannot import name 'fail'`

- [ ] **Step 3: Add `fail` to `_common/gha.py`**

Append:

```python
from typing import NoReturn


def fail(message: str, code: int = 1) -> NoReturn:
    """Emit a GitHub Actions error annotation and exit."""
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(code)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest _common/test_gha.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add _common/gha.py _common/test_gha.py
git commit -m "feat(common): add gha.fail helper"
```

---

### Task 3: Add `append_summary`

**Files:**
- Modify: `_common/gha.py`
- Modify: `_common/test_gha.py`

- [ ] **Step 1: Write the failing test**

Append to `_common/test_gha.py`:

```python
from gha import append_summary


def test_append_summary_writes_with_newline(tmp_path: Path, monkeypatch) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    append_summary("## Heading")
    append_summary("body line")
    assert summary.read_text() == "## Heading\nbody line\n"


def test_append_summary_no_env_is_noop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    append_summary("ignored")  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest _common/test_gha.py::test_append_summary_writes_with_newline -v`
Expected: `ImportError`.

- [ ] **Step 3: Add `append_summary` to `_common/gha.py`**

Append:

```python
def append_summary(markdown: str) -> None:
    """Append a line of Markdown to GITHUB_STEP_SUMMARY. No-op if unset."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return
    with open(summary_file, "a", encoding="utf-8") as fh:
        fh.write(markdown + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest _common/test_gha.py -v`
Expected: PASS (all 9 tests).

- [ ] **Step 5: Commit**

```bash
git add _common/gha.py _common/test_gha.py
git commit -m "feat(common): add gha.append_summary helper"
```

---

### Task 4: Add `update_toml_top_level_key`

**Files:**
- Modify: `_common/gha.py`
- Modify: `_common/test_gha.py`

- [ ] **Step 1: Write the failing test**

Append to `_common/test_gha.py`:

```python
import tomllib

import pytest

from gha import update_toml_top_level_key


def test_update_toml_top_level_string_value() -> None:
    content = 'name = "pkg"\nversion = "1.0.0"\n\n[dependencies]\nfoo = "0.1"\n'
    out = update_toml_top_level_key(content, "version", "2.0.0")
    assert 'version = "2.0.0"' in out
    assert out.endswith('[dependencies]\nfoo = "0.1"\n')


def test_update_toml_preserves_quoting_style() -> None:
    content = 'version    =    "1.0.0"\n'
    out = update_toml_top_level_key(content, "version", "1.1.0")
    assert out == 'version    =    "1.1.0"\n'


def test_update_toml_only_touches_top_level() -> None:
    content = (
        'version = "1.0.0"\n'
        "\n"
        "[dependencies]\n"
        'other = "1.0.0"\n'
    )
    out = update_toml_top_level_key(content, "version", "2.0.0")
    assert out.count('"2.0.0"') == 1
    assert 'other = "1.0.0"' in out


def test_update_toml_missing_key_raises() -> None:
    with pytest.raises(KeyError):
        update_toml_top_level_key('name = "pkg"\n', "version", "1.0.0")


def test_update_toml_non_string_value_raises() -> None:
    with pytest.raises(TypeError):
        update_toml_top_level_key("version = 1\n", "version", "2")


def test_update_toml_invalid_input_raises() -> None:
    with pytest.raises(tomllib.TOMLDecodeError):
        update_toml_top_level_key("not = valid = toml", "x", "y")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest _common/test_gha.py -v -k toml`
Expected: `ImportError`.

- [ ] **Step 3: Add to `_common/gha.py`**

Add the import at the top (`import tomllib`), then append:

```python
def _top_level_region_end(content: str) -> int:
    """Return the offset of the first `[table]` header, or len(content) if none."""
    match = re.search(r"^[ \t]*\[", content, re.MULTILINE)
    return match.start() if match else len(content)


def update_toml_top_level_key(content: str, key: str, new_value: str) -> str:
    """Replace the top-level `key = "..."` string assignment in `content`.

    Raises:
        tomllib.TOMLDecodeError: if `content` is not valid TOML.
        KeyError: if `key` is not a top-level key.
        TypeError: if the top-level `key` is not a string value.
        ValueError: if exactly one matching assignment line cannot be located.
    """
    data = tomllib.loads(content)
    if key not in data:
        raise KeyError(f"Top-level key {key!r} not found")
    if not isinstance(data[key], str):
        raise TypeError(f"Top-level key {key!r} is not a string value")

    end = _top_level_region_end(content)
    head, tail = content[:end], content[end:]

    pattern = re.compile(
        rf'^({re.escape(key)}[ \t]*=[ \t]*)"[^"\n]*"',
        re.MULTILINE,
    )
    new_head, count = pattern.subn(
        lambda m: f'{m.group(1)}"{new_value}"', head
    )
    if count != 1:
        raise ValueError(
            f"Expected exactly one top-level assignment for {key!r}, found {count}"
        )
    return new_head + tail
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest _common/test_gha.py -v`
Expected: PASS (all 15 tests).

- [ ] **Step 5: Commit**

```bash
git add _common/gha.py _common/test_gha.py
git commit -m "feat(common): canonical TOML top-level key updater"
```

---

### Task 5: Add `parse_colon_entries`

**Files:**
- Modify: `_common/gha.py`
- Modify: `_common/test_gha.py`

- [ ] **Step 1: Write the failing test**

Append to `_common/test_gha.py`:

```python
from gha import parse_colon_entries


def test_parse_colon_entries_two_fields() -> None:
    text = "gleam.toml:version\npackages/foo/gleam.toml:version\n"
    result = parse_colon_entries(text, fields=2)
    assert result == [
        ("gleam.toml", "version"),
        ("packages/foo/gleam.toml", "version"),
    ]


def test_parse_colon_entries_three_fields() -> None:
    text = "vestibule:gleam.toml:version\n"
    result = parse_colon_entries(text, fields=3)
    assert result == [("vestibule", "gleam.toml", "version")]


def test_parse_colon_entries_skips_blank_and_comments() -> None:
    text = "\n# a comment\n  \nfoo:bar\n"
    assert parse_colon_entries(text, fields=2) == [("foo", "bar")]


def test_parse_colon_entries_strips_whitespace() -> None:
    text = "  foo  :  bar  \n"
    assert parse_colon_entries(text, fields=2) == [("foo", "bar")]


def test_parse_colon_entries_wrong_field_count_raises() -> None:
    with pytest.raises(ValueError, match="expected 2 fields"):
        parse_colon_entries("a:b:c\n", fields=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest _common/test_gha.py -v -k colon`
Expected: `ImportError`.

- [ ] **Step 3: Add to `_common/gha.py`**

Append:

```python
def parse_colon_entries(text: str, fields: int) -> list[tuple[str, ...]]:
    """Parse newline-separated, colon-delimited entries.

    Blank lines and lines starting with `#` are skipped. Whitespace around
    each field is stripped. Each non-empty line must split into exactly
    `fields` parts.
    """
    out: list[tuple[str, ...]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = [p.strip() for p in stripped.split(":")]
        if len(parts) != fields:
            raise ValueError(
                f"line {lineno}: expected {fields} fields, got {len(parts)}: {raw!r}"
            )
        out.append(tuple(parts))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest _common/test_gha.py -v`
Expected: PASS (all 20 tests).

- [ ] **Step 5: Commit**

```bash
git add _common/gha.py _common/test_gha.py
git commit -m "feat(common): add gha.parse_colon_entries helper"
```

---

## Phase 2 — Migrate consumers to `_common`

Each migration follows the same pattern: confirm the action's existing tests are green, replace the private helper with an import, confirm tests still green, commit. No new behaviour is introduced.

The standard import block that every migrated script needs near the top (after stdlib imports, before any local code):

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import write_output, fail, append_summary  # noqa: E402
```

(Trim the imported names to what each script actually uses.)

### Task 6: Migrate `binary-size/binary_size.py`

**Files:**
- Modify: `binary-size/binary_size.py`

- [ ] **Step 1: Baseline — run existing tests, confirm green**

Run: `pytest binary-size/ -v`
Expected: all tests PASS.

- [ ] **Step 2: Add the `_common` import block**

Add after the existing imports at the top of `binary-size/binary_size.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import write_output, fail  # noqa: E402
```

- [ ] **Step 3: Delete `_write_output` and `_fail` from `binary-size/binary_size.py`**

Remove the function definitions (current lines ~162–178). Then update call sites: replace every `_write_output(` with `write_output(` and every `_fail(` with `fail(`.

- [ ] **Step 4: Run tests, confirm still green**

Run: `pytest binary-size/ -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add binary-size/binary_size.py
git commit -m "refactor(binary-size): use _common/gha helpers"
```

---

### Task 7: Migrate `changie-auto-tag/changie_auto_tag.py`

**Files:**
- Modify: `changie-auto-tag/changie_auto_tag.py`

- [ ] **Step 1: Baseline — run existing tests, confirm green**

Run: `pytest changie-auto-tag/ -v`
Expected: all tests PASS.

- [ ] **Step 2: Add the `_common` import block**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import write_output, fail  # noqa: E402
```

- [ ] **Step 3: Delete `_write_output` and `_fail`**

Remove the function definitions (current lines ~223–235). Replace every `_write_output(` with `write_output(` and every `_fail(` with `fail(`.

- [ ] **Step 4: Run tests, confirm still green**

Run: `pytest changie-auto-tag/ -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add changie-auto-tag/changie_auto_tag.py
git commit -m "refactor(changie-auto-tag): use _common/gha helpers"
```

---

### Task 8: Migrate `changie-check/changie_check.py`

**Files:**
- Modify: `changie-check/changie_check.py`

- [ ] **Step 1: Baseline — run existing tests, confirm green**

Run: `pytest changie-check/ -v`
Expected: all tests PASS.

- [ ] **Step 2: Add the `_common` import block**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import write_output, fail  # noqa: E402
```

- [ ] **Step 3: Delete `_write_output` and `_fail`**

Remove the function definitions (current lines ~110–126). Replace call sites: `_write_output(` → `write_output(`, `_fail(` → `fail(`.

- [ ] **Step 4: Run tests, confirm still green**

Run: `pytest changie-check/ -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add changie-check/changie_check.py
git commit -m "refactor(changie-check): use _common/gha helpers"
```

---

### Task 9: Migrate `changie-release/changie_release.py`

This one is heavier: it drops both `_write_output`/`_fail` AND its local copy of `update_toml_top_level_key` / `_top_level_region_end`.

**Files:**
- Modify: `changie-release/changie_release.py`

- [ ] **Step 1: Baseline — run existing tests, confirm green**

Run: `pytest changie-release/ -v`
Expected: all tests PASS.

- [ ] **Step 2: Add the `_common` import block**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import write_output, fail, update_toml_top_level_key  # noqa: E402
```

- [ ] **Step 3: Delete the duplicated functions**

In `changie-release/changie_release.py`, delete the following function definitions:
- `_write_output` (~line 164)
- `_fail` (~line 179)
- `update_toml_top_level_key` (~line 72) — the canonical version comes from `_common/gha.py` now.

If a top-level `import tomllib` becomes unused after this, remove it. (It is used by other parts of this file — recheck before removing.)

Then update call sites: `_write_output(` → `write_output(`, `_fail(` → `fail(`. Existing `update_toml_top_level_key(` call sites do not change (same name, just imported now).

- [ ] **Step 4: Run tests, confirm still green**

Run: `pytest changie-release/ -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add changie-release/changie_release.py
git commit -m "refactor(changie-release): use _common/gha helpers"
```

---

### Task 10: Migrate `gleam-publish/gleam_publish.py`

**Files:**
- Modify: `gleam-publish/gleam_publish.py`

- [ ] **Step 1: Baseline — run existing tests, confirm green**

Run: `pytest gleam-publish/ -v`
Expected: all tests PASS.

- [ ] **Step 2: Add the `_common` import block**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import write_output, fail, append_summary  # noqa: E402
```

- [ ] **Step 3: Delete `_write_output`, `_fail`, `_append_summary`**

Remove the function definitions (current lines ~111–130). Replace call sites:
- `_write_output(` → `write_output(`
- `_fail(` → `fail(`
- `_append_summary(` → `append_summary(`

- [ ] **Step 4: Run tests, confirm still green**

Run: `pytest gleam-publish/ -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gleam-publish/gleam_publish.py
git commit -m "refactor(gleam-publish): use _common/gha helpers"
```

---

### Task 11: Migrate `update-version-files/update_version_files.py`

This drops the local `update_toml_top_level_key` + `_top_level_region_end` + `_fail`.

**Files:**
- Modify: `update-version-files/update_version_files.py`

- [ ] **Step 1: Baseline — run existing tests, confirm green**

Run: `pytest update-version-files/ -v`
Expected: all tests PASS.

- [ ] **Step 2: Add the `_common` import block**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from gha import fail, update_toml_top_level_key  # noqa: E402
```

- [ ] **Step 3: Delete the duplicated functions**

Delete:
- `_top_level_region_end` (~line 54)
- `update_toml_top_level_key` (~line 60)
- `_fail` (~line 92)

If `import re` or `import tomllib` becomes unused after this, remove it. Replace `_fail(` call sites with `fail(`.

- [ ] **Step 4: Run tests, confirm still green**

Run: `pytest update-version-files/ -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add update-version-files/update_version_files.py
git commit -m "refactor(update-version-files): use _common/gha helpers"
```

---

### Task 12: Migrate `parse_entries` / `parse_replace_path_deps` / `parse_version_files` to `parse_colon_entries`

The earlier migration tasks left the action-specific `parse_*` functions in place because their call sites use their semantic names. This task replaces them with `parse_colon_entries` and confirms behaviour is preserved.

**Files:**
- Modify: `update-version-files/update_version_files.py`
- Modify: `gleam-publish/gleam_publish.py`
- Modify: `changie-release/changie_release.py`

- [ ] **Step 1: Baseline — run existing tests, confirm green**

Run: `pytest update-version-files/ gleam-publish/ changie-release/ -v`
Expected: all tests PASS.

- [ ] **Step 2: In `update-version-files/update_version_files.py`**

Add `parse_colon_entries` to the existing `from gha import …` line. Delete the local `parse_entries` function. Replace its call site with `parse_colon_entries(text, fields=2)`. Adjust any unpacking — current `parse_entries` returns `list[tuple[str, str]]`; `parse_colon_entries` returns `list[tuple[str, ...]]`. If type narrowing is needed, do it at the call site.

- [ ] **Step 3: In `gleam-publish/gleam_publish.py`**

Add `parse_colon_entries` to the existing `from gha import …` line. Delete the local `parse_replace_path_deps` function. Replace its call site with `parse_colon_entries(text, fields=2)`.

- [ ] **Step 4: In `changie-release/changie_release.py`**

This one is different: `parse_version_files` accepts a `multi_project: bool` and returns dicts with `project`/`path`/`key` fields where `project` may be `None`. Keep the local wrapper — it adds semantic value over the generic parser — but rewrite its body to call `parse_colon_entries(text, fields=3 if multi_project else 2)` internally and then map tuples to the dict shape it returns today.

- [ ] **Step 5: Run all three test suites**

Run: `pytest update-version-files/ gleam-publish/ changie-release/ -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add update-version-files/update_version_files.py gleam-publish/gleam_publish.py changie-release/changie_release.py
git commit -m "refactor: use _common parse_colon_entries across actions"
```

---

## Phase 3 — Auto-detect Mix in `setup-gleam`

### Task 13: Add Mix detection step to `setup-gleam/action.yml`

**Files:**
- Modify: `setup-gleam/action.yml`
- Create: `tests/setup-gleam-mix-test.sh`

- [ ] **Step 1: Write the failing bash test**

Create `tests/setup-gleam-mix-test.sh`:

```bash
#!/usr/bin/env bash
# Tests the Mix-detection helper script in isolation. The composite action
# step shells out to this same logic — see setup-gleam/action.yml.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
script="$repo_root/setup-gleam/resolve_elixir_version.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

run_resolver() {
  local dir=$1
  local explicit=$2
  ( cd "$dir" && ELIXIR_VERSION_INPUT="$explicit" "$script" )
}

# 1. Explicit input wins, no mix.exs
mkdir -p "$tmp/case1"
result=$(run_resolver "$tmp/case1" "1.18")
[[ "$result" == "1.18" ]] || { echo "case1 expected 1.18, got $result"; exit 1; }

# 2. No mix.exs, no input -> empty (don't install Elixir)
mkdir -p "$tmp/case2"
result=$(run_resolver "$tmp/case2" "")
[[ -z "$result" ]] || { echo "case2 expected empty, got $result"; exit 1; }

# 3. mix.exs present, no input, no .tool-versions -> fallback 1.17
mkdir -p "$tmp/case3"
: > "$tmp/case3/mix.exs"
result=$(run_resolver "$tmp/case3" "")
[[ "$result" == "1.17" ]] || { echo "case3 expected 1.17, got $result"; exit 1; }

# 4. mix.exs present, .tool-versions declares elixir -> use that
mkdir -p "$tmp/case4"
: > "$tmp/case4/mix.exs"
cat > "$tmp/case4/.tool-versions" <<EOF
erlang 28.0
elixir 1.16.3
EOF
result=$(run_resolver "$tmp/case4" "")
[[ "$result" == "1.16.3" ]] || { echo "case4 expected 1.16.3, got $result"; exit 1; }

# 5. mix.exs present BUT explicit input set -> input wins
mkdir -p "$tmp/case5"
: > "$tmp/case5/mix.exs"
cat > "$tmp/case5/.tool-versions" <<EOF
elixir 1.16.3
EOF
result=$(run_resolver "$tmp/case5" "1.18.2")
[[ "$result" == "1.18.2" ]] || { echo "case5 expected 1.18.2, got $result"; exit 1; }

echo "OK"
```

Make it executable:

```bash
chmod +x tests/setup-gleam-mix-test.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `tests/setup-gleam-mix-test.sh`
Expected: failure — script does not exist yet.

- [ ] **Step 3: Create the resolver script**

Create `setup-gleam/resolve_elixir_version.sh`:

```bash
#!/usr/bin/env bash
# Resolve the Elixir version to install for setup-gleam.
#
# Inputs (env):
#   ELIXIR_VERSION_INPUT  - explicit `elixir-version` action input (may be empty)
#
# Behaviour:
#   - If ELIXIR_VERSION_INPUT is set, echo it and exit.
#   - Else if no mix.exs in PWD, echo nothing (do not install Elixir).
#   - Else if .tool-versions declares `elixir <ver>`, echo that version.
#   - Else echo the static fallback 1.17.
set -euo pipefail

FALLBACK="1.17"

if [[ -n "${ELIXIR_VERSION_INPUT:-}" ]]; then
  echo "$ELIXIR_VERSION_INPUT"
  exit 0
fi

if [[ ! -f mix.exs ]]; then
  exit 0
fi

if [[ -f .tool-versions ]]; then
  version=$(awk '$1 == "elixir" { print $2; exit }' .tool-versions)
  if [[ -n "$version" ]]; then
    echo "$version"
    exit 0
  fi
fi

echo "$FALLBACK"
```

Make it executable:

```bash
chmod +x setup-gleam/resolve_elixir_version.sh
```

- [ ] **Step 4: Run the test, confirm it passes**

Run: `tests/setup-gleam-mix-test.sh`
Expected: `OK`.

- [ ] **Step 5: Wire the resolver into `setup-gleam/action.yml`**

Edit `setup-gleam/action.yml`. After the existing "Install tools" step and before the BEAM-setup steps, add:

```yaml
    - name: Resolve Elixir version
      id: resolve-elixir
      shell: bash
      working-directory: ${{ inputs.working-directory }}
      env:
        ELIXIR_VERSION_INPUT: ${{ inputs.elixir-version }}
      run: |
        version=$("$GITHUB_ACTION_PATH/resolve_elixir_version.sh")
        echo "elixir-version=$version" >> "$GITHUB_OUTPUT"
        if [[ -n "$version" && -z "$ELIXIR_VERSION_INPUT" ]]; then
          echo "Auto-detected Elixir requirement (mix.exs found): $version"
        fi
```

Then change every later reference to `inputs.elixir-version` in this file to `steps.resolve-elixir.outputs.elixir-version`. Specifically the `if:` conditions on the two BEAM-setup steps that gate on Elixir, the `with: elixir-version:` value, and the `if:` on the "Cache Mix dependencies" and "Install Mix dependencies" steps.

- [ ] **Step 6: Update the README section for `setup-gleam`**

In `README.md`, add a short note under the `setup-gleam` action's docs:

```markdown
**Mix auto-detection:** if `mix.exs` is present in `working-directory` and
`elixir-version` is unset, Elixir is installed automatically — version comes
from `.tool-versions` if it declares `elixir`, otherwise falls back to
`1.17`.
```

- [ ] **Step 7: Re-run the bash test, confirm still passes**

Run: `tests/setup-gleam-mix-test.sh`
Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
git add setup-gleam/action.yml setup-gleam/resolve_elixir_version.sh tests/setup-gleam-mix-test.sh README.md
git commit -m "feat(setup-gleam): auto-detect Mix and resolve Elixir version

Detects mix.exs, prefers .tool-versions elixir line, falls back to 1.17."
```

---

## Phase 4 — Step-summary convention

### Task 14: Document the `$GITHUB_STEP_SUMMARY` convention

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a "Step summaries" section to `README.md`**

Add a new section near the top (before the per-action documentation):

```markdown
## Step summaries

Every action in this repo contributes a section to `$GITHUB_STEP_SUMMARY`
using a consistent shape:

    ## <Action Name>

    <one-sentence outcome>

    <optional Markdown body: tables for tabular data, bullet lists otherwise>

Skipped or no-op runs still emit a section so the summary is a faithful
record of what ran. Python-backed actions use `_common/gha.append_summary`;
inline-bash actions append directly to `$GITHUB_STEP_SUMMARY`.
```

- [ ] **Step 2: Add an internal-conventions section to `CLAUDE.md`**

Append to `CLAUDE.md` (after the existing Gotchas section):

```markdown
## Internal conventions

- **Shared Python helpers** live in `_common/gha.py`. Action scripts inject
  `$GITHUB_ACTION_PATH/../_common` into `sys.path` and import from `gha`.
  See `_common/gha.py` for the module docstring and `_common/test_gha.py`
  for usage examples. Do not copy these helpers back into individual
  actions.

- **Step summaries** follow the shape documented in `README.md`. Use
  `gha.append_summary()` from Python helpers; use `>> "$GITHUB_STEP_SUMMARY"`
  from inline bash.

- **CI** runs on every PR (`.github/workflows/test.yml`): pytest across all
  Python helpers, the `tests/*-test.sh` integration scripts, and smoke
  tests that exercise the `setup-*` composite actions against fixtures
  under `tests/fixtures/`.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document step-summary convention and internal cohesion rules"
```

---

### Task 15: Add summary writes to actions that lack them

This is a sweep. Each sub-step has its own commit so the diff per action stays small.

**Files (sub-step list):**
- `changie-release/changie_release.py`
- `changie-auto-tag/changie_auto_tag.py`
- `changie-check/changie_check.py`
- `update-version-files/update_version_files.py`
- `binary-size/binary_size.py`
- `read-gleam-workspace/parse_workspace.py`
- `install-tools/action.yml`
- `run-gleam-workspace/action.yml`
- `setup-gleam/action.yml`
- `setup-go/action.yml`
- `setup-node/action.yml`
- `setup-rust/action.yml`
- `download-ccl-tests/action.yml`
- `gleam-publish/gleam_publish.py` (already writes a summary — verify it matches the convention; reshape if not)
- `publish-homebrew-formula/action.yml`

- [ ] **Step 1: For each Python-backed action above, add summary writes**

Pattern — in each script's `main()` (or its action-specific finalisation point):

```python
append_summary(f"## {ACTION_DISPLAY_NAME}")
append_summary(outcome_sentence)
# Optional: append a Markdown table or bullets for details.
```

`ACTION_DISPLAY_NAME` matches the `name:` field in the action's `action.yml`.

Examples of outcome sentences (do not literally copy — write what fits the action):
- `changie-release`: `f"Created release PR for {version}."` or `"No unreleased changes; skipped."`
- `changie-auto-tag`: `f"Created tags: {', '.join(created_tags)}."` or `"No new tags to create."`
- `binary-size`: `f"Measured {n} binaries; total delta {delta:+d} bytes."`
- `read-gleam-workspace`: `f"Discovered {n} packages: {', '.join(names)}."`

Add a `gha.append_summary` import to the existing `from gha import …` line if needed.

After editing each script, run its existing test suite to confirm no regression. Commit per action:

```bash
git add <action>/...
git commit -m "feat(<action>): write step summary"
```

- [ ] **Step 2: For each inline-bash composite action above, add a final summary step**

Pattern — append at the end of `runs.steps:`:

```yaml
    - name: Write step summary
      shell: bash
      run: |
        {
          echo "## <Action Display Name>"
          echo
          echo "<one-sentence outcome>"
        } >> "$GITHUB_STEP_SUMMARY"
```

Tailor the outcome line per action. For setup-* actions, include the installed version (read from the tool, e.g. `gleam --version | head -1`). Commit per action:

```bash
git add <action>/action.yml
git commit -m "feat(<action>): write step summary"
```

- [ ] **Step 3: Verify `gleam-publish` already-existing summary matches the convention**

Inspect `gleam-publish/gleam_publish.py` summary lines. If the header is not `## Gleam Publish`, change it. Otherwise no edit needed.

- [ ] **Step 4: Run full test suite**

Run: `pytest .` from the repo root.
Expected: all tests PASS.

Run: `for f in tests/*-test.sh; do "$f"; done`
Expected: all scripts print `OK` and exit 0.

---

## Phase 5 — CI workflow + fixtures

### Task 16: Create smoke-test fixtures

**Files:**
- Create: `tests/fixtures/setup-gleam/gleam.toml`
- Create: `tests/fixtures/setup-gleam/.tool-versions`
- Create: `tests/fixtures/setup-go/go.mod`
- Create: `tests/fixtures/setup-rust/Cargo.toml`
- Create: `tests/fixtures/setup-node/package.json`
- Create: `tests/fixtures/install-tools/.keep`
- Create: `tests/fixtures/run-gleam-workspace/workspace.toml`
- Create: `tests/fixtures/run-gleam-workspace/packages/demo/gleam.toml`

- [ ] **Step 1: Create `tests/fixtures/setup-gleam/`**

`tests/fixtures/setup-gleam/gleam.toml`:

```toml
name = "smoke"
version = "0.0.0"
target = "erlang"

[dependencies]
```

`tests/fixtures/setup-gleam/.tool-versions`:

```
erlang 28.0
gleam 1.13.0
```

- [ ] **Step 2: Create `tests/fixtures/setup-go/`**

`tests/fixtures/setup-go/go.mod`:

```
module smoke

go 1.23
```

- [ ] **Step 3: Create `tests/fixtures/setup-rust/`**

`tests/fixtures/setup-rust/Cargo.toml`:

```toml
[package]
name = "smoke"
version = "0.0.0"
edition = "2021"

[lib]
path = "lib.rs"
```

`tests/fixtures/setup-rust/lib.rs`:

```rust
```

(empty file)

- [ ] **Step 4: Create `tests/fixtures/setup-node/`**

`tests/fixtures/setup-node/package.json`:

```json
{
  "name": "smoke",
  "version": "0.0.0",
  "private": true
}
```

- [ ] **Step 5: Create `tests/fixtures/install-tools/.keep`** (empty placeholder)

```bash
mkdir -p tests/fixtures/install-tools
: > tests/fixtures/install-tools/.keep
```

- [ ] **Step 6: Create `tests/fixtures/run-gleam-workspace/`**

`tests/fixtures/run-gleam-workspace/workspace.toml`:

```toml
[workspace]
members = ["packages/*"]
```

`tests/fixtures/run-gleam-workspace/packages/demo/gleam.toml`:

```toml
name = "demo"
version = "0.0.0"
target = "erlang"
```

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/
git commit -m "test: add smoke-test fixtures for setup-* actions"
```

---

### Task 17: Create `.github/workflows/test.yml` with pytest + bash-tests jobs

**Files:**
- Create: `.github/workflows/test.yml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/test.yml`:

```yaml
name: test

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  pytest:
    name: pytest (py${{ matrix.python }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python: ["3.11", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
          cache: pip
      - name: Install pytest
        run: pip install pytest
      - name: Run pytest
        run: pytest -v

  bash-tests:
    name: bash integration tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run integration scripts
        run: |
          for script in tests/*-test.sh; do
            echo "=== $script ==="
            "$script"
          done
```

- [ ] **Step 2: Push the branch and confirm both jobs run green**

```bash
git add .github/workflows/test.yml
git commit -m "ci: run pytest and bash integration tests on PR"
git push -u origin "$(git branch --show-current)"
```

Watch the resulting GitHub Actions run. Both jobs must be green.

Expected: pytest reports the full count of tests across `_common/` and every action directory; bash-tests prints `OK` from each of the four `tests/*-test.sh` scripts (`changie-auto-tag-test.sh`, `gleam-publish-test.sh`, `read-gleam-workspace-test.sh`, `setup-gleam-mix-test.sh`).

---

### Task 18: Add the `smoke` job for `setup-*` actions

**Files:**
- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: Append the smoke job**

Edit `.github/workflows/test.yml`, append under `jobs:`:

```yaml
  smoke:
    name: smoke (${{ matrix.action }} on ${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        action: [setup-gleam, setup-go, setup-rust, setup-node]
        os: [ubuntu-latest, macos-latest]
        include:
          - action: install-tools
            os: ubuntu-latest
          - action: run-gleam-workspace
            os: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: setup-gleam smoke
        if: matrix.action == 'setup-gleam'
        uses: ./setup-gleam
        with:
          working-directory: tests/fixtures/setup-gleam
          version-file: tests/fixtures/setup-gleam/.tool-versions
          run-deps: 'false'
      - name: setup-gleam assertion
        if: matrix.action == 'setup-gleam'
        run: gleam --version

      - name: setup-go smoke
        if: matrix.action == 'setup-go'
        uses: ./setup-go
        with:
          working-directory: tests/fixtures/setup-go
      - name: setup-go assertion
        if: matrix.action == 'setup-go'
        run: go version

      - name: setup-rust smoke
        if: matrix.action == 'setup-rust'
        uses: ./setup-rust
      - name: setup-rust assertion
        if: matrix.action == 'setup-rust'
        run: rustc --version

      - name: setup-node smoke
        if: matrix.action == 'setup-node'
        uses: ./setup-node
        with:
          working-directory: tests/fixtures/setup-node
      - name: setup-node assertion
        if: matrix.action == 'setup-node'
        run: node --version

      - name: install-tools smoke
        if: matrix.action == 'install-tools'
        uses: ./install-tools
        with:
          tools: just
      - name: install-tools assertion
        if: matrix.action == 'install-tools'
        run: just --version

      - name: run-gleam-workspace smoke
        if: matrix.action == 'run-gleam-workspace'
        uses: ./run-gleam-workspace
        with:
          packages: packages/demo
          command: 'echo hello-from-$(basename "$PWD")'
          working-directory: tests/fixtures/run-gleam-workspace
```

The `with:` keys above are best-effort based on each action's current inputs. If any input does not exist on the action, adjust to match what the action actually accepts — the action's `action.yml` is the source of truth, not this plan.

- [ ] **Step 2: Push and watch the smoke job**

```bash
git add .github/workflows/test.yml
git commit -m "ci: add smoke job for setup-* composite actions"
git push
```

Watch the workflow. Every matrix cell must be green. If a setup action's existing input names don't match what's used above, fix the workflow to match the action — not the other way around.

- [ ] **Step 3: Verify smoke fails when an action is broken**

Sanity check the safety net is real:

1. On a throwaway commit, introduce a syntax error in one `setup-*/action.yml` (e.g., misspell `composite:` as `composit:`).
2. Push. Confirm the corresponding smoke matrix cell fails.
3. Revert the throwaway commit.

This step is gated on access to a throwaway branch — record the result in the PR description but do not commit the throwaway change to main.

---

## Final verification

Before opening the PR for this cluster:

- [ ] `pytest -v` passes locally with full test count (all `_common/`, all action directories).
- [ ] Every `tests/*-test.sh` script prints `OK` locally.
- [ ] The `test.yml` workflow on the PR shows three green jobs: `pytest`, `bash-tests`, and `smoke` (all matrix cells).
- [ ] No copy of `_write_output`, `_fail`, `_append_summary`, or `update_toml_top_level_key` remains outside `_common/gha.py`. Verify with:

  ```bash
  rg "def _write_output|def _fail|def _append_summary|def update_toml_top_level_key" --type py
  ```

  Expected: only matches inside `_common/`.

- [ ] `setup-gleam` on a fixture with `mix.exs` and no `elixir-version` installs Elixir; on a fixture without `mix.exs` it does not.
- [ ] Every action's run produces a `## <Action Name>` section in the step summary on the smoke-job runs.
