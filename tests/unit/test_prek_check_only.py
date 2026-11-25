"""Configuration seam: no whole-project hooks (0085).

The repo-lint rules prek-confidentiality-guards and prek-check-only-hooks hold
the hook config itself.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_hygiene_is_a_leg_of_check_not_a_new_recipe() -> None:
    text = (ROOT / "justfile").read_text(encoding="utf-8")
    # `check` reaches the hygiene leg through check-except-go (ADR-0089)
    assert "@just check-except-go" in text.split("\ncheck:\n", 1)[1].split("\n\n", 1)[0]
    check = text.split("\ncheck-except-go:\n", 1)[1].split("\n\n", 1)[0]
    assert "@mise exec -- go run tools/text-hygiene/main.go" in check
    assert "--fix" not in "\n".join(
        line
        for line in check.splitlines()
        if not line.lstrip().startswith("#") and "echo" not in line
    )
