"""The image's frozen tool generation has one source, and cannot drift from it.

`config/mise/image-tools.toml` is the single place the devcontainer image's
version facts live. The image cannot read the host's `config/mise/config.toml`
at build time (mise does not treat a repo-local `config/mise/config.toml` as a
project config), so before this landed the same versions were hand-written in
two places and drifted silently: the image's `uv` tarball sat at 0.12.21 while
its baked mise copy was 0.13.1, and `just` at 1.58.0 vs 1.59.0, with no check.
ADR 0006 §3 promised a check; ADR 0060/0061 record how it is built.

`tools/mise-versions/` (Go) is the single writer and the checker. This file is
the **oracle**: it drives that tool through its CLI and reads the result back
with `tomllib`, the standard library's real TOML parser. The tool parses TOML
itself (Go has no standard-library reader and this repo asks for the standard
library first), so the oracle is what keeps a hand-rolled reader honest — a
misread or a bad escape shows up here as a difference from what `tomllib` says.

Three groups of tests:

1. the committed scripts match what the tool renders (no drift),
2. the tool reports every one-sided edit, refuses invalid input the way
   `tomllib` does, and writes nothing when it fails,
3. the invariants that make "one place" true: no version written twice, every
   `[tools]` / `[fetch]` tool declared on the host with equal exact pins, and
   `[bootstrap].mise` compared with `install.sh`'s `_mise_ver` only (mise is
   not a mise tool, so the host config has no entry for it).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools" / "mise-versions"
MAIN = MODULE / "main.go"
# Relative on purpose: a temp checkout joins them onto its own root.
REL_SOURCE = Path("config/mise/image-tools.toml")
REL_HOST = Path("config/mise/config.toml")
REL_FEATURE = Path(".devcontainer/features/dotfiles-tools/install.sh")
REL_BOOTSTRAP = Path("install.sh")
TREE = (REL_SOURCE, REL_HOST, REL_FEATURE, REL_BOOTSTRAP)
SOURCE = ROOT / REL_SOURCE
HOST = ROOT / REL_HOST
FEATURE = ROOT / REL_FEATURE
BOOTSTRAP = ROOT / REL_BOOTSTRAP

# The sandbox tests parse the baked config out of install.sh; keep the shape.
_HEREDOC = re.compile(r"cat > /etc/mise/config\.toml <<'EOF'\n(.*?)\nEOF", re.DOTALL)


@pytest.fixture(scope="session")
def tool(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the checker once (module mode, so go.mod's directive applies)."""
    assert MAIN.is_file(), (
        "tools/mise-versions/main.go must exist: it is the single writer of the "
        "image's frozen generation (and the checker `just lint` runs)."
    )
    go = shutil.which("go")
    assert go, "the oracle drives the Go checker, so `go` must be on PATH"
    name = "mise-versions.exe" if os.name == "nt" else "mise-versions"
    binary = tmp_path_factory.mktemp("mise-versions") / name
    built = subprocess.run(
        [go, "build", "-o", str(binary), "."],
        cwd=MODULE,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        text=True,
    )
    assert built.returncode == 0, f"go build failed:\n{built.stdout}{built.stderr}"
    return binary


def cli(tool: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(tool), *args],
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        text=True,
    )


def check(tool: Path, root: Path) -> subprocess.CompletedProcess[str]:
    return cli(tool, "check", "--root", str(root))


def tree(tmp_path: Path) -> Path:
    """A minimal checkout: the four files the tool reads and writes.

    Every path stays relative, and the target is asserted to be inside
    `tmp_path`: joining an absolute path onto another root silently yields the
    original (that mistake once let these tests edit the real checkout).
    """
    for rel in TREE:
        assert not rel.is_absolute(), f"{rel} must be relative to the checkout root"
        target = tmp_path / rel
        assert tmp_path in target.parents, f"{target} escaped {tmp_path}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    return tmp_path


def mutate(root: Path, rel: Path, old: str, new: str) -> None:
    """Rewrite one file inside a temp checkout.

    Guards the two ways this test file once edited the real checkout: joining an
    absolute path onto another root yields the original, and a `str.replace`
    that matches nothing fails silently.
    """
    assert not rel.is_absolute(), f"{rel} must be relative to the checkout root"
    path = root / rel
    assert root in path.parents, f"{path} escaped {root}"
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {rel}: the fixture would be a no-op"
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    assert b"\r\n" not in path.read_bytes(), (
        "temp mutations must preserve LF on Windows"
    )


