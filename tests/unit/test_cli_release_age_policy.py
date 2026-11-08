"""Permanent CLI exceptions never become global or project exemptions."""

import shlex
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NPM_CLIS = {
    "vp": "latest",
    "markdownlint-cli2": "latest",
    "npm:portless": "0.15.9",
    "npm:@informalsystems/quint": "0.33.0",
    "npm:@openai/codex": "latest",
    "npm:@anthropic-ai/claude-code": "latest",
    "npm:@github/copilot": "latest",
    "npm:@earendil-works/pi-coding-agent": "latest",
    "npm:@playwright/cli": "latest",
    "npm:cf": "1.0.0-beta.20",
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


def test_native_mise_just_uv_and_deferred_lsp_settings_are_preserved() -> None:
    cfg = config()
    assert cfg["settings"]["minimum_release_age"] == "0d"
    assert cfg["settings"]["npm"]["package_manager"] == "bun"
    assert cfg["tools"]["just"] == cfg["tools"]["uv"] == "latest"
    assert cfg["tools"]["npm:typescript-language-server"] == "latest"
    assert cfg["tools"]["go:golang.org/x/tools/gopls"] == "latest"
    assert cfg["env"] == {
        "RTK_TELEMETRY_DISABLED": "1",
        "HEADROOM_BEACON": "off",
        "DO_NOT_TRACK": "1",
    }
    assert (
        not {"UV_EXCLUDE_NEWER", "BUN_CONFIG_MINIMUM_RELEASE_AGE"} & cfg["env"].keys()
    )


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        "emulator/pyproject.toml",
        "tools/rttm/pyproject.toml",
        "telemetry/examples/pyproject.toml",
    ],
)
def test_repository_dependency_quarantine_stays_local_and_seven_days(path: str) -> None:
    uv = tomllib.loads((ROOT / path).read_text(encoding="utf-8"))["tool"]["uv"]
    assert uv["exclude-newer"] == "7 days"
    assert uv.get("exclude-newer-package", {}).get("pytest") is not False
