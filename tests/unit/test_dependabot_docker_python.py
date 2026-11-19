"""Dependabot keeps every Docker python base image on its minor.

The compiled dependencies of emulator/a2a-inspector (cffi, pydantic-core,
asyncpg) have no wheels for newer Pythons, so a minor bump builds them from
sdist and fails in a slim image. .github/dependabot.yaml ignores minor and
major python updates for the docker ecosystem.

The ignore matches Dependabot's dependency name, not the text of the FROM line.
dependabot-core drops a leading registry (a first component that holds a dot,
docker.io included) and names the dependency by the rest: the FROM
``docker.io/library/python:3.12.15-slim`` is ``library/python``. An ignore of
``python`` alone stopped matching once the FROM lines were fully qualified, and
Dependabot moved the image to 3.15 (PR #652).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPENDABOT = ROOT / ".github" / "dependabot.yaml"

# dependabot-core docker/lib/dependabot/shared/shared_file_parser.rb: REGISTRY
# is a domain of two or more dot-joined components with an optional port.
_REGISTRY = re.compile(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?::\d+)?$")
_FROM = re.compile(
    r"^FROM\s+(?:--platform=\S+\s+)?(?P<ref>\S+)", re.MULTILINE | re.IGNORECASE
)
_SKIPPED_UPDATES = {"version-update:semver-major", "version-update:semver-minor"}


def dependabot_name(reference: str) -> str:
    """The dependency name Dependabot gives an image reference.

    The digest and the tag are dropped: a tag is a colon in the last path
    component (a colon in the first one is a registry port).
    """
    reference = reference.split("@", 1)[0]
    head, slash, last = reference.rpartition("/")
    reference = head + slash + last.split(":", 1)[0]
    first, _, rest = reference.partition("/")
    return rest if rest and _REGISTRY.match(first) else reference


def docker_entry() -> str:
    """The text of the docker ecosystem entry in dependabot.yaml."""
    text = DEPENDABOT.read_text(encoding="utf-8")
    start = text.index('- package-ecosystem: "docker"\n')
    following = text.find("\n  - package-ecosystem:", start)
    return text[start : following if following != -1 else len(text)]


def docker_directories(entry: str) -> list[str]:
    block = entry.split("directories:", 1)[1].split("\n    cooldown:", 1)[0]
    return re.findall(r'^\s+- "(/[^"]+)"$', block, re.MULTILINE)


def ignored_updates(entry: str) -> dict[str, set[str]]:
    """Each ignored dependency name and the update types it skips."""
    block = entry.split("\n    ignore:\n", 1)[1]
    ignored: dict[str, set[str]] = {}
    for item in re.split(r"\n      - (?=dependency-name:)", "\n" + block)[1:]:
        name = re.match(r'dependency-name: "([^"]+)"', item)
        assert name, f"an ignore item without a quoted name: {item!r}"
        ignored[name.group(1)] = set(re.findall(r'- "(version-update:[^"]+)"', item))
    return ignored


def python_images() -> dict[str, str]:
    """Each python base image Dependabot reads, by Dockerfile."""
    images: dict[str, str] = {}
    for directory in docker_directories(docker_entry()):
        for folder in sorted(ROOT.glob(directory.lstrip("/"))):
            for dockerfile in sorted(folder.glob("Dockerfile*")):
                source = dockerfile.read_text(encoding="utf-8")
                for match in _FROM.finditer(source):
                    name = dependabot_name(match.group("ref"))
                    if name.rsplit("/", 1)[-1] == "python":
                        images[dockerfile.relative_to(ROOT).as_posix()] = name
    return images


def test_dependabot_names_an_image_without_its_registry() -> None:
    assert dependabot_name("docker.io/library/python:3.12.15-slim") == "library/python"
    assert dependabot_name("docker.io/library/python@sha256:ab12") == "library/python"
    assert dependabot_name("python:3.12-slim") == "python"
    assert dependabot_name("gcr.io/cloud-spanner-emulator/emulator") == (
        "cloud-spanner-emulator/emulator"
    )
    assert dependabot_name("registry.local:5000/team/python") == "team/python"
    assert dependabot_name("python") == "python"
    assert dependabot_name("library/python") == "library/python"


def test_every_python_base_image_is_held_on_its_minor() -> None:
    images = python_images()
    assert images, (
        "no python base image found; the directories or the FROM parse changed"
    )
    ignored = ignored_updates(docker_entry())
    for dockerfile, name in images.items():
        assert _SKIPPED_UPDATES <= ignored.get(name, set()), (
            f"{dockerfile}: Dependabot names its python image {name!r}; "
            f"the docker ignore must skip {sorted(_SKIPPED_UPDATES)} for it"
        )
