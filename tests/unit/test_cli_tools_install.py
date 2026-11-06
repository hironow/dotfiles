"""Shared CLI tool pins and checkout-scoped installer contracts."""

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "config/mise/config.toml"
TOOLS = [
    ("hunk", "hunk"),
    ("ripgrep", "rg"),
    ("fd", "fd"),
    ("sd", "sd"),
    ("github:harehare/mq", "mq"),
    ("witr", "witr"),
    ("aqua:jqlang/jq", "jq"),
    ("aqua:mikefarah/yq", "yq"),
    ("aqua:wader/fq", "fq"),
]


@pytest.mark.parametrize(
    ("tool", "version"),
    [
        ("github:harehare/mq", "0.10.0"),
        ("witr", "0.3.4"),
        ("aqua:jqlang/jq", "1.8.2"),
        ("aqua:mikefarah/yq", "4.54.1"),
        ("aqua:wader/fq", "0.18.0"),
    ],
)
def test_requested_cli_tools_have_exact_pins(tool: str, version: str) -> None:
    tools = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["tools"]
    pin = tools[tool]
    assert (pin["version"] if isinstance(pin, dict) else pin) == version


def test_mq_is_platform_scoped_and_every_raw_asset_has_a_checksum() -> None:
    mq = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["tools"][
        "github:harehare/mq"
    ]
    assert set(mq["os"]) == {
        "macos/arm64",
        "linux/x64",
        "linux/arm64",
        "windows/x64",
        "windows/arm64",
    }
    assert mq["rename_exe"] == "mq"
    assets = {
        "macos-arm64": "mq-aarch64-apple-darwin",
        "linux-x64": "mq-x86_64-unknown-linux-gnu",
        "linux-arm64": "mq-aarch64-unknown-linux-gnu",
        "windows-x64": "mq-x86_64-pc-windows-msvc.exe",
        "windows-arm64": "mq-aarch64-pc-windows-msvc.exe",
    }
    assert set(mq["platforms"]) == {target.replace("/", "-") for target in mq["os"]}
    for platform, options in mq["platforms"].items():
        # Host-expanded os()/arch() templates produce incorrect cross-platform
        # locks; explicit platform assets also exclude helper CLIs and packages.
        assert options["asset_pattern"] == assets[platform]
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", options["checksum"])


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell stub and symlink fixture")
@pytest.mark.parametrize(
    ("include_mq", "fail_at"),
    [
        (include, failure)
        for include, count in [(True, len(TOOLS) + 1), (False, len(TOOLS))]
        for failure in range(count + 1)
    ],
)
def test_actual_installer_dispatch_and_failure_propagation(
    tmp_path: Path, include_mq: bool, fail_at: int
) -> None:
    just = shutil.which("just")
    if not just:
        pytest.skip("just is not installed")
    home = tmp_path / "empty home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("bash", "env"):
        executable = shutil.which(name)
        assert executable
        (bin_dir / name).symlink_to(Path(executable).resolve())
    stub = bin_dir / "mise"
    stub.write_text(
        "#!/bin/sh\n"
        'printf "%s" "$MISE_GLOBAL_CONFIG_FILE" >> "$CALL_LOG"\n'
        'printf "\\t%s" "$@" >> "$CALL_LOG"\n'
        'printf "\\n" >> "$CALL_LOG"\n'
        "count=0\n"
        'if [ -f "$COUNT_FILE" ]; then read -r count < "$COUNT_FILE"; fi\n'
        "count=$((count + 1))\n"
        'printf "%s\\n" "$count" > "$COUNT_FILE"\n'
        'if [ "$count" -eq "$FAIL_AT" ]; then exit 17; fi\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    log = tmp_path / "calls.tsv"
    result = subprocess.run(
        [
            just,
            "--justfile",
            str(REPO / "justfile"),
            "--set",
            "CLI_TOOLS_MQ",
            "github:harehare/mq" if include_mq else "",
            "cli-tools-install",
        ],
        cwd=tmp_path,
        env={
            "HOME": str(home),
            "PATH": str(bin_dir),
            "CALL_LOG": str(log),
            "COUNT_FILE": str(tmp_path / "count"),
            "FAIL_AT": str(fail_at),
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    assert result.returncode == (17 if fail_at else 0), result.stdout + result.stderr
    selected = [
        (tool, binary) for tool, binary in TOOLS if include_mq or binary != "mq"
    ]
    commands = [["install", *[tool for tool, _ in selected]]]
    commands.extend(
        ["exec", tool, "--", binary, "--version"] for tool, binary in selected
    )
    expected = [[str(CONFIG), "-C", "/", *command] for command in commands]
    assert [
        line.split("\t") for line in log.read_text(encoding="utf-8").splitlines()
    ] == (expected[:fail_at] if fail_at else expected)
    if not include_mq and not fail_at:
        assert "mq unavailable" in result.stdout


def test_mac_homebrew_restore_does_not_reinstall_mise_jq() -> None:
    manifest = (REPO / "dump/macbook/Brewfile").read_text(encoding="utf-8")
    formula = re.compile(r"""^\s*brew\s*(?:\(\s*)?["']jq["']""", re.MULTILINE)
    assert not formula.search(manifest)


def test_agent_router_exposes_each_structured_query_branch() -> None:
    hub = (REPO / "ROOT_AGENTS.md").read_text(encoding="utf-8")
    spoke = (REPO / "ROOT_AGENTS_docs_agents_cli-tools.md").read_text(encoding="utf-8")
    for tool in ("jq", "yq", "mq", "fq", "witr"):
        assert f"`{tool}`" in hub
        assert f"`{tool}`" in spoke
