"""Startup ignores only Windows home configs before activating mise."""

from pathlib import Path

from _zsh_startup import run_zsh

ACTIVATE_STARTUP = r"""
export _WIN_HOME_ROOT="${HOME:h}/mount/Users"
export MISE_IGNORED_CONFIG_PATHS=/mnt/c
mise() {
    [[ "$#" == 2 && "$1" == activate && "$2" == zsh ]] || exit 94
    /bin/sh -c 'printf "%s\n" "$MISE_IGNORED_CONFIG_PATHS"' >> "${HOME:h}/activate.log"
}
source "$1"
"""


def _homes(tmp_path: Path) -> list[str]:
    root = tmp_path / "mount/Users"
    homes = [root / name / ".config/mise" for name in ("Alice", "Bob Smith")]
    for home in homes:
        home.mkdir(parents=True)
    (root / "other/.config").mkdir(parents=True)
    (root / "file/.config").mkdir(parents=True)
    (root / "file/.config/mise").write_text("not a directory", encoding="utf-8")
    (tmp_path / "mount/project").mkdir()
    return [str(home) for home in homes]


def test_zshrc_ignores_the_windows_homes_mise_config_before_activate(
    tmp_path: Path,
) -> None:
    homes = _homes(tmp_path)
    run_zsh(tmp_path, ACTIVATE_STARTUP)
    assert (tmp_path / "activate.log").read_text(encoding="utf-8").splitlines() == [
        ":".join(homes)
    ]


def test_zshrc_overwrites_the_value_and_keeps_projects_under_mnt_c(
    tmp_path: Path,
) -> None:
    homes = _homes(tmp_path)
    run_zsh(tmp_path, ACTIVATE_STARTUP + '\nsource "$1"')
    assert (tmp_path / "activate.log").read_text(encoding="utf-8").splitlines() == [
        ":".join(homes),
        ":".join(homes),
    ]
