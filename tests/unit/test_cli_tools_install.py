"""Shared CLI tool pins and checkout-scoped installer contracts."""

import os
import shutil
import subprocess
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
