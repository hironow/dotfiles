"""Unit tests for scripts/check_effective_settings.py generation.

The fragment layers (`{env, settings}` wrappers) are not a settings.json
shape, so the checker composes the effective settings.json for every
claude-family profile x OS and validates each structurally with the
stdlib validator (ADR 0037/0041). These tests cover generation and the
validator against the repo's real fragments (no external tools).
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
    # status lines crashed with UnicodeEncodeError. _configure_output()
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


def test_validator_accepts_real_composed_settings(tmp_path: Path) -> None:
    # The stdlib validator (ADR 0041 — third-party claudelint retired) must
    # pass every settings.json this repo's real fragments compose.
    from check_effective_settings import _validate_settings, generate

    generated = generate(DOTFILES, tmp_path)
    for label, path in generated.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        assert _validate_settings(data) == [], f"{label} failed validation"


def test_validator_rejects_malformed_shapes() -> None:
    from check_effective_settings import _validate_settings

    assert _validate_settings([]) != [], "non-object top level must fail"
    assert _validate_settings({"env": {"A": 1}}) != [], "non-str env value must fail"
    assert _validate_settings({"permissions": {"deny": "WebFetch"}}) != [], (
        "permissions.deny as a bare str must fail"
    )
    assert _validate_settings({"hooks": {"PreToolUse": [{"hooks": []}]}}) != [], (
        "empty inner hooks list must fail"
    )
    assert (
        _validate_settings(
            {"hooks": {"PreToolUse": [{"hooks": [{"type": "command"}]}]}}
        )
        != []
    ), "command hook without a command string must fail"
    assert (
        _validate_settings(
            {
                "env": {"A": "1"},
                "permissions": {"deny": ["WebFetch"], "defaultMode": "plan"},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": "x"}],
                        }
                    ]
                },
                "unknownFutureKey": {"anything": True},
            }
        )
        == []
    ), "well-formed settings (incl. unknown future keys) must pass"
