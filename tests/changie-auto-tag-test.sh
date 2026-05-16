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

test_skips_remote_existing_tags_without_local_tag
