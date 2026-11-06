"""Cloud profile lists stay local and preserve CLI failures.

Execute the real justfile with offline CLI stubs and an isolated HOME/PATH;
no cloud credentials or services are needed. Static checks also run on Windows.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = [
    ("alibaba-list", "aliyun", ["configure", "list"]),
    ("akamai-list", "linode-cli", ["show-users"]),
]


@pytest.mark.parametrize("recipe,cli,args", COMMANDS)
def test_cloud_list_recipe_is_local_and_in_cloud_group(
    recipe: str, cli: str, args: list[str]
) -> None:
    text = (ROOT / "justfile").read_text(encoding="utf-8")
    command = " ".join([cli, *args])
    expected = f"[group('Cloud')]\n{recipe}:\n    {command}\n"
    assert expected in text
    body = re.search(
        rf"^{re.escape(recipe)}:\n((?:[ \t]+[^\n]*\n)+)", text, re.MULTILINE
    )
    assert body is not None
    assert body.group(1).strip() == command


@pytest.mark.skipif(sys.platform == "win32", reason="CLI stubs use POSIX shell scripts")
@pytest.mark.parametrize("recipe,cli,args", COMMANDS)
@pytest.mark.parametrize("exit_code", [0, 17], ids=["success", "cli-failure"])
def test_cloud_list_dispatch_and_failure_propagation(
    tmp_path: Path, recipe: str, cli: str, args: list[str], exit_code: int
) -> None:
    just = shutil.which("just")
    if just is None:
        pytest.skip("just unavailable")
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copyfile(ROOT / "justfile", repo / "justfile")
    home = tmp_path / "home"
    home.mkdir()
    stubs = tmp_path / "bin"
    stubs.mkdir()
    calls = tmp_path / "calls"
    for name in ("aliyun", "linode-cli"):
        stub = stubs / name
        stub.write_text(
            "#!/bin/sh\nset -eu\n"
            'printf "%s\\n" "${0##*/}" "$@" > "$CLOUD_TEST_CALLS"\n'
            'printf "test-profile\\n"\n'
            'if [ "$CLOUD_TEST_EXIT" -ne 0 ]; then\n'
            '  printf "test-cli-failed\\n" >&2\n'
            "fi\n"
            'exit "$CLOUD_TEST_EXIT"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
    result = subprocess.run(
        [just, "--justfile", str(repo / "justfile"), recipe],
        cwd=repo,
        env={
            "PATH": os.pathsep.join([str(stubs), "/usr/bin", "/bin"]),
            "HOME": str(home),
            "CLOUD_TEST_CALLS": str(calls),
            "CLOUD_TEST_EXIT": str(exit_code),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
    )
    assert calls.is_file(), result.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == [cli, *args]
    assert result.stdout == "test-profile\n"
    assert result.returncode == exit_code, result.stderr
    if exit_code:
        assert "test-cli-failed" in result.stderr
    assert list(home.iterdir()) == []
