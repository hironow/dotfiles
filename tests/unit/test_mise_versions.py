"""The image's frozen tool generation has one source, and cannot drift from it.

`config/mise/image-tools.toml` is the single place the devcontainer image's
version facts live. The image cannot read the host's `config/mise/config.toml`
at build time (mise does not treat a repo-local `config/mise/config.toml` as a
project config), so before this landed the same versions were hand-written in
two places and drifted silently: the image's `uv` tarball sat at 0.12.21 while
its baked mise copy was 0.13.1, and `just` at 1.58.0 vs 1.59.0, with no check.
ADR 0006 §3 promised a check; this is it.

Three groups of tests:

1. the committed scripts match what the generator renders (no drift),
2. the generator reports every one-sided edit (source only, host only, a
   mutated generated region, a mutated bootstrap constant),
3. the invariants that make "one place" true: no version written twice, every
   `[tools]` / `[fetch]` tool declared on the host with equal exact pins, and
   `[bootstrap].mise` compared with `install.sh`'s `_mise_ver` only (mise is
   not a mise tool, so the host config has no entry for it).
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "mise_versions.py"
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


def generator():
    assert SCRIPT.is_file(), (
        "scripts/mise_versions.py must exist: it is the single writer of the "
        "image's frozen generation (and the checker `just lint` runs)."
    )
    spec = importlib.util.spec_from_file_location("mise_versions", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def mutate(root: Path, rel: Path, old: str, new: str) -> None:
    """Rewrite one file inside a temp checkout.

    Guards the two ways this test once edited the real checkout: joining an
    absolute path onto another root yields the original, and a `str.replace`
    that matches nothing fails silently.
    """
    assert not rel.is_absolute(), f"{rel} must be relative to the checkout root"
    path = root / rel
    assert root in path.parents, f"{path} escaped {root}"
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {rel}: the fixture would be a no-op"
    path.write_text(text.replace(old, new), encoding="utf-8")


def check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--root", str(root)],
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        text=True,
    )


def tree(tmp_path: Path) -> Path:
    """A minimal checkout: the four files the generator reads and writes.

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


def _source(root: Path = ROOT) -> dict:
    return tomllib.loads((root / SOURCE).read_text(encoding="utf-8"))


def _host_tools(root: Path = ROOT) -> dict:
    return tomllib.loads((root / HOST).read_text(encoding="utf-8"))["tools"]


def _pinned(spec: object) -> str | None:
    if isinstance(spec, dict):
        spec = spec.get("version")
    return spec if isinstance(spec, str) and spec not in {"latest", "lts"} else None


# ---------- 1. the committed scripts match the generator ----------


def test_the_committed_scripts_match_the_generated_regions() -> None:
    """A generated region edited by hand, or a source change not synced."""
    result = check(ROOT)
    assert result.returncode == 0, (
        "the image's version regions drifted from config/mise/image-tools.toml; "
        "run `just mise-versions-sync`.\n" + result.stdout + result.stderr
    )


# ---------- 2. every one-sided edit is reported ----------


def test_a_source_only_edit_is_reported(tmp_path: Path) -> None:
    root = tree(tmp_path)
    mutate(
        root,
        REL_SOURCE,
        '"aqua:rossmacarthur/sheldon" = "0.8.5"',
        '"aqua:rossmacarthur/sheldon" = "0.9.0"',
    )
    result = check(root)
    assert result.returncode != 0
    assert "sheldon" in result.stderr


def test_a_host_only_edit_is_reported(tmp_path: Path) -> None:
    root = tree(tmp_path)
    mutate(
        root,
        REL_HOST,
        '"aqua:rossmacarthur/sheldon" = { version = "0.8.5"',
        '"aqua:rossmacarthur/sheldon" = { version = "0.9.0"',
    )
    result = check(root)
    assert result.returncode != 0
    assert "sheldon" in result.stderr


def test_a_mutated_generated_region_is_reported(tmp_path: Path) -> None:
    root = tree(tmp_path)
    mutate(root, REL_FEATURE, 'bun = "1.4.3"', 'bun = "1.4.4"')
    result = check(root)
    assert result.returncode != 0
    assert "mise-versions-sync" in result.stderr


def test_a_mutated_bootstrap_constant_is_reported(tmp_path: Path) -> None:
    root = tree(tmp_path)
    mutate(root, REL_BOOTSTRAP, '_mise_ver="2026.9.0"', '_mise_ver="2026.8.0"')
    result = check(root)
    assert result.returncode != 0
    assert "_mise_ver" in result.stdout


