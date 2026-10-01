#!/usr/bin/env python3
"""The environment Windows persists for the User or the Machine (the registry).

A fresh process, a service or a scheduled task sees these values, not what a
shell exported, so harden-env writes there and doctor reads there. One reader
for ai_tools_check (telemetry switches) and claude_git_bash
(CLAUDE_CODE_GIT_BASH_PATH); each caller keeps its own policy for a key that
cannot be opened.
"""

import sys
from collections.abc import Iterable

MACHINE_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def persisted(names: Iterable[str], *, machine: bool = False) -> dict[str, str] | None:
    """The persisted values among `names` that are set; None off Windows.

    Raises OSError when the scope's key cannot be opened; a name with no value
    is left out of the result.
    """
    if sys.platform != "win32":
        return None
    import winreg

    root, path = (
        (winreg.HKEY_LOCAL_MACHINE, MACHINE_KEY)
        if machine
        else (winreg.HKEY_CURRENT_USER, "Environment")
    )
    values: dict[str, str] = {}
    with winreg.OpenKey(root, path) as key:
        for name in names:
            try:
                values[name] = str(winreg.QueryValueEx(key, name)[0])
            except OSError:
                continue
    return values
