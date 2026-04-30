#!/usr/bin/env python3
"""Parse autoresearch results.tsv and output summary statistics as JSON."""

import json
import sys
from pathlib import Path


def parse_results(filepath: str, direction: str = "lower") -> dict:
    """Parse results.tsv and return summary statistics.

    Args:
        filepath: Path to results.tsv file.
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
            if len(parts) >= 4:
                rows.append(
                    {
                        "commit": parts[0],
                        "metric": float(parts[1]),
                        "status": parts[2],
                        "description": parts[3],
                    }
                )

    if not rows:
        return {"error": "No experiment data found", "total": 0}

    keeps = [r for r in rows if r["status"] == "keep"]
    discards = [r for r in rows if r["status"] == "discard"]
    crashes = [r for r in rows if r["status"] == "crash"]

    baseline = rows[0]["metric"] if rows else 0.0
    select_best = min if direction == "lower" else max
    best_metric = (
        select_best((r["metric"] for r in keeps), default=baseline)
        if keeps
        else baseline
    )

    raw_improvement = (
        baseline - best_metric if direction == "lower" else best_metric - baseline
    )
    relative_improvement = (
        (raw_improvement / abs(baseline) * 100) if baseline != 0 else 0.0
    )

    return {
        "total_experiments": len(rows),
        "keeps": len(keeps),
        "discards": len(discards),
        "crashes": len(crashes),
        "keep_rate": round(len(keeps) / len(rows) * 100, 1) if rows else 0.0,
        "baseline_metric": baseline,
        "best_metric": best_metric,
        "metric_direction": direction,
        "absolute_improvement": round(raw_improvement, 6),
        "relative_improvement": round(relative_improvement, 2),
        "kept_experiments": [
            {
                "commit": r["commit"],
                "metric": r["metric"],
                "delta": round(r["metric"] - baseline, 6),
                "description": r["description"],
            }
            for r in keeps
        ],
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: parse-results.py <results.tsv> [lower|higher]", file=sys.stderr)
        sys.exit(1)

    direction = sys.argv[2] if len(sys.argv) >= 3 else "lower"
    result = parse_results(sys.argv[1], direction=direction)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
