"""The unit suite runs as shards, and a gate proves that nothing was dropped.

The shard count lives in three places (the matrix, `--splits`, and the gate's
`--junit` list). These tests keep them equal, so a change to one fails here
and not as a silent hole in CI.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIT = (ROOT / ".github/workflows/unit-test.yaml").read_text(encoding="utf-8")
DURATIONS = ROOT / "tests/durations/unit.json"


def _job(name: str) -> str:
    start = UNIT.index(f"\n  {name}:\n") + 1
    rest = UNIT[start + 1 :]
    match = re.search(r"\n  [\w-]+:\n", rest)
    return UNIT[start : start + 1 + match.start()] if match else UNIT[start:]


def test_matrix_splits_and_gate_agree_on_the_shard_count() -> None:
    shard = _job("unit-shard")
    (groups,) = re.findall(r"group: \[([\d, ]+)\]", shard)
    count = len(groups.split(","))
    assert groups.replace(" ", "") == ",".join(str(i) for i in range(1, count + 1))
    assert f"--splits {count}" in shard
    gate = _job("unit")
    assert len(re.findall(r"--junit ", gate)) == count
    # One list per shard, compared by ids: a byte compare fails on pytest's
    # summary line, which holds the collection time.
    assert len(re.findall(r"--collected ", gate)) == count
    assert "cmp " not in gate
    # a slow runner must not read as stale durations
    assert "--durations-in ../../tests/durations/unit.json" in gate
    assert f"of {count})" in shard


def test_the_gate_keeps_its_name_and_waits_for_every_shard_and_the_extras() -> None:
    gate = _job("unit")
    assert "name: unit tests + instruction budget" in gate
    assert "needs: [unit-shard, unit-extras]" in gate
    assert "always()" in gate
    assert '"success success"' in gate
    assert "go run . shards" in gate


def test_the_durations_file_covers_the_suite() -> None:
    durations = json.loads(DURATIONS.read_text(encoding="utf-8"))
    assert len(durations) > 1000
    assert all(key.startswith("tests/unit/") for key in durations)
    assert all(isinstance(v, int | float) and v >= 0 for v in durations.values())
