"""The recipes that guard secrets do what they guard, run with fake tools.

ADR-0093 D4: a guard for secrets is held by a test that runs the code. The
justfile phase moved these guards to repo-lint rules; these tests run the real
recipes from the checkout's justfile and check what the recipe asked for:

- `install-hooks` installs the commit-msg hook, where the secret scan of the
  commit message runs, as well as pre-commit;
- `check-forbidden-tokens` scans the staged change with the gate's value;
- the branch and tree scans run with the gate's value, and `ci` reaches both
  (a dry run: just prints the commands its dependencies resolve to);
- `check-pr-body` scans a pull request body;
- the tailnet recipes give OpenTofu the state passphrase as TF_ENCRYPTION and no
  backend file;
- the local servers listen on loopback and never serve the checkout, which
  holds private keys and certificates, or a folder above it; the page server
  serves a copy of the page without the files git ignores.

PATH holds only recording fakes and links to the plain tools the recipes need
(bash, git, tar, ...), so a recipe that turns to another tool fails instead of
reaching it. Native Windows skips: the recipes run under bash there through
Git Bash, and the fakes are POSIX shell scripts.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUST = shutil.which("just")
PLAIN_TOOLS = ("bash", "sh", "cat", "mktemp", "rm", "tar", "git", "find", "sort", "tr")
ARG_END = "\x1f"
CALL_END = "\x1e"

pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX fakes"),
    pytest.mark.skipif(JUST is None, reason="needs just"),
]


class Fakes:
    """A PATH of recording fakes and links to the plain tools.

    Each fake appends its name and arguments to the log as one call and runs
    `extra` in the caller's working directory."""

    def __init__(self, tmp_path: Path, *names: str) -> None:
        assert JUST is not None
        self.bin = tmp_path / "fake-bin"
        self.bin.mkdir()
        self.tools = tmp_path / "tools"
        self.tools.mkdir()
        for tool in (*PLAIN_TOOLS, "just"):
            real = shutil.which(tool)
            if real is None:
                pytest.skip(f"needs {tool}")
            (self.tools / tool).symlink_to(real)
        self.log = tmp_path / "calls"
        self.log.touch()
        self.home = tmp_path / "home"
        self.home.mkdir()
        for name in names:
            self.add(name, "")

    def add(self, name: str, extra: str) -> None:
        path = self.bin / name
        path.write_text(
            f'#!/bin/sh\nprintf "%s{ARG_END}" "{name}" "$@" >> "{self.log}"\n'
            f'printf "{CALL_END}" >> "{self.log}"\n{extra}exit 0\n',
            encoding="utf-8",
            newline="\n",
        )
        path.chmod(0o755)

    def just(
        self, *args: str, dry: bool = False, checkout: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run a recipe of the real justfile, in `checkout` when given."""
        cmd = [str(self.tools / "just"), "--justfile", str(ROOT / "justfile")]
        if checkout is not None:
            cmd += ["--working-directory", str(checkout)]
        if dry:
            cmd.append("--dry-run")
        return subprocess.run(
            [*cmd, *args],
            env={"PATH": f"{self.bin}:{self.tools}", "HOME": str(self.home)},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )

    def calls(self) -> list[list[str]]:
        text = self.log.read_text(encoding="utf-8")
        return [call.split(ARG_END)[:-1] for call in text.split(CALL_END)[:-1]]


def _ok(done: subprocess.CompletedProcess[str]) -> None:
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]


def _gate() -> list[str]:
    assert JUST is not None
    value = subprocess.run(
        [
            JUST,
            "--justfile",
            str(ROOT / "justfile"),
            "--evaluate",
            "FORBIDDEN_TOKEN_GATE",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    return shlex.split(value)


# tools/simple-server's flags and their defaults.
SERVER_FLAGS = {"host": "localhost", "port": "8080", "dir": ".", "cert": "", "key": ""}


def _server_flags(args: list[str]) -> dict[str, str]:
    """The values simple-server's flag.Parse sees in its arguments.

    Go's flag package stops at the first argument that is not a flag and
    after `--`, takes -name v, -name=v, --name v and --name=v alike, keeps
    the last value, and exits on a flag it does not define."""
    seen = dict(SERVER_FLAGS)
    i = 0
    while i < len(args):
        word = args[i]
        if word == "--" or len(word) < 2 or not word.startswith("-"):
            break
        name, eq, value = word.lstrip("-").partition("=")
        assert name in SERVER_FLAGS, f"flag provided but not defined: {word}"
        if not eq:
            assert i + 1 < len(args), f"flag needs an argument: {word}"
            i += 1
            value = args[i]
        seen[name] = value
        i += 1
    return seen


def _hcl_code(text: str) -> str:
    """HCL without its comments (/* */, # and //)."""
    text = re.sub(r"(?s)/\*.*?\*/", "", text)
    return re.sub(r"(?m)(?:#|//).*$", "", text)


def _not_the_checkout(served: Path, checkout: Path) -> None:
    """The served folder is neither the checkout nor a folder above it."""
    checkout = checkout.resolve()
    assert served not in (checkout, *checkout.parents), served


def test_install_hooks_installs_the_commit_message_scan(tmp_path: Path) -> None:
    fakes = Fakes(tmp_path, "mise")
    _ok(fakes.just("install-hooks"))
    (call,) = fakes.calls()
    assert call[:4] == ["mise", "exec", "--", "prek"]
    assert "install" in call
    hook_types = [call[i + 1] for i, word in enumerate(call) if word == "--hook-type"]
    assert sorted(hook_types) == ["commit-msg", "pre-commit"]


def test_the_staged_scan_runs_with_the_gate(tmp_path: Path) -> None:
    fakes = Fakes(tmp_path, "python3")
    _ok(fakes.just("check-forbidden-tokens"))
    assert fakes.calls() == [
        ["python3", "scripts/check_forbidden_tokens.py", "staged", *_gate()]
    ]
    assert "--require-list" in _gate()


@pytest.mark.parametrize("scope", ["branch", "tree"])
def test_ci_rescans_the_branch_and_tree(tmp_path: Path, scope: str) -> None:
    fakes = Fakes(tmp_path, "python3")
    _ok(fakes.just(f"check-forbidden-tokens-{scope}"))
    assert fakes.calls() == [
        ["python3", "scripts/check_forbidden_tokens.py", scope, *_gate()]
    ]
    done = fakes.just("ci", dry=True)
    _ok(done)
    plan = done.stdout + done.stderr
    line = f"python3 scripts/check_forbidden_tokens.py {scope} {shlex.join(_gate())}"
    assert line in [step.strip() for step in plan.splitlines()], plan[-3000:]
    assert len(fakes.calls()) == 1


def test_a_pull_request_body_is_scanned(tmp_path: Path) -> None:
    fakes = Fakes(tmp_path, "python3")
    body = tmp_path / "body.md"
    body.write_text("A pull request body.\n", encoding="utf-8")
    _ok(fakes.just("check-pr-body", str(body)))
    assert fakes.calls() == [
        ["python3", "scripts/check_forbidden_tokens.py", "file", str(body)]
    ]


def test_tailnet_state_is_encrypted_with_the_passphrase(tmp_path: Path) -> None:
    fakes = Fakes(tmp_path)
    env = tmp_path / "env"
    fakes.add("mise", f'printf "TF_ENCRYPTION=%s\\n" "$TF_ENCRYPTION" >> "{env}"\n')
    secret = fakes.home / ".config" / "tofu" / "tailnet.passphrase"
    secret.parent.mkdir(parents=True)
    secret.write_text("correct-horse-battery-staple\n", encoding="utf-8")
    _ok(fakes.just("tailnet-init"))
    (call,) = fakes.calls()
    assert call[:5] == ["mise", "x", "--", "tofu", "init"]
    assert not any("backend-config" in word for word in call)
    encryption = env.read_text(encoding="utf-8")
    assert 'passphrase = "correct-horse-battery-staple"' in encryption
    code = _hcl_code(encryption)
    for block in ("state", "plan"):
        body = re.search(rf"(?ms)^\s*{block}\s*\{{(.*?)^\s*\}}", code)
        assert body is not None, encryption
        assert re.search(r"(?m)^\s*enforced\s*=\s*true\s*$", body[1]), (
            f"{block}: {body[1]}"
        )


def _available(fakes: Fakes, recipe: str) -> bool:
    return fakes.just("--show", recipe).returncode == 0


def _checkout(tmp_path: Path) -> Path:
    """A checkout with the page, a tracked file the page does not need, and
    ignored private keys at the top and inside the page's folder."""
    repo = tmp_path / "checkout"
    for path, text in {
        "index.html": "<!doctype html>\n",
        "site/page.html": "<p>page</p>\n",
        "README.md": "not the page\n",
        ".gitignore": "private/\n",
        "private/certificates/privkey.pem": "not a real key\n",
        "site/private/privkey.pem": "not a real key\n",
    }.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text, encoding="utf-8")
    (repo / "tools" / "simple-server").mkdir(parents=True)
    (repo / "docs").mkdir()
    # No GIT_* from the caller: GIT_DIR or GIT_INDEX_FILE would point these
    # commands at the real checkout.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    for args in (
        ["init", "-q"],
        ["add", "index.html", "site", "README.md", ".gitignore"],
    ):
        subprocess.run(
            ["git", *args], cwd=repo, env=env, check=True, capture_output=True
        )
    return repo


