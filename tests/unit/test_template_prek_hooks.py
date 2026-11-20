"""The repo template's git hooks are prek hooks that only check (ADR 0084).

A hook never writes a file and never runs the whole gate: the template's
`.pre-commit-config.yaml` holds prek's builtin checks (two of them in their
non-writing `--check` mode) and ruff in check mode on the staged Python files.
prek stashes unstaged changes while hooks run, so they see what will be
committed. `just check` (the whole gate, which never writes) runs in CI.

The static tests read files only and run everywhere. The runtime tests run prek
itself in a temp git repo: where prek is absent they skip, except under
DOTFILES_REQUIRE_PREK=1 (the Linux unit-test job), where they fail; a prek older
than 0.5.4 (the first with `--check`) always fails them. They use POSIX shell
shims, so they do not run on native Windows.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates/agent-baseline"
CONFIG = TEMPLATE / ".pre-commit-config.yaml"
JUSTFILE = TEMPLATE / "justfile"
CI = TEMPLATE / ".github/workflows/quality-gate.yaml"
PREKIGNORE = ROOT / ".prekignore"
HOOK_IDS = [
    "trailing-whitespace",
    "end-of-file-fixer",
    "check-yaml",
    "check-toml",
    "check-json",
    "check-added-large-files",
    "check-merge-conflict",
    "detect-private-key",
    "ruff-format-check",
    "ruff-check",
]
RUFF_FORMAT = (
    "entry: uv run --locked --only-group lint ruff format --check --force-exclude --"
)
RUFF_CHECK = "entry: uv run --locked --only-group lint ruff check --no-fix --no-fix-only --force-exclude --"
MIN_PREK = (0, 5, 4)


def _config() -> str:
    return CONFIG.read_text(encoding="utf-8")


def _hook_block(hook_id: str) -> str:
    """The lines of one hook in the template's config, up to the next hook."""
    text = _config()
    start = text.index(f"- id: {hook_id}\n")
    rest = text[start + 1 :]
    nxt = re.search(r"\n\s*- (?:id|repo):", rest)
    return text[start : start + 1 + (nxt.start() if nxt else len(rest))]


def _recipe(name: str) -> tuple[list[str], list[str]]:
    """The dependencies and the command lines of the template recipe `name`."""
    lines = JUSTFILE.read_text(encoding="utf-8").splitlines()
    for start, line in enumerate(lines):
        header = re.match(rf"^{re.escape(name)}\s*:(?!=)(?P<deps>.*)$", line)
        if header:
            break
    else:
        raise AssertionError(f"no recipe {name} in {JUSTFILE}")
    deps = header.group("deps").split("#", 1)[0].split()
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        if line.strip() and not line.strip().startswith("#"):
            body.append(line.strip())
    return deps, body


# --- static -----------------------------------------------------------------


def test_the_template_hooks_are_prek_not_githooks() -> None:
    assert CONFIG.is_file()
    assert not (TEMPLATE / ".githooks").exists()
    with pytest.raises(AssertionError):
        _recipe("pre-commit")


def test_the_config_holds_exactly_the_check_only_hooks() -> None:
    text = _config()
    assert re.findall(r"(?m)^\s+- id: (\S+)$", text) == HOOK_IDS
    assert re.search(r'(?m)^minimum_prek_version: "0\.5\.4"$', text)
    assert re.search(r"(?m)^default_install_hook_types: \[pre-commit\]$", text)
    assert re.search(r"(?m)^default_stages: \[pre-commit\]$", text)
    settings = re.sub(r"(?m)^\s*#.*$", "", text)
    assert "pre-push" not in settings
    for hook in ("trailing-whitespace", "end-of-file-fixer"):
        assert "args: [--check]" in _hook_block(hook), hook
    for hook in HOOK_IDS:
        # A hook's own manifest can name pre-push too (prek's builtins do).
        assert "stages: [pre-commit]" in _hook_block(hook), hook
    assert "just " not in settings


def test_ruff_runs_in_check_mode_on_the_staged_files() -> None:
    fmt, chk = _hook_block("ruff-format-check"), _hook_block("ruff-check")
    assert RUFF_FORMAT in fmt
    assert RUFF_CHECK in chk
    for block in (fmt, chk):
        assert "require_serial: true" in block
        assert "types_or: [python, pyi]" in block
        assert "language: system" in block
        assert "pass_filenames: false" not in block


def test_the_strict_gate_never_writes() -> None:
    deps, _ = _recipe("check")
    assert "fmt" not in deps
    assert {"lint", "semgrep", "test"} <= set(deps)
    _, lint = _recipe("lint")
    assert (
        "uv run --locked --only-group lint ruff check --no-fix --no-fix-only ." in lint
    )
    assert re.search(r"(?m)^\s+run: just check\s*$", CI.read_text(encoding="utf-8"))


