"""`just agent-hooks-test-installed` tests the release a home's link names.

The recipe resolves the home's stable link, checks the release with
`hookrelease check`, and runs agent-hook's process tests (cmd/agent-hook)
against it through `_agent-hooks-test-binary`: AGENT_HOOK_UNDER_TEST names
the binary, AGENT_HOOK_EXPECT_RELEASE its release ID, and `go test` runs
with -count=1, so no cached result stands in for the run. These tests run
that private recipe with three programs at one path, and show that it runs
the one it is given: one that passes every hook fails a blocking case, one
with another release ID fails before any test, and the dev build passes.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_hooks_go import STRICT_GO, why_go_cannot_build_the_module

ROOT = Path(__file__).resolve().parents[2]
REAL_GO = shutil.which("go")
BLOCKING = "TestTheBinaryAnswersAsThePayloadCorpusExpects"

pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="the recipe is [unix]"),
    pytest.mark.skipif(shutil.which("just") is None, reason="just is not installed"),
]


@pytest.fixture(scope="module")
def go_env(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """The environment every Go run here uses: a home, caches, and state of
    its own, and the module cache this machine already has."""
    home = tmp_path_factory.mktemp("go-home")
    why = why_go_cannot_build_the_module(REAL_GO, home)
    if why:
        if STRICT_GO:
            pytest.fail(why)
        pytest.skip(why)
    modules = os.environ.get("GOMODCACHE") or str(Path.home() / "go" / "pkg" / "mod")
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / "state"),
        "GOCACHE": str(home / ".cache" / "go-build"),
        "GOMODCACHE": modules,
        "GOTOOLCHAIN": "local",
    }


@pytest.fixture(scope="module")
def link(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One path that each test puts its own program at, as a home's link."""
    path = (
        tmp_path_factory.mktemp("data")
        / "dotfiles/agent-hooks/current/claude/agent-hook"
    )
    path.parent.mkdir(parents=True)
    return path


