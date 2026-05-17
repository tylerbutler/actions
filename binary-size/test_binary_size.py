"""Tests for binary_size.

Run:
    uv run --with pytest pytest binary-size/test_binary_size.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from binary_size import (  # noqa: E402
    cmd_cache_keys,
    cmd_measure_and_report,
    format_delta,
    format_percent,
    format_size,
    generate_report,
    hash_paths,
    measure_sizes,
    parse_paths,
    sanitize_branch,
)


# --- format_size ---


class TestFormatSize:
    def test_bytes(self):
        assert format_size(0) == "0 B"
        assert format_size(512) == "512 B"
        assert format_size(1023) == "1023 B"

    def test_kb(self):
        assert format_size(1024) == "1.00 KB"
        assert format_size(2048) == "2.00 KB"

    def test_mb(self):
        assert format_size(1024 * 1024) == "1.00 MB"
        assert format_size(int(2.5 * 1024 * 1024)) == "2.50 MB"

    def test_gb(self):
        assert format_size(1024 ** 3) == "1.00 GB"

    def test_negative(self):
        assert format_size(-1024) == "-1.00 KB"
        assert format_size(-512) == "-512 B"


# --- format_delta ---


class TestFormatDelta:
    def test_positive(self):
        assert format_delta(1024) == "+1.00 KB"

    def test_negative(self):
        assert format_delta(-2048) == "-2.00 KB"

    def test_zero(self):
        assert format_delta(0) == "±0 B"


# --- format_percent ---


class TestFormatPercent:
    def test_zero_to_zero(self):
        assert format_percent(0, 0) == "±0%"

    def test_zero_to_nonzero(self):
        assert format_percent(0, 100) == "new"

    def test_increase(self):
        assert format_percent(100, 150) == "+50.00%"

    def test_decrease(self):
        assert format_percent(100, 50) == "-50.00%"

    def test_unchanged(self):
        assert format_percent(100, 100) == "±0%"


# --- parse_paths ---


class TestParsePaths:
    def test_simple(self):
        assert parse_paths("a\nb\nc") == ["a", "b", "c"]

    def test_skip_blank(self):
        assert parse_paths("a\n\nb\n   \nc") == ["a", "b", "c"]

    def test_skip_comments(self):
        assert parse_paths("a\n# comment\nb") == ["a", "b"]

    def test_strip_whitespace(self):
        assert parse_paths("  a  \n\tb\t") == ["a", "b"]


# --- hash_paths ---


class TestHashPaths:
    def test_stable(self):
        h1 = hash_paths("a\nb\nc")
        h2 = hash_paths("a\nb\nc")
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        assert hash_paths("a") != hash_paths("b")

    def test_length_16(self):
        assert len(hash_paths("anything")) == 16


# --- sanitize_branch ---


class TestSanitizeBranch:
    def test_replaces_slashes(self):
        assert sanitize_branch("feat/foo") == "feat-foo"

    def test_no_slash_unchanged(self):
        assert sanitize_branch("main") == "main"

    def test_multiple_slashes(self):
        assert sanitize_branch("a/b/c") == "a-b-c"


# --- measure_sizes ---


class TestMeasureSizes:
    def test_existing_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.bin").write_bytes(b"x" * 100)
        (tmp_path / "b.bin").write_bytes(b"y" * 200)
        sizes, total, missing = measure_sizes(["a.bin", "b.bin"], Path("."))
        assert sizes == {"a.bin": 100, "b.bin": 200}
        assert total == 300
        assert missing == []

    def test_missing_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.bin").write_bytes(b"x" * 50)
        sizes, total, missing = measure_sizes(["a.bin", "missing.bin"], Path("."))
        assert sizes == {"a.bin": 50}
        assert total == 50
        assert missing == ["missing.bin"]


# --- generate_report ---


class TestGenerateReport:
    def test_no_baseline(self):
        current = {"a.bin": 1024}
        report, total_delta = generate_report(current, None, "main")
        assert "### 📦 Binary Size Report" in report
        assert "| File | Size |" in report
        assert "`a.bin`" in report
        assert "1.00 KB" in report
        assert "No baseline" in report
        assert total_delta == 0

    def test_with_baseline_growth(self):
        current = {"a.bin": 2048}
        baseline = {"a.bin": 1024}
        report, total_delta = generate_report(current, baseline, "main")
        assert "Δ Delta" in report
        assert "+1.00 KB" in report
        assert "+100.00%" in report
        assert "main" in report
        assert total_delta == 1024

    def test_with_baseline_shrink(self):
        current = {"a.bin": 512}
        baseline = {"a.bin": 1024}
        report, total_delta = generate_report(current, baseline, "main")
        assert "-512 B" in report
        assert "-50.00%" in report
        assert total_delta == -512

    def test_new_file_no_baseline(self):
        current = {"a.bin": 100}
        baseline: dict[str, int] = {}
        report, total_delta = generate_report(current, baseline, "main")
        assert "new" in report  # percent column
        assert total_delta == 100

    def test_files_sorted(self):
        current = {"z.bin": 100, "a.bin": 100, "m.bin": 100}
        report, _ = generate_report(current, None, "main")
        a_idx = report.index("a.bin")
        m_idx = report.index("m.bin")
        z_idx = report.index("z.bin")
        assert a_idx < m_idx < z_idx


# --- cmd_cache_keys ---


def _read_outputs(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    lines = path.read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if "<<" in line and "=" not in line.split("<<", 1)[0]:
            key, sentinel = line.split("<<", 1)
            buf = []
            i += 1
            while i < len(lines) and lines[i] != sentinel:
                buf.append(lines[i])
                i += 1
            out[key] = "\n".join(buf)
        elif "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
        i += 1
    return out


class TestCmdCacheKeys:
    def test_emits_keys(self, tmp_path, monkeypatch):
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("INPUT_PATHS", "bin/a\nbin/b")
        monkeypatch.setenv("CACHE_PREFIX", "binary-size")
        monkeypatch.setenv("BASE_BRANCH", "main")
        monkeypatch.setenv("SAVE_BRANCH", "feat/foo")
        monkeypatch.setenv("GITHUB_SHA", "abc123")
        cmd_cache_keys()
        result = _read_outputs(outputs)
        assert result["save-key"].startswith("binary-size-feat-foo-")
        assert result["save-key"].endswith("-abc123")
        assert result["restore-prefix"].startswith("binary-size-main-")
        assert result["restore-prefix"].endswith("-")


# --- cmd_measure_and_report ---


class TestCmdMeasureAndReport:
    def test_no_baseline_first_run(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.bin").write_bytes(b"x" * 1024)

        cache_dir = tmp_path / "cache"
        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("INPUT_PATHS", "a.bin")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setenv("BASE_BRANCH", "main")
        monkeypatch.setenv("CACHE_DIR", str(cache_dir))
        monkeypatch.setenv("BASELINE_FILE", str(tmp_path / "baseline.json"))

        cmd_measure_and_report()

        result = _read_outputs(outputs)
        assert result["has-baseline"] == "false"
        assert result["total-size"] == "1024"
        assert json.loads(result["sizes-json"]) == {"a.bin": 1024}
        assert result["total-delta"] == "0"
        assert "1.00 KB" in result["report"]
        # Cache file written for the next run
        assert (cache_dir / "sizes.json").exists()

    def test_with_baseline_diff(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.bin").write_bytes(b"x" * 2048)

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        # Simulate cache restore having placed a baseline at the cache path
        (cache_dir / "sizes.json").write_text(json.dumps({"a.bin": 1024}))

        outputs = tmp_path / "outputs"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        monkeypatch.setenv("INPUT_PATHS", "a.bin")
        monkeypatch.setenv("WORKING_DIRECTORY", ".")
        monkeypatch.setenv("BASE_BRANCH", "main")
        monkeypatch.setenv("CACHE_DIR", str(cache_dir))
        monkeypatch.setenv("BASELINE_FILE", str(tmp_path / "baseline.json"))

        cmd_measure_and_report()

        result = _read_outputs(outputs)
        assert result["has-baseline"] == "true"
        assert result["total-size"] == "2048"
        assert result["total-delta"] == "1024"
        assert "+1.00 KB" in result["report"]
        assert "+100.00%" in result["report"]
