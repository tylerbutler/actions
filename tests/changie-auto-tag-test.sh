#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

extract_create_tags_script() {
  awk '
    /- name: Get version and create tags/ { in_step = 1; next }
    in_step && /run: \|/ { in_run = 1; next }
    in_run && /^$/ { print ""; next }
    in_run && /^        / { sub(/^        /, ""); print; next }
    in_run && !/^        / { exit }
  ' "$repo_root/changie-auto-tag/action.yml"
}

extract_create_releases_script() {
  awk '
    /- name: Create GitHub Releases/ { in_step = 1; next }
    in_step && /run: \|/ { in_run = 1; next }
    in_run && /^$/ { print ""; next }
    in_run && /^        / { sub(/^        /, ""); print; next }
    in_run && !/^        / { exit }
  ' "$repo_root/changie-auto-tag/action.yml"
}

assert_eq() {
  local expected=$1
  local actual=$2
  local message=$3

  if [ "$actual" != "$expected" ]; then
    echo "Expected $message to be '$expected', got '$actual'" >&2
    exit 1
  fi
}

test_skips_remote_existing_tags_without_local_tag() {
  mkdir "$tmp/bin" "$tmp/seed" "$tmp/work"

  cat > "$tmp/bin/changie" <<'CHANGIE'
#!/usr/bin/env bash
set -euo pipefail

if [ "$1" = "latest" ] && [ "$2" = "--project" ]; then
  printf '%s-v1.0.0\n' "$3"
  exit 0
fi

echo "unexpected changie invocation: $*" >&2
exit 1
CHANGIE
  chmod +x "$tmp/bin/changie"

  git init --bare "$tmp/origin.git" >/dev/null

  git -C "$tmp/seed" init >/dev/null
  git -C "$tmp/seed" config user.email test@example.com
  git -C "$tmp/seed" config user.name "Test User"
  git -C "$tmp/seed" commit --allow-empty -m "seed" >/dev/null
  git -C "$tmp/seed" tag core-v1.0.0
  git -C "$tmp/seed" remote add origin "$tmp/origin.git"
  git -C "$tmp/seed" push origin main core-v1.0.0 >/dev/null

  git -C "$tmp/work" init >/dev/null
  git -C "$tmp/work" config user.email test@example.com
  git -C "$tmp/work" config user.name "Test User"
  git -C "$tmp/work" commit --allow-empty -m "release" >/dev/null
  git -C "$tmp/work" remote add origin "$tmp/origin.git"

  extract_create_tags_script > "$tmp/create-tags.sh"

  (
    cd "$tmp/work"
    PATH="$tmp/bin:$PATH" \
      PROJECTS="core,app" \
      PREFIX="" \
      GITHUB_TOKEN="test-token" \
      GITHUB_OUTPUT="$tmp/output" \
      bash "$tmp/create-tags.sh"
  )

  if git -C "$tmp/work" tag -l core-v1.0.0 | grep -q .; then
    echo "Expected remote-existing tag core-v1.0.0 not to be created locally" >&2
    exit 1
  fi

  assert_eq "created-tags=app-v1.0.0" "$(grep '^created-tags=' "$tmp/output")" "created-tags output"
  git --git-dir="$tmp/origin.git" rev-parse --verify refs/tags/app-v1.0.0 >/dev/null
}

