"""The root JS workspace gate delegates the Pi extension to a real Bun gate."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = (ROOT / "justfile").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/unit-test.yaml").read_text(encoding="utf-8")


def test_pi_extension_is_excluded_from_inapplicable_vp_and_built_with_bun() -> None:
    assert "':!config/pi/extensions/**'" in JUSTFILE
    assert "':!tests/unit/jev_sonnet_fallback.test.ts'" in JUSTFILE
    assert (
        "just pi-jev-test" in JUSTFILE.split("check:\n", 1)[1].split("\n[group(", 1)[0]
    )
    fmt = JUSTFILE.split("fmt:\n", 1)[1].split("\n[group(", 1)[0]
    assert "':!config/pi/extensions/**'" in fmt
    assert "':!tests/unit/jev_sonnet_fallback.test.ts'" in fmt
    lint = JUSTFILE.split("lint:\n", 1)[1].split("\n[group(", 1)[0]
    assert "':!config/pi/extensions/**'" in lint
    assert "':!tests/unit/jev_sonnet_fallback.test.ts'" in lint
    assert "just pi-jev-test" in lint
    assert "bun build config/pi/extensions/jev-sonnet-fallback.ts" in JUSTFILE
    assert "bun test tests/unit/jev_sonnet_fallback.test.ts" in JUSTFILE
    assert WORKFLOW.count("bun test tests/unit/jev_sonnet_fallback.test.ts") == 2
