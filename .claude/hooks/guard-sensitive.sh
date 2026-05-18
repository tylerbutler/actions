#!/usr/bin/env bash
# PreToolUse hook: ask before editing release-critical files.
# Consumers pin to @main with no versioning, so changes to these paths immediately
# affect every downstream repo. Force a deliberate confirmation.

set -o pipefail

payload=$(cat)
file=$(jq -r '.tool_input.file_path // empty' <<<"$payload" 2>/dev/null)
[ -z "$file" ] && exit 0

project_dir=${CLAUDE_PROJECT_DIR:-$PWD}

# Normalise to a repo-relative path.
case "$file" in
  /*)
    rel=${file#"$project_dir/"}
    ;;
  *)
    rel=$file
    ;;
esac

case "$rel" in
  .github/workflows/auto-tag.yml \
  | .github/workflows/gleam-workspace-ci.yml \
  | publish-homebrew-formula/action.yml \
  | changie-auto-tag/action.yml \
  | changie-release/action.yml \
  | gleam-publish/action.yml)
    jq -n --arg f "$rel" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "ask",
        permissionDecisionReason: ("Editing release-critical file: " + $f + ". Consumers pin to @main — confirm this change is intentional and that you have verified downstream impact.")
      }
    }'
    exit 0
    ;;
esac

exit 0
