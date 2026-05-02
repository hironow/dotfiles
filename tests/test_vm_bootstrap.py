"""Tests for the workspace VM startup script in
exe/coder/templates/dotfiles-devcontainer/main.tf.

The startup_script is a bash heredoc embedded in terraform that runs
as root on every fresh workspace VM. Three categories of supply
chain risk live here:

  1. **`curl ... | sh`** patterns. Any command that pipes a remote
     payload directly into a shell interpreter is TOFU at best and
     a one-shot RCE on a compromised CDN at worst. The classic
     offender is `curl https://get.docker.com | sh`, which we
     replace with Docker's official apt repository plus a pinned
     GPG fingerprint check.

  2. **GPG fingerprint pinning**. Apt repository keys fetched with
     `curl -fsSL ... > /etc/apt/keyrings/<x>.gpg` constitute TOFU on
     the first-use HTTPS connection. The dev container feature at
     `.devcontainer/features/dotfiles-tools/install.sh` already
     uses an `import_apt_key_with_fingerprint` helper that imports
     the key into a temporary keyring, extracts the actual
     fingerprint via `gpg --with-colons`, and aborts on mismatch.
     The VM bootstrap must apply the same discipline for the
     vendor keys it imports (Docker for now; Tailscale and Google
     Cloud are tracked as ADR 0005 Open Question 2 follow-up).

  3. **Versioned package install vs `latest` semantics**. Out of
     scope for this test file — that lives under ADR 0006.

These tests are pure regex assertions over main.tf source text.
They don't execute the bootstrap script, because doing so would
require a real GCE VM. The intent is to catch a regression at PR
review time the moment someone reintroduces a curl|bash or strips
a fingerprint.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN_TF = ROOT / "exe" / "coder" / "templates" / "dotfiles-devcontainer" / "main.tf"


@pytest.fixture(scope="module")
def main_tf_text() -> str:
    assert MAIN_TF.is_file(), f"main.tf missing at {MAIN_TF}"
    return MAIN_TF.read_text(encoding="utf-8")


# Docker's official apt-repo signing key, published at
# https://docs.docker.com/engine/install/debian/. The full
# fingerprint is split into 5 groups of 8 hex digits in the docs;
# we compare against the unspaced canonical form gpg emits with
# --with-colons.
DOCKER_GPG_FINGERPRINT = "9DC85822 9FC7DD38 854AE2D8 8D81803C 0EBFCD88".replace(" ", "")


def test_main_tf_does_not_pipe_remote_script_into_shell(main_tf_text: str) -> None:
    """No `curl ... | sh`, `curl ... | bash`, `wget ... | sh` etc.
    Match must allow `curl -fsSL ... -o /tmp/file.tar.gz` and other
    non-pipe download forms."""
    forbidden = [
        r"get\.docker\.com",
        r"curl\s[^\n]*\|\s*sh\b",
        r"curl\s[^\n]*\|\s*bash\b",
        r"wget\s[^\n]*\|\s*sh\b",
        r"wget\s[^\n]*\|\s*bash\b",
        r"sh\s+/tmp/get-docker\.sh",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, main_tf_text), (
            f"VM bootstrap still contains forbidden pattern {pattern!r}. "
            "Replace with apt repo + GPG fingerprint pin (see "
            ".devcontainer/features/dotfiles-tools/install.sh)."
        )


def test_main_tf_uses_docker_official_apt_repo(main_tf_text: str) -> None:
    """Positive assertion: the bootstrap downloads the docker key
    from download.docker.com (NOT get.docker.com) and writes an apt
    sources.list entry that signs it. This is the supply-chain-safe
    install path Docker themselves recommend."""
    assert "download.docker.com" in main_tf_text, (
        "main.tf must install docker via download.docker.com apt repo, "
        "not get.docker.com curl|bash."
    )
    assert re.search(
        r"deb \[signed-by=[^\]]*docker[^\]]*\] https://download\.docker\.com/linux/debian",
        main_tf_text,
    ), (
        "main.tf must register docker apt repo with signed-by= pointing "
        "at the verified keyring path."
    )


def test_main_tf_pins_docker_gpg_fingerprint(main_tf_text: str) -> None:
    """The Docker apt-key fingerprint is hardcoded so a compromised
    download.docker.com cannot swap in a different signing key."""
    assert DOCKER_GPG_FINGERPRINT in main_tf_text, (
        f"Docker GPG fingerprint {DOCKER_GPG_FINGERPRINT} missing from "
        f"main.tf. Without the pin the apt key import is TOFU."
    )


def test_main_tf_has_fingerprint_helper_function(main_tf_text: str) -> None:
    """The bootstrap must define a helper that aborts on fingerprint
    mismatch. Pattern matches the install.sh helper but allows for
    name variation (helper might inline-only the docker case)."""
    # Either the named helper from install.sh or an inline
    # equivalent ('expected fingerprint' check + exit on mismatch).
    has_helper = (
        "import_apt_key_with_fingerprint" in main_tf_text
        or re.search(r"GPG fingerprint mismatch", main_tf_text, re.IGNORECASE)
        is not None
    )
    assert has_helper, (
        "main.tf must call out fingerprint-mismatch as an explicit "
        "abort path. Either import the install.sh helper pattern or "
        "inline the gpg --with-colons + diff check."
    )


def test_main_tf_installs_docker_via_apt(main_tf_text: str) -> None:
    """Docker is installed as `apt-get install ... docker-ce ...`,
    not via the legacy convenience script. The package list should
    include the engine, CLI, and containerd at minimum so existing
    `docker run` / `docker pull` calls in the script keep working."""
    assert re.search(r"apt-get install[\s\S]*?docker-ce", main_tf_text), (
        "Docker engine must be installed via the docker-ce apt package."
    )


def test_main_tf_still_runs_docker_pull_and_run(main_tf_text: str) -> None:
    """Sanity: the supply-chain refactor must not have removed the
    actual docker pull + docker run steps that bring up the dev
    container."""
    assert "docker pull" in main_tf_text, "docker pull step missing"
    assert "docker run" in main_tf_text, "docker run step missing"
    assert "auth configure-docker" in main_tf_text, "AR docker login step missing"
