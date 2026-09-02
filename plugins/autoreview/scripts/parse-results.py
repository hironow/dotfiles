#!/usr/bin/env python3
"""Parse autoreview review-results.tsv and output summary statistics as JSON.

Columns (tab-separated, one header row):
    commit  mode  category  file  findings_before  findings_after  status  description
"""

import json
import sys
from pathlib import Path

COLUMNS = 8


def _row(parts: list[str]) -> dict:
    return {
        "commit": parts[0],
        "mode": parts[1],
        "category": parts[2],
        "file": parts[3],
        "findings_before": int(float(parts[4])),
        "findings_after": int(float(parts[5])),
        "status": parts[6],
        "description": parts[7] if len(parts) > 7 else "",
    }


def _group(rows: list[dict], key: str) -> list[dict]:
    """Summarize rows grouped by `key`, ordered by findings reduction."""
    names: list[str] = []
    for row in rows:
        if row[key] not in names:
            names.append(row[key])

    groups: list[dict] = []
    for name in names:
        member = [r for r in rows if r[key] == name]
        attempts = [r for r in member if r["status"] != "skip"]
        start = attempts[0]["findings_before"] if attempts else 0
        end = attempts[-1]["findings_after"] if attempts else 0
        groups.append(
            {
                key: name,
                "iterations": len(member),
                "keeps": len([r for r in member if r["status"] == "keep"]),
                "reverts": len([r for r in member if r["status"] == "revert"]),
                "skips": len([r for r in member if r["status"] == "skip"]),
                "crashes": len([r for r in member if r["status"] == "crash"]),
                "findings_start": start,
                "findings_end": end,
                "reduction": start - end,
            }
        )
    groups.sort(key=lambda g: (-g["reduction"], g[key]))
    return groups


def parse_results(filepath: str) -> dict:
    """Parse review-results.tsv and return summary statistics."""
    path = Path(filepath)
    if not path.exists():
        return {"error": f"File not found: {filepath}"}

    rows: list[dict] = []
    with open(path) as f:
        for lineno, line in enumerate(f):
            parts = line.rstrip("\n").split("\t")
            if lineno == 0 and parts[0] == "commit":
                continue
            if len(parts) >= COLUMNS - 1 and parts[0]:
                rows.append(_row(parts))

    if not rows:
        return {"error": "No review iterations found", "total_iterations": 0}

    attempts = [r for r in rows if r["status"] != "skip"]
    keeps = [r for r in rows if r["status"] == "keep"]
    baseline = attempts[0]["findings_before"] if attempts else 0
    final = attempts[-1]["findings_after"] if attempts else 0

    return {
        "total_iterations": len(rows),
        "keeps": len(keeps),
        "reverts": len([r for r in rows if r["status"] == "revert"]),
        "skips": len([r for r in rows if r["status"] == "skip"]),
        "crashes": len([r for r in rows if r["status"] == "crash"]),
        "keep_rate": round(len(keeps) / len(rows) * 100, 1),
        "modes": sorted({r["mode"] for r in rows}),
        "baseline_findings": baseline,
        "final_findings": final,
        "net_reduction": baseline - final,
        "by_category": _group(rows, "category"),
        "by_file": _group(rows, "file"),
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: parse-results.py <review-results.tsv>", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(parse_results(sys.argv[1]), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
