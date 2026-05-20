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
