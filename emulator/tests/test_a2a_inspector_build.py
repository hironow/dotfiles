import re
from pathlib import Path

# Match the runtime base on Python 3.12, allowing an optional patch pin
# (`python:3.12-slim` or `python:3.12.13-slim`); the Dockerfile pins the patch.
_PY312_SLIM = re.compile(r"^FROM python:3\.12(\.\d+)?-slim\b")


def test_a2a_inspector_dockerfile_uses_python_312() -> None:
    dockerfile_lines = (
        Path("a2a-inspector/Dockerfile").read_text(encoding="utf-8").splitlines()
    )
    assert any(_PY312_SLIM.match(line.strip()) for line in dockerfile_lines), (
        "Expected runtime stage to base on python:3.12(.x)-slim"
    )


# The inspector is built from upstream source with this Dockerfile's
# Python/TypeScript layout (backend/, frontend/, pyproject.toml). Upstream
# rewrote it in Go on main (a2aproject/a2a-inspector#221), so the default ref
# is a commit, not a moving branch: a branch default breaks the build the day
# upstream changes its layout.
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_COMPOSE_REF = re.compile(r"A2A_INSPECTOR_REF: \$\{A2A_INSPECTOR_REF:-([^}]+)\}")
_DOCKERFILE_REF = re.compile(r"^ARG A2A_INSPECTOR_REF=(\S+)$", re.MULTILINE)


def test_a2a_inspector_default_ref_is_a_pinned_commit() -> None:
    compose_ref = _COMPOSE_REF.search(Path("compose.yaml").read_text(encoding="utf-8"))
    dockerfile_ref = _DOCKERFILE_REF.search(
        Path("a2a-inspector/Dockerfile").read_text(encoding="utf-8")
    )
    assert compose_ref, "compose.yaml should pass A2A_INSPECTOR_REF with a default"
    assert dockerfile_ref, "the Dockerfile should declare A2A_INSPECTOR_REF"
    assert _COMMIT_SHA.match(compose_ref.group(1)), compose_ref.group(1)
    assert compose_ref.group(1) == dockerfile_ref.group(1)


def test_a2a_inspector_source_fetch_accepts_a_commit() -> None:
    # `git clone --branch` takes only a branch or tag name, never a commit
    instructions = "\n".join(
        line
        for line in Path("a2a-inspector/Dockerfile")
        .read_text(encoding="utf-8")
        .splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "--branch" not in instructions
    assert 'fetch --depth 1 origin "${A2A_INSPECTOR_REF}"' in instructions


def test_docker_compose_uses_local_a2a_inspector_context() -> None:
    compose_text = Path("compose.yaml").read_text(encoding="utf-8")
    assert "context: ./a2a-inspector" in compose_text, (
        "compose.yaml should build a2a-inspector from the local Dockerfile "
        "to ensure Python 3.12 is used"
    )