def test_a_channel_instead_of_a_pin_in_the_source_is_rejected(tmp_path: Path) -> None:
    """`latest` in the image's own generation would silently unfreeze it."""
    root = tree(tmp_path)
    mutate(
        root,
        REL_SOURCE,
        '"npm:@informalsystems/quint" = "0.33.0"',
        '"npm:@informalsystems/quint" = "latest"',
    )
    result = check(root)
    assert result.returncode != 0
    assert "quint" in result.stderr


def test_a_value_needing_escaping_round_trips(tmp_path: Path) -> None:
    """A quote or a backslash must not turn the generated TOML into garbage."""
    root = tree(tmp_path)
    mutate(
        root,
        REL_SOURCE,
        'rename_exe = "antigravity"',
        'rename_exe = "antigravity\\"x\\\\y"',
    )
    mod = generator()
    mod.sync(root)
    match = _HEREDOC.search((root / REL_FEATURE).read_text(encoding="utf-8"))
    assert match, "the temp checkout must still bake the heredoc"
    baked = tomllib.loads(match.group(1))
    source = tomllib.loads((root / REL_SOURCE).read_text(encoding="utf-8"))
    assert baked["tools"] == source["tools"]


def test_a_partial_or_empty_version_is_rejected(tmp_path: Path) -> None:
    """mise resolves `24` / `prefix:24` / `""` to a moving target, not a pin."""
    for spec in ('"24"', '"prefix:24"', '""'):
        root = tree(tmp_path)
        mutate(root, REL_SOURCE, 'node = "24.22.0"', f"node = {spec}")
        result = check(root)
        assert result.returncode != 0, spec
        assert "node" in result.stderr, spec


def test_an_inline_table_entry_yields_a_version_constant(tmp_path: Path) -> None:
    """`uv = { version = "0.13.1" }` must write UV_VERSION="0.13.1", not a dict."""
    root = tree(tmp_path)
    mutate(root, REL_SOURCE, 'uv = "0.13.1"', 'uv = { version = "0.13.1" }')
    generator().sync(root)
    feature = (root / REL_FEATURE).read_text(encoding="utf-8")
    assert re.search(r'^UV_VERSION="0\.13\.1"$', feature, re.MULTILINE)


def test_sync_is_idempotent(tmp_path: Path) -> None:
    root = tree(tmp_path)
    mod = generator()
    # The temp checkout is a copy of an un-synced tree, so the first sync writes;
    # the point is that the second one is a no-op.
    mod.sync(root)
    assert mod.sync(root) == []
    assert check(root).returncode == 0


# ---------- 3. the invariants that make "one place" true ----------


def test_bootstrap_mise_is_not_required_on_the_host() -> None:
    """mise is not a mise tool: the host config carries no `mise` entry."""
    host = _host_tools()
    assert "mise" not in host
    assert _source()["bootstrap"]["mise"]
    assert check(ROOT).returncode == 0


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
    gen = generator()
    for key, value in {**source["tools"], **gen.fetch_tools(source)}.items():
        assert key in host, (
            f"{key} is baked into the image but not declared on the host"
        )
        host_version = _pinned(host[key])
        if host_version is not None:
            assert _pinned(value) in (None, host_version), (
                f"{key}: the image is {_pinned(value)} but the host pins {host_version}"
            )


def test_the_generated_heredoc_is_a_toml_the_sandbox_tests_can_parse() -> None:
    """tests/unit/test_sandbox_check_tools.py parses this block the same way."""
    match = _HEREDOC.search(FEATURE.read_text(encoding="utf-8"))
    assert match, "install.sh must still bake /etc/mise/config.toml through a heredoc"
    baked = tomllib.loads(match.group(1))
    source = _source()
    assert baked["settings"]["npm"] == source["settings"]["npm"]
    assert baked["tools"] == source["tools"]


def test_the_generated_constants_come_from_the_single_source() -> None:
    source = _source()
    gen = generator()
    feature = FEATURE.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    for name, expected in (
        ("UV_VERSION", source["tools"]["uv"]),
        ("JUST_VERSION", source["tools"]["just"]),
        ("SHELDON_VERSION", gen.fetch_tools(source)["aqua:rossmacarthur/sheldon"]),
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


def test_the_generator_stays_on_the_standard_library() -> None:
    """No third-party import: `tomllib` is why this is Python (ADR 0060)."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "tomllib" in text
    for third_party in ("import requests", "import yaml", "import tomli"):
        assert third_party not in text, "the generator stays on the standard library"
