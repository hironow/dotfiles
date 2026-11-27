"""install.sh must self-provision `mise` (and its toolchain) on a bare
Linux/WSL host — not merely assume the devcontainer feature already did.

Why this exists
---------------
install.sh's Linux path historically skipped almost everything with
"covered by apt + dev container feature". That is true inside a dev
container image, but a plain WSL Ubuntu box running `curl … | bash`
gets no mise, hence no uv/node/prek/… and every downstream step self-skips.

Two new steps close that, without disturbing the container flow (both are
`command -v` guarded — a devcontainer with mise already present is a no-op):

- `step_mise_bootstrap`: if mise is missing, download the pinned mise
  release binary to ~/.local/bin, SHA256-verified (same posture as the
  existing `step_just_bootstrap`; no `curl | bash`, per the repo guardrail).
- `step_mise_install`: `mise trust && mise install` to materialize the
  mise.toml toolset. Gated by INSTALL_SKIP_ADD_UPDATE so the Podman
  install-verification (which sets it) stays fast.

What install.sh says (the steps defined and driven, the download from
mise's GitHub release, no pipe to a shell, the skip variable) is the
repo-lint rule install-facts (ADR-0093). The checksum gate is held here by a
run of the real step with a fake curl (ADR-0093 D4).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = ROOT / "install.sh"


# ADR-0093 D4: the downloaded mise runs as the user, so the SHA256 check
# against the release's SHASUMS is held by a run of the real step.
FAKE_CURL = """#!/bin/sh
out=""; url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    --proto) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
printf '%s\\n' "$url" >> "$FIXTURE_LOG"
case "$url" in
  */SHASUMS256.txt)
    cd "$(dirname "$out")"
    if [ "$FIXTURE_SUMS" = match ]; then
      sha256sum mise-*.tar.gz > "$out"
    else
      for f in mise-*.tar.gz; do
        printf '%064d  %s\\n' 0 "$f"
      done > "$out"
    fi
    ;;
  *.tar.gz) cp "$FIXTURE_TARBALL" "$out" ;;
  *) exit 97 ;;
esac
"""


def run_mise_bootstrap(
    tmp_path: Path, install_sh: Path, *, sums: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run install.sh's step_mise_bootstrap under its `set -eu` on a bare
    Linux host: a fake uname and curl, the real sha256sum, tar and install.
    Returns the run and where mise would land."""
    bash, checker = shutil.which("bash"), shutil.which("sha256sum")
    if bash is None or checker is None:
        pytest.skip("needs bash and sha256sum (the step's checker)")
    text = install_sh.read_text(encoding="utf-8")
    step = re.search(
        r"^step_mise_bootstrap\(\) \{\n.*?^\}\n", text, re.MULTILINE | re.DOTALL
    )
    assert step, "install.sh has no step_mise_bootstrap()"
    fake = tmp_path / "bin"
    fake.mkdir()
    # sha256sum alone from its folder: a folder on PATH could hold a mise,
    # and the step returns early when one is found.
    (fake / "sha256sum").symlink_to(checker)
    for name, body in {
        "uname": 'case "$1" in -m) echo x86_64 ;; *) echo Linux ;; esac',
        "curl": FAKE_CURL.removeprefix("#!/bin/sh\n"),
    }.items():
        (fake / name).write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
        (fake / name).chmod(0o755)
    payload = tmp_path / "payload"
    (payload / "mise" / "bin").mkdir(parents=True)
    (payload / "mise" / "bin" / "mise").write_text(
        "#!/bin/sh\necho mise\n", encoding="utf-8"
    )
    tarball = tmp_path / "mise.tar.gz"
    subprocess.run(
        ["tar", "-czf", str(tarball), "-C", str(payload), "mise"], check=True
    )
    home = tmp_path / "home"
    home.mkdir()
    temp = tmp_path / "tmp"
    temp.mkdir()
    script = (
        "set -eu\n_skip_windows() { :; }\n"
        + step.group(0)
        + "DOTFILES_OS=linux\nstep_mise_bootstrap\n"
    )
    done = subprocess.run(
        [bash, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            "PATH": f"{fake}:/usr/bin:/bin",
            "HOME": str(home),
            "TMPDIR": str(temp),
            "FIXTURE_SUMS": sums,
            "FIXTURE_TARBALL": str(tarball),
            "FIXTURE_LOG": str(tmp_path / "urls"),
        },
        check=False,
        timeout=60,
    )
    return done, home / ".local" / "bin" / "mise"


def check_a_mismatched_download_is_not_installed(
    tmp_path: Path, install_sh: Path
) -> None:
    done, mise = run_mise_bootstrap(tmp_path, install_sh, sums="mismatch")
    assert done.returncode != 0, done.stdout + done.stderr
    assert not mise.exists(), "a download that failed its checksum was installed"


def check_a_verified_download_is_installed(tmp_path: Path, install_sh: Path) -> None:
    done, mise = run_mise_bootstrap(tmp_path, install_sh, sums="match")
    assert done.returncode == 0, done.stdout + done.stderr
    assert mise.is_file()
    urls = (tmp_path / "urls").read_text(encoding="utf-8").split()
    assert all(
        u.startswith("https://github.com/jdx/mise/releases/download/") for u in urls
    ), urls


@pytest.mark.skipif(
    sys.platform == "win32", reason="the step's Linux path, with POSIX fakes"
)
def test_a_download_that_fails_its_checksum_is_not_installed(tmp_path: Path) -> None:
    check_a_mismatched_download_is_not_installed(tmp_path, INSTALL_SH)


@pytest.mark.skipif(
    sys.platform == "win32", reason="the step's Linux path, with POSIX fakes"
)
def test_a_verified_download_is_installed(tmp_path: Path) -> None:
    check_a_verified_download_is_installed(tmp_path, INSTALL_SH)
