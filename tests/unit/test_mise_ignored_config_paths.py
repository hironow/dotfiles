"""Startup ignores only Windows home configs before activating mise."""

from pathlib import Path

from _zsh_startup import run_startup


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
    result = run_startup(tmp_path, "")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "activate.log").read_text(encoding="utf-8").splitlines() == [
        ":".join(homes)
    ]


def test_zshrc_overwrites_the_value_and_keeps_projects_under_mnt_c(
    tmp_path: Path,
) -> None:
    homes = _homes(tmp_path)
    result = run_startup(tmp_path, 'source "$STARTUP_FILE"')
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "activate.log").read_text(encoding="utf-8").splitlines() == [
        ":".join(homes),
        ":".join(homes),
    ]