def test_install_hooks_runs_prek_install() -> None:
    text = JUSTFILE.read_text(encoding="utf-8")
    assert "install-hooks:\n    #!/usr/bin/env bash\n" in text
    _, body = _recipe("install-hooks")
    assert body[-1] == "prek install"
    assert "git config --show-scope --get-all core.hooksPath" in "\n".join(body)


def test_dotfiles_own_prek_does_not_run_the_template_config() -> None:
    lines = PREKIGNORE.read_text(encoding="utf-8").splitlines()
    assert "templates/agent-baseline/" in lines


# --- runtime ----------------------------------------------------------------


def _prek() -> str:
    if sys.platform == "win32":
        pytest.skip("the runtime tests use POSIX shell shims")
    found = shutil.which("prek")
    if found is None:
        if os.environ.get("DOTFILES_REQUIRE_PREK") == "1":
            pytest.fail(
                "prek is required here (DOTFILES_REQUIRE_PREK=1) but not on PATH"
            )
        pytest.skip("prek is not installed")
    out = subprocess.run(
        [found, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    assert match, out
    version = tuple(int(x) for x in match.groups())
    assert version >= MIN_PREK, f"prek {out.strip()} is older than 0.5.4 (no --check)"
    return found


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


class Repo:
    """A temp git repo holding the template's prek config, with a `uv` shim on
    PATH that runs dotfiles' pinned ruff with the arguments after `ruff`."""

    def __init__(self, tmp: Path, config: str | None = None) -> None:
        self.prek = _prek()
        uv = shutil.which("uv")
        if uv is None:
            pytest.skip("uv is not installed")
        self.root = tmp / "repo"
        self.root.mkdir()
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "t@example.invalid")
        _git(self.root, "config", "user.name", "t")
        (self.root / ".pre-commit-config.yaml").write_text(
            config if config is not None else _config(), encoding="utf-8"
        )
        self.bin = tmp / "bin"
        self.bin.mkdir()
        shim = self.bin / "uv"
        shim.write_text(
            "#!/bin/sh\n"
            'while [ "$#" -gt 0 ] && [ "$1" != ruff ]; do shift; done\n'
            "shift\n"
            f'exec "{uv}" run --project "{ROOT}" --frozen --only-group lint ruff "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}

    def write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def stage(self, *names: str) -> None:
        _git(self.root, "add", "-f", "--", *names)

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.prek, "run", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.env,
            timeout=300,
            check=False,
        )


def _fails(done: subprocess.CompletedProcess[str], hook: str) -> None:
    assert done.returncode != 0, done.stdout + done.stderr
    assert hook in done.stdout + done.stderr


@pytest.mark.parametrize(
    ("hook", "bad", "good"),
    [
        ("trailing-whitespace", b"x  \n", b"x\n"),
        ("end-of-file-fixer", b"x", b"x\n"),
    ],
)
def test_the_hygiene_hooks_report_and_never_write(
    tmp_path: Path, hook: str, bad: bytes, good: bytes
) -> None:
    repo = Repo(tmp_path)
    path = repo.write("a.txt", bad)
    repo.stage("a.txt")
    _fails(repo.run(hook), hook)
    assert path.read_bytes() == bad
    repo.write("a.txt", good)
    repo.stage("a.txt")
    assert repo.run(hook).returncode == 0


def test_ruff_format_reports_and_never_writes(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    path = repo.write("bad.py", b"x=1\n")
    repo.stage("bad.py")
    _fails(repo.run("ruff-format-check"), "ruff-format-check")
    assert path.read_bytes() == b"x=1\n"
    repo.write("bad.py", b"x = 1\n")
    repo.stage("bad.py")
    assert repo.run("ruff-format-check").returncode == 0


def test_ruff_check_never_fixes_even_when_the_config_says_fix(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.write(
        "pyproject.toml",
        b'[tool.ruff]\nfix = true\n[tool.ruff.lint]\nselect = ["F401"]\n',
    )
    path = repo.write("m.py", b"import os\n")
    repo.stage("pyproject.toml", "m.py")
    _fails(repo.run("ruff-check"), "ruff-check")
    assert path.read_bytes() == b"import os\n"


def test_partial_staging_checks_what_will_be_committed(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.write("pyproject.toml", b'[tool.ruff.lint]\nselect = ["F401"]\n')
    repo.write("m.py", b"import os\n")
    repo.stage("pyproject.toml", "m.py")
    path = repo.write("m.py", b"x = 1\n")  # the fix, not staged
    _fails(repo.run("ruff-check"), "ruff-check")
    assert path.read_bytes() == b"x = 1\n"  # the unstaged edit is still there
    repo.stage("m.py")
    repo.write("m.py", b"import os\n")  # staged good, unstaged bad
    assert repo.run("ruff-check").returncode == 0
    assert path.read_bytes() == b"import os\n"


def test_a_file_name_starting_with_a_dash_is_checked(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.write("-m.py", b"x=1\n")
    repo.stage("-m.py")
    _fails(repo.run("ruff-format-check"), "ruff-format-check")


def test_no_hook_runs_at_pre_push(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.write("a.txt", b"x  \n")
    repo.stage("a.txt")
    done = repo.run("--hook-stage", "pre-push", "--all-files")
    assert done.returncode == 0, done.stdout + done.stderr
    for hook in HOOK_IDS:
        assert hook not in done.stdout


def test_prekignore_stops_discovery_but_not_root_checks(tmp_path: Path) -> None:
    root_config = "repos:\n  - repo: builtin\n    hooks:\n      - id: check-yaml\n"
    repo = Repo(tmp_path, config=root_config)
    repo.write(".prekignore", PREKIGNORE.read_bytes())
    repo.write("templates/agent-baseline/.pre-commit-config.yaml", CONFIG.read_bytes())
    repo.write("templates/agent-baseline/broken.yaml", b"a: [\n")
    repo.stage(".prekignore", "templates/agent-baseline/.pre-commit-config.yaml")
    listed = subprocess.run(
        [repo.prek, "list", "--refresh"],
        cwd=repo.root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=repo.env,
        check=False,
    )
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "ruff-format-check" not in listed.stdout
    repo.stage("templates/agent-baseline/broken.yaml")
    _fails(repo.run("check-yaml"), "check-yaml")


# --- install-hooks ------------------------------------------------------------


def _install_hooks(tmp: Path) -> tuple[Path, subprocess.CompletedProcess[str]]:
    """Run the template's install-hooks recipe in a temp repo with a fake prek."""
    if sys.platform == "win32":
        pytest.skip("the runtime tests use POSIX shell shims")
    just = shutil.which("just")
    if just is None:
        pytest.skip("just is not installed")
    repo = tmp / "repo"
    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "prek"
    fake.write_text(
        "#!/bin/sh\n"
        '[ "$1" = install ] || exit 2\n'
        'hooks="$(git rev-parse --git-common-dir)/hooks"\n'
        'mkdir -p "$hooks"\n'
        "printf '#!/bin/sh\\n# File generated by prek: test\\n' > \"$hooks/pre-commit\"\n"
        "echo installed\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    done = subprocess.run(
        [
            just,
            "--justfile",
            str(JUSTFILE),
            "--working-directory",
            str(repo),
            "install-hooks",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        timeout=60,
        check=False,
    )
    return repo, done


def _new_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    return repo


def _hooks_path(repo: Path) -> str:
    return subprocess.run(
        ["git", "config", "--show-scope", "--get-all", "core.hooksPath"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    ).stdout.strip()


def test_install_hooks_installs_when_nothing_is_in_the_way(tmp_path: Path) -> None:
    _new_repo(tmp_path)
    repo, done = _install_hooks(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "installed" in done.stdout
    assert "# File generated by prek" in (repo / ".git/hooks/pre-commit").read_text(
        encoding="utf-8"
    )


def test_install_hooks_replaces_the_old_template_setting(tmp_path: Path) -> None:
    repo = _new_repo(tmp_path)
    _git(repo, "config", "--local", "core.hooksPath", ".githooks")
    _, done = _install_hooks(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert _hooks_path(repo) == ""


def test_install_hooks_reinstalls_over_its_own_shim(tmp_path: Path) -> None:
    repo = _new_repo(tmp_path)
    (repo / ".git/hooks").mkdir(exist_ok=True)
    (repo / ".git/hooks/pre-commit").write_text(
        "#!/bin/sh\n# File generated by prek: old\n", encoding="utf-8"
    )
    _, done = _install_hooks(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize(
    "setup",
    [
        "other-local",
        "worktree",
        "foreign-hook",
        "foreign-hook-with-githooks",
        "legacy-file",
    ],
)
def test_install_hooks_stops_and_changes_nothing(tmp_path: Path, setup: str) -> None:
    repo = _new_repo(tmp_path)
    hooks = repo / ".git/hooks"
    hooks.mkdir(exist_ok=True)
    if setup == "other-local":
        _git(repo, "config", "--local", "core.hooksPath", "custom-hooks")
    elif setup == "worktree":
        _git(repo, "config", "extensions.worktreeConfig", "true")
        _git(repo, "config", "--worktree", "core.hooksPath", "wt-hooks")
    elif setup == "foreign-hook":
        (hooks / "pre-commit").write_text("#!/bin/sh\njust check\n", encoding="utf-8")
    elif setup == "foreign-hook-with-githooks":
        _git(repo, "config", "--local", "core.hooksPath", ".githooks")
        (hooks / "pre-commit").write_text("#!/bin/sh\njust check\n", encoding="utf-8")
    else:
        (hooks / "pre-commit.legacy").write_text("#!/bin/sh\n", encoding="utf-8")
    before_path = _hooks_path(repo)
    before_files = {p.name: p.read_bytes() for p in hooks.iterdir() if p.is_file()}
    _, done = _install_hooks(tmp_path)
    assert done.returncode != 0
    assert "installed" not in done.stdout
    assert _hooks_path(repo) == before_path
    assert {
        p.name: p.read_bytes() for p in hooks.iterdir() if p.is_file()
    } == before_files
