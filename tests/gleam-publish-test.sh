#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

extract_rewrite_script() {
  awk '
    /- name: Rewrite path dependencies/ { in_step = 1; next }
    in_step && /run: \|/ { in_run = 1; next }
    in_run && /^$/ { print ""; next }
    in_run && /^        / { sub(/^        /, ""); print; next }
    in_run && !/^        / { exit }
  ' "$repo_root/gleam-publish/action.yml"
}

assert_file_contains() {
  local file=$1
  local expected=$2

  if ! grep -Fq "$expected" "$file"; then
    echo "Expected $file to contain: $expected" >&2
    echo "--- $file ---" >&2
    cat "$file" >&2
    exit 1
  fi
}

test_removes_stale_manifest_when_rewriting_path_deps() {
  mkdir -p "$tmp/packages/core" "$tmp/packages/app"

  cat > "$tmp/packages/core/gleam.toml" <<'TOML'
name = "core"
version = "1.2.3"
TOML

  cat > "$tmp/packages/app/gleam.toml" <<'TOML'
name = "app"
version = "2.0.0"

[dependencies]
core = { path = "../core" }
TOML

  cat > "$tmp/packages/app/manifest.toml" <<'TOML'
packages = [
  { name = "core", version = "1.2.3", source = "local", path = "../core" },
]

[requirements]
core = { path = "../core" }
TOML

  extract_rewrite_script > "$tmp/rewrite.sh"

  (
    cd "$tmp"
    REPLACE_PATH_DEPS="core:packages/core/gleam.toml" \
      PACKAGES="packages/core packages/app" \
      bash "$tmp/rewrite.sh"
  )

  assert_file_contains "$tmp/packages/app/gleam.toml" 'core = ">= 1.2.3 and < 2.0.0"'

  if [ -e "$tmp/packages/app/manifest.toml" ]; then
    echo "Expected stale manifest.toml to be removed after rewriting a path dependency" >&2
    exit 1
  fi
}

test_removes_stale_manifest_when_rewriting_path_deps
