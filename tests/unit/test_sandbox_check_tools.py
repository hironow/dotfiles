"""The sandbox image carries every tool `just check` runs.

tests/test_just_sandbox.py runs `just check` inside the dev container image,
which has no project mise.toml: it resolves tools only from the
/etc/mise/config.toml that .devcontainer/features/dotfiles-tools/install.sh
bakes, or from the apt packages the same script installs. When `just check`
gained a formal-methods gate that ran `mise x -- quint`, the image had no
quint, and PR #385's sandbox job failed with "quint couldn't exec process".
This test reads the recipes `just check` runs and the baked config, and fails
on any tool the image would not have.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INSTALL = REPO / ".devcontainer" / "features" / "dotfiles-tools" / "install.sh"
DEVCONTAINER = REPO / ".devcontainer" / "devcontainer.json"


def assignment(name: str) -> str:
    m = re.search(
        rf'^{name}="([^"]*)"', INSTALL.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert m, f"install.sh must set {name}"
    return m.group(1)


def test_quints_evaluator_is_built_from_a_pinned_commit() -> None:
    # `quint run` and `quint test` execute on a Rust evaluator that quint
    # downloads on first use, and its Linux release binaries need GLIBC_2.39;
    # the image is bookworm (2.36). So the image builds that release from
    # source, pinned to the tag's commit and its Cargo.lock, into the path
    # quint checks before it downloads anything.
    script = INSTALL.read_text(encoding="utf-8")
    assert re.fullmatch(r"[0-9a-f]{40}", assignment("QUINT_EVALUATOR_REV"))
    assert re.fullmatch(r"v\d+\.\d+\.\d+", assignment("QUINT_EVALUATOR_VERSION"))
    assert "cargo build --release --locked" in script
    assert (
        '"${QUINT_HOME}/rust-evaluator-${QUINT_EVALUATOR_VERSION}/quint_evaluator"'
        in script
    )


def test_quint_home_is_outside_the_home_directory() -> None:
    # A mount over /root hides whatever was baked under $HOME; the retired
    # Coder workspace did exactly that (ADR 0006). An evaluator baked into
    # ~/.quint would be hidden, and quint would then download one that
    # cannot run on this glibc.
    m = re.search(
        r"cat > /etc/profile.d/dotfiles-mise.sh <<'PROFILE'\n(.*?)\nPROFILE",
        INSTALL.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert m, "install.sh must write /etc/profile.d/dotfiles-mise.sh"
    assert re.search(r"^export QUINT_HOME=/opt/quint$", m.group(1), re.MULTILINE)
    assert re.search(
        r'"QUINT_HOME":\s*"/opt/quint"', DEVCONTAINER.read_text(encoding="utf-8")
    )
