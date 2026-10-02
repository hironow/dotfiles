"""The compression payloads must be deterministic to the byte.

The spoke publishes a ratio per payload. A ratio is only comparable across
headroom versions if the input is identical, so these tests pin the payloads by
hash: changing one is allowed, but it has to be a deliberate edit here too, and
the published table has to be re-measured when it happens.

Nothing here starts headroom. The live measurement is
`just headroom-compress-measure`.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from headroom_compress_measure import (
    EGRESS_OFF,
    PAYLOADS,
    Measurement,
    format_table,
)

# sha256 of the payload's UTF-8 bytes, and its length in characters.
#
# These are not arbitrary: headroom's own answer carries a `hash` field that is
# this sha256 truncated to 24 hex characters, which is how the table published
# in the spoke was confirmed to have been measured over exactly these bytes.
EXPECTED: dict[str, tuple[int, str]] = {
    "700 log lines": (
        71289,
        "e5078f356157f23b9002653d7e08f1cf372b7eb3662e037b4553b2afc6dfb186",
    ),
    "700-object JSON array": (
        90879,
        "e47b83f3b5294dedc7e1a0e43f6a0ef46fc09df1dcf613d8031664e5143e4c85",
    ),
    "700-line `ls -la` listing": (
        44099,
        "8ffd5de2eb5ca25d3c554fcd4dfe58ac9802ef7c437311876693f7009aa397e4",
    ),
    "repetitive prose": (
        12399,
        "5ff8650b13849ee0f07b5f09d88ffe8a0c910ec93e68474733558de62c27461a",
    ),
}


def test_every_payload_is_pinned() -> None:
    """No payload may be added or renamed without pinning it here."""
    assert sorted(PAYLOADS) == sorted(EXPECTED)


@pytest.mark.parametrize("label", sorted(EXPECTED))
def test_payload_is_deterministic(label: str) -> None:
    """Two calls produce the same bytes, and they are the pinned bytes."""
    build = PAYLOADS[label]
    first = build()
    second = build()
    assert first == second, f"{label} is not deterministic across calls"

    length, digest = EXPECTED[label]
    assert len(first) == length
    assert hashlib.sha256(first.encode("utf-8")).hexdigest() == digest


def test_payloads_are_distinct() -> None:
    """Four different payload kinds, not the same text under four names."""
    bodies = {label: build() for label, build in PAYLOADS.items()}
    assert len(set(bodies.values())) == len(bodies)


def test_egress_switches_are_both_forced() -> None:
    """The measurement must never be the thing that enables the beacon."""
    assert EGRESS_OFF == {"HEADROOM_BEACON": "off", "DO_NOT_TRACK": "1"}


def test_format_table_marks_a_missing_row_instead_of_dropping_it() -> None:
    """An unmeasured payload is reported, never silently absent or blank."""
    table = format_table(
        [
            Measurement("measured", 1000, 250),
            Measurement("unmeasured", 1000, None, "no answer within the timeout"),
        ],
        version="headroom, version 0.0.0",
    )
    assert "| measured | **0.250** |" in table
    assert "NOT MEASURED -- no answer within the timeout" in table


def test_format_table_calls_an_unchanged_payload_unchanged() -> None:
    """Ratio 1.000 reads as `unchanged`, which is what the spoke publishes."""
    table = format_table(
        [Measurement("prose", 500, 500)], version="headroom, version 0.0.0"
    )
    assert "| prose | 1.000 -- unchanged |" in table


def test_ratio_is_none_when_nothing_came_back() -> None:
    assert Measurement("x", 10, None).ratio is None
    assert Measurement("x", 10, 5).ratio == pytest.approx(0.5)
