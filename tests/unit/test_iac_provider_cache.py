"""`just test-iac` and the IaC workflow reuse a provider cache.

Each `tofu test` run starts from a fresh TF_DATA_DIR, so without a cache every
run downloads the tailscale provider from github.com release assets, which
returned 504s for hours on 2026-11-09. OpenTofu reuses a cached provider only
when it matches the hashes in the stack's .terraform.lock.hcl, so the cache
saves the download without loosening the check, as long as nothing sets
TF_PLUGIN_CACHE_MAY_BREAK_DEPENDENCY_LOCK_FILE.

A stub `mise` first on PATH, a POSIX sh script that Git's sh also runs,
records what each `mise x -- tofu ...` call would see, so no tofu runs here.
The unit-test workflow's windows-jev job runs this file on Windows, from Git
Bash's usr/bin like the runbook says shebang recipes run.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/iac-test.yaml"
CACHE_SUFFIX = Path("opentofu", "plugin-cache")
BREAK_LOCK = "TF_PLUGIN_CACHE_MAY_BREAK_DEPENDENCY_LOCK_FILE"

pytestmark = pytest.mark.skipif(
    shutil.which("just") is None, reason="just is not installed"
)

# One line per call: the cache dir, whether the stub saw it as a directory,
# the data dir, and the lock-file escape hatch. Tabs separate the fields.
STUB = (
    "#!/bin/sh\n"
    'if [ -d "$TF_PLUGIN_CACHE_DIR" ]; then is_dir=yes; else is_dir=no; fi\n'
    "printf '%s\\t%s\\t%s\\t%s\\n' "
    '"$TF_PLUGIN_CACHE_DIR" "$is_dir" "$TF_DATA_DIR" '
    f'"${{{BREAK_LOCK}-<unset>}}" >> "$IAC_CACHE_RECORD"\n'
)


def _git_usr_bin() -> Path:
    """Git for Windows' usr/bin, which holds the env and cygpath just needs."""
    candidates = []
    if sh := shutil.which("sh"):
        candidates.append(Path(sh).parent)
    if git := shutil.which("git"):
        candidates.append(Path(git).parents[1] / "usr" / "bin")
    for directory in candidates:
        if (directory / "env.exe").is_file() and (directory / "cygpath.exe").is_file():
            return directory
    pytest.fail(f"no Git usr/bin with env.exe and cygpath.exe among {candidates}")


