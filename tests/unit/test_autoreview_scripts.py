"""Unit tests for the autoreview plugin's loop-control scripts.

`plugins/autoreview/scripts/next-target.sh` picks the next (category, file)
for a review iteration from review-config.yaml + review-results.tsv and
retires categories that hit a cap (iteration cap, consecutive stalls,
keep/revert oscillation). `plugins/autoreview/scripts/parse-results.py`
summarizes review-results.tsv as JSON. Both replace arithmetic the reviewer
agent used to do by hand from prose, so these tests pin the decision rules
the prose used to state (skills/review-loop/references/decision-logic.md).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from _bash_hook import run_bash

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "plugins" / "autoreview" / "scripts"
NEXT_TARGET = SCRIPTS / "next-target.sh"
PARSE_RESULTS = SCRIPTS / "parse-results.py"

HEADER = "commit\tmode\tcategory\tfile\tfindings_before\tfindings_after\tstatus\tdescription\n"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="next-target.sh needs bash on PATH",
)


def _config(
    categories: list[str],
    max_iter: int = 3,
    max_stall: int = 2,
    block_style: bool = False,
) -> str:
    if block_style:
        cats = "rule_categories:\n" + "".join(f"  - {c}\n" for c in categories)
    else:
        cats = "rule_categories: [" + ", ".join(categories) + "]\n"
    return (
        "mode: scan-fix\n"
        f"{cats}"
        f"max_iterations_per_category: {max_iter}\n"
        f"max_consecutive_no_improvement: {max_stall}\n"
        "results_file: review-results.tsv\n"
    )


def _row(
    category: str,
    file: str,
    before: int,
    after: int,
    status: str,
    commit: str = "abc1234",
) -> str:
    return (
        f"{commit}\tscan-fix\t{category}\t{file}\t{before}\t{after}\t{status}\tdesc\n"
    )


def _setup(tmp_path: Path, config: str, rows: list[str] | None) -> None:
    (tmp_path / "review-config.yaml").write_text(config)
    if rows is not None:
        (tmp_path / "review-results.tsv").write_text(HEADER + "".join(rows))


def _next(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return run_bash(
        NEXT_TARGET,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        companions=(SCRIPTS / "resolve-guardrails.sh",),
    )


# --- next-target.sh -------------------------------------------------------


def test_next_target_picks_category_with_most_remaining_findings(
    tmp_path: Path,
) -> None:
    _setup(
        tmp_path,
        _config(["naming", "type-safety"]),
        [
            _row("naming", "a.py", 5, 3, "keep"),
            _row("type-safety", "b.py", 8, 6, "keep"),
        ],
    )
    result = _next(tmp_path)
    assert result.returncode == 0, result.stderr
    category, file, reason = result.stdout.rstrip("\n").split("\t")
    assert (category, file) == ("type-safety", "b.py")
    assert "6 findings remaining" in reason
    assert result.stderr == ""


def test_next_target_without_results_file_starts_with_first_category(
    tmp_path: Path,
) -> None:
    _setup(tmp_path, _config(["naming", "type-safety"]), rows=None)
    result = _next(tmp_path)
    assert result.returncode == 0, result.stderr
    category, file, reason = result.stdout.rstrip("\n").split("\t")
    assert category == "naming"
    assert file == "-"
    assert "no iteration logged yet" in reason


def test_next_target_retires_category_at_iteration_cap(tmp_path: Path) -> None:
    _setup(
        tmp_path,
        _config(["naming", "type-safety"], max_iter=3),
        [
            _row("naming", "a.py", 9, 8, "keep"),
            _row("naming", "a.py", 8, 7, "keep"),
            _row("naming", "a.py", 7, 6, "keep"),
            _row("type-safety", "b.py", 2, 1, "keep"),
        ],
    )
    result = _next(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("type-safety\tb.py\t")
    assert "skip: naming: reached max_iterations_per_category (3)" in result.stderr


def test_next_target_reports_done_on_oscillation(tmp_path: Path) -> None:
    _setup(
        tmp_path,
        _config(["naming"], max_iter=10, max_stall=10),
        [
            _row("naming", "a.py", 5, 4, "keep"),
            _row("naming", "a.py", 4, 4, "revert"),
            _row("naming", "a.py", 4, 3, "keep"),
        ],
    )
    result = _next(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("DONE\t")
    assert "skip: naming: keep/revert oscillation" in result.stderr


def test_next_target_retires_category_after_consecutive_stalls(tmp_path: Path) -> None:
    _setup(
        tmp_path,
        _config(["naming"], max_iter=10, max_stall=2),
        [
            _row("naming", "a.py", 5, 4, "keep"),
            _row("naming", "a.py", 4, 4, "revert"),
            _row("naming", "a.py", 4, 4, "crash"),
        ],
    )
    result = _next(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("DONE\t")
    assert "skip: naming: 2 consecutive iterations without improvement" in result.stderr


def test_next_target_skip_rows_retire_category_silently(tmp_path: Path) -> None:
    _setup(
        tmp_path,
        _config(["naming", "type-safety"], block_style=True),
        [
            _row("naming", "-", 0, 0, "skip"),
            _row("type-safety", "-", 0, 0, "skip"),
        ],
    )
    result = _next(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "DONE\tall categories are capped or skipped\n"
    assert result.stderr == ""


def test_next_target_fails_loudly_without_config(tmp_path: Path) -> None:
    result = _next(tmp_path)
    assert result.returncode == 1
    assert "config not found" in result.stderr


# --- parse-results.py -----------------------------------------------------


def _parse(path: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(PARSE_RESULTS), str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_parse_results_summarizes_counts_rate_and_reduction(tmp_path: Path) -> None:
    tsv = tmp_path / "review-results.tsv"
    tsv.write_text(
        HEADER
        + _row("naming", "a.py", 10, 7, "keep")
        + _row("naming", "a.py", 7, 7, "revert")
        + _row("type-safety", "b.py", 5, 2, "keep")
        + _row("naming", "-", 0, 0, "skip")
    )
    summary = _parse(tsv)
    assert summary["total_iterations"] == 4
    assert (
        summary["keeps"],
        summary["reverts"],
        summary["skips"],
        summary["crashes"],
    ) == (
        2,
        1,
        1,
        0,
    )
    assert summary["keep_rate"] == 50.0
    assert summary["modes"] == ["scan-fix"]
    assert summary["baseline_findings"] == 10
    assert summary["final_findings"] == 2
    assert summary["net_reduction"] == 8
    by_category = {g["category"]: g for g in summary["by_category"]}
    assert by_category["naming"]["reduction"] == 3
    assert by_category["naming"]["skips"] == 1
    assert by_category["type-safety"]["reduction"] == 3
    assert [g["file"] for g in summary["by_file"]] == ["a.py", "b.py", "-"]


def test_parse_results_reports_missing_file_as_error(tmp_path: Path) -> None:
    summary = _parse(tmp_path / "missing.tsv")
    assert "error" in summary


def test_parse_results_header_only_file_has_zero_iterations(tmp_path: Path) -> None:
    tsv = tmp_path / "review-results.tsv"
    tsv.write_text(HEADER)
    summary = _parse(tsv)
    assert summary["total_iterations"] == 0
    assert "error" in summary
