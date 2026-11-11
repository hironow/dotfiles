"""The local telemetry stack is one upstream grafana/otel-lgtm container.

ADR 0072: dotfiles keeps no collector, backend, or Grafana config of its own,
no dashboards, and no example app. These tests read telemetry/compose.yaml as
text (the unit gate has no YAML parser) and check that the files around it
(lint scopes, docs, CI triggers, Dependabot) follow the same stack.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY = ROOT / "telemetry"

# The ports grafana/otel-lgtm exposes: Grafana, Tempo, Pyroscope, OTLP gRPC,
# OTLP HTTP, Prometheus. The owner chose to publish them on the same numbers.
LGTM_PORTS = {3000, 3200, 4040, 4317, 4318, 9090}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _top_level(text: str) -> dict[str, str]:
    """Each top-level key's block of a two-space indented YAML file."""
    parts = re.split(r"^([a-z]+):\n", text, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def _list(block: str, key: str, indent: int) -> list[str]:
    """The items of the list `key:` at `indent` spaces, quotes removed."""
    pad = " " * indent
    found = re.search(rf"^{pad}{key}:\n((?:{pad}  - .*\n)+)", block, flags=re.MULTILINE)
    if not found:
        return []
    items = re.findall(rf"^{pad}  - (.*?)\s*(?:#.*)?$", found[1], re.MULTILINE)
    return [item.strip('"') for item in items]


def _services() -> dict[str, str]:
    section = _top_level(_read(TELEMETRY / "compose.yaml"))["services"]
    parts = re.split(r"^  ([\w-]+):\n", section, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def _published_ports() -> set[int]:
    ports = set()
    for service in _services().values():
        for entry in _list(service, "ports", 4):
            found = re.fullmatch(r"127\.0\.0\.1:(\d+):(\d+)", entry)
            assert found, f"publish on 127.0.0.1 only, as host:container: {entry}"
            ports.add(int(found[1]))
    return ports


def test_compose_runs_one_pinned_lgtm_container() -> None:
    services = _services()
    assert list(services) == ["lgtm"]
    images = re.findall(r"^    image: (\S+)$", services["lgtm"], re.MULTILINE)
    assert len(images) == 1
    assert re.fullmatch(r"docker\.io/grafana/otel-lgtm:\d+\.\d+\.\d+", images[0]), (
        f"pin a released version with the full registry name, not {images[0]}"
    )


def test_compose_publishes_the_lgtm_ports_on_the_same_numbers_on_loopback() -> None:
    entries = _list(_services()["lgtm"], "ports", 4)
    assert len(entries) == len(LGTM_PORTS)
    for entry in entries:
        found = re.fullmatch(r"127\.0\.0\.1:(\d+):(\d+)", entry)
        assert found, f"publish on 127.0.0.1 only: {entry}"
        assert found[1] == found[2], f"keep lgtm's port number on the host: {entry}"
    assert _published_ports() == LGTM_PORTS


def test_compose_keeps_upstream_config_and_one_named_data_volume() -> None:
    text = _read(TELEMETRY / "compose.yaml")
    assert not re.search(r"^\s+- \.{1,2}/", text, re.MULTILINE), (
        "no bind mounts: dotfiles keeps no config files for the stack"
    )
    assert _list(_services()["lgtm"], "volumes", 4) == ["lgtm-data:/data"]
    assert re.findall(r"^  ([\w-]+):", _top_level(text)["volumes"], re.MULTILINE) == [
        "lgtm-data"
    ]


def test_compose_declares_the_upstream_healthcheck() -> None:
    # Podman may drop an image's HEALTHCHECK; the isolated run waits on health.
    lgtm = _services()["lgtm"]
    assert re.search(
        r'^    healthcheck:\n      test: \["CMD", "/otel-lgtm/docker/healthcheck\.sh"\]\n',
        lgtm,
        re.MULTILINE,
    )
    assert re.search(r"^      interval: \d+s$", lgtm, re.MULTILINE)


def test_compose_joins_the_shared_network_as_its_default() -> None:
    # tests.utils.isolation rewrites networks.default to the run's own network.
    networks = _top_level(_read(TELEMETRY / "compose.yaml"))["networks"]
    assert networks == "  default:\n    name: shared-otel-net\n    external: true\n"


def test_telemetry_tracks_only_compose_readme_and_env_ignore() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "telemetry"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.split()
    assert sorted(tracked) == [
        "telemetry/.gitignore",
        "telemetry/README.md",
        "telemetry/compose.yaml",
    ]


def test_env_files_next_to_the_compose_file_stay_untracked() -> None:
    # podman-compose reads telemetry/.env; upstream puts OTLP auth headers there.
    result = subprocess.run(
        ["git", "check-ignore", "telemetry/.env", "telemetry/.env.local"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.stdout.split() == ["telemetry/.env", "telemetry/.env.local"]


def test_root_lint_covers_telemetry() -> None:
    justfile = _read(ROOT / "justfile")
    assert "':!telemetry'" not in justfile
    ruff = tomllib.loads(_read(ROOT / "pyproject.toml"))["tool"]["ruff"]
    assert "telemetry" not in ruff["extend-exclude"]
    markdownlint = _read(ROOT / ".markdownlint-cli2.yaml")
    assert not re.search(r"^\s*- telemetry/", markdownlint, re.MULTILINE)
    precommit = _read(ROOT / ".pre-commit-config.yaml")
    assert not re.search(r"^\s*telemetry/\|", precommit, re.MULTILINE)


def test_tel_down_also_removes_containers_of_an_older_stack() -> None:
    # After a pull, compose knows only lgtm; the old five would keep 4317/4318.
    recipe = re.search(
        r"^tel-down:\n((?:    .*\n)+)", _read(ROOT / "justfile"), re.MULTILINE
    )
    assert recipe
    assert "{{PODMAN_COMPOSE}} down --remove-orphans" in recipe[1]


def test_portless_telemetry_aliases_use_published_ports() -> None:
    doc = _read(ROOT / "docs" / "portless-urls.md")
    section = re.search(
        r"^# telemetry \(telemetry/compose\.yaml\)\n((?:portless alias .*\n)+)",
        doc,
        re.MULTILINE,
    )
    assert section, "docs/portless-urls.md lost its telemetry section"
    ports = {
        int(p)
        for p in re.findall(r"^portless alias \S+ (\d+) ", section[1], re.MULTILINE)
    }
    assert ports
    assert ports <= _published_ports()


def test_observability_spoke_points_at_published_ports_and_the_lgtm_name() -> None:
    spoke = _read(ROOT / "ROOT_AGENTS_docs_agents_observability.md")
    shared = spoke.split("**First choice", 1)[1].split("**Alternative", 1)[0]
    ports = {int(p) for p in re.findall(r"localhost:(\d+)", shared)}
    assert ports
    assert ports <= _published_ports()
    assert "lgtm:4317" in shared
    assert "otel-collector" not in spoke


def test_emulator_ci_runs_when_telemetry_changes() -> None:
    # The isolated CI run starts telemetry/compose.yaml (`--telemetry`).
    body = _read(ROOT / ".github" / "workflows" / "test-emulators.yaml")
    assert body.count("      - 'telemetry/**'\n") == 2
    assert body.count("      - '!telemetry/**/*.md'\n") == 2


def test_dependabot_bumps_the_lgtm_tag_after_a_cooldown() -> None:
    config = _read(ROOT / ".github" / "dependabot.yaml")
    entries = re.split(r"^  - package-ecosystem: ", config, flags=re.MULTILINE)[1:]
    compose = [e for e in entries if e.startswith('"docker-compose"')]
    assert len(compose) == 1
    assert re.search(r'^    directory: "/telemetry"$', compose[0], re.MULTILINE)
    assert re.search(r"^      default-days: 7$", compose[0], re.MULTILINE)
    assert "/telemetry/examples" not in config
