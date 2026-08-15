"""Unit tests for scripts/check_effective_settings.py generation.

claudelint only auto-detects `.claude/settings.json`, so the fragment layers
(`{env, settings}` wrappers) cannot be validated directly. The checker
composes the effective settings.json for every claude-family profile x OS and
writes them out for claudelint to validate (ADR 0037). These tests cover the
generation step against the repo's real fragments (no bunx invocation).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_effective_settings import generate

DOTFILES = Path(__file__).resolve().parents[2]
PROFILE_KEYS = {"claude", "work-a", "work-b", "work-c", "work-d"}
OS_NAMES = {"macos", "linux", "windows"}


def test_generates_all_profiles_times_os(tmp_path: Path) -> None:
    """One effective settings.json per claude-family profile x OS."""
    generated = generate(DOTFILES, tmp_path)

    labels = set(generated)
    assert labels == {f"{k}-{o}" for k in PROFILE_KEYS for o in OS_NAMES}
    for path in generated.values():
        assert path.name == "settings.json"
        assert path.parent.name == ".claude"
        assert json.loads(path.read_text(encoding="utf-8"))


def test_effective_settings_reflect_layering(tmp_path: Path) -> None:
    """Spot-check composed output: shared + OS overlay + profile all land."""
    generated = generate(DOTFILES, tmp_path)

    work_c_mac = json.loads(generated["work-c-macos"].read_text(encoding="utf-8"))
    assert work_c_mac["effortLevel"] == "xhigh"
    assert "Bash(npm:*)" in work_c_mac["permissions"]["deny"]
    assert work_c_mac["preferredNotifChannel"] == "ghostty"
    assert work_c_mac["skillOverrides"]["yeet"] == "name-only"
    assert work_c_mac["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "claude-opus-5"
    # env is the original git-managed fragment set only -- per-home tuning
    # values were never promoted into shared (user decision on PR #281)
    assert "MAX_THINKING_TOKENS" not in work_c_mac["env"]

    work_c_linux = json.loads(generated["work-c-linux"].read_text(encoding="utf-8"))
    assert "preferredNotifChannel" not in work_c_linux

    claude_mac = json.loads(generated["claude-macos"].read_text(encoding="utf-8"))
    assert claude_mac["effortLevel"] == "medium"
    assert claude_mac["permissions"]["defaultMode"] == "auto"


def test_repo_root_is_derived_from_script_location() -> None:
    """The checker must not assume the repo lives at ~/dotfiles (CI checkout)."""
    import check_effective_settings as ces

    assert ces.REPO_ROOT == DOTFILES
    assert (ces.REPO_ROOT / ".claude" / "settings.shared.json").is_file()


def test_output_survives_cp932_stdout() -> None:
    # Windows Git Bash gives Python a cp932 stdout; the checker's emoji
    # status lines crashed with UnicodeEncodeError, and decoding claudelint's
    # UTF-8 output as cp932 crashed the capture thread. _configure_output()
    # must make printing safe.
    import os
    import subprocess

    script = (
        "import sys; sys.path.insert(0, r'{scripts}');"
        "import check_effective_settings as ces; ces._configure_output();"
        "print('\u2705 ok')"
    ).format(scripts=Path(__file__).resolve().parents[2] / "scripts")
    env = dict(os.environ, PYTHONIOENCODING="cp932")
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, (
        "checker output must not crash on a cp932 stdout:\n" + proc.stderr
    )


def test_claudelint_capture_decodes_utf8() -> None:
    # The claudelint subprocess capture must pin encoding="utf-8": text=True
    # alone uses the locale codec (cp932 on Japanese Windows) and the reader
    # thread dies with UnicodeDecodeError on claudelint's UTF-8 output.
    source = (DOTFILES / "scripts" / "check_effective_settings.py").read_text(
        encoding="utf-8"
    )
    import re

    assert re.search(
        r"subprocess\.run\(\s*CLAUDELINT[^)]*encoding=\"utf-8\"", source
    ), "subprocess.run(CLAUDELINT, ...) must pass encoding='utf-8'."
