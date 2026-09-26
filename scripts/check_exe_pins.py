#!/usr/bin/env python3
"""Keep exe/versions.json the single source of truth for the exe/ax pins.

The ax release, the Agent Substrate release and the GKE cluster minor have to
move together, and nothing in the toolchain couples them. OpenTofu plans fine
with a hardcoded "v0.1.0" in one stack and a jsondecode() of exe/versions.json
in another; `tofu validate` never evaluates values; and the substrate version is
not just a download URL -- it is stamped on every node as the value of the
`ate.dev/substrate-version` label, so a stale literal does not fail loudly, it
produces nodes the version selector quietly declines to match.

So exe/versions.json is declared the one place those pins live, and this gate is
what makes the declaration true. It pins the document's schema (a typo must not
be able to introduce a second pin), rejects any second substrate version
literal, rejects a patch-level GKE pin (GKE owns patches -- we own the minor
only), holds 0.x providers to dependency class 2 (cooldown + changelog, see
docs/agents/dependency-policy.md), and greps every existing tofu stack both for
a hardcoded pin and for a missing jsondecode() reference back to this file.

config/mise/config.toml pins the ax CLI as well -- mise is what installs it on
every host and a mise entry cannot jsondecode() anything, so that entry is the
one place the tag is necessarily written down twice, and this gate holds it to
being a mirror of ax.version rather than a second opinion. A checkout without
that config is skipped rather than failed: the pin document is the source of
truth, and a mirror can only be checked where the mirror exists.

The upstream tag->SHA comparison is deliberately opt-in: `verify_shas` takes a
resolver, and the one main() passes returns None unless
EXE_PINS_VERIFY_UPSTREAM=1 is set. A CI gate that needs api.github.com is a gate
that fails for reasons unrelated to the pins, so offline it reports "skipped".

Exit code: 0 = clean, 1 = violations found (listed on stderr). Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

EXIT_OK = 0
EXIT_FAIL = 1

# Path of the pin document, relative to the repo root. Also the tail every
# stack's jsondecode(file(...)) argument must end with.
PINS_REL = "exe/versions.json"

# The mise config that installs the ax CLI, relative to the repo root, and the
# `[tools]` key it declares ax under (the Go backend builds cmd/ax from source
# because upstream publishes no release binaries).
MISE_CONFIG_REL = "config/mise/config.toml"
MISE_AX_TOOL_KEY = "go:github.com/google/ax/cmd/ax"

# GKE release channels as the API spells them. The cluster minor is pinned; the
# patch inside a minor is GKE's to choose, so a patch-level string is a bug.
RELEASE_CHANNELS = ("RAPID", "REGULAR", "STABLE", "EXTENDED")

# Env var that opts the SHA comparison into hitting api.github.com.
VERIFY_ENV = "EXE_PINS_VERIFY_UPSTREAM"
GITHUB_TIMEOUT_S = 10

# Required shape. Blocks are closed (unknown non-`_` keys are violations) so a
# typo cannot silently become a second, unread pin.
_STR = str
_TOP_REQUIRED: dict[str, type] = {
    "_source_of_truth": _STR,
    "ax": dict,
    "substrate": dict,
    "gke": dict,
    "providers": dict,
    "stacks": list,
}
_AX_REQUIRED = ("version", "repo", "sha")
_SUBSTRATE_REQUIRED = (
    "version",
    "repo",
    "sha",
    "version_label_key",
    "version_label_value",
)
_GKE_REQUIRED = ("release_channel", "cluster_minor")
_PROVIDER_KEYS = ("version", "dependency_class")

# Keys under `substrate` that are allowed to hold the version string. Every
# other (non-`_`) substrate value carrying a vX.Y.Z literal is a second pin.
_SUBSTRATE_VERSION_KEYS = ("version", "version_label_value")

_SEMVER_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_SEMVER_LITERAL_RE = re.compile(r"v\d+\.\d+\.\d+")
_PROVIDER_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CLUSTER_MINOR_RE = re.compile(r"^1\.\d+$")

# Kubernetes label grammar (implemented here rather than pulled in as a dep).
# Name/value: 1-63 chars of alphanumeric, `-`, `_`, `.`, starting and ending
# alphanumeric. Key prefix: an optional DNS subdomain before a single `/`.
_LABEL_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]{0,61}[A-Za-z0-9])?$")
_DNS_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_DNS_SUBDOMAIN_MAX = 253

# `jsondecode(file("<path>"))` with the path captured. Whitespace-tolerant;
# single-expression only, which is how every stack is expected to read the pins.
_JSONDECODE_FILE_RE = re.compile(
    r"jsondecode\(\s*file\(\s*\"([^\"]+)\"\s*\)", re.MULTILINE
)
_COMMENT_STARTS = ("#", "//")


class ShaVerification(NamedTuple):
    """Outcome of comparing pinned SHAs against a resolver.

    `skipped` is not a failure: it is the offline path, reported so an operator
    can tell "upstream agrees" apart from "nobody asked upstream".
    """

    violations: list[str]
    skipped: list[str]


# --- loading ----------------------------------------------------------------


def load_pins(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Read <root>/exe/versions.json. Missing or unparsable is a violation."""
    path = root / PINS_REL
    if not path.is_file():
        return None, [
            f"{PINS_REL}: missing -- this repo must always carry the pin "
            f"document; every exe stack reads it with jsondecode(file(...))."
        ]
    try:
        loaded = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return None, [f"{PINS_REL}: unparsable JSON ({exc})."]
    if not isinstance(loaded, dict):
        return None, [f"{PINS_REL}: top level must be a JSON object."]
    return loaded, []


