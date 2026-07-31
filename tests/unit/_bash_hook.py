"""Portable invocation of bash hook scripts from unit tests.

Why this exists
---------------
Git's MSYS ``bash``, when launched from a **native-Windows** Python process
(not from inside an MSYS shell), has no drive mount table set up. As a result
it cannot open a script whose path is *absolute* (``C:\\...``, ``C:/...`` or
``/c/...``) **or ascends from cwd via ``..``** — every such form exits 127.
Only a path that **descends from cwd** resolves (verified: 5/5 reliable, while
the ``..`` form fails 5/5).

So when the script does not already live under ``cwd``, this helper stages it
(and any ``companions`` it resolves next to itself) into a throwaway subdir
*under* ``cwd`` and invokes it by that descendant path. ``cwd`` itself is never
changed, so the hook's cwd-based logic (config files, upward lockfile search,
env ``PATH``) is preserved. On POSIX all of this is a behavioural no-op.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _is_wsl_launcher(exe: str) -> bool:
    """True when ``exe`` is ``%SystemRoot%\\System32\\bash.exe`` (the WSL entry
    point), which is a distro launcher rather than a bash we can run scripts
    with."""
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    try:
        return Path(exe).parent.samefile(system32)
    except OSError:
        return False


def resolve_bash() -> str:
    """Absolute path to a bash that can actually run this repo's scripts.

    A bare ``bash`` lookup on native Windows finds
    ``%SystemRoot%\\System32\\bash.exe`` — the **WSL** launcher — because
    Windows resolves System32 ahead of ``PATH``. That bash runs inside the
    distro, where the host's ``jq`` / ``git`` are not installed, so hook
    scripts exit 127 (command not found) instead of exercising their logic;
    the tests then read that as a failure of the script under test.

    System32 ships no ``sh.exe``, so resolving ``sh`` and taking its sibling
    ``bash.exe`` lands on Git Bash. This is the same escape hatch the justfile
    uses via ``set windows-shell`` (see CLAUDE.md, "Windows の shell 選択").
    On POSIX this is a no-op.
    """
    found = shutil.which("bash")
    if os.name != "nt":
        return found or "bash"
    if found and not _is_wsl_launcher(found):
        return found
    sh = shutil.which("sh")
    if sh:
        sibling = Path(sh).with_name("bash.exe")
        if sibling.is_file():
            return str(sibling)
    return found or "bash"


# Resolve bash to an ABSOLUTE path once. argv[0] (the interpreter) may be
# absolute — only the *script argument* trips MSYS. Absolute also keeps bash
# findable for tests that pass a restricted ``env={"PATH": ...}``.
_BASH = resolve_bash()


def run_bash(
    script: str | os.PathLike[str],
    *args: str,
    cwd: str | os.PathLike[str],
    companions: tuple[str | os.PathLike[str], ...] = (),
    **kwargs: object,
) -> subprocess.CompletedProcess[str]:
    """Run ``bash <script> [args...]`` from ``cwd``, Windows-safely.

    ``companions`` are files the script self-locates next to itself (e.g.
    ``block-prohibited-commands.py``); they are staged alongside it. Remaining
    ``kwargs`` (``input``/``env``/``capture_output``/``text``/``check`` …) are
    forwarded to :func:`subprocess.run` unchanged.
    """
    # `text=True` alone decodes child output with the *locale* codec (cp932 on
    # a Japanese Windows), which throws on the utf-8 these scripts emit — and
    # it throws inside subprocess' reader thread, surfacing as an unrelated
    # warning rather than a readable failure. Pin utf-8 unless a caller asked
    # for something else.
    if kwargs.get("text") and "encoding" not in kwargs:
        kwargs["encoding"] = "utf-8"
    cwd_p = Path(os.fspath(cwd))
    script_p = Path(os.fspath(script))
    rel = os.path.relpath(script_p, cwd_p)
    if not rel.startswith(".."):
        # Script already descends from cwd — MSYS bash can open it directly.
        return subprocess.run(  # noqa: S603 - fixed argv, test-only helper
            [_BASH, rel.replace(os.sep, "/"), *args],
            cwd=str(cwd_p),
            **kwargs,  # type: ignore[arg-type]
        )
    # Script lives outside cwd: stage it (+ companions) into a descendant dir.
    staged = Path(tempfile.mkdtemp(prefix=".bashhook-", dir=cwd_p))
    try:
        shutil.copy(script_p, staged / script_p.name)
        for comp in companions:
            comp_p = Path(os.fspath(comp))
            shutil.copy(comp_p, staged / comp_p.name)
        staged_rel = os.path.relpath(staged / script_p.name, cwd_p).replace(os.sep, "/")
        return subprocess.run(  # noqa: S603 - fixed argv, test-only helper
            [_BASH, staged_rel, *args],
            cwd=str(cwd_p),
            **kwargs,  # type: ignore[arg-type]
        )
    finally:
        shutil.rmtree(staged, ignore_errors=True)
