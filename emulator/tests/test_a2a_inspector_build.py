import re
from pathlib import Path

# The inspector is the Go rewrite (a2aproject/a2a-inspector#221, v0.2.0): one
# static binary with the UI embedded. This Dockerfile repeats upstream's build
# stages so the base images stay pinned here and under Dependabot, and the
# default ref is a commit, not a moving branch: a branch default broke the
# build the day upstream changed its layout.
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_COMPOSE_REF = re.compile(r"A2A_INSPECTOR_REF: \$\{A2A_INSPECTOR_REF:-([^}]+)\}")
_DOCKERFILE_REF = re.compile(r"^ARG A2A_INSPECTOR_REF=(\S+)$", re.MULTILINE)


def _instructions() -> str:
    """The Dockerfile without its comment lines."""
    return "\n".join(
        line
        for line in Path("a2a-inspector/Dockerfile")
        .read_text(encoding="utf-8")
        .splitlines()
        if not line.lstrip().startswith("#")
    )


def _compose_service() -> str:
    """The a2a-inspector service block of compose.yaml."""
    text = Path("compose.yaml").read_text(encoding="utf-8")
    start = text.index("\n  a2a-inspector:\n")
    end = re.compile(r"\n  [a-z0-9-]+:\n").search(text, start + 1)
    assert end, "a2a-inspector should not be the last service"
    return text[start : end.start()]


def test_a2a_inspector_builds_the_go_binary() -> None:
    instructions = _instructions()
    assert "FROM python" not in instructions, "the Python inspector is retired"
    assert "go build" in instructions
    assert "-o /a2a-inspector" in instructions


def test_a2a_inspector_listens_on_all_interfaces_inside_the_container() -> None:
    # The binary listens on 127.0.0.1 by default, which the published port
    # cannot reach from outside the container.
    entrypoint = re.search(r"^ENTRYPOINT (\[.*\])$", _instructions(), re.MULTILINE)
    assert entrypoint, "the runtime stage should set an ENTRYPOINT"
    for arg in ('"--host", "0.0.0.0"', '"--port", "8080"', '"--no-open"'):
        assert arg in entrypoint.group(1), arg


def test_compose_does_not_health_check_with_a_missing_curl() -> None:
    # The runtime image is distroless (no shell, no curl); readiness is checked
    # from the host by scripts/wait-for-services.sh instead.
    assert "distroless" in _instructions()
    settings = [
        line
        for line in _compose_service().splitlines()
        if not line.lstrip().startswith("#")
    ]
    assert not [line for line in settings if "curl" in line], settings


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
    instructions = _instructions()
    assert "--branch" not in instructions
    assert 'fetch --depth 1 origin "${A2A_INSPECTOR_REF}"' in instructions


def test_docker_compose_uses_local_a2a_inspector_context() -> None:
    assert "context: ./a2a-inspector" in _compose_service(), (
        "compose.yaml should build a2a-inspector from the local Dockerfile, "
        "whose base images are pinned and kept current by Dependabot"
    )
