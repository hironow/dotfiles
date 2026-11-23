"""The unit suite runs as shards, and a gate proves that nothing was dropped.

The shard count lives in three places (the matrix, `--splits`, and the gate's
`--junit` list). These tests keep them equal, so a change to one fails here
and not as a silent hole in CI.
"""

import json
import re
from pathlib import Path

import pytest

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


CACHE_SHA = "55cc8345863c7cc4c66a329aec7e433d2d1c52a9"  # actions/cache v6.1.0


# Windows only: measured on PR #680 with three cold and three warm runs,
# alternating, the cache cut the slowest Windows shard in every pair
# (141 -> 118, 137 -> 121, 145 -> 121 s); on Linux it did not in one pair
# (75 -> 84 s), so Linux has no cache step.
@pytest.mark.parametrize(
    ("job_id", "test_step"),
    [("windows-unit-shard", "- name: Unit tests, this shard")],
)
def test_the_shards_restore_mains_go_cache_and_shard_1_on_main_saves_it(
    job_id: str, test_step: str
) -> None:
    # Each xdist worker builds tools/text-hygiene once (the session fixture
    # in test_check_text_hygiene.py): 4 builds a shard, 17-51 s each from an
    # empty cache. Seeded from main (docs/agents/ci-speed.md); the fixture
    # still builds from source every run, so a cold cache costs only time.
    job = _job(job_id)
    restore = job.index(f"uses: actions/cache/restore@{CACHE_SHA} # v6.1.0")
    tests = job.index(test_step)
    save = job.index(f"uses: actions/cache/save@{CACHE_SHA} # v6.1.0")
    assert restore < tests < save
    # the Go that builds is in the key: a runner Go update makes a new key,
    # which main then saves (a cache key cannot be overwritten)
    assert 'echo "UNIT_GO_VERSION=$(go env GOVERSION)"' in job
    key = (
        "key: unit-go-${{ runner.os }}-${{ runner.arch }}-${{ env.UNIT_GO_VERSION }}-"
        "${{ hashFiles('tools/text-hygiene/**') }}"
    )
    assert job.count(key) == 2, "restore and save use the same key"
    assert "restore-keys: unit-go-${{ runner.os }}-${{ runner.arch }}-\n" in job
    save_step = job[job.rindex("\n      - ", 0, save) :]
    # one writer per key: shard 1, on main
    assert "if: github.event_name == 'push' && matrix.group == 1\n" in save_step
    assert 'echo "GOCACHE=$RUNNER_TEMP/go-build"' in job
    assert 'echo "GOMODCACHE=$RUNNER_TEMP/go-mod"' in job


def test_the_linux_shards_have_no_go_cache_step() -> None:
    assert "actions/cache/" not in _job("unit-shard")
