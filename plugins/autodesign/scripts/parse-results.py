#!/usr/bin/env python3
"""Parse autodesign design-results.tsv and output summary statistics as JSON."""

import json
import sys
from collections import defaultdict
from pathlib import Path


def parse_results(filepath: str, direction: str = "higher") -> dict:
    """Parse design-results.tsv and return summary statistics with axis-level breakdown.

    Args:
        filepath: Path to design-results.tsv file.
        direction: "lower" if lower metric is better, "higher" if higher is better.
    """
    path = Path(filepath)
    if not path.exists():
        return {"error": f"File not found: {filepath}"}

    rows: list[dict] = []
    with open(path) as f:
        f.readline()  # skip header
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 6:
                rows.append(
                    {
                        "commit": parts[0],
                        "composite_score": float(parts[1]),
                        "status": parts[2],
                        "constraint": parts[3],
                        "axis": parts[4],
                        "description": parts[5],
                    }
                )

    if not rows:
        return {"error": "No exploration data found", "total": 0}

    keeps = [r for r in rows if r["status"] == "keep"]
    discards = [r for r in rows if r["status"] == "discard"]
    constraint_fails = [r for r in rows if r["status"] == "constraint_fail"]
    crashes = [r for r in rows if r["status"] == "crash"]

    baseline = rows[0]["composite_score"] if rows else 0.0
    select_best = max if direction == "higher" else min
    best_score = (
        select_best((r["composite_score"] for r in keeps), default=baseline)
        if keeps
        else baseline
    )

    raw_improvement = (
        best_score - baseline if direction == "higher" else baseline - best_score
    )
    relative_improvement = (
        (raw_improvement / abs(baseline) * 100) if baseline != 0 else 0.0
    )

    # Axis-level breakdown
    axis_stats: dict[str, dict] = defaultdict(
        lambda: {"tried": 0, "kept": 0, "scores": []}
    )
    for r in rows:
        axis = r["axis"]
        if axis == "baseline":
            continue
        axis_stats[axis]["tried"] += 1
        if r["status"] == "keep":
            axis_stats[axis]["kept"] += 1
            axis_stats[axis]["scores"].append(r["composite_score"])

    axis_breakdown = {}
    for axis, stats in axis_stats.items():
        keep_rate = (
            round(stats["kept"] / stats["tried"] * 100, 1) if stats["tried"] > 0 else 0
        )
        best_delta = (
            round(max(stats["scores"]) - baseline, 6) if stats["scores"] else None
        )
        axis_breakdown[axis] = {
            "tried": stats["tried"],
            "kept": stats["kept"],
            "keep_rate": keep_rate,
            "best_delta": best_delta,
        }

    # Constraint violation patterns
    constraint_patterns: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for r in constraint_fails:
        constraint_patterns[r["constraint"]][r["axis"]] += 1

    return {
        "total_iterations": len(rows),
        "keeps": len(keeps),
        "discards": len(discards),
        "constraint_fails": len(constraint_fails),
        "crashes": len(crashes),
        "keep_rate": round(len(keeps) / len(rows) * 100, 1) if rows else 0.0,
        "baseline_score": baseline,
        "best_score": best_score,
        "metric_direction": direction,
        "absolute_improvement": round(raw_improvement, 6),
        "relative_improvement": round(relative_improvement, 2),
        "axis_breakdown": axis_breakdown,
        "constraint_violations": {
            k: dict(v) for k, v in constraint_patterns.items()
        },
        "kept_iterations": [
            {
                "commit": r["commit"],
                "composite_score": r["composite_score"],
                "delta": round(r["composite_score"] - baseline, 6),
                "axis": r["axis"],
                "description": r["description"],
            }
            for r in keeps
        ],
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: parse-results.py <design-results.tsv> [higher|lower]",
            file=sys.stderr,
        )
        sys.exit(1)

    direction = sys.argv[2] if len(sys.argv) >= 3 else "higher"
    result = parse_results(sys.argv[1], direction=direction)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