# --- check 1: schema --------------------------------------------------------


def _closed_block(
    pins: dict[str, Any], name: str, required: tuple[str, ...]
) -> list[str]:
    """Require every key in `required` to be a string, and reject extras."""
    violations: list[str] = []
    block = pins.get(name)
    if not isinstance(block, dict):
        return violations  # typed at the top level already
    for key in required:
        value = block.get(key)
        if not isinstance(value, str) or not value:
            violations.append(
                f"{PINS_REL}: schema -- {name}.{key} must be a non-empty string."
            )
    allowed = set(required)
    for key in block:
        if not key.startswith("_") and key not in allowed:
            violations.append(
                f"{PINS_REL}: schema -- unknown key '{key}' in block '{name}'. "
                f"A typo here creates a pin nothing reads; prefix prose with "
                f"'_' or fix the name."
            )
    return violations


def check_schema(pins: dict[str, Any]) -> list[str]:
    """Pin the document's shape: required keys, types, and no unknown keys."""
    violations: list[str] = []

    for key, expected in _TOP_REQUIRED.items():
        if key not in pins:
            violations.append(f"{PINS_REL}: schema -- required key '{key}' is missing.")
        elif not isinstance(pins[key], expected):
            violations.append(
                f"{PINS_REL}: schema -- '{key}' must be {expected.__name__}, "
                f"got {type(pins[key]).__name__}."
            )
    for key in pins:
        if not key.startswith("_") and key not in _TOP_REQUIRED:
            violations.append(
                f"{PINS_REL}: schema -- unknown top-level key '{key}'. Only the "
                f"declared pins live here; prefix prose with '_'."
            )

    violations.extend(_closed_block(pins, "ax", _AX_REQUIRED))
    violations.extend(_closed_block(pins, "substrate", _SUBSTRATE_REQUIRED))
    violations.extend(_closed_block(pins, "gke", _GKE_REQUIRED))

    for name in ("ax", "substrate"):
        block = pins.get(name)
        if not isinstance(block, dict):
            continue
        version = block.get("version")
        if isinstance(version, str) and not _SEMVER_TAG_RE.match(version):
            violations.append(
                f"{PINS_REL}: schema -- {name}.version '{version}' is not a "
                f"vMAJOR.MINOR.PATCH upstream tag."
            )

    providers = pins.get("providers")
    if isinstance(providers, dict):
        for name, entry in providers.items():
            if not isinstance(entry, dict):
                violations.append(
                    f"{PINS_REL}: schema -- providers['{name}'] must be an object."
                )
                continue
            if not isinstance(entry.get("version"), str):
                violations.append(
                    f"{PINS_REL}: schema -- providers['{name}'].version must be "
                    f"a string."
                )
            for key in entry:
                if not key.startswith("_") and key not in _PROVIDER_KEYS:
                    violations.append(
                        f"{PINS_REL}: schema -- unknown key '{key}' in "
                        f"providers['{name}']."
                    )

    stacks = pins.get("stacks")
    if isinstance(stacks, list):
        for entry in stacks:
            if not isinstance(entry, str) or not entry:
                violations.append(
                    f"{PINS_REL}: schema -- every 'stacks' entry must be a "
                    f"non-empty repo-relative path, got {entry!r}."
                )
    return violations