test_wait_for_publish_checks_each_pushed_tag_serially() {
  rm -rf "$tmp/bin" "$tmp/seed" "$tmp/work" "$tmp/origin.git" "$tmp/output" "$tmp/create-tags.sh" "$tmp/gh-calls.log"
  mkdir "$tmp/bin" "$tmp/work"

  cat > "$tmp/bin/changie" <<'CHANGIE'
#!/usr/bin/env bash
set -euo pipefail

if [ "$1" = "latest" ] && [ "$2" = "--project" ]; then
  printf '%s-v1.0.0\n' "$3"
  exit 0
fi

echo "unexpected changie invocation: $*" >&2
exit 1
CHANGIE
  chmod +x "$tmp/bin/changie"

  cat > "$tmp/bin/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail

echo "$*" >> "$GH_CALL_LOG"

if [ "$1" = "run" ] && [ "$2" = "list" ]; then
  tag=""
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--branch" ]; then
      tag="$2"
      break
    fi
    shift
  done
  printf '[{"databaseId":123,"status":"completed","conclusion":"success","headBranch":"%s"}]\n' "$tag"
  exit 0
fi

if [ "$1" = "run" ] && [ "$2" = "view" ]; then
  printf '{"status":"completed","conclusion":"success"}\n'
  exit 0
fi

echo "unexpected gh invocation: $*" >&2
exit 1
GH
  chmod +x "$tmp/bin/gh"

  git init --bare "$tmp/origin.git" >/dev/null

  git -C "$tmp/work" init >/dev/null
  git -C "$tmp/work" config user.email test@example.com
  git -C "$tmp/work" config user.name "Test User"
  git -C "$tmp/work" commit --allow-empty -m "release" >/dev/null
  git -C "$tmp/work" remote add origin "$tmp/origin.git"

  extract_create_tags_script > "$tmp/create-tags.sh"
  : > "$tmp/gh-calls.log"

  (
    cd "$tmp/work"
    PATH="$tmp/bin:$PATH" \
      PROJECTS="core,app" \
      PREFIX="" \
      GITHUB_TOKEN="test-token" \
      GH_TOKEN="test-token" \
      GITHUB_OUTPUT="$tmp/output" \
      WAIT_FOR_PUBLISH="true" \
      PUBLISH_WORKFLOW_NAME="Publish" \
      PUBLISH_WAIT_TIMEOUT_SECONDS="30" \
      PUBLISH_WAIT_POLL_SECONDS="1" \
      GH_CALL_LOG="$tmp/gh-calls.log" \
      bash "$tmp/create-tags.sh"
  )

  assert_eq "created-tags=core-v1.0.0 app-v1.0.0" "$(grep '^created-tags=' "$tmp/output")" "created-tags output"
  grep -Fq 'run list --workflow Publish --branch core-v1.0.0' "$tmp/gh-calls.log"
  grep -Fq 'run list --workflow Publish --branch app-v1.0.0' "$tmp/gh-calls.log"
}

test_wait_for_publish_failure_stops_later_tags() {
  rm -rf "$tmp/bin" "$tmp/work" "$tmp/origin.git" "$tmp/output" "$tmp/create-tags.sh" "$tmp/combined-output" "$tmp/gh-calls.log"
  mkdir "$tmp/bin" "$tmp/work"

  cat > "$tmp/bin/changie" <<'CHANGIE'
#!/usr/bin/env bash
set -euo pipefail

if [ "$1" = "latest" ] && [ "$2" = "--project" ]; then
  printf '%s-v1.0.0\n' "$3"
  exit 0
fi

echo "unexpected changie invocation: $*" >&2
exit 1
CHANGIE
  chmod +x "$tmp/bin/changie"

  cat > "$tmp/bin/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail

echo "$*" >> "$GH_CALL_LOG"

if [ "$1" = "run" ] && [ "$2" = "list" ]; then
  tag=""
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--branch" ]; then
      tag="$2"
      break
    fi
    shift
  done
  if [ "$tag" = "core-v1.0.0" ]; then
    printf '[{"databaseId":321,"status":"completed","conclusion":"failure","headBranch":"%s"}]\n' "$tag"
  else
    printf '[{"databaseId":654,"status":"completed","conclusion":"success","headBranch":"%s"}]\n' "$tag"
  fi
  exit 0
fi

if [ "$1" = "run" ] && [ "$2" = "view" ]; then
  if [ "$3" = "321" ]; then
    printf '{"status":"completed","conclusion":"failure"}\n'
  else
    printf '{"status":"completed","conclusion":"success"}\n'
  fi
  exit 0
fi

echo "unexpected gh invocation: $*" >&2
exit 1
GH
  chmod +x "$tmp/bin/gh"

  git init --bare "$tmp/origin.git" >/dev/null

  git -C "$tmp/work" init >/dev/null
  git -C "$tmp/work" config user.email test@example.com
  git -C "$tmp/work" config user.name "Test User"
  git -C "$tmp/work" commit --allow-empty -m "release" >/dev/null
  git -C "$tmp/work" remote add origin "$tmp/origin.git"

  extract_create_tags_script > "$tmp/create-tags.sh"
  : > "$tmp/gh-calls.log"

  if (
    cd "$tmp/work"
    PATH="$tmp/bin:$PATH" \
      PROJECTS="core,app" \
      PREFIX="" \
      GITHUB_TOKEN="test-token" \
      GH_TOKEN="test-token" \
      GITHUB_OUTPUT="$tmp/output" \
      WAIT_FOR_PUBLISH="true" \
      PUBLISH_WORKFLOW_NAME="Publish" \
      PUBLISH_WAIT_TIMEOUT_SECONDS="30" \
      PUBLISH_WAIT_POLL_SECONDS="1" \
      GH_CALL_LOG="$tmp/gh-calls.log" \
      bash "$tmp/create-tags.sh"
  ) > "$tmp/combined-output" 2>&1; then
    echo "Expected publish failure for core-v1.0.0 to stop later tags" >&2
    exit 1
  fi

  git --git-dir="$tmp/origin.git" rev-parse --verify refs/tags/core-v1.0.0 >/dev/null
  if git --git-dir="$tmp/origin.git" rev-parse --verify refs/tags/app-v1.0.0 >/dev/null 2>&1; then
    echo "Expected app-v1.0.0 not to be pushed after core publish failure" >&2
    exit 1
  fi
  grep -Fq 'Publish workflow run 321 for tag core-v1.0.0 completed with conclusion failure' "$tmp/combined-output"
}

