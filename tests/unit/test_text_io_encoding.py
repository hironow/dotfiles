"""Our Python never relies on the locale encoding for text I/O.

Without `encoding=`, Path.read_text/write_text, open() and subprocess's
text=True decode and encode with the locale code page. That is UTF-8 on
Linux/macOS but cp932 on Japanese Windows, where it crashed readers on the
first non-ASCII byte, wrote tracked files in the wrong codec, and made a
guard that reads repo content silently fail open. ruff's PLW1514 is preview
and misses most of these forms, so this scan is the gate.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Our own Python; vendored trees and intentional-violation fixtures excluded.
SCOPES = ["scripts", "tests", "plugins", "tools/rttm", "emulator"]
SKIP_PARTS = {".venv", "node_modules", ".semgrep"}

FILE_IO = {"read_text", "write_text", "open", "NamedTemporaryFile", "TemporaryFile"}
SUBPROCESS = {"run", "check_output", "Popen", "call", "check_call"}


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _binary(call: ast.Call, name: str) -> bool:
    mode = _keyword(call, "mode")
    if mode is None and name == "open":
        positional = 1 if isinstance(call.func, ast.Name) else 0
        mode = call.args[positional] if len(call.args) > positional else None
    if mode is None and name in {"NamedTemporaryFile", "TemporaryFile"}:
        return True  # their default mode is "w+b"
    return isinstance(mode, ast.Constant) and "b" in str(mode.value)


def _findings(path: Path, root: Path = ROOT) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(root).as_posix()
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _keyword(node, "encoding") is not None:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in FILE_IO and not _binary(node, name):
            found.append(f"{rel}:{node.lineno}: {name}() without encoding=")
        elif name in SUBPROCESS and (
            _is_true(_keyword(node, "text"))
            or _is_true(_keyword(node, "universal_newlines"))
        ):
            found.append(f"{rel}:{node.lineno}: {name}(text=True) without encoding=")
    return found


def _sources() -> list[Path]:
    files = [*ROOT.glob("ROOT_AGENTS_hooks_*.py")]
    for scope in SCOPES:
        files.extend(
            path
            for path in (ROOT / scope).rglob("*.py")
            if not SKIP_PARTS.intersection(path.relative_to(ROOT).parts)
        )
    return sorted(files)


def test_the_scan_sees_our_code() -> None:
    names = {path.relative_to(ROOT).as_posix() for path in _sources()}
    assert "scripts/skills_lock.py" in names
    assert "tools/rttm/to_eaf.py" in names
    assert "ROOT_AGENTS_hooks_rtk-hook-claude.py" in names


@pytest.mark.parametrize(
    ("snippet", "flagged"),
    [
        ("p.read_text()", True),
        ('p.read_text(encoding="utf-8")', False),
        ('open(p, "rb")', False),
        ('p.open("rb")', False),
        ("open(p)", True),
        ("subprocess.run(cmd, text=True)", True),
        ('subprocess.run(cmd, text=True, encoding="utf-8")', False),
        ("subprocess.run(cmd, capture_output=True)", False),  # bytes
        ("tempfile.NamedTemporaryFile()", False),  # w+b by default
        ('tempfile.NamedTemporaryFile(mode="w")', True),
    ],
)
def test_the_scan_flags_only_locale_dependent_calls(
    tmp_path: Path, snippet: str, flagged: bool
) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(snippet + "\n", encoding="utf-8")
    assert bool(_findings(probe, root=tmp_path)) is flagged


def test_no_text_io_relies_on_the_locale_encoding() -> None:
    findings = [hit for path in _sources() for hit in _findings(path)]
    assert findings == [], "\n".join(findings)
