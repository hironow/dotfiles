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

# Resolve bash to an ABSOLUTE path once. argv[0] (the interpreter) may be
# absolute — only the *script argument* trips MSYS. Absolute also keeps bash
# findable for tests that pass a restricted ``env={"PATH": ...}``.
_BASH = shutil.which("bash") or "bash"


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