test_wait_for_publish_ignores_discovery_command_and_parse_failures() {
  rm -rf "$tmp/bin" "$tmp/work" "$tmp/origin.git" "$tmp/output" "$tmp/create-tags.sh" "$tmp/gh-calls.log" "$tmp/gh-list-count"
  mkdir "$tmp/bin" "$tmp/work"

  cat > "$tmp/bin/changie" <<'CHANGIE'
#!/usr/bin/env bash
set -euo pipefail

if [ "$1" = "latest" ]; then
  printf 'v1.0.0\n'
  exit 0
fi

echo "unexpected changie invocation: $*" >&2
exit 1
CHANGIE
  chmod +x "$tmp/bin/changie"

  cat > "$tmp/bin/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail

echo "$*" >> "$GH_CALL_LOG"

if [ "$1" = "run" ] && [ "$2" = "list" ]; then
  count=$(cat "$GH_LIST_COUNT" 2>/dev/null || printf '0')
  count=$((count + 1))
  printf '%s' "$count" > "$GH_LIST_COUNT"

  if [ "$count" -eq 1 ]; then
    echo "temporary gh list failure" >&2
    exit 1
  fi
  if [ "$count" -eq 2 ]; then
    printf 'not-json\n'
    exit 0
  fi

  printf '[{"databaseId":456,"status":"queued","conclusion":null,"headBranch":"v1.0.0"}]\n'
  exit 0
fi

if [ "$1" = "run" ] && [ "$2" = "view" ]; then
  printf '{"status":"completed","conclusion":"success"}\n'
  exit 0
fi

echo "unexpected gh invocation: $*" >&2
exit 1
GH
  chmod +x "$tmp/bin/gh"

  git init --bare "$tmp/origin.git" >/dev/null

  git -C "$tmp/work" init >/dev/null
  git -C "$tmp/work" config user.email test@example.com
  git -C "$tmp/work" config user.name "Test User"
  git -C "$tmp/work" commit --allow-empty -m "release" >/dev/null
  git -C "$tmp/work" remote add origin "$tmp/origin.git"

  extract_create_tags_script > "$tmp/create-tags.sh"
  : > "$tmp/gh-calls.log"
  printf '0' > "$tmp/gh-list-count"

  (
    cd "$tmp/work"
    PATH="$tmp/bin:$PATH" \
      PROJECTS="" \
      PREFIX="" \
      GITHUB_TOKEN="test-token" \
      GH_TOKEN="test-token" \
      GITHUB_OUTPUT="$tmp/output" \
      WAIT_FOR_PUBLISH="true" \
      PUBLISH_WORKFLOW_NAME="Publish" \
      PUBLISH_WAIT_TIMEOUT_SECONDS="30" \
      PUBLISH_WAIT_POLL_SECONDS="1" \
      GH_CALL_LOG="$tmp/gh-calls.log" \
      GH_LIST_COUNT="$tmp/gh-list-count" \
      bash "$tmp/create-tags.sh"
  )

  assert_eq "3" "$(cat "$tmp/gh-list-count")" "gh run list attempts"
  assert_eq "created-tags=v1.0.0" "$(grep '^created-tags=' "$tmp/output")" "created-tags output"
  grep -Fq 'run view 456 --json status,conclusion' "$tmp/gh-calls.log"
}

