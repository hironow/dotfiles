"""Run the Windows paths of deploy, clean and dump instead of reading them.

ADR 0018/0022/0024/0031/0033: on native Windows, `just deploy` places only the
cross-platform subset (starship, git ignore, the mise config) and wires
PowerShell's $PROFILE with managed blocks; `just clean` removes exactly that.
ADR 0019/0030: `just dump` records scoop's apps, normalized, per host, and
never installs. scripts/deploy.sh, scripts/clean.sh and the justfile's dump
recipe dispatch on `uname -s`, so a fake `uname` on PATH takes their Windows
branch on Linux and macOS. Each test runs the real script in a temporary HOME
with fake tools, and checks what it did (ADR-0093). A fake `git` that fails
keeps a break that falls through to the Unix path off the network.

Native Windows skips: the fake `uname` and the POSIX PATH do not apply there.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="runs the Windows branch on POSIX through a fake uname",
)

# The three patterns of the scripts' Windows branch (MINGW*|MSYS*|CYGWIN*).
WINDOWS_UNAMES = ["MINGW64_NT-10.0-26100", "MSYS_NT-10.0-26100", "CYGWIN_NT-10.0-26100"]

BEGIN = {
    "mise": "# >>> dotfiles managed block: mise activate >>>",
    "starship": "# >>> dotfiles managed block: starship init >>>",
    "corepack": "# >>> dotfiles managed block: mise node corepack >>>",
    "jev": "# >>> dotfiles managed block: Jev launchers >>>",
}
END = "# <<< end dotfiles managed block <<<"
GIT_BLOCK = "# >>> dotfiles managed block: git aliases include >>>"
ALIASES_INCLUDE = "path = ~/dotfiles/config/git/aliases.gitconfig"
OPERATOR_LINE = "Set-Alias ll Get-ChildItem"
GIT_OVERRIDE = "[commit]\n\tgpgsign = false\n"

# What deploy copies, from where (relative to ~/dotfiles).
SUBSET = {
    ".config/starship.toml": "starship.toml",
    ".config/git/ignore": "dump/gitignore-global",
    ".config/mise/config.toml": "config/mise/config.toml",
}
UNIX_ONLY = (
    ".zshrc",
    ".zprofile",
    ".tmux.conf",
    ".config/sheldon",
    ".config/ghostty",
    ".local/share/fzf-tab",
)


def _bash() -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("needs bash")
    return bash


def _stub(bin_dir: Path, name: str, body: str) -> None:
    stub = bin_dir / name
    stub.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
    stub.chmod(0o755)


def _fake_bin(tmp_path: Path, uname: str, log: Path) -> Path:
    """uname, a git that logs and fails, a mise that does nothing, and on
    macOS a GNU-style `sed -i`. The fakes come first on PATH, so a real git or
    mise in /usr/bin never runs and nothing reaches the network."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "uname", f'printf "%s\\n" "{uname}"\n')
    _stub(bin_dir, "git", f'echo "git $*" >> "{log}"\nexit 1\n')
    _stub(bin_dir, "mise", "exit 0\n")
    if sys.platform == "darwin":
        # Git Bash ships GNU sed; macOS's BSD sed takes `-i ''`.
        _stub(
            bin_dir,
            "sed",
            'if [ "$1" = "-i" ]; then shift; exec /usr/bin/sed -i "" "$@"; fi\n'
            'exec /usr/bin/sed "$@"\n',
        )
    return bin_dir


class Host:
    """A temporary HOME holding copies of what the Windows branch reads."""

    def __init__(self, tmp_path: Path, uname: str) -> None:
        self.home = tmp_path / "home"
        self.log = tmp_path / "calls"
        self.log.touch()
        dotfiles = self.home / "dotfiles"
        for rel in (*SUBSET.values(), "config/git/aliases.gitconfig"):
            (dotfiles / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, dotfiles / rel)
        self.profile = (
            self.home / "Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
        )
        self.gitconfig = self.home / ".gitconfig"
        self.bin = _fake_bin(tmp_path, uname, self.log)
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.home),
            "DOTFILES_PS_PROFILE": str(self.profile),
        }

    def run(self, script: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [_bash(), str(ROOT / "scripts" / script)],
            cwd=self.home,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def seed(self, rel: str, text: str) -> Path:
        path = self.home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def calls(self) -> str:
        return self.log.read_text(encoding="utf-8")


def _ok(done: subprocess.CompletedProcess[str]) -> None:
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]


