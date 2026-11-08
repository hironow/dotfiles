"""Real Podman e2e fixtures. Selected mandatory failures must never skip."""

import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.utils.helpers import (
    RUN_LABEL,
    build_test_image,
    require_running,
    run_manifest,
    run_test_image,
)
from tests.utils.helpers import podman_client as create_podman_client


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    e2e_root = Path(__file__).parent.resolve()
    for item in items:
        if Path(str(item.path)).resolve().is_relative_to(e2e_root):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def e2e_network_name() -> str:
    manifest = run_manifest()
    if not manifest:
        raise RuntimeError("E2E requires an isolated run manifest; see README")
    return manifest["network"]


@pytest.fixture(scope="session")
def podman_client():
    client = create_podman_client()
    yield client
    client.close()


@pytest.fixture
def ensure_network(podman_client, e2e_network_name: str) -> Callable[[], None]:
    def ensure() -> None:
        network = podman_client.networks.get(e2e_network_name)
        assert (
            network.attrs.get("Labels", {}).get(RUN_LABEL) == run_manifest()["run_id"]
        )

    return ensure


@pytest.fixture
def require_services(podman_client) -> Callable[[list[str]], None]:
    return lambda names: require_running(podman_client, names)


@pytest.fixture
def built_images() -> dict[str, str]:
    return {}


@pytest.fixture
def build_image(podman_client, built_images) -> Callable[[str, str], str]:
    def build(path: str, tag: str) -> str:
        image_id = build_test_image(podman_client, path)
        built_images[tag] = image_id
        return image_id

    return build


@pytest.fixture
def run_cli(podman_client, e2e_network_name, built_images):
    def run(image: str, binary: str, script: str, env: dict[str, str]) -> str:
        script = textwrap.dedent(script).lstrip("\n")
        return run_test_image(
            podman_client,
            built_images[image],
            f"cat <<'EOF' | ./{binary}\n{script}\nEOF",
            env,
        )

    return run


@pytest.fixture
def run_shell(podman_client, e2e_network_name, built_images):
    def run(image: str, command: str, env: dict[str, str]) -> str:
        return run_test_image(podman_client, built_images[image], command, env)

    return run