def _stand_in(path: Path, version: str) -> None:
    # It answers `version`, and passes every hook: exit 0, nothing printed.
    path.unlink(missing_ok=True)
    path.write_text(
        f'#!/bin/sh\nif [ "$1" = version ]; then echo "{version}"; fi\nexit 0\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def _test_binary(binary: Path, release: str, env: dict[str, str]) -> str:
    assert REAL_GO is not None
    done = subprocess.run(
        [
            "just",
            "--justfile",
            str(ROOT / "justfile"),
            "_agent-hooks-test-binary",
            str(binary),
            release,
            REAL_GO,
            "-run",
            BLOCKING,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    return f"exit {done.returncode}\n{done.stdout}\n{done.stderr}"


def test_a_binary_that_passes_every_hook_fails_a_blocking_case(
    go_env: dict[str, str], link: Path
) -> None:
    # given a program with the expected release ID that blocks nothing
    _stand_in(link, "agent-hook 0123456789abcdef go0")
    # when the recipe tests it, then the corpus's blocking cases fail
    out = _test_binary(link, "0123456789abcdef", go_env)
    assert not out.startswith("exit 0") and f"--- FAIL: {BLOCKING}" in out, out


def test_a_binary_with_another_release_id_fails_before_any_test(
    go_env: dict[str, str], link: Path
) -> None:
    # given a program that says it is another release, at the same path
    _stand_in(link, "agent-hook fedcba9876543210 go0")
    # when the recipe tests it as 0123456789abcdef, then no test runs
    out = _test_binary(link, "0123456789abcdef", go_env)
    assert not out.startswith("exit 0"), out
    assert "is release fedcba9876543210, not 0123456789abcdef" in out, out
    assert "--- FAIL: Test" not in out, out


def test_the_dev_build_passes(go_env: dict[str, str], link: Path) -> None:
    # given the dev build, at the same path, when the recipe tests it as dev
    link.unlink(missing_ok=True)
    built = subprocess.run(
        [str(REAL_GO), "build", "-o", str(link), "./cmd/agent-hook"],
        cwd=ROOT / "tools/agent-hooks",
        env=go_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    # then the blocking cases pass
    out = _test_binary(link, "dev", go_env)
    assert out.startswith("exit 0"), out


# ---- the public recipe, end to end ----


def _public_recipe(key: str, env: dict[str, str], go: str | None = None) -> str:
    assert REAL_GO is not None
    done = subprocess.run(
        [
            "just",
            "--justfile",
            str(ROOT / "justfile"),
            "agent-hooks-test-installed",
            key,
            go or REAL_GO,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    return f"exit {done.returncode}\n{done.stdout}\n{done.stderr}"


@pytest.fixture(scope="module")
def scratch_release(
    go_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory
) -> tuple[dict[str, str], Path]:
    """A real release this checkout builds, in a scratch data directory, and
    the environment that names that directory."""
    assert REAL_GO is not None
    data = tmp_path_factory.mktemp("installed") / "data"
    env = {**go_env, "XDG_DATA_HOME": str(data)}
    tools = tmp_path_factory.mktemp("tools")
    module = ROOT / "tools/agent-hooks"
    for args in (
        [REAL_GO, "build", "-o", str(tools / "hookrelease"), "./cmd/hookrelease"],
        [
            str(tools / "hookrelease"),
            "build",
            "--into",
            str(data / "dotfiles/agent-hooks/releases"),
        ],
    ):
        done = subprocess.run(
            args,
            cwd=module,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            check=False,
        )
        assert done.returncode == 0, done.stderr
    return env, Path(done.stdout.strip())


def _link(env: dict[str, str], key: str, target: Path) -> None:
    link = (
        Path(env["XDG_DATA_HOME"]) / "dotfiles/agent-hooks/current" / key / "agent-hook"
    )
    link.parent.mkdir(parents=True, exist_ok=True)
    link.unlink(missing_ok=True)
    link.symlink_to(target)


def test_the_recipe_tests_the_release_the_named_homes_link_names(
    scratch_release: tuple[dict[str, str], Path], tmp_path: Path
) -> None:
    # given work-a's link to a real release, no link for claude, and a Go
    # that records what `go test` is told to test, then runs the real Go
    env, built = scratch_release
    _link(env, "work-a", built)
    record = tmp_path / "under-test.txt"
    recording_go = tmp_path / "go"
    recording_go.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = test ]; then\n'
        '  printf "%s\\n%s\\n" "${AGENT_HOOK_UNDER_TEST-unset}" '
        '"${AGENT_HOOK_EXPECT_RELEASE-unset}" > "$UNDER_TEST_RECORD"\n'
        "fi\n"
        'exec "$REAL_GO" "$@"\n',
        encoding="utf-8",
    )
    recording_go.chmod(0o755)
    assert REAL_GO is not None
    env = {**env, "UNDER_TEST_RECORD": str(record), "REAL_GO": REAL_GO}
    # when the recipe tests work-a, then the release passes agent-hook's tests
    out = _public_recipe("work-a", env, str(recording_go))
    assert out.startswith("exit 0"), out
    # and the tests were told to run work-a's link, as the release it names
    link = Path(env["XDG_DATA_HOME"]) / "dotfiles/agent-hooks/current/work-a/agent-hook"
    assert record.read_text(encoding="utf-8").splitlines() == [
        str(link),
        built.parent.name,
    ]
    assert (
        "ok  \tgithub.com/hironow/dotfiles/tools/agent-hooks/cmd/agent-hook" in out
    ), out


def test_the_recipe_refuses_a_release_this_checkout_does_not_build(
    scratch_release: tuple[dict[str, str], Path],
) -> None:
    # given work-b's link to a program under another release's ID
    env, built = scratch_release
    other = built.parent.parent / "fedcba9876543210" / "agent-hook"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_bytes(built.read_bytes())
    other.chmod(0o755)
    _link(env, "work-b", other)
    # when the recipe tests work-b, then hookrelease check refuses it, and no
    # test runs
    out = _public_recipe("work-b", env)
    assert not out.startswith("exit 0"), out
    assert "differs from checkout ID" in out, out
    assert "--- FAIL" not in out and "ok  \t" not in out, out


def test_the_recipe_refuses_a_home_with_no_link(
    scratch_release: tuple[dict[str, str], Path],
) -> None:
    env, _ = scratch_release
    out = _public_recipe("work-c", env)
    assert not out.startswith("exit 0"), out
    assert "ok  \t" not in out, out
