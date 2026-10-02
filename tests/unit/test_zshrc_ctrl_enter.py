"""Ctrl+Enter must reach Claude Code as CSI-u, and must not litter the prompt.

Ghostty's default for ctrl+enter is a bare CR -- byte-identical to plain Enter
-- so Claude Code cannot tell the two apart and cannot offer "newline, don't
submit". `tools/ghostty-config` therefore binds ctrl+enter to the CSI-u
encoding (`ESC [ 13 ; 5 u`), which carries the modifier.

That shifts the problem into zsh: an escape sequence no keymap claims is echoed
back by zle as `[13;5u` garbage at the prompt. `.zshrc` claims it -- and the
xterm modifyOtherKeys spelling (`ESC [ 27 ; 5 ; 13 ~`) other terminals send for
the same key -- with a widget that inserts a literal newline, so Ctrl+Enter is
multi-line editing in the shell too.

Static checks on the tracked files plus `zsh -n`, which is skipped where zsh is
absent (native Windows hosts run this suite too), so this lives in tests/unit/.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ZSHRC = ROOT / ".zshrc"
GHOSTTY_CONFIG = ROOT / "tools" / "ghostty-config"

WIDGET = "_ctrl_enter_newline"
# As spelled in .zshrc: zsh's `^[` caret notation for ESC, not a real ESC byte.
CSI_U = "'^[[13;5u'"
MODIFY_OTHER_KEYS = "'^[[27;5;13~'"


def _zshrc() -> str:
    return ZSHRC.read_text(encoding="utf-8")


def test_ghostty_sends_csi_u_for_ctrl_enter() -> None:
    config = GHOSTTY_CONFIG.read_text(encoding="utf-8")
    assert r"keybind = ctrl+enter=text:\x1b[13;5u" in config


def test_zshrc_registers_the_widget() -> None:
    text = _zshrc()
    # Same `name() {` style as the helpers at the top of the file.
    assert re.search(rf"^{WIDGET}\(\) \{{$", text, re.MULTILINE), (
        f".zshrc must define {WIDGET}()"
    )
    assert f"zle -N {WIDGET}" in text, f"{WIDGET} must be registered as a widget"


def test_the_widget_inserts_a_newline_without_executing() -> None:
    body = re.search(
        rf"^{WIDGET}\(\) \{{\n(.*?)^\}}$", _zshrc(), re.MULTILINE | re.DOTALL
    )
    assert body, f".zshrc must define {WIDGET}()"
    # Appending to LBUFFER edits the line being read; `zle accept-line` is what
    # would execute it, so this is strictly multi-line editing. A widget that
    # only reports (`zle -M`) would leave Ctrl+Enter useless in the shell.
    assert r"LBUFFER+=$'\n'" in body.group(1)


def test_both_encodings_are_bound_to_the_widget() -> None:
    text = _zshrc()
    bindings = re.findall(rf"^bindkey (.*) {WIDGET}$", text, re.MULTILINE)
    assert sorted(bindings) == sorted([CSI_U, MODIFY_OTHER_KEYS]), (
        "both the CSI-u and the modifyOtherKeys spelling must reach the widget"
    )
    # Bare `bindkey`, i.e. the `main` keymap: .zshrc never sets `bindkey -e`/`-v`
    # nor binds with `-M`, so `main` is whatever zsh linked it to from
    # EDITOR/VISUAL at startup. Following `main` binds the keymap actually in
    # use; naming one explicitly would miss on hosts that picked the other.
    assert "-M" not in " ".join(bindings)


def test_the_widget_exists_before_it_is_bound() -> None:
    text = _zshrc()
    # bindkey to an unregistered widget is a startup error, not a no-op.
    assert text.index(f"zle -N {WIDGET}") < text.index(f"bindkey {CSI_U}")


@pytest.mark.skipif(shutil.which("zsh") is None, reason="needs zsh")
def test_zshrc_parses() -> None:
    result = subprocess.run(
        ["zsh", "-n", str(ZSHRC)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr
