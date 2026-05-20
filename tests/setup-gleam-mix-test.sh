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