# Inside the fake, every folder the server could serve: its working folder and
# each argument, or value after "=", that names a folder. The page server
# deletes its copy when the recipe ends, so the fake lists them right away.
FOLDERS = """for a in . "$@"; do
  for d in "$a" "${{a#*=}}"; do
    if [ -d "$d" ]; then
      printf '%s\\t%s\\t' "$d" "$(cd "$d" && pwd -P)" >> "{out}"
      (cd "$d" && find . -type f | sort | tr '\\n' ' ') >> "{out}"
      echo >> "{out}"
    fi
  done
done
"""


def _served(out: Path, value: str) -> tuple[Path, list[str]]:
    """The folder the server serves for its -dir value, and its files."""
    for line in out.read_text(encoding="utf-8").splitlines():
        name, real, files = line.split("\t", 2)
        if name == value:
            return Path(real), files.split()
    raise AssertionError(f"-dir {value!r} names no folder")


def test_the_page_server_listens_on_loopback_and_serves_a_copy(tmp_path: Path) -> None:
    fakes = Fakes(tmp_path)
    if not _available(fakes, "site-serve"):
        pytest.skip("site-serve is a [unix] recipe")
    checkout = _checkout(tmp_path)
    out = tmp_path / "folders"
    fakes.add("mise", FOLDERS.format(out=out))
    _ok(fakes.just("site-serve", checkout=checkout))
    (call,) = fakes.calls()
    assert call[:6] == ["mise", "exec", "--", "go", "run", "."]
    flags = _server_flags(call[6:])
    assert flags["host"] == "127.0.0.1"
    served, files = _served(out, flags["dir"])
    _not_the_checkout(served, checkout)
    assert checkout.resolve() not in served.parents, "serve a copy, not the checkout"
    assert files == ["./index.html", "./site/page.html"]


def test_the_tls_check_server_never_serves_the_checkout(tmp_path: Path) -> None:
    fakes = Fakes(tmp_path)
    if not _available(fakes, "check-localhost-tls"):
        pytest.skip("check-localhost-tls is a [unix] recipe")
    checkout = _checkout(tmp_path)
    out = tmp_path / "folders"
    fakes.add("sudo", FOLDERS.format(out=out))
    _ok(fakes.just("check-localhost-tls", checkout=checkout))
    (call,) = fakes.calls()
    assert call[:3] == ["sudo", "go", "run"]
    flags = _server_flags(call[4:])
    assert flags["host"] in ("127.0.0.1", "localhost")
    served, _ = _served(out, flags["dir"])
    _not_the_checkout(served, checkout)
