#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

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

create_workspace() {
  mkdir -p "$tmp/packages/core" "$tmp/packages/counters" "$tmp/packages/maps"

  cat > "$tmp/workspace.toml" <<'TOML'
[workspace]
members = ["packages/*"]
TOML

  cat > "$tmp/packages/core/gleam.toml" <<'TOML'
name = "lattice_core"
version = "1.0.0"
TOML

  cat > "$tmp/packages/counters/gleam.toml" <<'TOML'
name = "lattice_counters"
version = "1.1.0"

[dependencies]
lattice_core = { path = "../core" }
TOML

  cat > "$tmp/packages/maps/gleam.toml" <<'TOML'
name = "lattice_maps"
version = "1.1.0"

[dependencies]
lattice_core = { path = "../core" }
lattice_counters = { path = "../counters" }
TOML
}

test_selects_package_path_from_tag() {
  create_workspace

  (
    cd "$tmp"
    WORKSPACE_FILE="workspace.toml" \
      TAG_NAME="lattice_counters-v1.1.0" \
      GITHUB_OUTPUT="$tmp/output" \
      python3 "$repo_root/read-gleam-workspace/parse_workspace.py"
  )

  assert_file_contains "$tmp/output" "tag-package=lattice_counters"
  assert_file_contains "$tmp/output" "tag-package-path=packages/counters"
}

test_selects_prefixed_package_path_from_tag() {
  create_workspace

  (
    cd "$tmp"
    WORKSPACE_FILE="workspace.toml" \
      TAG_NAME="release-lattice_maps-v1.1.0" \
      TAG_PREFIX="release-" \
      GITHUB_OUTPUT="$tmp/output" \
      python3 "$repo_root/read-gleam-workspace/parse_workspace.py"
  )

  assert_file_contains "$tmp/output" "tag-package=lattice_maps"
  assert_file_contains "$tmp/output" "tag-package-path=packages/maps"
}

test_rejects_unknown_tag_package() {
  create_workspace

  set +e
  (
    cd "$tmp"
    WORKSPACE_FILE="workspace.toml" \
      TAG_NAME="lattice_unknown-v1.0.0" \
      python3 "$repo_root/read-gleam-workspace/parse_workspace.py"
  ) >"$tmp/unknown-output.txt" 2>&1
  local status=$?
  set -e

  if [ "$status" -eq 0 ]; then
    echo "Expected unknown tag package to fail" >&2
    exit 1
  fi

  assert_file_contains "$tmp/unknown-output.txt" "::error::Tag 'lattice_unknown-v1.0.0' does not match any workspace package"
}

test_rejects_tag_prefix_mismatch() {
  create_workspace

  set +e
  (
    cd "$tmp"
    WORKSPACE_FILE="workspace.toml" \
      TAG_NAME="wrong-lattice_maps-v1.1.0" \
      TAG_PREFIX="release-" \
      python3 "$repo_root/read-gleam-workspace/parse_workspace.py"
  ) >"$tmp/prefix-output.txt" 2>&1
  local status=$?
  set -e

  if [ "$status" -eq 0 ]; then
    echo "Expected tag prefix mismatch to fail" >&2
    exit 1
  fi

  assert_file_contains "$tmp/prefix-output.txt" "::error::Tag 'wrong-lattice_maps-v1.1.0' does not start with prefix 'release-'"
}

test_rejects_invalid_package_name() {
  rm -rf "$tmp"/*
  mkdir -p "$tmp/packages/evil"

  cat > "$tmp/workspace.toml" <<'TOML'
[workspace]
members = ["packages/*"]
TOML

  cat > "$tmp/packages/evil/gleam.toml" <<'TOML'
name = """evil
malicious"""
version = "1.0.0"
TOML

  set +e
  (
    cd "$tmp"
    WORKSPACE_FILE="workspace.toml" \
      python3 "$repo_root/read-gleam-workspace/parse_workspace.py"
  ) >"$tmp/invalid-name-output.txt" 2>&1
  local status=$?
  set -e

  if [ "$status" -eq 0 ]; then
    echo "Expected invalid package name to fail" >&2
    exit 1
  fi

  assert_file_contains "$tmp/invalid-name-output.txt" "::error::Invalid package name in packages/evil/gleam.toml"
}

test_rejects_invalid_package_path() {
  rm -rf "$tmp"/*
  local evil_path
  evil_path=$'packages/evil\nmalicious'
  mkdir -p "$tmp/$evil_path"

  cat > "$tmp/workspace.toml" <<'TOML'
[workspace]
members = ["packages/*"]
TOML

  cat > "$tmp/$evil_path/gleam.toml" <<'TOML'
name = "evil"
version = "1.0.0"
TOML

  set +e
  (
    cd "$tmp"
    WORKSPACE_FILE="workspace.toml" \
      python3 "$repo_root/read-gleam-workspace/parse_workspace.py"
  ) >"$tmp/invalid-path-output.txt" 2>&1
  local status=$?
  set -e

  if [ "$status" -eq 0 ]; then
    echo "Expected invalid package path to fail" >&2
    exit 1
  fi

  assert_file_contains "$tmp/invalid-path-output.txt" "::error::Invalid package path"
}

test_selects_package_path_from_tag
test_selects_prefixed_package_path_from_tag
test_rejects_unknown_tag_package
test_rejects_tag_prefix_mismatch
test_rejects_invalid_package_name
test_rejects_invalid_package_path