def _mise_block() -> str:
    """The mise block, as the library prints it."""
    return subprocess.run(
        [_bash(), "-c", f'. "{ROOT}/scripts/ps_profile_lib.sh"; ps_profile_mise_block'],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout


def _block(text: str, begin: str) -> str:
    start = text.index(begin)
    return text[start : text.index(END, start) + len(END)]


@pytest.fixture(params=WINDOWS_UNAMES)
def windows(request: pytest.FixtureRequest, tmp_path: Path) -> Host:
    return Host(tmp_path, request.param)


@pytest.fixture
def mingw(tmp_path: Path) -> Host:
    return Host(tmp_path, WINDOWS_UNAMES[0])


# ---------- deploy -----------------------------------------------------


def test_windows_deploy_places_only_the_cross_platform_subset(windows: Host) -> None:
    _ok(windows.run("deploy.sh"))
    for target, source in SUBSET.items():
        assert (windows.home / target).read_bytes() == (
            windows.home / "dotfiles" / source
        ).read_bytes(), target
    # The Unix path never ran: the branch ends before it.
    for unix_only in UNIX_ONLY:
        assert not (windows.home / unix_only).exists(), unix_only
    assert windows.calls() == ""


def test_windows_deploy_takes_the_shared_gitignore(mingw: Host) -> None:
    # ADR 0030: gitignore-global is shared, never a host's copy.
    mingw.seed("dotfiles/dump/testhost/gitignore-global", "host-only\n")
    _ok(mingw.run("deploy.sh", DOTFILES_HOST="testhost"))
    assert (mingw.home / ".config/git/ignore").read_bytes() == (
        ROOT / "dump/gitignore-global"
    ).read_bytes()


def test_windows_deploy_writes_the_profile_blocks(mingw: Host) -> None:
    mingw.seed(str(mingw.profile.relative_to(mingw.home)), OPERATOR_LINE + "\n")
    _ok(mingw.run("deploy.sh"))
    text = mingw.profile.read_text(encoding="utf-8")
    assert text.count(OPERATOR_LINE) == 1
    for begin in BEGIN.values():
        assert text.count(begin) == 1, begin
    # mise first: starship is mise-managed, so its guard needs mise on PATH.
    assert text.index(BEGIN["mise"]) < text.index(BEGIN["starship"])
    assert _mise_block().strip() in text
    starship = _block(text, BEGIN["starship"])
    assert "if (Get-Command starship -ErrorAction SilentlyContinue) {" in starship
    assert "Invoke-Expression (&starship init powershell)" in starship
    assert '$env:MISE_NODE_COREPACK = "0"' in _block(text, BEGIN["corepack"])


def test_a_second_windows_deploy_adds_no_block(mingw: Host) -> None:
    mingw.seed(str(mingw.profile.relative_to(mingw.home)), OPERATOR_LINE + "\n")
    _ok(mingw.run("deploy.sh"))
    _ok(mingw.run("deploy.sh"))
    text = mingw.profile.read_text(encoding="utf-8")
    assert text.count(OPERATOR_LINE) == 1
    for begin in BEGIN.values():
        assert text.count(begin) == 1, begin
    assert text.count(END) == len(BEGIN)


def test_the_corepack_block_reaches_a_profile_with_the_older_blocks(
    mingw: Host,
) -> None:
    # A host deployed before the corepack block carries the other two; deploy
    # skips a block whose marker is present, so corepack needs its own marker.
    starship = (
        f"\n{BEGIN['starship']}\n"
        "if (Get-Command starship -ErrorAction SilentlyContinue) {\n"
        "    Invoke-Expression (&starship init powershell)\n"
        f"}}\n{END}\n"
    )
    mingw.seed(
        str(mingw.profile.relative_to(mingw.home)),
        OPERATOR_LINE + "\n\n" + _mise_block() + starship,
    )
    _ok(mingw.run("deploy.sh"))
    text = mingw.profile.read_text(encoding="utf-8")
    for begin in BEGIN.values():
        assert text.count(begin) == 1, begin
    assert '$env:MISE_NODE_COREPACK = "0"' in _block(text, BEGIN["corepack"])


def test_windows_deploy_installs_the_global_mise_tools(mingw: Host) -> None:
    # ADR 0033 with ADR 0031's corepack guard: node must not EPERM.
    _stub(
        mingw.bin,
        "mise",
        f'echo "mise $* MISE_NODE_COREPACK=${{MISE_NODE_COREPACK-unset}}" >> "{mingw.log}"\n',
    )
    _ok(mingw.run("deploy.sh"))
    assert "mise -C / install MISE_NODE_COREPACK=0\n" in mingw.calls()


def test_windows_deploy_wires_only_the_git_aliases(mingw: Host) -> None:
    # ADR 0033/0021: never re-include shared.gitconfig over a local override.
    mingw.seed(".gitconfig", GIT_OVERRIDE)
    _ok(mingw.run("deploy.sh"))
    _ok(mingw.run("deploy.sh"))
    text = mingw.gitconfig.read_text(encoding="utf-8")
    assert text.startswith(GIT_OVERRIDE)
    assert text.count(GIT_BLOCK) == 1
    assert text.count(ALIASES_INCLUDE) == 1
    assert "shared.gitconfig" not in text


# ---------- clean ------------------------------------------------------


def test_windows_clean_undoes_deploy_and_nothing_else(windows: Host) -> None:
    windows.seed(str(windows.profile.relative_to(windows.home)), OPERATOR_LINE + "\n")
    windows.seed(".gitconfig", GIT_OVERRIDE)
    users = {
        rel: windows.seed(rel, f"the user's {rel}\n")
        for rel in (
            ".zshrc",
            ".tmux.conf",
            ".config/ghostty/config",
            ".config/sheldon/plugins.toml",
        )
    }
    _ok(windows.run("deploy.sh"))
    _ok(windows.run("clean.sh"))
    profile = windows.profile.read_text(encoding="utf-8")
    assert "dotfiles managed block" not in profile
    assert OPERATOR_LINE in profile
    gitconfig = windows.gitconfig.read_text(encoding="utf-8")
    assert "dotfiles managed block" not in gitconfig
    assert gitconfig.startswith(GIT_OVERRIDE)
    for target in SUBSET:
        assert not (windows.home / target).exists(), target
    # The Unix rm block never ran.
    for rel, path in users.items():
        assert path.read_text(encoding="utf-8") == f"the user's {rel}\n", rel


# ---------- dump -------------------------------------------------------

SCOOP_EXPORT = {
    "buckets": [
        {
            "Name": "main",
            "Source": "https://github.com/ScoopInstaller/Main",
            "Updated": "2026-11-26T01:02:03",
            "Manifests": 1400,
        },
        {
            "Name": "extras",
            "Source": "https://github.com/ScoopInstaller/Extras",
            "Updated": "2026-11-26T01:02:04",
            "Manifests": 2100,
        },
    ],
    "apps": [
        {
            "Name": "jq",
            "Version": "1.8.2",
            "Source": "main",
            "Updated": "2026-11-20T00:00:00",
            "Info": "",
        },
        {
            "Name": "git",
            "Version": "2.53.0",
            "Source": "main",
            "Updated": "2026-11-21T00:00:00",
            "Info": "",
        },
    ],
}
SCOOP_RECORD = {
    "buckets": [
        {"Name": "extras", "Source": "https://github.com/ScoopInstaller/Extras"},
        {"Name": "main", "Source": "https://github.com/ScoopInstaller/Main"},
    ],
    "apps": [
        {"Name": "git", "Version": "2.53.0", "Source": "main"},
        {"Name": "jq", "Version": "1.8.2", "Source": "main"},
    ],
}


class DumpRepo:
    """A copy of the justfile and dump_host.sh, run with `just dump`."""

    def __init__(self, tmp_path: Path, uname: str) -> None:
        self.just = shutil.which("just")
        jq = shutil.which("jq")
        if self.just is None or jq is None:
            pytest.skip("needs just and jq")
        self.repo = tmp_path / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy(ROOT / "justfile", self.repo / "justfile")
        shutil.copy(ROOT / "scripts/dump_host.sh", self.repo / "scripts/dump_host.sh")
        self.home = tmp_path / "home"
        (self.home / ".config/git").mkdir(parents=True)
        (self.home / ".config/git/ignore").write_text("*.swp\n", encoding="utf-8")
        self.log = tmp_path / "calls"
        self.log.touch()
        self.bin = _fake_bin(tmp_path, uname, self.log)
        (self.bin / "jq").symlink_to(jq)
        export = json.dumps(SCOOP_EXPORT)
        _stub(
            self.bin,
            "scoop",
            f'echo "scoop $*" >> "{self.log}"\n'
            f"if [ \"$1\" = export ]; then printf '%s\\n' '{export}'; exit 0; fi\n"
            "exit 1\n",
        )
        _stub(
            self.bin,
            "gcloud",
            f'echo "gcloud $*" >> "{self.log}"\nprintf "beta\\nalpha\\n"\n',
        )

    def with_brew(self) -> None:
        _stub(
            self.bin,
            "brew",
            f'echo "brew $*" >> "{self.log}"\n'
            'if [ "$1 $2" = "bundle dump" ]; then echo \'brew "jq"\' > Brewfile; fi\n',
        )

    def dump(self) -> subprocess.CompletedProcess[str]:
        assert self.just is not None
        return subprocess.run(
            [self.just, "dump"],
            cwd=self.repo,
            env={
                "PATH": f"{self.bin}:/usr/bin:/bin",
                "HOME": str(self.home),
                "DOTFILES_HOST": "testhost",
            },
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("uname", WINDOWS_UNAMES)
def test_windows_dump_records_the_scoop_apps(tmp_path: Path, uname: str) -> None:
    repo = DumpRepo(tmp_path, uname)
    repo.with_brew()
    _ok(repo.dump())
    record = repo.repo / "dump/testhost/scoop.json"
    first = record.read_bytes()
    assert json.loads(first) == SCOOP_RECORD
    # Updated and Manifests change on every export; the record leaves them out.
    assert b"Updated" not in first
    assert b"Manifests" not in first
    _ok(repo.dump())
    assert record.read_bytes() == first
    # Record-only (ADR 0019), and the Mac/Linux tail never runs.
    assert repo.calls() == ["scoop export", "scoop export"]


def test_the_unix_dump_writes_host_manifests_and_a_shared_gitignore(
    tmp_path: Path,
) -> None:
    repo = DumpRepo(tmp_path, "Linux")
    repo.with_brew()
    _ok(repo.dump())
    host = repo.repo / "dump/testhost"
    assert (host / "Brewfile").read_text(encoding="utf-8") == 'brew "jq"\n'
    assert (host / "gcloud").read_text(encoding="utf-8") == "alpha\nbeta\n"
    # ADR 0030: gitignore-global is shared config, not a host's state.
    assert (repo.repo / "dump/gitignore-global").read_text(
        encoding="utf-8"
    ) == "*.swp\n"
    assert not (host / "gitignore-global").exists()


def test_a_brewless_host_still_dumps(tmp_path: Path) -> None:
    # WSL and mise-managed hosts have no Homebrew: skip the Brewfile, go on.
    repo = DumpRepo(tmp_path, "Linux")
    done = repo.dump()
    _ok(done)
    assert "skipping Brewfile dump" in done.stderr
    host = repo.repo / "dump/testhost"
    assert not (host / "Brewfile").exists()
    assert (host / "gcloud").read_text(encoding="utf-8") == "alpha\nbeta\n"
    assert (repo.repo / "dump/gitignore-global").read_text(
        encoding="utf-8"
    ) == "*.swp\n"