def _cygpath(flag: str, path: str) -> str:
    done = subprocess.run(
        [str(_git_usr_bin() / "cygpath.exe"), flag, path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return done.stdout.strip()


def _posix(path: Path) -> str:
    """The path as Git Bash spells it (`/c/...` on Windows)."""
    return str(path) if sys.platform != "win32" else _cygpath("-u", str(path))


def _native(path: str) -> Path:
    """A path the recipe printed, as this OS's Python opens it."""
    return Path(path) if sys.platform != "win32" else Path(_cygpath("-w", path))


def _run_test_iac(tmp_path: Path, **env_overrides: str | None) -> list[list[str]]:
    """Run `just test-iac` against the stub and return one record per tofu call."""
    bin_dir = tmp_path / "stub bin"
    bin_dir.mkdir(exist_ok=True)
    record = tmp_path / "calls.tsv"
    stub = bin_dir / "mise"
    # LF only: a CR after the shebang would name another interpreter.
    stub.write_bytes(STUB.encode("utf-8"))
    stub.chmod(0o755)
    path = [str(bin_dir)]
    if sys.platform == "win32":
        path.append(str(_git_usr_bin()))
    env = {
        **os.environ,
        "PATH": os.pathsep.join([*path, os.environ["PATH"]]),
        "IAC_CACHE_RECORD": record.as_posix(),
    }
    env.pop("XDG_CACHE_HOME", None)
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    done = subprocess.run(
        ["just", "--justfile", str(ROOT / "justfile"), "test-iac"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert done.returncode == 0, done.stderr
    calls = [
        line.split("\t") for line in record.read_text(encoding="utf-8").splitlines()
    ]
    # init and test for every stack, so never zero calls.
    assert calls, "the recipe ran no tofu command"
    return calls


def _assert_cache_used(calls: list[list[str]], expected: Path) -> None:
    assert expected.is_dir(), f"the recipe did not create {expected}"
    for cache_dir, is_dir, _, _ in calls:
        assert is_dir == "yes", (
            f"tofu ran with a cache dir it could not see: {cache_dir}"
        )
        assert _native(cache_dir).samefile(expected), (cache_dir, expected)


def test_test_iac_uses_the_xdg_provider_cache(tmp_path: Path) -> None:
    # given an absolute XDG_CACHE_HOME
    xdg = tmp_path / "xdg cache"
    # when test-iac runs
    calls = _run_test_iac(
        tmp_path, XDG_CACHE_HOME=_posix(xdg), HOME=str(tmp_path / "home")
    )
    # then every tofu call uses the cache under it
    _assert_cache_used(calls, xdg / CACHE_SUFFIX)
    assert not (tmp_path / "home" / ".cache").exists()


def test_test_iac_falls_back_to_home_cache(tmp_path: Path) -> None:
    # given no XDG_CACHE_HOME
    home = tmp_path / "home dir"
    home.mkdir()
    # when test-iac runs, then the cache is ~/.cache/opentofu/plugin-cache
    calls = _run_test_iac(tmp_path, XDG_CACHE_HOME=None, HOME=str(home))
    _assert_cache_used(calls, home / ".cache" / CACHE_SUFFIX)


@pytest.mark.parametrize(
    "relative",
    [
        "rel-xdg",
        pytest.param(
            "C:/rel-xdg",
            marks=pytest.mark.skipif(
                sys.platform == "win32", reason="a drive path is relative only on POSIX"
            ),
        ),
    ],
)
def test_test_iac_ignores_a_relative_xdg_cache_home(
    tmp_path: Path, relative: str
) -> None:
    # given a relative XDG_CACHE_HOME, which the XDG spec says to ignore
    home = tmp_path / "home dir"
    home.mkdir()
    calls = _run_test_iac(tmp_path, XDG_CACHE_HOME=relative, HOME=str(home))
    # then the cache falls back to ~/.cache, and nothing lands in the repo
    _assert_cache_used(calls, home / ".cache" / CACHE_SUFFIX)
    top = relative.split("/")[0]
    assert not (ROOT / top).exists()
    assert not (ROOT / "tofu" / "tailnet" / top).exists()


def test_test_iac_keeps_a_fresh_data_dir_outside_the_cache(tmp_path: Path) -> None:
    home = tmp_path / "home dir"
    home.mkdir()
    calls = _run_test_iac(tmp_path, HOME=str(home))
    data_dirs = {data_dir for _, _, data_dir, _ in calls}
    for cache_dir, _, data_dir, _ in calls:
        assert data_dir, "tofu ran without a TF_DATA_DIR of its own"
        assert not data_dir.startswith(cache_dir), (data_dir, cache_dir)
    # the recipe removes each data dir when its stack is done
    for data_dir in data_dirs:
        assert not _native(data_dir).exists(), data_dir


def test_test_iac_never_lets_the_cache_break_the_lock_file(tmp_path: Path) -> None:
    # given a caller's shell that would let a cached package bypass the lock file
    home = tmp_path / "home dir"
    home.mkdir()
    calls = _run_test_iac(tmp_path, HOME=str(home), **{BREAK_LOCK: "true"})
    # then tofu never sees it
    assert {escape for *_, escape in calls} == {"<unset>"}


def _workflow_steps() -> list[str]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return re.split(r"\n      - ", text.split("\n    steps:\n", 1)[1])


def test_iac_workflow_caches_providers_keyed_on_lock_files() -> None:
    steps = _workflow_steps()
    exports = next(i for i, s in enumerate(steps) if "TF_PLUGIN_CACHE_DIR=" in s)
    cache = next(i for i, s in enumerate(steps) if "actions/cache@" in s)
    init = next(i for i, s in enumerate(steps) if "tofu init" in s)
    assert "$GITHUB_ENV" in steps[exports]
    assert re.search(r"uses: actions/cache@[0-9a-f]{40} # v\d", steps[cache])
    assert "path: ${{ env.TF_PLUGIN_CACHE_DIR }}" in steps[cache]
    assert "hashFiles('tofu/**/.terraform.lock.hcl')" in steps[cache]
    # the path is set before the cache restores into it, and both precede init
    assert exports < cache < init


def test_nothing_lets_the_cache_break_the_lock_file() -> None:
    for path in (ROOT / "justfile", WORKFLOW):
        text = path.read_text(encoding="utf-8")
        assert "plugin_cache_may_break_dependency_lock_file" not in text, path
        assert not re.search(rf"{BREAK_LOCK}\s*[=:]", text), path
