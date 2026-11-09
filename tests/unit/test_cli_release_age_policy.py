"""Permanent CLI exceptions never become global or project exemptions."""

import re
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


def test_installer_image_provisions_native_podman_before_nonroot_setup() -> None:
    dockerfile = (ROOT / "tests/docker/InstallTest.Dockerfile").read_text(
        encoding="utf-8"
    )
    root_stage = dockerfile.split("USER testuser", 1)[0]
    for package in ("podman", "netavark", "aardvark-dns", "uidmap", "fuse-overlayfs"):
        assert package in root_stage
    assert "NOPASSWD" not in dockerfile
    assert dockerfile.count("bash /tmp/dotfiles-repo/install.sh") == 2
    assert "podman-provisioning-calls" in dockerfile
    assert 'exec /usr/bin/podman "$@"' in dockerfile


def test_installer_image_busts_only_setup_cache_and_emits_run_bound_evidence() -> None:
    dockerfile = (ROOT / "tests/docker/InstallTest.Dockerfile").read_text(
        encoding="utf-8"
    )
    nonce = "DOTFILES_INSTALL_ACCEPTANCE_RUN"
    assert f"ARG {nonce}" in dockerfile, "each run must invalidate setup layers"
    first = dockerfile.index("bash /tmp/dotfiles-repo/install.sh")
    second = dockerfile.index("bash /tmp/dotfiles-repo/install.sh", first + 1)
    assert dockerfile.index("USER testuser") < dockerfile.index(f"ARG {nonce}") < first
    assert f'test -n "${nonce}"' in dockerfile[:first]
    pass1 = dockerfile.index("DOTFILES_INSTALL_PASS1:%s")
    pass2 = dockerfile.index("DOTFILES_INSTALL_PASS2:%s")
    final = dockerfile.index("DOTFILES_INSTALL_TRIPWIRE:%s")
    assert first < pass1 < second < pass2 < final
    assert dockerfile.index('test "$(wc -l') < final
    assert dockerfile.index('test "$(sort -u') < final
    for marker in ("PASS1", "PASS2", "TRIPWIRE"):
        assert f"printf 'DOTFILES_INSTALL_{marker}:%s\\n' \"${nonce}\"" in dockerfile


def test_root_readme_documents_native_podman_not_docker_setup() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "install -y docker.io" not in readme
    assert "systemctl enable --now docker" not in readme
    assert " -- docker run " not in readme
    assert "just podman-install" in readme
    assert "podman run --rm -i docker.io/grafana/mcp-k6" in readme


def test_rtk_guidance_preserves_the_native_podman_engine() -> None:
    guidance = (ROOT / "ROOT_AGENTS_docs_agents_rtk.md").read_text(encoding="utf-8")
    assert "never substitute `rtk docker` for Podman" in guidance
    assert "run `podman` directly" in guidance


def test_doctor_checks_required_podman_cli_and_selected_engine() -> None:
    doctor = (ROOT / "scripts/doctor.sh").read_text(encoding="utf-8")
    assert "podman --version" in doctor
    assert "podman info --format" in doctor
    assert "has podman-compose" in doctor
    assert "log_err 'podman'" in doctor
    assert "log_err 'podman-compose'" in doctor
    assert "docker info" not in doctor
    assert "podman machine init" not in doctor
    assert "podman machine start" not in doctor


def test_shell_selects_the_provider_without_probing_or_redirecting_engines() -> None:
    shell = (ROOT / ".zshrc").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in shell.splitlines() if not line.lstrip().startswith("#")
    )
    assert "PODMAN_COMPOSE_PROVIDER=podman-compose" in code
    assert "podman machine inspect" not in code
    assert "DOCKER_HOST=" not in code
    assert ".orbstack" not in code
    assert ".docker/completions" not in code


def test_mac_package_manifest_provisions_podman_without_docker_providers() -> None:
    packages = set(
        re.findall(
            r'^(?:brew|cask) "([^"]+)"',
            (ROOT / "dump/macbook/Brewfile").read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )
    assert "podman" in packages
    assert not packages & {
        "docker",
        "docker-buildx",
        "docker-compose",
        "docker-credential-helper",
        "docker-desktop",
        "orbstack",
    }


def test_devcontainer_cli_has_one_frozen_age_exempt_host_image_pin() -> None:
    expected = {"version": "0.89.0", "bun_args": "--minimum-release-age=0"}
    assert config()["tools"].get("npm:@devcontainers/cli") == expected
    image = tomllib.loads(
        (ROOT / "config/mise/image-tools.toml").read_text(encoding="utf-8")
    )
    assert image["tools"].get("npm:@devcontainers/cli") == expected
    feature = (ROOT / ".devcontainer/features/dotfiles-tools/install.sh").read_text(
        encoding="utf-8"
    )
    generated = re.search(
        r"cat > /etc/mise/config\.toml <<'EOF'\n(.*?)\nEOF", feature, re.DOTALL
    )
    assert generated, "missing generated image configuration"
    assert (
        tomllib.loads(generated.group(1))["tools"].get("npm:@devcontainers/cli")
        == expected
    )


def test_agent_policy_requires_age_exempt_podman_without_docker_fallback() -> None:
    base = (ROOT / "ROOT_AGENTS.md").read_text(encoding="utf-8")
    assert "Podman 5+" in base
    assert "podman-compose" in base
    assert "required installed permanent CLIs" in base
    assert "exempt from the seven-day cooldown" in base
    assert "Never fall back to a Docker engine" in base
    assert "PODMAN_COMPOSE_PROVIDER=podman-compose" in base
    policy = (ROOT / "ROOT_AGENTS_docs_agents_dependency-policy.md").read_text(
        encoding="utf-8"
    )
    permanent = policy.split("## Permanent main CLI exception", 1)[1].split("\n## ", 1)[
        0
    ]
    assert "Podman" in permanent and "podman-compose" in permanent


def test_image_freezes_the_same_age_exempt_compose_provider() -> None:
    expected = {
        "version": "1.6.0",
        "uvx_args": "--python 3.13 --exclude-newer 0d",
    }
    image = tomllib.loads(
        (ROOT / "config/mise/image-tools.toml").read_text(encoding="utf-8")
    )
    assert image["tools"].get("pypi:podman-compose") == expected
    feature = (ROOT / ".devcontainer/features/dotfiles-tools/install.sh").read_text(
        encoding="utf-8"
    )
    generated = re.search(
        r"cat > /etc/mise/config\.toml <<'EOF'\n(.*?)\nEOF", feature, re.DOTALL
    )
    assert generated, "missing generated image configuration"
    assert (
        tomllib.loads(generated.group(1))["tools"].get("pypi:podman-compose")
        == expected
    )


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
    assert spec["version"] == "0.7.5"
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
