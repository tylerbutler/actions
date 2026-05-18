---
name: actionlint-check
description: Validate all composite action.yml and workflow files in this repo with actionlint. Run before committing changes to any action.
disable-model-invocation: true
---

# actionlint-check

Runs [`actionlint`](https://github.com/rhysd/actionlint) across every `action.yml` and `.github/workflows/*.yml` in the repo and reports problems.

`actionlint` is provided via `mise` (`~/.local/share/mise/installs/actionlint/`). If it is not on `PATH`, fall back to `mise exec actionlint -- actionlint ...`.

## Steps

1. Discover targets:
   ```bash
   fd -e yml -e yaml --full-path '(action\.ya?ml|\.github/workflows/.*\.ya?ml)$' .
   ```
2. Run actionlint against the full set:
   ```bash
   actionlint $(fd -e yml -e yaml --full-path '(action\.ya?ml|\.github/workflows/.*\.ya?ml)$' .)
   ```
3. If `shellcheck` is available, actionlint will lint embedded `run:` blocks automatically. If `shellcheck` is missing, mention it in the report so the user knows shell-script issues weren't checked.
4. Summarise findings grouped by file. For each problem, quote the offending line and propose a fix. If everything passes, say so explicitly.

## Notes

- Don't auto-fix — surface the issues so the user can review.
- The `tests/` shell scripts are not GitHub Actions and should be skipped.