def _source(root: Path = ROOT) -> dict:
    return tomllib.loads((root / REL_SOURCE).read_text(encoding="utf-8"))


def _host_tools(root: Path = ROOT) -> dict:
    return tomllib.loads((root / REL_HOST).read_text(encoding="utf-8"))["tools"]


def _pinned(spec: object) -> str | None:
    if isinstance(spec, dict):
        spec = spec.get("version")
    return spec if isinstance(spec, str) and spec not in {"latest", "lts"} else None


# ---------- 1. the committed scripts match the tool ----------


def test_the_committed_scripts_match_the_generated_regions(tool: Path) -> None:
    """A generated region edited by hand, or a source change not synced."""
    result = check(tool, ROOT)
    assert result.returncode == 0, (
        "the image's version regions drifted from config/mise/image-tools.toml; "
        "run `just mise-versions-sync`.\n" + result.stdout + result.stderr
    )


# ---------- 2. every one-sided edit is reported ----------


def test_a_source_only_edit_is_reported(tool: Path, tmp_path: Path) -> None:
    root = tree(tmp_path)
    mutate(
        root,
        REL_SOURCE,
        '"aqua:rossmacarthur/sheldon" = "0.8.5"',
        '"aqua:rossmacarthur/sheldon" = "0.9.0"',
    )
    result = check(tool, root)
    assert result.returncode != 0
    assert "sheldon" in result.stderr


def test_a_host_only_edit_is_reported(tool: Path, tmp_path: Path) -> None:
    root = tree(tmp_path)
    mutate(
        root,
        REL_HOST,
        '"aqua:rossmacarthur/sheldon" = { version = "0.8.5"',
        '"aqua:rossmacarthur/sheldon" = { version = "0.9.0"',
    )
    result = check(tool, root)
    assert result.returncode != 0
    assert "sheldon" in result.stderr


def test_a_mutated_generated_region_is_reported(tool: Path, tmp_path: Path) -> None:
    root = tree(tmp_path)
    mutate(root, REL_FEATURE, 'bun = "1.4.4"', 'bun = "1.4.5"')
    result = check(tool, root)
    assert result.returncode != 0
    assert "mise-versions-sync" in result.stderr


def test_a_mutated_bootstrap_constant_is_reported(tool: Path, tmp_path: Path) -> None:
    root = tree(tmp_path)
    mutate(root, REL_BOOTSTRAP, '_mise_ver="2026.10.17"', '_mise_ver="2026.8.0"')
    result = check(tool, root)
    assert result.returncode != 0
    assert "_mise_ver" in result.stdout


def test_a_partial_or_empty_version_is_rejected(tool: Path, tmp_path: Path) -> None:
    """mise resolves `24` / `prefix:24` / `""` to a moving target, not a pin."""
    for spec in ('"24"', '"prefix:24"', '""'):
        root = tree(tmp_path)
        mutate(root, REL_SOURCE, 'node = "26.13.0"', f"node = {spec}")
        result = check(tool, root)
        assert result.returncode != 0, spec
        assert "node" in result.stderr, spec


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('bun = "1.4.4"', 'bun = "1.4.4"\nbun = "1.4.4"'),
        ("[tools]\n", "[tools]\n[tools]\n"),
        ('rename_exe = "antigravity"', 'rename_exe = "anti\\qgravity"'),
        ('mise_tools = ["uv", "just"]', 'mise_tools = ["uv",,"just"]'),
        ('mise_tools = ["uv", "just"]', 'mise_tools = [,"uv", "just"]'),
        ('uv = "0.13.5"', 'uv = { version = "0.13.5", }'),
        ('uv = "0.13.5"', 'uv = { version = "0.13.5",, os = ["linux"] }'),
        ('rename_exe = "antigravity"', 'rename_exe = "anti\x01gravity"'),
        ('rename_exe = "antigravity"', 'rename_exe = "anti\x7fgravity"'),
    ],
    ids=[
        "duplicate-same-value",
        "redefined-table",
        "escape-metadata",
        "array-hole",
        "array-leading-comma",
        "inline-trailing-comma",
        "inline-hole",
        "raw-control",
        "raw-DEL",
    ],
)
def test_invalid_input_is_rejected_the_way_tomllib_rejects_it(
    tool: Path, tmp_path: Path, old: str, new: str
) -> None:
    """The input must fail parsing, not merely version validation or drift."""
    root = tree(tmp_path)
    mutate(root, REL_SOURCE, old, new)
    assert_parse_rejected_without_writes(tool, root, REL_SOURCE)


