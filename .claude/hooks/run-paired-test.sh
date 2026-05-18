#!/usr/bin/env bash
# PostToolUse hook: when a Python file is edited, run its paired test_*.py.
# Tests are pytest-based and invoked via `uv run --with pytest pytest <path>`.
# Reads the Edit/Write tool input from stdin (JSON).

set -uo pipefail

file=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$file" ] && exit 0

case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac

dir=$(dirname "$file")
base=$(basename "$file")

case "$base" in
  test_*.py)
    target="$file"
    ;;
  *)
    target="$dir/test_$base"
    [ -f "$target" ] || exit 0
    ;;
esac

command -v uv >/dev/null 2>&1 || { echo "[run-paired-test] uv not on PATH; skipping" >&2; exit 0; }

echo "[run-paired-test] uv run --with pytest pytest $target" >&2
uv run --with pytest pytest "$target" 2>&1
