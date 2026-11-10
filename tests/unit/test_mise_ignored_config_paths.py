"""WSL's mise must not read the Windows home's mise config under /mnt/c.

A WSL shell started from Windows begins under `/mnt/c/Users/<user>/...`.
mise walks every ancestor directory for configs, including
`<dir>/.config/mise/config.toml`, so it finds the Windows-global config that
`just deploy` writes there and treats it as a directory-local one: it warns
that the global-only `github.credential_command` "is ignored for security
reasons", and resolves the WSL toolchain from the Windows copy.

`.zshrc` sets MISE_IGNORED_CONFIG_PATHS to the Windows homes' mise configs
before `mise activate`. Measured on mise 2026.11.4 (2026-11-10):

- The variable matches by path prefix; a glob in it does not work, and
  several paths are joined with ":". So the shell's glob lists the homes.
- Only the Windows homes are ignored, not all of /mnt/c: a project under
  /mnt/c keeps its own mise.toml in WSL.
- `[settings] ignored_config_paths` in config/mise/config.toml has no effect:
  the config is found before file settings load. If a later mise honors it
  during discovery, move the entry there; it would then cover bash and
  non-interactive shells too, which this .zshrc line does not.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ZSHRC = ROOT / ".zshrc"
CONFIG = ROOT / "config" / "mise" / "config.toml"

GLOB = re.compile(
    r"^\s*_win_mise=\(/mnt/c/Users/\*/\.config/mise\(N/\)\)\s*$", re.MULTILINE
)
EXPORT = re.compile(
    r"^\s*\(\( \$\{#_win_mise\} \)\) && "
    r'export MISE_IGNORED_CONFIG_PATHS="\$\{\(j\.:\.\)_win_mise\}"\s*$',
    re.MULTILINE,
)
ACTIVATE = re.compile(r'^\s*eval "\$\(mise activate zsh\)"\s*$', re.MULTILINE)


def test_zshrc_ignores_the_windows_homes_mise_config_before_activate():
    text = ZSHRC.read_text(encoding="utf-8")
    glob, export, activate = (
        GLOB.search(text),
        EXPORT.search(text),
        ACTIVATE.search(text),
    )
    assert glob and export, (
        ".zshrc must collect /mnt/c/Users/*/.config/mise and export them as "
        "MISE_IGNORED_CONFIG_PATHS"
    )
    assert activate, ".zshrc no longer activates mise? Update this test."
    assert glob.start() < export.start() < activate.start()


def test_zshrc_overwrites_the_value_and_keeps_projects_under_mnt_c():
    text = ZSHRC.read_text(encoding="utf-8")
    exports = re.findall(r"export MISE_IGNORED_CONFIG_PATHS=.*", text)
    # overwrite, so a nested shell or `relogin` does not grow it, and an old
    # value cannot keep ignoring all of /mnt/c
    assert len(exports) == 1 and "$MISE_IGNORED_CONFIG_PATHS" not in exports[0]
    assert not re.search(
        r'MISE_IGNORED_CONFIG_PATHS="?/mnt/c"?\s*$', text, re.MULTILINE
    )


def test_the_config_has_no_ignored_config_paths_that_does_nothing():
    settings = tomllib.loads(CONFIG.read_text(encoding="utf-8")).get("settings", {})
    assert "ignored_config_paths" not in settings
