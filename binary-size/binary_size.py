#!/usr/bin/env python3
"""binary-size composite action helper.

Subcommands:
    cache-keys           Emit save/restore cache keys for the current run.
    measure-and-report   Detect baseline, measure files, write markdown report.

Replaces the bash + jq + awk implementation. Same outputs:
    has-baseline, total-size, sizes-json, total-delta, report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import NoReturn


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


_KB = 1024
_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024


def format_size(byte_count: int) -> str:
    """Render a byte count as '1.00 KB' / '2.50 MB' / '512 B' (signed)."""
    sign = "-" if byte_count < 0 else ""
    n = abs(byte_count)
    if n >= _GB:
        return f"{sign}{n / _GB:.2f} GB"
    if n >= _MB:
        return f"{sign}{n / _MB:.2f} MB"
    if n >= _KB:
        return f"{sign}{n / _KB:.2f} KB"
    return f"{sign}{n} B"


def format_delta(delta: int) -> str:
    if delta > 0:
        return f"+{format_size(delta)}"
    if delta < 0:
        return format_size(delta)
    return "±0 B"


def format_percent(old: int, new: int) -> str:
    if old == 0:
        return "±0%" if new == 0 else "new"
    pct = (new - old) / old * 100
    if pct > 0:
        return f"+{pct:.2f}%"
    if pct < 0:
        return f"{pct:.2f}%"
    return "±0%"


def parse_paths(text: str) -> list[str]:
    """Parse newline-separated paths; skip blanks and comment lines."""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def hash_paths(text: str) -> str:
    """Return the first 16 hex chars of sha256 of the input (mirrors bash)."""
    # bash piped via `echo "$INPUT" | sha256sum`, which appends a newline.
    # Match that to keep cache keys stable across the migration.
    payload = text if text.endswith("\n") else text + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def sanitize_branch(name: str) -> str:
    return name.replace("/", "-")


def measure_sizes(
    paths: list[str], working_dir: Path
) -> tuple[dict[str, int], int, list[str]]:
    """Stat each path; return (sizes_map, total, missing_list)."""
    sizes: dict[str, int] = {}
    total = 0
    missing: list[str] = []
    for p in paths:
        full = working_dir / p
        if not full.is_file():
            missing.append(p)
            continue
        size = full.stat().st_size
        sizes[p] = size
        total += size
    return sizes, total, missing


def generate_report(
    current: dict[str, int],
    baseline: dict[str, int] | None,
    base_branch: str,
) -> tuple[str, int]:
    """Render the markdown report and return (report_text, total_delta)."""
    files = sorted(current.keys())
    current_total = sum(current.values())
    lines = ["### 📦 Binary Size Report", ""]

    if baseline is not None:
        lines.append("| File | Size | Δ Delta | % Change |")
        lines.append("|------|------|---------|----------|")
        baseline_total = 0
        for f in files:
            cur = current[f]
            base = baseline.get(f, 0)
            baseline_total += base
            lines.append(
                f"| `{f}` | {format_size(cur)} | "
                f"{format_delta(cur - base)} | {format_percent(base, cur)} |"
            )
        total_delta = current_total - baseline_total
        lines.append(
            f"| **Total** | **{format_size(current_total)}** | "
            f"**{format_delta(total_delta)}** | "
            f"**{format_percent(baseline_total, current_total)}** |"
        )
        lines += [
            "",
            "<details><summary>Details</summary>",
            "",
            f"Compared against baseline from `{base_branch}`.",
            "",
            "</details>",
        ]
        return "\n".join(lines), total_delta

    lines.append("| File | Size |")
    lines.append("|------|------|")
    for f in files:
        lines.append(f"| `{f}` | {format_size(current[f])} |")
    lines.append(f"| **Total** | **{format_size(current_total)}** |")
    lines += [
        "",
        "> ℹ️ No baseline found. Sizes will be used as the baseline for future comparisons.",
    ]
    return "\n".join(lines), 0


# ---------------------------------------------------------------------------
# IO glue
# ---------------------------------------------------------------------------


def _write_output(key: str, value: str) -> None:
    out_file = os.environ.get("GITHUB_OUTPUT")
    if "\n" in value:
        sentinel = f"EOF_{key.upper().replace('-', '_')}"
        block = f"{key}<<{sentinel}\n{value}\n{sentinel}\n"
    else:
        block = f"{key}={value}\n"
    if out_file:
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(block)
    else:
        sys.stdout.write(block)


def _fail(message: str) -> NoReturn:
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_cache_keys() -> None:
    paths_text = os.environ.get("INPUT_PATHS", "")
    prefix = os.environ.get("CACHE_PREFIX", "binary-size")
    base_branch = os.environ.get("BASE_BRANCH", "main")
    save_branch = os.environ.get("SAVE_BRANCH", "")
    sha = os.environ.get("GITHUB_SHA", "")

    paths_hash = hash_paths(paths_text)
    save_safe = sanitize_branch(save_branch)
    base_safe = sanitize_branch(base_branch)

    _write_output("save-key", f"{prefix}-{save_safe}-{paths_hash}-{sha}")
    _write_output("restore-prefix", f"{prefix}-{base_safe}-{paths_hash}-")


def cmd_measure_and_report() -> None:
    paths_text = os.environ.get("INPUT_PATHS", "")
    working_dir = Path(os.environ.get("WORKING_DIRECTORY", "."))
    base_branch = os.environ.get("BASE_BRANCH", "main")
    cache_dir = Path(os.environ.get("CACHE_DIR", "/tmp/binary-size-cache"))
    baseline_file = Path(
        os.environ.get("BASELINE_FILE", "/tmp/binary-size-baseline.json")
    )

    # Detect + preserve baseline before we overwrite the cache directory
    cache_sizes = cache_dir / "sizes.json"
    has_baseline = cache_sizes.is_file()
    baseline: dict[str, int] | None = None
    if has_baseline:
        shutil.copyfile(cache_sizes, baseline_file)
        try:
            baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            _fail(f"Failed to parse baseline cache: {e}")
        print("Baseline loaded from cache")
    else:
        cache_dir.mkdir(parents=True, exist_ok=True)
        print("No baseline found — sizes will be reported without comparison")

    paths = parse_paths(paths_text)
    sizes, total, missing = measure_sizes(paths, working_dir)
    for m in missing:
        print(f"::warning::File not found: {m}")

    cache_sizes.write_text(json.dumps(sizes), encoding="utf-8")

    report, total_delta = generate_report(sizes, baseline, base_branch)

    _write_output("has-baseline", "true" if has_baseline else "false")
    _write_output("total-size", str(total))
    _write_output("sizes-json", json.dumps(sizes))
    _write_output("total-delta", str(total_delta))
    _write_output("report", report)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


_HANDLERS = {
    "cache-keys": cmd_cache_keys,
    "measure-and-report": cmd_measure_and_report,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(_HANDLERS))
    args = parser.parse_args()
    _HANDLERS[args.command]()


if __name__ == "__main__":
    main()
