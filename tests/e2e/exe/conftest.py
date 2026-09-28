"""Fixtures for the exe stack's end-to-end tests; the harness is exe_live.py.

Every test here is skipped unless EXE_E2E=1: `just exe-e2e` runs them.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from exe_live import Exe, leave_asleep, log


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if os.environ.get("EXE_E2E") == "1":
        return
    here = Path(__file__).parent
    skip = pytest.mark.skip(reason="live exe e2e: EXE_E2E=1 (just exe-e2e) runs it")
    for item in items:
        if item.path.is_relative_to(here):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def out_dir() -> Path:
    configured = os.environ.get("EXE_E2E_OUT")
    path = Path(configured) if configured else Path(tempfile.mkdtemp(prefix="exe-e2e-"))
    path.mkdir(parents=True, exist_ok=True)
    log(f"measurements go to {path / 'measurements.jsonl'}")
    return path


# Module-scoped: a module is one scenario on the node, and its end, pass or
# fail, is where the pool goes back to 0.
@pytest.fixture(scope="module")
def exe(out_dir: Path) -> Iterator[Exe]:
    image = os.environ.get("EXE_E2E_IMAGE", "")
    if "@sha256:" not in image:
        pytest.fail(
            "EXE_E2E_IMAGE must be a task image pinned by digest (`just exe-image` prints one)"
        )
    kubeconfig = os.environ.get("KUBECONFIG") or str(
        Path.home() / ".config" / "exe" / "kubeconfig"
    )
    e = Exe(image=image, out=out_dir, kubeconfig=kubeconfig)
    try:
        yield e
    finally:
        leave_asleep(e)
