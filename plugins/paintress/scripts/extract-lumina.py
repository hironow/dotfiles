#!/usr/bin/env python3
"""Extract Lumina patterns (success/failure) from journal.tsv."""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "fix", "add", "update", "change", "modify", "remove", "delete",
})

OFFENSIVE_THRESHOLD = 3
DEFENSIVE_THRESHOLD = 2


def tokenize(text: str) -> list[str]:
    words = text.lower().split()
    return [w for w in words if len(w) > 2 and w not in STOP_WORDS]


def extract_key_phrase(description: str) -> str:
    tokens = tokenize(description)
    return " ".join(tokens[:6]) if tokens else description.lower().strip()


def find_similar_groups(descriptions: list[str]) -> list[tuple[str, int]]:
    phrases = [extract_key_phrase(d) for d in descriptions]
    counter = Counter(phrases)
    return [(phrase, count) for phrase, count in counter.most_common() if count >= 2]


def extract_lumina(journal_path: str) -> dict:
    path = Path(journal_path)
    if not path.exists():
        return {"offensive": [], "defensive": [], "recent_failures": []}

    entries: list[dict] = []
    with path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            entries.append(row)

    successes = [e.get("description", "") for e in entries if e.get("status") == "success"]
    failures = [e for e in entries if e.get("status", "").startswith("fail:")]
    failure_descs = [e.get("description", "") for e in failures]

    # Offensive Lumina: success patterns (3+ occurrences)
    offensive: list[dict[str, str | int]] = []
    for phrase, count in find_similar_groups(successes):
        if count >= OFFENSIVE_THRESHOLD:
            offensive.append({"pattern": phrase, "count": count})

    # Defensive Lumina: failure patterns (2+ occurrences)
    defensive: list[dict[str, str | int]] = []
    for phrase, count in find_similar_groups(failure_descs):
        if count >= DEFENSIVE_THRESHOLD:
            defensive.append({"pattern": phrase, "count": count})

    # Recent failures (last 3)
    recent_failures: list[dict[str, str]] = []
    for e in reversed(entries):
        if e.get("status", "").startswith("fail:"):
            recent_failures.append({
                "status": e.get("status", ""),
                "description": e.get("description", ""),
            })
            if len(recent_failures) >= 3:
                break

    return {
        "offensive": offensive,
        "defensive": defensive,
        "recent_failures": recent_failures,
    }


def format_markdown(lumina: dict) -> str:
    lines = ["## Lumina (Learned Patterns)", ""]

    if lumina["offensive"]:
        lines.append("### Offensive (Proven Approaches)")
        for p in lumina["offensive"]:
            lines.append(f"[OK] Proven approach ({p['count']}x successful): {p['pattern']}")
        lines.append("")

    if lumina["defensive"]:
        lines.append("### Defensive (Known Pitfalls)")
        for p in lumina["defensive"]:
            lines.append(f"[WARN] Avoid — failed {p['count']} times: {p['pattern']}")
        lines.append("")

    if lumina["recent_failures"]:
        lines.append("### Recent Failure Context")
        for f in lumina["recent_failures"]:
            lines.append(f"- {f['status']} — {f['description']}")
        lines.append("")

    if not lumina["offensive"] and not lumina["defensive"]:
        lines.append("No patterns detected yet. First expeditions build the knowledge base.")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: extract-lumina.py <journal.tsv> [--output lumina.md]", file=sys.stderr)
        sys.exit(1)

    lumina = extract_lumina(sys.argv[1])

    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = Path(sys.argv[idx + 1])
            output_path.write_text(format_markdown(lumina))
            print(f"Written to {output_path}", file=sys.stderr)

    print(json.dumps(lumina, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
