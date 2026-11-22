"""Every pull request checks what the sandbox would refuse to copy.

The dev container tests copy every tracked file into a snapshot and refuse a
tracked symlink, a junction, or a reserved name before the container starts
(tests/test_just_sandbox.py). They run on a pull request only when it changes
something outside the directories `test-just.yaml` ignores (ADR-0089), so a
symlink added under `docs/` would be found only on main. This runs the same
validation, without the copy, on every pull request and every OS shard.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _sandbox() -> Any:
    # Loaded under its own name, as tests/unit/test_sandbox_mount_fence.py does,
    # so pytest's own collection of that file is untouched.
    spec = importlib.util.spec_from_file_location(
        "just_sandbox_for_inputs", ROOT / "tests" / "test_just_sandbox.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_checkout_has_nothing_the_snapshot_refuses() -> None:
    files = _sandbox()._tracked_files(str(ROOT))
    assert files, "no tracked file was read"


@pytest.mark.skipif(
    sys.platform == "win32", reason="symlinks need privileges on Windows"
)
def test_a_tracked_symlink_is_refused(tmp_path: Path) -> None:
    git = ["git", "-C", str(tmp_path)]
    subprocess.run([*git, "init", "-q"], check=True)
    (tmp_path / "real.md").write_text("x\n", encoding="utf-8")
    (tmp_path / "link.md").symlink_to("real.md")
    subprocess.run([*git, "add", "real.md", "link.md"], check=True)
    with pytest.raises(RuntimeError, match="symlink"):
        _sandbox()._tracked_files(str(tmp_path))
