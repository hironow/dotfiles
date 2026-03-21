#!/usr/bin/env python3
"""Parse journal.tsv and output structured JSON summary."""

import csv
import json
import sys
from pathlib import Path


def parse_journal(journal_path: str) -> dict:
    path = Path(journal_path)
    if not path.exists():
        return {"error": f"File not found: {journal_path}"}

    entries: list[dict] = []
    with path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            entries.append(row)

    total = len(entries)
    success = [e for e in entries if e.get("status") == "success"]
    fails = [e for e in entries if e.get("status", "").startswith("fail:")]
    skips = [e for e in entries if e.get("status", "").startswith("skip")]
    partials = [e for e in entries if e.get("status", "").startswith("partial:")]

    fail_categories: dict[str, int] = {}
    for e in fails:
        cat = e.get("status", "fail:unknown")
        fail_categories[cat] = fail_categories.get(cat, 0) + 1

    skip_categories: dict[str, int] = {}
    for e in skips:
        cat = e.get("status", "skip")
        skip_categories[cat] = skip_categories.get(cat, 0) + 1

    return {
        "total_expeditions": total,
        "success_count": len(success),
        "fail_count": len(fails),
        "skip_count": len(skips),
        "partial_count": len(partials),
        "success_rate": round(len(success) / total * 100, 1) if total > 0 else 0,
        "fail_categories": fail_categories,
        "skip_categories": skip_categories,
        "successful_issues": [
            {
                "issue": e.get("issue", ""),
                "commit": e.get("commit", ""),
                "pr_url": e.get("pr_url", ""),
                "description": e.get("description", ""),
            }
            for e in success
        ],
        "failed_issues": [
            {
                "issue": e.get("issue", ""),
                "status": e.get("status", ""),
                "description": e.get("description", ""),
            }
            for e in fails
        ],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: parse-journal.py <journal.tsv>", file=sys.stderr)
        sys.exit(1)
    result = parse_journal(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