# --- check 2: exactly one substrate version reference ----------------------


def check_single_substrate_ref(pins: dict[str, Any]) -> list[str]:
    """Require one substrate version string, mirrored only by the label value.

    Two places holding "the substrate version" is the drift this whole file
    exists to prevent, so the label value must equal it and no other (non-`_`)
    substrate value may carry a vX.Y.Z literal at all.
    """
    violations: list[str] = []
    substrate = pins.get("substrate")
    if not isinstance(substrate, dict):
        return violations

    version = substrate.get("version")
    label_value = substrate.get("version_label_value")
    if isinstance(version, str) and isinstance(label_value, str):
        if label_value != version:
            violations.append(
                f"{PINS_REL}: substrate -- version_label_value "
                f"'{label_value}' != version '{version}'. The label stamped on "
                f"nodes is the version, not a second pin."
            )

    for key, value in substrate.items():
        if key.startswith("_") or key in _SUBSTRATE_VERSION_KEYS:
            continue  # `_`-prefixed keys are prose and may name the tag freely
        if isinstance(value, str) and _SEMVER_LITERAL_RE.search(value):
            violations.append(
                f"{PINS_REL}: substrate -- stray version literal in "
                f"substrate.{key} ('{value}'). substrate.version is the only "
                f"substrate version reference."
            )
    return violations


# --- check 3: SHA shape, and match against upstream ------------------------


def check_sha_shapes(pins: dict[str, Any]) -> list[str]:
    """Require full 40-char lowercase hex commit SHAs (no abbreviations)."""
    violations: list[str] = []
    for name in ("ax", "substrate"):
        block = pins.get(name)
        if not isinstance(block, dict):
            continue
        sha = block.get("sha")
        if not isinstance(sha, str) or not _SHA_RE.match(sha):
            violations.append(
                f"{PINS_REL}: sha -- {name}.sha must be 40 lowercase hex chars, "
                f"got {sha!r}."
            )
    return violations


def verify_shas(
    pins: dict[str, Any], resolver: Callable[[str, str], str | None]
) -> ShaVerification:
    """Compare each pinned SHA with `resolver(repo, tag)`.

    A resolver returning None means "not consulted" -- reported as skipped, not
    as a violation, so the gate stays deterministic without the network.
    """
    violations: list[str] = []
    skipped: list[str] = []
    for name in ("ax", "substrate"):
        block = pins.get(name)
        if not isinstance(block, dict):
            continue
        repo = block.get("repo")
        tag = block.get("version")
        sha = block.get("sha")
        if not (
            isinstance(repo, str) and isinstance(tag, str) and isinstance(sha, str)
        ):
            continue  # shape problems are check_schema / check_sha_shapes's job
        upstream = resolver(repo, tag)
        if upstream is None:
            skipped.append(f"{name}: upstream SHA for {repo}@{tag} not consulted")
            continue
        if upstream != sha:
            violations.append(
                f"{PINS_REL}: sha -- {name}.sha {sha} != upstream {upstream} "
                f"for {repo}@{tag}. Either the tag moved or the pin is wrong."
            )
    return ShaVerification(violations, skipped)


