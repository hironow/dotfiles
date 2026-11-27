"""Permanent CLI exceptions never become global or project exemptions."""

import re
import shlex
import subprocess
import tomllib
from pathlib import Path

import pytest
from _zsh_startup import run_zsh

ROOT = Path(__file__).resolve().parents[2]
NPM_CLIS = {
    "vp": "latest",
    "markdownlint-cli2": "latest",
    "npm:portless": "0.17.0",
    "npm:@informalsystems/quint": "0.33.0",
    "npm:@openai/codex": "latest",
    "npm:@anthropic-ai/claude-code": "latest",
    "npm:@github/copilot": "latest",
    "npm:@earendil-works/pi-coding-agent": "latest",
    "npm:@playwright/cli": "latest",
    "npm:cf": "1.0.0-beta.30",
    "npm:resend-cli": "latest",
    "npm:@stripe/cli": "latest",
    "npm:@dataform/cli": "latest",
}


def config() -> dict:
    return tomllib.loads((ROOT / "config/mise/config.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,version", NPM_CLIS.items())
def test_permanent_npm_cli_dependencies_have_scoped_zero_age(
    name: str, version: str
) -> None:
    spec = config()["tools"][name]
    assert spec["version"] == version
    assert shlex.split(spec["bun_args"]) == ["--minimum-release-age=0"]
    assert "npm_args" not in spec


@pytest.mark.parametrize("docker_host", [None, "unix:///operator-selected.sock"])
def test_shell_provider_preserves_engine_selection(
    tmp_path: Path, docker_host: str | None
) -> None:
    output = run_zsh(
        tmp_path,
        r"""
source "$1"
print -r -- "$PODMAN_COMPOSE_PROVIDER|${DOCKER_HOST-unset}"
""",
        docker_host=docker_host,
    )
    assert output.strip() == f"podman-compose|{docker_host or 'unset'}"


def test_podman_compose_has_a_dedicated_zero_age_cli_environment() -> None:
    spec = config()["tools"].get("pypi:podman-compose")
    assert isinstance(spec, dict), (
        "required Compose provider needs a dedicated mise tool"
    )
    assert spec["version"] == "1.6.0"
    assert shlex.split(spec["uvx_args"]) == [
        "--python",
        "3.13",
        "--exclude-newer",
        "0d",
    ]


def test_colab_cli_has_a_dedicated_zero_age_environment_and_skips_windows() -> None:
    # The owner exempts the Colab CLI like headroom and podman-compose: only its
    # dedicated uv tool environment. Upstream supports Linux and macOS only.
    spec = config()["tools"].get("pypi:google-colab-cli")
    assert isinstance(spec, dict), "the Colab CLI needs a dedicated mise tool"
    assert spec["version"] == "0.8.0"
    assert shlex.split(spec["uvx_args"]) == [
        "--python",
        "3.13",
        "--exclude-newer",
        "0d",
    ]
    assert spec["os"] == ["linux", "macos"]


def test_headroom_whole_dedicated_environment_not_only_top_package_is_exempt() -> None:
    spec = config()["tools"]["pypi:headroom-ai"]
    assert spec["version"] == "0.41.0"
    assert spec["extras"] == "proxy,code"
    assert shlex.split(spec["uvx_args"]) == [
        "--python",
        "3.13",
        "--exclude-newer",
        "0d",
    ]


def _tracked_uv_projects() -> list[str]:
    return sorted(
        subprocess.run(
            ["git", "ls-files", "*pyproject.toml"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout.split()
    )


def test_every_exclude_newer_check_lists_each_tracked_uv_project() -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    calls = re.findall(r"check_uv_exclude_newer\.py ([^\n]+)", justfile)
    assert calls
    for call in calls:
        assert sorted(call.split()) == _tracked_uv_projects()


@pytest.mark.parametrize("path", _tracked_uv_projects())
def test_repository_dependency_quarantine_stays_local_and_seven_days(path: str) -> None:
    uv = tomllib.loads((ROOT / path).read_text(encoding="utf-8"))["tool"]["uv"]
    assert uv["exclude-newer"] == "7 days"
    assert uv.get("exclude-newer-package", {}).get("pytest") is not False
