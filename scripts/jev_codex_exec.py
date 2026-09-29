#!/usr/bin/env python3
"""pi-subagents command runner: let Jev pick the Codex model and effort, then run `codex exec`.

The built-in codex-exec adapters fix their argv (and ignore config.toml), so they cannot
select a model. This runner is the same one-shot run with `-m` and the reasoning effort
added. Prompt on stdin, final message on stdout, like every command-runner agent.
"""

from collections.abc import Callable
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import TextIO

from jev_core import CODEX_SANDBOXES, build_codex_exec_command
from jev_launch import choose_codex, jev_key


def _sandbox(argv: list[str]) -> str:
    """Functional core: the requested sandbox, read-only by default."""
    if not argv:
        return "read-only"
    if len(argv) == 2 and argv[0] == "--sandbox" and argv[1] in CODEX_SANDBOXES:
        return argv[1]
    raise ValueError(
        f"usage: jev_codex_exec.py [--sandbox {'|'.join(CODEX_SANDBOXES)}]"
    )


def _record(model: str, effort: str) -> None:
    """Optional evidence for the live verification; never the prompt or the key."""
    path = os.environ.get("JEV_HOOK_LOG")
    if path:
        record = {"kind": "codex-exec", "model": model, "effort": effort}
        with open(path, "a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")


def main(
    argv: list[str],
    stdin: TextIO,
    stdout: TextIO,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    choose: Callable[[str, str | None], tuple[str, str]] = choose_codex,
    key_of: Callable[[], str | None] = jev_key,
) -> int:
    try:
        sandbox = _sandbox(argv)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    prompt = stdin.read()
    model, effort = choose(prompt, key_of())
    print(f"Jev: codex {model} / {effort} ({sandbox})", file=sys.stderr)
    _record(model, effort)
    with tempfile.TemporaryDirectory() as tmp:
        final = Path(tmp) / "final-message.txt"
        command = build_codex_exec_command(model, effort, sandbox, str(final))
        result = run(
            command, input=prompt, text=True, stdout=subprocess.DEVNULL, check=False
        )
        if result.returncode != 0:
            return result.returncode
        message = final.read_text(encoding="utf-8").strip() if final.exists() else ""
    if not message:
        print("codex exec wrote no final message", file=sys.stderr)
        return 1
    stdout.write(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], sys.stdin, sys.stdout))
