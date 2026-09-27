"""The exe task image is amd64 and built only from pinned inputs.

docker/exe-task.Dockerfile is upstream ax's Dockerfile.task-runner contract
(the runner at /usr/local/bin/ax-task-runner, python + antigravity for its
workspace bootstrap) plus the agent CLIs, built by Cloud Build in the private
project from exe/ax/cloudbuild.yaml (`just exe-image`).

The node is e2 (amd64) and every task pod pulls this image under gVisor, so an
arm64 image, or one that silently picked up a moved tag, fails on the worker
rather than here. These tests hold the build to linux/amd64 and every input to
an exact pin: base images by digest, the Claude binary by version and sha256,
python packages by version, Debian packages through a dated snapshot.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILE = _REPO_ROOT / "docker" / "exe-task.Dockerfile"
_CLOUDBUILD = _REPO_ROOT / "exe" / "ax" / "cloudbuild.yaml"
_JUSTFILE = _REPO_ROOT / "justfile"

_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def _instructions(path: Path) -> list[str]:
    """Dockerfile instructions with continuation lines joined, comments dropped."""
    joined: list[str] = []
    current = ""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not current and (not line or line.startswith("#")):
            continue
        if line.endswith("\\"):
            current += line[:-1] + " "
            continue
        joined.append(current + line)
        current = ""
    return joined


def _image_refs(instructions: list[str]) -> list[str]:
    """Every image a FROM or COPY --from names (stage names excluded)."""
    stages: set[str] = set()
    refs: list[str] = []
    for ins in instructions:
        words = ins.split()
        if words[0].upper() == "FROM":
            args = [w for w in words[1:] if not w.startswith("--")]
            refs.append(args[0])
            if len(args) >= 3 and args[1].upper() == "AS":
                stages.add(args[2])
        elif words[0].upper() == "COPY":
            for w in words[1:]:
                if w.startswith("--from="):
                    ref = w.split("=", 1)[1]
                    if ref not in stages:
                        refs.append(ref)
    return refs


def test_every_image_the_dockerfile_uses_is_pinned_by_digest() -> None:
    refs = _image_refs(_instructions(_DOCKERFILE))
    assert refs, "no FROM found"
    unpinned = [r for r in refs if not _DIGEST.search(r)]
    assert unpinned == [], f"images not pinned by digest: {unpinned}"


def test_the_runner_sits_where_ax_starts_it() -> None:
    text = _DOCKERFILE.read_text()
    assert re.search(
        r"^COPY\s+ax-task-runner\s+/usr/local/bin/ax-task-runner$", text, re.MULTILINE
    )
    assert 'ENTRYPOINT ["/usr/local/bin/ax-task-runner"]' in text


def test_the_claude_binary_is_a_pinned_version_checked_by_sha256() -> None:
    text = _DOCKERFILE.read_text()
    assert re.search(r"^ARG CLAUDE_CODE_VERSION=\d+\.\d+\.\d+$", text, re.MULTILINE)
    assert re.search(r"^ARG CLAUDE_CODE_SHA256=[0-9a-f]{64}$", text, re.MULTILINE)
    assert "sha256sum -c" in text


def test_python_packages_are_pinned_by_version() -> None:
    installs = [i for i in _instructions(_DOCKERFILE) if "pip install" in i]
    assert installs, "the antigravity bootstrap needs its python package"
    for ins in installs:
        packages = [
            w for w in ins.split("pip install", 1)[1].split() if not w.startswith("-")
        ]
        assert packages and all("==" in p for p in packages), ins


def test_debian_packages_come_from_a_dated_snapshot() -> None:
    text = _DOCKERFILE.read_text()
    assert re.search(r"^ARG DEBIAN_SNAPSHOT=\d{8}T\d{6}Z$", text, re.MULTILINE)
    assert "snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}" in text


def test_cloud_build_builds_linux_amd64_with_a_pinned_builder() -> None:
    text = _CLOUDBUILD.read_text()
    assert "--platform=linux/amd64" in text
    builders = re.findall(r"^\s*-?\s*name:\s*(\S+)", text, re.MULTILINE)
    assert builders and all(_DIGEST.search(b) for b in builders), builders


def test_cloud_build_logs_to_cloud_logging_only() -> None:
    assert re.search(
        r"^\s+logging:\s+CLOUD_LOGGING_ONLY$", _CLOUDBUILD.read_text(), re.MULTILINE
    )


def test_exe_image_stages_in_the_bounded_bucket_as_the_build_sa_and_checks_amd64() -> (
    None
):
    body = _JUSTFILE.read_text().split("\nexe-image:", 1)[1].split("\n\n", 1)[0]
    assert "--gcs-source-staging-dir" in body and "bucket_build" in body
    assert "--service-account" in body
    assert "exe/ax/cloudbuild.yaml" in body
    # After the push: the manifest must be linux/amd64, and the ref printed by
    # a sha256 digest read back from the registry.
    assert '"$platform" != "linux/amd64"' in body
    assert "sha256:*)" in body and '"${tag}@${digest}"' in body