def assert_parse_rejected_without_writes(tool: Path, root: Path, rel: Path) -> None:
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads((root / rel).read_text(encoding="utf-8"))
    before = {path: (root / path).read_bytes() for path in (REL_FEATURE, REL_BOOTSTRAP)}
    for command in ("check", "sync"):
        result = cli(tool, command, "--root", str(root))
        assert result.returncode == 1, result.stdout + result.stderr
        assert "line " in result.stderr, (
            "a parse error, not drift/validation, must reject the input"
        )
        assert before == {path: (root / path).read_bytes() for path in before}


@pytest.mark.parametrize("space", ["\u00a0", "\v", "\f"])
def test_non_toml_whitespace_is_not_normalized(
    tool: Path, tmp_path: Path, space: str
) -> None:
    root = tree(tmp_path)
    mutate(root, REL_SOURCE, 'node = "26.13.0"', f'node{space}= "26.13.0"')
    assert_parse_rejected_without_writes(tool, root, REL_SOURCE)


@pytest.mark.parametrize(
    "header", ['[settings."npm"]', '[settings."other".deep.value]']
)
def test_host_non_tools_headers_are_outside_the_subset(
    tool: Path, tmp_path: Path, header: str
) -> None:
    root = tree(tmp_path)
    mutate(root, REL_HOST, "[settings.npm]", header)
    tomllib.loads((root / REL_HOST).read_text(encoding="utf-8"))
    result = check(tool, root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_inline_table_cannot_be_redeclared(tool: Path, tmp_path: Path) -> None:
    root = tree(tmp_path)
    mutate(root, REL_SOURCE, 'uv = "0.13.5"', 'uv = { version = "0.13.5" }')
    path = root / REL_SOURCE
    path.write_text(
        path.read_text(encoding="utf-8") + "\n[tools.uv]\n",
        encoding="utf-8",
        newline="\n",
    )
    assert_parse_rejected_without_writes(tool, root, REL_SOURCE)


def test_host_table_cannot_be_redeclared(tool: Path, tmp_path: Path) -> None:
    root = tree(tmp_path)
    path = root / REL_HOST
    path.write_text(
        path.read_text(encoding="utf-8") + "\n[ tools ]\n",
        encoding="utf-8",
        newline="\n",
    )
    assert_parse_rejected_without_writes(tool, root, REL_HOST)


def test_invalid_utf8_is_rejected_without_writes(tool: Path, tmp_path: Path) -> None:
    root = tree(tmp_path)
    path = root / REL_SOURCE
    path.write_bytes(path.read_bytes().replace(b'antigravity"', b'anti\xffgravity"'))
    with path.open("rb") as stream, pytest.raises(UnicodeDecodeError):
        tomllib.load(stream)
    before = {rel: (root / rel).read_bytes() for rel in (REL_FEATURE, REL_BOOTSTRAP)}
    result = cli(tool, "sync", "--root", str(root))
    assert result.returncode == 1
    assert "invalid UTF-8" in result.stderr
    assert before == {rel: (root / rel).read_bytes() for rel in before}


def test_a_failed_sync_writes_neither_file(tool: Path, tmp_path: Path) -> None:
    root = tree(tmp_path)
    before = (root / REL_FEATURE).read_bytes() + (root / REL_BOOTSTRAP).read_bytes()
    mutate(root, REL_SOURCE, 'node = "26.13.0"', 'node = "24"')
    assert cli(tool, "sync", "--root", str(root)).returncode != 0
    after = (root / REL_FEATURE).read_bytes() + (root / REL_BOOTSTRAP).read_bytes()
    assert before == after, "a failed sync wrote to disk"


def test_sync_is_idempotent(tool: Path, tmp_path: Path) -> None:
    root = tree(tmp_path)
    assert cli(tool, "sync", "--root", str(root)).returncode == 0
    assert check(tool, root).returncode == 0
    result = cli(tool, "sync", "--root", str(root))
    assert "up to date" in result.stdout


def test_the_default_root_follows_the_source_file(tool: Path, tmp_path: Path) -> None:
    """The working directory must not matter, and --root must win."""
    result = subprocess.run(
        [str(tool), "check"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "up to date" in result.stdout


# ---------- 3. the oracle: tomllib reads what the tool wrote ----------


def test_the_generated_heredoc_parses_with_tomllib(tool: Path, tmp_path: Path) -> None:
    """tests/unit/test_sandbox_check_tools.py parses this block the same way."""
    match = _HEREDOC.search(FEATURE.read_text(encoding="utf-8"))
    assert match, "install.sh must still bake /etc/mise/config.toml through a heredoc"
    baked = tomllib.loads(match.group(1))
    source = _source()
    assert baked["settings"] == source["settings"]
    assert baked["tools"] == source["tools"]
    # And what the tool would write is the same thing.
    root = tree(tmp_path)
    assert cli(tool, "sync", "--root", str(root)).returncode == 0
    assert (root / REL_FEATURE).read_bytes() == FEATURE.read_bytes()


def test_a_value_needing_escaping_round_trips(tool: Path, tmp_path: Path) -> None:
    """A quote or a backslash must not turn the generated TOML into garbage."""
    root = tree(tmp_path)
    mutate(
        root,
        REL_SOURCE,
        'rename_exe = "antigravity"',
        'rename_exe = "antigravity\\"x\\\\y"',
    )
    assert cli(tool, "sync", "--root", str(root)).returncode == 0
    match = _HEREDOC.search((root / REL_FEATURE).read_text(encoding="utf-8"))
    assert match, "the temp checkout must still bake the heredoc"
    baked = tomllib.loads(match.group(1))
    source = tomllib.loads((root / REL_SOURCE).read_text(encoding="utf-8"))
    assert baked["tools"] == source["tools"]


def test_an_inline_table_entry_yields_a_version_constant(
    tool: Path, tmp_path: Path
) -> None:
    """An inline version table must write a string constant, not a dict."""
    root = tree(tmp_path)
    mutate(root, REL_SOURCE, 'uv = "0.13.5"', 'uv = { version = "0.13.5" }')
    assert cli(tool, "sync", "--root", str(root)).returncode == 0
    feature = (root / REL_FEATURE).read_text(encoding="utf-8")
    assert re.search(r'^UV_VERSION="0\.13\.5"$', feature, re.MULTILINE)


def test_the_generated_constants_come_from_the_single_source() -> None:
    source = _source()
    feature = FEATURE.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    for name, expected in (
        ("UV_VERSION", source["tools"]["uv"]),
        ("JUST_VERSION", source["tools"]["just"]),
        ("SHELDON_VERSION", source["fetch"]["aqua:rossmacarthur/sheldon"]),
    ):
        assert re.search(rf'^{name}="{re.escape(expected)}"$', feature, re.MULTILINE), (
            name
        )
    for name, expected in (
        ("_mise_ver", source["bootstrap"]["mise"]),
        ("_just_ver", source["tools"]["just"]),
    ):
        assert re.search(
            rf'^\s*{name}="{re.escape(expected)}"$', bootstrap, re.MULTILINE
        ), name


def test_bootstrap_mise_is_not_required_on_the_host() -> None:
    """mise is not a mise tool: the host config carries no `mise` entry."""
    host = _host_tools()
    assert "mise" not in host
    assert _source()["bootstrap"]["mise"]


def test_no_version_is_written_twice_in_the_source() -> None:
    source = _source()
    tools = set(source["tools"])
    fetch = {key for key in source["fetch"] if key != "mise_tools"}
    bootstrap = set(source["bootstrap"])
    assert not tools & fetch, "a tarball tool must not restate its [tools] version"
    assert not tools & bootstrap
    assert not fetch & bootstrap
    assert set(source["fetch"]["mise_tools"]) <= tools, (
        "mise_tools must name existing [tools] entries"
    )


def test_every_image_tool_is_on_the_host_with_matching_exact_pins() -> None:
    source = _source()
    host = _host_tools()
    fetched = {name: source["tools"][name] for name in source["fetch"]["mise_tools"]}
    fetched.update({k: v for k, v in source["fetch"].items() if k != "mise_tools"})
    for key, value in {**source["tools"], **fetched}.items():
        assert key in host, (
            f"{key} is baked into the image but not declared on the host"
        )
        host_version = _pinned(host[key])
        if host_version is not None:
            assert _pinned(value) in (None, host_version), (
                f"{key}: the image is {_pinned(value)} but the host pins {host_version}"
            )
