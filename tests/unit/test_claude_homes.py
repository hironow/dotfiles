"""What every per-home Claude script shares: which homes, and how to visit them.

claude_plugins and headroom_mcp (and doctor's settings checks) each carried
their own copy of the five home names; claude_homes holds them, in the order
the scripts report them, and only existing homes are visited.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import claude_homes  # noqa: E402


def test_the_homes_in_report_order() -> None:
    assert claude_homes.NAMES == (
        ".claude",
        ".claude-work-a",
        ".claude-work-b",
        ".claude-work-c",
        ".claude-work-d",
    )


def test_only_existing_homes_are_visited(tmp_path: Path) -> None:
    for name in (".claude-work-c", ".claude"):
        (tmp_path / name).mkdir()
    (tmp_path / ".claude-work-a").write_text("not a dir", encoding="utf-8")
    assert claude_homes.existing(tmp_path) == [
        tmp_path / ".claude",
        tmp_path / ".claude-work-c",
    ]


@pytest.mark.parametrize(
    ("deadline", "now", "timeout"),
    [
        (None, 0.0, claude_homes.CALL_TIMEOUT),  # installing: no overall budget
        (1000.0, 0.0, claude_homes.CALL_TIMEOUT),
        (100.0, 90.0, 10.0),  # the budget's rest, so doctor gets every line
        (100.0, 100.0, None),  # spent: skip, reported as unreadable
    ],
)
def test_each_call_fits_the_overall_budget(
    deadline: float | None, now: float, timeout: float | None
) -> None:
    assert claude_homes.call_timeout(deadline, now) == timeout


def test_the_check_budget_ends_before_doctor_stops_waiting() -> None:
    import ai_tools_check  # noqa: PLC0415

    assert claude_homes.CHECK_BUDGET < ai_tools_check.CHECKER_TIMEOUT


class Done:
    def __init__(self, code: int, out: str) -> None:
        self.returncode, self.stdout = code, out


@pytest.mark.parametrize(
    ("code", "out", "answer"), [(0, "", ""), (0, "x", "x"), (1, "x", None)]
)
def test_a_call_runs_in_its_home_and_answers_stdout_or_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: int,
    out: str,
    answer: str | None,
) -> None:
    seen: dict[str, object] = {}

    def run(argv: list[str], **kwargs: object) -> Done:
        seen.update(kwargs, argv=argv)
        return Done(code, out)

    monkeypatch.setattr(claude_homes.subprocess, "run", run)
    call = claude_homes.runner("claude", tmp_path, None, cwd=tmp_path, no_stdin=True)
    assert call(["plugin", "list"]) == answer
    assert seen["argv"] == ["claude", "plugin", "list"]
    env = seen["env"]
    assert isinstance(env, dict) and env["CLAUDE_CONFIG_DIR"] == str(tmp_path)
    assert (seen["cwd"], seen["stdin"]) == (tmp_path, subprocess.DEVNULL)


def test_a_spent_budget_skips_the_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(claude_homes.subprocess, "run", lambda *_a, **_k: Done(0, "x"))
    assert claude_homes.runner("claude", tmp_path, deadline=0.0)(["x"]) is None