def _github_tag_sha(repo: str, tag: str) -> str | None:
    """Resolve a tag to its commit SHA via the GitHub API, or None on any error."""
    parts = repo.split("/")
    if len(parts) != 3 or parts[0] != "github.com":
        return None
    url = f"https://api.github.com/repos/{parts[1]}/{parts[2]}/git/refs/tags/{tag}"
    request = urllib.request.Request(  # noqa: S310 - fixed https api.github.com
        url, headers={"Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=GITHUB_TIMEOUT_S) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None  # never let the network decide whether the gate passes
    obj = payload.get("object") if isinstance(payload, dict) else None
    sha = obj.get("sha") if isinstance(obj, dict) else None
    return sha if isinstance(sha, str) else None


def default_resolver(repo: str, tag: str) -> str | None:
    """Offline unless EXE_PINS_VERIFY_UPSTREAM=1 opts into the GitHub lookup."""
    if os.environ.get(VERIFY_ENV) != "1":
        return None
    return _github_tag_sha(repo, tag)


# --- check 4: Kubernetes label validity ------------------------------------


def is_valid_label_key(key: object) -> bool:
    """True for a valid Kubernetes label key (optional DNS prefix + '/' + name)."""
    if not isinstance(key, str) or not key:
        return False
    if key.count("/") > 1:
        return False
    prefix, slash, name = key.rpartition("/")
    if slash:
        if not prefix or len(prefix) > _DNS_SUBDOMAIN_MAX:
            return False
        if not all(_DNS_LABEL_RE.match(part) for part in prefix.split(".")):
            return False
    return bool(_LABEL_NAME_RE.match(name))


def is_valid_label_value(value: object) -> bool:
    """True for a valid Kubernetes label value (empty, or <=63 chars of the set)."""
    if not isinstance(value, str):
        return False
    return value == "" or bool(_LABEL_NAME_RE.match(value))


def check_labels(pins: dict[str, Any]) -> list[str]:
    """The substrate version label must be a key/value Kubernetes accepts."""
    violations: list[str] = []
    substrate = pins.get("substrate")
    if not isinstance(substrate, dict):
        return violations
    key = substrate.get("version_label_key")
    if not is_valid_label_key(key):
        violations.append(
            f"{PINS_REL}: label -- substrate.version_label_key {key!r} is not a "
            f"valid Kubernetes label key (optional DNS-subdomain prefix + '/' + "
            f"1-63 alphanumeric/'-'/'_'/'.' chars starting and ending alphanumeric)."
        )
    value = substrate.get("version_label_value")
    if not is_valid_label_value(value):
        violations.append(
            f"{PINS_REL}: label -- substrate.version_label_value {value!r} is "
            f"not a valid Kubernetes label value (<=63 chars, starts and ends "
            f"alphanumeric); it is stamped on every node, so the node would be "
            f"rejected."
        )
    return violations


# --- check 5: GKE channel + minor-only pin ---------------------------------


def check_gke(pins: dict[str, Any]) -> list[str]:
    """Known release channel, and a minor-only cluster version."""
    violations: list[str] = []
    gke = pins.get("gke")
    if not isinstance(gke, dict):
        return violations
    channel = gke.get("release_channel")
    if channel not in RELEASE_CHANNELS:
        violations.append(
            f"{PINS_REL}: gke -- release_channel {channel!r} must be one of "
            f"{', '.join(RELEASE_CHANNELS)}."
        )
    minor = gke.get("cluster_minor")
    if not isinstance(minor, str) or not _CLUSTER_MINOR_RE.match(minor):
        violations.append(
            f"{PINS_REL}: gke -- cluster_minor {minor!r} must match ^1\\.<minor>$ "
            f"(e.g. '1.37'). GKE manages patches inside a minor, so pinning a "
            f"patch guarantees drift on the next upgrade."
        )
    return violations


# --- check 6: dependency class of 0.x providers ---------------------------


def check_providers(pins: dict[str, Any]) -> list[str]:
    """A 0.x provider is Class 2 by policy: cooldown + changelog, never Class 1."""
    violations: list[str] = []
    providers = pins.get("providers")
    if not isinstance(providers, dict):
        return violations
    for name, entry in providers.items():
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        if not isinstance(version, str):
            continue
        match = _PROVIDER_VERSION_RE.match(version)
        if match is None:
            violations.append(
                f"{PINS_REL}: providers -- '{name}' version {version!r} is not a "
                f"MAJOR.MINOR[.PATCH] version."
            )
            continue
        declared = entry.get("dependency_class")
        if declared is not None and declared not in (1, 2):
            violations.append(
                f"{PINS_REL}: providers -- '{name}' dependency_class "
                f"{declared!r} must be 1 or 2."
            )
        if match.group(1) == "0" and declared != 2:
            violations.append(
                f"{PINS_REL}: providers -- '{name}' is {version} (major 0) so it "
                f"is dependency class 2 (cooldown + changelog), but declares "
                f"{declared!r}. See docs/agents/dependency-policy.md."
            )
    return violations


# --- check 7: every stack resolves this same pin file ----------------------


def _pinned_literals(pins: dict[str, Any]) -> list[str]:
    """The strings a stack must never hardcode (deduped, order preserved)."""
    candidates: list[object] = []
    for block_name, keys in (
        ("ax", ("version",)),
        ("substrate", ("version", "sha", "version_label_value")),
        ("gke", ("cluster_minor",)),
    ):
        block = pins.get(block_name)
        if isinstance(block, dict):
            candidates.extend(block.get(key) for key in keys)
    literals: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, str) and candidate and candidate not in literals:
            literals.append(candidate)
    return literals


def _strip_comments(text: str) -> str:
    """Drop HCL comments (`#`/`//` to EOL, `/* */`), keeping strings intact.

    String-aware on purpose: a regex stripper eats everything after the `//` of
    an `https://` URL, which is precisely where a stale hardcoded version is
    most likely to hide (a release-download URL). Newlines are preserved so
    line structure survives.
    """
    out: list[str] = []
    index = 0
    end = len(text)
    in_string = False
    while index < end:
        char = text[index]
        if in_string:
            if char == "\\" and index + 1 < end:
                out.append(text[index : index + 2])
                index += 2
                continue
            if char == '"':
                in_string = False
            out.append(char)
            index += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            index += 1
            continue
        if char == "#" or text.startswith("//", index):
            newline = text.find("\n", index)
            index = end if newline == -1 else newline
            continue
        if text.startswith("/*", index):
            close = text.find("*/", index + 2)
            index = end if close == -1 else close + 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def check_stacks(root: Path, pins: dict[str, Any]) -> list[str]:
    """Every existing declared stack reads this file, and hardcodes no pin.

    A stack that does not exist yet is skipped (later phases create them), but
    the declaration list itself must never be empty -- an empty list would make
    this whole check vacuous.
    """
    violations: list[str] = []
    stacks = pins.get("stacks")
    if not isinstance(stacks, list) or not stacks:
        return [
            f"{PINS_REL}: stacks -- must declare at least one stack path; an "
            f"empty list makes the hardcoded-pin check vacuous."
        ]

    literals = _pinned_literals(pins)
    expected_target = (root / PINS_REL).resolve()

    for rel in stacks:
        if not isinstance(rel, str):
            continue  # typed by check_schema
        stack_dir = root / rel
        if not stack_dir.is_dir():
            continue  # built in a later phase; a declaration alone must not fail
        tf_files = sorted(stack_dir.glob("*.tf"))
        if not tf_files:
            violations.append(f"{rel}: stack directory contains no *.tf files.")
            continue

        referenced: list[str] = []
        for tf in tf_files:
            # Both scans run on the comment-free body: a commented-out
            # jsondecode() is not a reference, and a commented pin is not a pin.
            body = _strip_comments(tf.read_text())
            for raw_path in _JSONDECODE_FILE_RE.findall(body):
                referenced.append(raw_path)
                if not raw_path.endswith(PINS_REL):
                    continue
                resolved = Path(
                    raw_path.replace("${path.module}", str(stack_dir))
                ).resolve()
                if resolved != expected_target:
                    violations.append(
                        f'{rel}/{tf.name}: jsondecode(file("{raw_path}")) '
                        f"resolves to {resolved}, not the repo's {PINS_REL} "
                        f"({expected_target}). Every stack must read one file."
                    )
            for literal in literals:
                pattern = re.compile(r"(?<![\w.-])" + re.escape(literal) + r"(?![\w-])")
                if pattern.search(body):
                    violations.append(
                        f"{rel}/{tf.name}: hardcodes the pinned literal "
                        f"'{literal}'. Read it from {PINS_REL} via "
                        f"jsondecode(file(...)) instead."
                    )
        if not any(path.endswith(PINS_REL) for path in referenced):
            violations.append(
                f'{rel}: no jsondecode(file("...{PINS_REL}")) reference found. '
                f"A declared stack must read its pins from the single source."
            )
    return violations


# --- check 8: the mise ax pin mirrors ax.version ---------------------------


def _mise_tool_versions(value: object) -> list[str] | None:
    """The versions a mise `[tools]` value declares, or None for an odd shape.

    mise spells a tool value three ways: a bare version string, a table whose
    `version` key carries it alongside options (`os`, `exe`, ...), or a list of
    either when several versions are installed side by side. Anything else is
    reported as unrecognised rather than guessed at -- a shape this function
    cannot read is a pin this gate cannot compare.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        version = value.get("version")
        return [version] if isinstance(version, str) else None
    if isinstance(value, list) and value:
        versions: list[str] = []
        for entry in value:
            if isinstance(entry, str):
                versions.append(entry)
            elif isinstance(entry, dict) and isinstance(entry.get("version"), str):
                versions.append(entry["version"])
            else:
                return None
        return versions
    return None


def check_mise_pin(mise_config_path: Path, pins: dict[str, Any]) -> list[str]:
    """The mise ax pin must equal ax.version, and must exist at all.

    Every declared version is compared, so a list form cannot smuggle a second
    ax build in beside the pinned one. A missing or garbled ax.version is
    check_schema's violation and is not re-reported here.
    """
    violations: list[str] = []
    ax = pins.get("ax")
    expected = ax.get("version") if isinstance(ax, dict) else None
    if not isinstance(expected, str) or not expected:
        return violations  # check_schema already reports that

    # A checkout without the mise config must not fail the gate: the pin
    # document is the source of truth and the mirror is only checkable here.
    if not mise_config_path.is_file():
        return violations

    try:
        with mise_config_path.open("rb") as handle:
            config = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as exc:
        return [f"{MISE_CONFIG_REL}: unparsable TOML ({exc})."]

    tools = config.get("tools")
    value = tools.get(MISE_AX_TOOL_KEY) if isinstance(tools, dict) else None
    if value is None:
        return [
            f"{MISE_CONFIG_REL}: [tools] does not declare "
            f"'{MISE_AX_TOOL_KEY}'. The ax CLI must be pinned somewhere "
            f"mechanical, and this is that place: it mirrors ax.version "
            f"('{expected}') from {PINS_REL}."
        ]

    versions = _mise_tool_versions(value)
    if versions is None:
        return [
            f"{MISE_CONFIG_REL}: [tools]['{MISE_AX_TOOL_KEY}'] has an "
            f"unrecognised shape ({value!r}); mise declares a tool as a version "
            f"string, a table with a 'version' key, or a list of either."
        ]

    for version in versions:
        if version != expected:
            violations.append(
                f"{MISE_CONFIG_REL}: [tools]['{MISE_AX_TOOL_KEY}'] pins "
                f"'{version}' but {PINS_REL} pins ax.version '{expected}'. "
                f"{PINS_REL} is the source of truth; mise mirrors it, so move "
                f"the pin there first."
            )
    return violations


# --- entry point ------------------------------------------------------------


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    pins, violations = load_pins(root)

    skipped: list[str] = []
    if pins is not None:
        violations.extend(check_schema(pins))
        violations.extend(check_single_substrate_ref(pins))
        violations.extend(check_sha_shapes(pins))
        sha_result = verify_shas(pins, default_resolver)
        violations.extend(sha_result.violations)
        skipped.extend(sha_result.skipped)
        violations.extend(check_labels(pins))
        violations.extend(check_gke(pins))
        violations.extend(check_providers(pins))
        violations.extend(check_stacks(root, pins))
        violations.extend(check_mise_pin(root / MISE_CONFIG_REL, pins))

    if violations:
        print(
            f"check-exe-pins: FAILED -- {PINS_REL} must stay the single source "
            "of truth for the ax / substrate / GKE pins:",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return EXIT_FAIL

    stacks = pins.get("stacks", []) if pins is not None else []
    existing = sum(
        1 for rel in stacks if isinstance(rel, str) and (root / rel).is_dir()
    )
    note = f", {len(skipped)} upstream SHA check(s) skipped" if skipped else ""
    print(
        f"check-exe-pins: OK -- {PINS_REL} is the single pin source "
        f"({existing}/{len(stacks)} declared stacks present and clean{note})."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
