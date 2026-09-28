"""The sandbox image carries every tool `just check` runs.

tests/test_just_sandbox.py runs `just check` inside the dev container image,
which has no project mise.toml: it resolves tools only from the
/etc/mise/config.toml that .devcontainer/features/dotfiles-tools/install.sh
bakes, or from the apt packages the same script installs. When `just check`
gained the formal-methods gate (`just spec-check`, which runs `mise x --
quint`), the image had no quint, and PR #385's sandbox job failed with
"quint couldn't exec process". This test reads the recipes `just check` runs
and the baked config, and fails on any tool the image would not have.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JUSTFILE = REPO / "justfile"
INSTALL = REPO / ".devcontainer" / "features" / "dotfiles-tools" / "install.sh"
DEVCONTAINER = REPO / ".devcontainer" / "devcontainer.json"
GLOBAL_MISE = REPO / "config" / "mise" / "config.toml"

# The recipes `just check` runs, itself included.
CHECK_RECIPES = ("check", "go-lint", "go-test", "spec-check")

# Tools install.sh puts on PATH through apt, not mise.
APT_TOOLS = {"shellcheck", "jq"}


def recipe_body(name: str) -> str:
    lines = JUSTFILE.read_text().splitlines()
    # The name, then parameters or nothing, then the colon: `check:` and not
    # `check-agent-refs *homes:`.
    header = re.compile(rf"^{re.escape(name)}(?:\s+[^:]*)?:(?!=)")
    start = next(i for i, line in enumerate(lines) if header.match(line))
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def tools_just_check_runs() -> set[str]:
    """Every binary the check recipes run through `mise x --` or `mise exec ... --`."""
    found: set[str] = set()
    for name in CHECK_RECIPES:
        found |= set(
            re.findall(r"mise (?:x|exec)(?: [^\n]*?)? -- ([\w.-]+)", recipe_body(name))
        )
    return found


def baked_tools() -> dict[str, object]:
    m = re.search(
        r"cat > /etc/mise/config.toml <<'EOF'\n(.*?)\nEOF", INSTALL.read_text(), re.S
    )
    assert m, "install.sh must bake /etc/mise/config.toml"
    return tomllib.loads(m.group(1))["tools"]


def binary_of(tool: str, spec: object) -> str:
    """The command a mise tool entry puts on PATH."""
    if isinstance(spec, dict) and "exe" in spec:
        return str(spec["exe"])
    return tool.split(":", 1)[-1].rsplit("/", 1)[-1]


def test_the_scan_sees_the_tools_it_should() -> None:
    assert {
        "quint",
        "golangci-lint",
        "go",
        "shellcheck",
        "markdownlint-cli2",
    } <= tools_just_check_runs()


def test_every_tool_just_check_runs_is_in_the_sandbox_image() -> None:
    have = {binary_of(tool, spec) for tool, spec in baked_tools().items()} | APT_TOOLS
    missing = tools_just_check_runs() - have
    assert missing == set(), (
        f"`just check` runs {sorted(missing)} through mise, but the sandbox image "
        "neither bakes them into /etc/mise/config.toml nor installs them with apt"
    )


def test_quint_is_baked_at_the_same_pin_as_the_workstation() -> None:
    # A checker under a mandatory gate changes its verdicts only deliberately:
    # the sandbox runs the version the workstation does (ADR 0006 parity).
    baked = baked_tools()
    workstation = tomllib.loads(GLOBAL_MISE.read_text())["tools"]
    key = "npm:@informalsystems/quint"
    assert key in workstation
    assert baked.get(key) == workstation[key]


def assignment(name: str) -> str:
    m = re.search(rf'^{name}="([^"]*)"', INSTALL.read_text(), re.M)
    assert m, f"install.sh must set {name}"
    return m.group(1)


def test_quints_evaluator_is_built_from_a_pinned_commit() -> None:
    # `quint run` and `quint test` execute on a Rust evaluator that quint
    # downloads on first use, and its Linux release binaries need GLIBC_2.39;
    # the image is bookworm (2.36). So the image builds that release from
    # source, pinned to the tag's commit and its Cargo.lock, into the path
    # quint checks before it downloads anything.
    script = INSTALL.read_text()
    assert re.fullmatch(r"[0-9a-f]{40}", assignment("QUINT_EVALUATOR_REV"))
    assert re.fullmatch(r"v\d+\.\d+\.\d+", assignment("QUINT_EVALUATOR_VERSION"))
    assert "cargo build --release --locked" in script
    assert (
        '"${QUINT_HOME}/rust-evaluator-${QUINT_EVALUATOR_VERSION}/quint_evaluator"'
        in script
    )


def test_quint_home_is_outside_the_home_directory() -> None:
    # Coder binds the user's home over /root (ADR 0006), which would hide an
    # evaluator baked into ~/.quint, and quint would then download one that
    # cannot run on this glibc.
    m = re.search(
        r"cat > /etc/profile.d/dotfiles-mise.sh <<'PROFILE'\n(.*?)\nPROFILE",
        INSTALL.read_text(),
        re.S,
    )
    assert m, "install.sh must write /etc/profile.d/dotfiles-mise.sh"
    assert re.search(r"^export QUINT_HOME=/opt/quint$", m.group(1), re.M)
    assert re.search(r'"QUINT_HOME":\s*"/opt/quint"', DEVCONTAINER.read_text())