test_wait_for_publish_fails_clearly_when_view_parse_fails() {
  rm -rf "$tmp/bin" "$tmp/work" "$tmp/origin.git" "$tmp/output" "$tmp/create-tags.sh" "$tmp/stderr" "$tmp/gh-calls.log"
  mkdir "$tmp/bin" "$tmp/work"

  cat > "$tmp/bin/changie" <<'CHANGIE'
#!/usr/bin/env bash
set -euo pipefail

if [ "$1" = "latest" ]; then
  printf 'v1.0.0\n'
  exit 0
fi

echo "unexpected changie invocation: $*" >&2
exit 1
CHANGIE
  chmod +x "$tmp/bin/changie"

  cat > "$tmp/bin/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail

echo "$*" >> "$GH_CALL_LOG"

if [ "$1" = "run" ] && [ "$2" = "list" ]; then
  printf '[{"databaseId":789,"status":"queued","conclusion":null,"headBranch":"v1.0.0"}]\n'
  exit 0
fi

if [ "$1" = "run" ] && [ "$2" = "view" ]; then
  printf 'not-json\n'
  exit 0
fi

echo "unexpected gh invocation: $*" >&2
exit 1
GH
  chmod +x "$tmp/bin/gh"

  git init --bare "$tmp/origin.git" >/dev/null

  git -C "$tmp/work" init >/dev/null
  git -C "$tmp/work" config user.email test@example.com
  git -C "$tmp/work" config user.name "Test User"
  git -C "$tmp/work" commit --allow-empty -m "release" >/dev/null
  git -C "$tmp/work" remote add origin "$tmp/origin.git"

  extract_create_tags_script > "$tmp/create-tags.sh"
  : > "$tmp/gh-calls.log"

  if (
    cd "$tmp/work"
    PATH="$tmp/bin:$PATH" \
      PROJECTS="" \
      PREFIX="" \
      GITHUB_TOKEN="test-token" \
      GH_TOKEN="test-token" \
      GITHUB_OUTPUT="$tmp/output" \
      WAIT_FOR_PUBLISH="true" \
      PUBLISH_WORKFLOW_NAME="Publish" \
      PUBLISH_WAIT_TIMEOUT_SECONDS="30" \
      PUBLISH_WAIT_POLL_SECONDS="1" \
      GH_CALL_LOG="$tmp/gh-calls.log" \
      bash "$tmp/create-tags.sh"
  ) 2> "$tmp/stderr"; then
    echo "Expected wait_for_publish to fail when gh run view output cannot be parsed" >&2
    exit 1
  fi

  grep -Fq 'Failed to read publish workflow run 789 for tag v1.0.0' "$tmp/stderr"
}

