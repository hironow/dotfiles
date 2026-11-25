"""The unit suite runs as shards, and a gate proves that nothing was dropped.

The shard count lives in three places (the matrix, `--splits`, and the gate's
`--junit` list). These tests keep them equal, so a change to one fails here
and not as a silent hole in CI.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DURATIONS = ROOT / "tests/durations/unit.json"


def test_the_durations_file_covers_the_suite() -> None:
    durations = json.loads(DURATIONS.read_text(encoding="utf-8"))
    assert len(durations) > 1000
    assert all(key.startswith("tests/unit/") for key in durations)
    assert all(isinstance(v, int | float) and v >= 0 for v in durations.values())


# Windows only: measured on PR #680 with three cold and three warm runs,
# alternating, the cache cut the slowest Windows shard in every pair
# (141 -> 118, 137 -> 121, 145 -> 121 s); on Linux it did not in one pair
# (75 -> 84 s), so Linux has no cache step.
