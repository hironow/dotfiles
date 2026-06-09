# Test fixture for agentcore-python-no-os-path.
import os.path  # noqa
from pathlib import Path


def build_path_bad(root: str, name: str) -> str:
    # ruleid: agentcore-python-no-os-path
    return os.path.join(root, name)


def build_path_good(root: str, name: str) -> Path:
    # ok: agentcore-python-no-os-path
    return Path(root) / name