test_single_project_skips_remote_existing_tag_without_waiting() {
  rm -rf "$tmp/bin" "$tmp/seed" "$tmp/work" "$tmp/origin.git" "$tmp/output" "$tmp/create-tags.sh" "$tmp/gh-calls.log"
  mkdir "$tmp/bin" "$tmp/seed" "$tmp/work"

  cat > "$tmp/bin/changie" <<'CHANGIE'
#!/usr/bin/env bash
set -euo pipefail

if [ "$1" = "latest" ]; then
  printf 'v1.0.0\n'
  exit 0
fi

echo "unexpected changie invocation: $*" >&2
exit 1
CHANGIE
  chmod +x "$tmp/bin/changie"

  cat > "$tmp/bin/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail

echo "$*" >> "$GH_CALL_LOG"
echo "gh should not be called when single-project tag already exists" >&2
exit 1
GH
  chmod +x "$tmp/bin/gh"

  git init --bare "$tmp/origin.git" >/dev/null

  git -C "$tmp/seed" init >/dev/null
  git -C "$tmp/seed" config user.email test@example.com
  git -C "$tmp/seed" config user.name "Test User"
  git -C "$tmp/seed" commit --allow-empty -m "seed" >/dev/null
  git -C "$tmp/seed" tag v1.0.0
  git -C "$tmp/seed" remote add origin "$tmp/origin.git"
  git -C "$tmp/seed" push origin main v1.0.0 >/dev/null

  git -C "$tmp/work" init >/dev/null
  git -C "$tmp/work" config user.email test@example.com
  git -C "$tmp/work" config user.name "Test User"
  git -C "$tmp/work" commit --allow-empty -m "release" >/dev/null
  git -C "$tmp/work" remote add origin "$tmp/origin.git"

  extract_create_tags_script > "$tmp/create-tags.sh"
  : > "$tmp/gh-calls.log"

  (
    cd "$tmp/work"
    PATH="$tmp/bin:$PATH" \
      PROJECTS="" \
      PREFIX="" \
      GITHUB_TOKEN="test-token" \
      GH_TOKEN="test-token" \
      GITHUB_OUTPUT="$tmp/output" \
      WAIT_FOR_PUBLISH="true" \
      PUBLISH_WORKFLOW_NAME="Publish" \
      PUBLISH_WAIT_TIMEOUT_SECONDS="30" \
      PUBLISH_WAIT_POLL_SECONDS="1" \
      GH_CALL_LOG="$tmp/gh-calls.log" \
      bash "$tmp/create-tags.sh"
  )

  assert_eq "created-tags=" "$(grep '^created-tags=' "$tmp/output")" "created-tags output"
  if [ -s "$tmp/gh-calls.log" ]; then
    echo "Expected no gh calls when single-project tag already exists" >&2
    exit 1
  fi
}

test_single_project_release_skips_when_no_created_tag() {
  rm -rf "$tmp/bin" "$tmp/work" "$tmp/create-release.sh" "$tmp/gh-calls.log"
  mkdir "$tmp/bin" "$tmp/work"

  cat > "$tmp/bin/changie" <<'CHANGIE'
#!/usr/bin/env bash
set -euo pipefail

if [ "$1" = "latest" ]; then
  printf 'v1.0.0\n'
  exit 0
fi

echo "unexpected changie invocation: $*" >&2
exit 1
CHANGIE
  chmod +x "$tmp/bin/changie"

  cat > "$tmp/bin/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail

echo "$*" >> "$GH_CALL_LOG"
echo "gh release create should not be called without a newly-created tag" >&2
exit 1
GH
  chmod +x "$tmp/bin/gh"

  extract_create_releases_script > "$tmp/create-release.sh"
  : > "$tmp/gh-calls.log"

  (
    cd "$tmp/work"
    PATH="$tmp/bin:$PATH" \
      PROJECTS="" \
      PREFIX="" \
      CREATED_TAGS="" \
      CHANGES_DIR=".changes" \
      SEPARATOR="-" \
      GH_CALL_LOG="$tmp/gh-calls.log" \
      bash "$tmp/create-release.sh"
  )

  if [ -s "$tmp/gh-calls.log" ]; then
    echo "Expected no gh calls when single-project release has no created tag" >&2
    exit 1
  fi
}

test_skips_remote_existing_tags_without_local_tag
test_wait_for_publish_checks_each_pushed_tag_serially
test_wait_for_publish_failure_stops_later_tags
test_wait_for_publish_ignores_discovery_command_and_parse_failures
test_wait_for_publish_fails_clearly_when_view_parse_fails
test_single_project_skips_remote_existing_tag_without_waiting
test_single_project_release_skips_when_no_created_tag
