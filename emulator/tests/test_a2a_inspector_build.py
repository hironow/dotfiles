import re
from pathlib import Path

# Match the runtime base on Python 3.12, allowing an optional patch pin
# (`python:3.12-slim` or `python:3.12.13-slim`); the Dockerfile pins the patch.
_PY312_SLIM = re.compile(r"^FROM python:3\.12(\.\d+)?-slim\b")


def test_a2a_inspector_dockerfile_uses_python_312() -> None:
    dockerfile_lines = Path("a2a-inspector/Dockerfile").read_text().splitlines()
    assert any(_PY312_SLIM.match(line.strip()) for line in dockerfile_lines), (
        "Expected runtime stage to base on python:3.12(.x)-slim"
    )


def test_docker_compose_uses_local_a2a_inspector_context() -> None:
    compose_text = Path("compose.yaml").read_text()
    assert "context: ./a2a-inspector" in compose_text, (
        "compose.yaml should build a2a-inspector from the local Dockerfile "
        "to ensure Python 3.12 is used"
    )
