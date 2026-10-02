"""Modifier+arrow must move by word in zsh, Ghostty and tmux.

zsh's default emacs keymap binds only the *bare* cursor keys
(`Src/Zle/zle_keymap.c: add_cursor_key`), so the xterm spellings for
modifier+arrow were unclaimed and zle echoed them back as `[1;3D` garbage.
`.zshrc` claims Option+arrow (iTerm2) and Ctrl+arrow (the pair Windows Terminal
does not take for pane focus); `tools/ghostty-config` pins Option+arrow to
ESC b / ESC f, zsh's built-in M-b / M-f, which also survive tmux.

The third artifact is tmux itself: `extended-keys always` is what lets
Ctrl+Enter reach Claude Code inside a pane (the default is `off`, and zsh never
asks for extended keys, so the key arrives as a plain CR). `xterm-keys` must
stay out -- it has defaulted to `on` since tmux 2.4, so adding it would only
mislead. The option needs tmux >= 3.2a; older versions print one warning and
still load the rest of the file, so that requirement is documented rather than
guarded.

tmux, zsh and Ghostty are all absent on native-Windows dev hosts, so these are
static checks on the tracked files plus `zsh -n`, which is skipped where zsh is
missing. Behaviour is confirmed by hand on macOS (`docs/plan/terminal-keys.md`).
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
TMUX_CONF = ROOT / "tools" / "tmux" / "tmux.conf"

# xterm modifier spellings: 3 = Alt/Option, 5 = Ctrl; D = left, C = right.
WORD_MOVEMENT = {
    "^[[1;3D": "backward-word",
    "^[[1;3C": "forward-word",
    "^[[1;5D": "backward-word",
    "^[[1;5C": "forward-word",
}
ARROW_BINDING = re.compile(r"^bindkey '(\^\[\[1;(\d)[DC])' (\S+)$", re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tmux_commands(path: Path) -> list[str]:
    """Command lines only: the comments in tmux.conf discuss `xterm-keys`."""
    return [
        line.strip()
        for line in _read(path).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_zshrc_binds_exactly_the_four_modifier_arrow_sequences() -> None:
    bindings = ARROW_BINDING.findall(_read(ZSHRC))
    sequences = [sequence for sequence, _modifier, _widget in bindings]
    assert len(sequences) == len(set(sequences)), f"duplicate binding: {sequences}"
    assert {sequence: widget for sequence, _m, widget in bindings} == WORD_MOVEMENT


def test_zshrc_does_not_bind_shift_arrow() -> None:
    # Shift+arrow is text selection in every other editor; 2 = Shift.
    assert all(
        modifier != "2"
        for _seq, modifier, _widget in ARROW_BINDING.findall(_read(ZSHRC))
    )


def test_ghostty_pins_option_arrows_to_meta_b_f() -> None:
    # Comments are skipped: the keybind lines are what Ghostty reads.
    lines = [
        line.strip()
        for line in _read(GHOSTTY_CONFIG).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert lines.count("keybind = opt+left=esc:b") == 1
    assert lines.count("keybind = opt+right=esc:f") == 1


def test_tmux_forces_extended_keys_for_clients_that_never_asked() -> None:
    lines = _tmux_commands(TMUX_CONF)
    # `always`, not `on`: zsh does not request extended keys, and `on` follows
    # the client's request.
    assert lines.count("set -s extended-keys always") == 1
    # The wiki's Modifier-Keys line; `-as` appends to the feature list.
    assert lines.count("set -as terminal-features 'xterm*:extkeys'") == 1


def test_tmux_does_not_add_xterm_keys_or_switch_the_format() -> None:
    lines = _tmux_commands(TMUX_CONF)
    # xterm-keys defaults to on since tmux 2.4; extended-keys-format defaults to
    # xterm, whose Ctrl+Enter spelling .zshrc already binds.
    assert not [line for line in lines if "xterm-keys" in line]
    assert not [line for line in lines if "extended-keys-format" in line]


def test_tmux_conf_documents_the_minimum_version() -> None:
    # The >= 3.2a requirement is policy, not a guard: keep it in the file.
    assert "3.2a" in _read(TMUX_CONF)


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
