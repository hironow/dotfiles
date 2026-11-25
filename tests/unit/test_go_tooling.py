"""Go 1.27 floor + golangci-lint v2 gate (docs/agents/go-tooling.md).

Tracked Go lives in the emulator CLIs and tools/simple-server. The floor is
the go directive; the quality gate is one root golangci-lint v2 config
(gofumpt-only formatters) invoked from just go-lint / go-fmt and wired into
just check. Per-module copies are not used.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_GO_DIRECTIVE = re.compile(r"^go (\d+)(?:\.(\d+))?(?:\.(\d+))?$")
_FLOOR = (1, 27)


def _git_ls(pattern: str) -> list[Path]:
    done = subprocess.run(
        ["git", "ls-files", "-z", "--", pattern],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    return [REPO / p for p in done.stdout.decode().split("\0") if p]


def _tracked_go_mods() -> list[Path]:
    paths = _git_ls("*go.mod")
    assert paths, "expected tracked go.mod files"
    return paths


def _go_version(path: Path) -> tuple[int, ...]:
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _GO_DIRECTIVE.fullmatch(line.strip())
        if m:
            return tuple(int(part or 0) for part in m.groups())
    raise AssertionError(f"{path}: no go directive")


def _justfile() -> str:
    return (REPO / "justfile").read_text(encoding="utf-8")


def _code_lines_with(text: str, pattern: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.search(pattern, stripped):
            hits.append((n, stripped))
    return hits


def test_tracked_go_modules_are_at_least_1_27() -> None:
    short: list[str] = []
    for path in _tracked_go_mods():
        version = _go_version(path)
        if version[:2] < _FLOOR:
            rel = path.relative_to(REPO)
            short.append(f"{rel}: go {'.'.join(map(str, version))}")
    assert not short, "go directive must be >= 1.27:\n" + "\n".join(short)


def test_root_golangci_config_is_v2_gofumpt_only() -> None:
    config = REPO / ".golangci.yaml"
    assert config.is_file(), "golangci-lint v2 config belongs at the repo root"
    text = config.read_text(encoding="utf-8")
    assert re.search(r'(?m)^version:\s*["\']?2', text), (
        ".golangci.yaml must declare version 2"
    )
    assert re.search(r"(?m)^\s+- gofumpt\s*$", text), (
        ".golangci.yaml must enable the gofumpt formatter"
    )
    assert not _code_lines_with(text, r"\bgoimports\b"), (
        "gofumpt-only: enabling goimports makes fmt and run disagree"
    )
    extras = [
        p.relative_to(REPO).as_posix()
        for p in _git_ls(".golangci.yaml") + _git_ls(".golangci.yml")
        if p.resolve() != config.resolve()
    ]
    assert not extras, "one root golangci config; found extra " + ", ".join(extras)


def test_justfile_has_go_lint_and_go_fmt_recipes() -> None:
    justfile = _justfile()
    assert re.search(r"(?m)^go-lint:", justfile), "just go-lint must exist"
    assert re.search(r"(?m)^go-fmt:", justfile), "just go-fmt must exist"
    lint_hits = _code_lines_with(justfile, r"golangci-lint\s+run")
    fmt_hits = _code_lines_with(justfile, r"golangci-lint\s+fmt")
    assert lint_hits, "go-lint must invoke golangci-lint run"
    assert fmt_hits, "go-fmt must invoke golangci-lint fmt"


def test_just_check_wires_go_lint() -> None:
    justfile = _justfile()
    in_recipe = False
    body: list[str] = []
    for line in justfile.splitlines():
        if re.match(r"^check:\s*$", line):
            in_recipe = True
            continue
        if in_recipe:
            if line and not line[0].isspace() and not line.startswith("#"):
                break
            body.append(line)
    joined = "\n".join(body)
    assert in_recipe, "just check recipe not found"
    assert re.search(r"\bgo-lint\b|golangci-lint\s+run", joined), (
        "just check must run the Go lint gate"
    )


def test_emu_fmt_uses_golangci_not_go_fmt() -> None:
    justfile = _justfile()
    in_recipe = False
    body: list[str] = []
    for line in justfile.splitlines():
        if re.match(r"^emu-fmt:\s*$", line):
            in_recipe = True
            continue
        if in_recipe:
            if line and not line[0].isspace() and not line.startswith("#"):
                break
            body.append(line)
    joined = "\n".join(body)
    assert in_recipe, "just emu-fmt recipe not found"
    assert "golangci-lint fmt" in joined, (
        "emu-fmt must format Go CLIs with golangci-lint fmt"
    )
    assert not re.search(r"\bgo fmt\b", joined), (
        "emu-fmt must not use go fmt; golangci-lint fmt (gofumpt) is the gate"
    )
