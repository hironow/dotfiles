#!/usr/bin/env python3
"""PreToolUse guard for Bash commands — parser-based, stdlib only.

Invoked by the thin block-prohibited-commands.sh wrapper. Reads Claude Code
tool input JSON on stdin and answers via exit code: 0 = allow, 2 = block
(stderr becomes the reason fed back to the agent). exit 1 would NOT block.

Pipeline (full semantics: docs/agents/enforcement.md):

1. Heredoc separation (line state machine). Bodies consumed by data sinks
   (cat, gh, git, tee, ...) are opaque prose and dropped before any scan;
   bodies fed to interpreters (bash, python, node, ...) are executable code
   and are re-analyzed recursively.
2. Raw-string guards on the heredoc-cleaned text for destructive/IaC
   commands (rm -rf /, gcloud/cdr mutations) — over-blocking is the safe
   side there, so quoting is deliberately ignored.
3. shlex tokenization (POSIX, punctuation_chars): quoted prose collapses
   into single tokens that never equal a tool name, across lines too.
4. Token walk with a minimal shell grammar: command boundaries are
   ; && || | & ( ); NAME=VALUE prefixes and wrappers (env/sudo/...) are
   skipped at command start; redirect operators consume the next token as
   their operand. Guards: pip/poetry/pipenv, npm/yarn, make (command name,
   basename-resolved), per-invocation pnpm lockfile gate, force-push to a
   protected branch (any force flag + a main/master refspec, order- and
   spelling-independent, including the flagless `+<refspec>` syntax), and
   .yml-creation detection (redirect targets, touch/tee args, cp/mv
   destinations).

If tokenization still fails after heredoc separation, tooling guards fall
back to the previous line-based quote-strip regex scan — never worse than
the old implementation. Known accepted long tail: quoted invocations
(bash -c "npm i") and wrapper forms outside the known set (mise exec -- ...).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

EXIT_ALLOW = 0
EXIT_BLOCK = 2

MSG_PIP = (
    "Python package management is 'uv' only (uv add / uv sync / uv run). "
    "Do not use pip/poetry/pipenv."
)
MSG_NODE = (
    "Node package management is 'bun' (or 'pnpm' iff pnpm-lock.yaml exists). "
    "Do not use npm/yarn."
)
MSG_MAKE = (
    "Task automation is 'just' only. Add a recipe to the root justfile "
    "instead of using make."
)
MSG_PNPM = (
    "'pnpm' is allowed only when pnpm-lock.yaml governs each pnpm "
    "invocation's target directory (resolved cd/-C/--dir target or cwd, "
    "searched upward). Use 'bun' instead — or, for a legitimate cross-repo "
    "call this guard can't resolve, ask the user to run it with the '!' "
    "prefix."
)
MSG_YML = (
    "creates a '.yml' file via Bash. This project uses '.yaml' exclusively "
    "(and 'compose.yaml', not docker-compose.*) — write the .yaml name "
    "instead."
)
MSG_FORCE_PUSH = (
    "Refusing force-push to a protected branch (main/master). Open a PR; "
    "never rewrite shared history on the default branch."
)

PIP_COMMANDS = {"pip", "pip3", "poetry", "pipenv"}
NODE_COMMANDS = {"npm", "yarn"}
WRAPPERS = {"env", "sudo", "time", "nohup", "command", "xargs"}
INTERPRETERS = {
    "sh",
    "bash",
    "zsh",
    "dash",
    "ksh",
    "python",
    "python3",
    "node",
    "deno",
    "bun",
    "ruby",
    "perl",
    "uv",
    "uvx",
    "npx",
}
COMMAND_SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", ";;"}
YML_CREATION_COMMANDS = {"touch", "tee", "cp", "mv"}
PROTECTED_REFS = {"main", "master"}
FORCE_PUSH_FLAGS = {"-f", "--force", "--force-if-includes"}

ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_OPEN_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
INTERPRETER_WORD_RE = re.compile(
    r"(^|[\s;&|(])(" + "|".join(sorted(INTERPRETERS)) + r")\b"
)

RAW_GUARDS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"rm[\s]+(-[a-zA-Z]*[rR][a-zA-Z]*[\s]+)?(-[a-zA-Z]*f[a-zA-Z]*[\s]+)?/($|[\s])"
        ),
        "Refusing 'rm -rf /' (or equivalent root deletion).",
    ),
    (
        re.compile(r"gcloud[\s].*(add-iam-policy-binding|set-iam-policy)"),
        "IAM changes go through OpenTofu (iam_*.tf) + PR, not gcloud. See "
        "docs/agents/iac-drift-policy.md.",
    ),
    (
        re.compile(
            r"gcloud[\s]+(compute|run|sql|secrets)[\s].*"
            r"(set-machine-type|resize|update|deploy|versions[\s]+add)"
        ),
        "This gcloud command mutates IaC-managed infra and will drift from "
        "tofu. Open an IaC PR. (Read-only debug is fine; emergency rollback "
        "must be followed by an IaC PR same session.)",
    ),
    (
        re.compile(r"cdr[\s]+workspaces[\s]+(update|edit)"),
        "Patch the Coder template (coder_parameter), not the running "
        "workspace. See docs/agents/iac-drift-policy.md.",
    ),
]


def block(reason: str) -> None:
    print(f"BLOCKED: {reason}", file=sys.stderr)
    sys.exit(EXIT_BLOCK)


def _basename(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _is_yml_name(token: str) -> bool:
    base = _basename(token)
    return base.endswith(".yml") or base in {"docker-compose.yaml"}


def _is_force_push_flag(token: str) -> bool:
    """True for any git push flag that rewrites the remote ref."""
    if token in FORCE_PUSH_FLAGS:
        return True
    # --force-with-lease and --force-with-lease=<ref>[:<expect>]
    return token == "--force-with-lease" or token.startswith("--force-with-lease=")


def _force_pushes_protected_ref(args: list[str]) -> bool:
    """True if this push rewrites main/master.

    Two force spellings: any force flag combined with a refspec that
    resolves to a protected branch, or the flagless `+<refspec>` syntax
    (`git push origin +main`), which forces that refspec on its own.
    Refspecs handled: bare names (`main`), `src:dst` (`HEAD:main`) and
    fully-qualified refs (`refs/heads/main`). Flags and the remote name
    are positionals too, but neither resolves to a protected branch, so
    they are simply not matched.
    """
    has_force_flag = any(_is_force_push_flag(a) for a in args)
    for arg in args:
        if arg.startswith("-"):
            continue
        forced_refspec = arg.startswith("+")
        dest = arg.lstrip("+").rsplit(":", 1)[-1]  # src:dst refspec -> dst
        dest = dest.rsplit("/", 1)[-1]  # refs/heads/main -> main
        if dest in PROTECTED_REFS and (has_force_flag or forced_refspec):
            return True
    return False


def split_heredocs(text: str) -> tuple[str, list[str]]:
    """Drop data-heredoc bodies; collect interpreter-heredoc bodies as code."""
    cleaned: list[str] = []
    code_bodies: list[str] = []
    body: list[str] = []
    pending: tuple[str, bool] | None = None  # (delimiter, body_is_code)
    for line in text.split("\n"):
        if pending is not None:
            delimiter, is_code = pending
            if line.strip() == delimiter:
                if is_code:
                    code_bodies.append("\n".join(body))
                body = []
                pending = None
                continue
            if is_code:
                body.append(line)
            continue
        match = HEREDOC_OPEN_RE.search(line)
        cleaned.append(line)
        if match:
            is_code = INTERPRETER_WORD_RE.search(line) is not None
            pending = (match.group(2), is_code)
    if pending is not None and pending[1]:
        code_bodies.append("\n".join(body))
    return "\n".join(cleaned), code_bodies


def find_pnpm_lock_upward(directory: str) -> bool:
    try:
        current = Path(directory).resolve(strict=True)
    except OSError:
        return False
    if not current.is_dir():
        return False
    while True:
        if (current / "pnpm-lock.yaml").is_file():
            return True
        if current.parent == current:
            return False
        current = current.parent


def _resolve_dir(target: str, base: str | None) -> str | None:
    """Resolve a cd/-C/--dir target; None means unresolvable (fail safe)."""
    if not target or "$" in target or "`" in target:
        return None
    target = os.path.expanduser(target)
    if os.path.isabs(target):
        return target
    if base is None:
        return None
    return os.path.join(base, target)


class _CommandWalker:
    """Token walk with the minimal shell grammar from enforcement.md."""

    def __init__(self) -> None:
        self.effective_dir: str | None = os.getcwd()

    def walk(self, tokens: list[str]) -> None:
        at_start = True
        pending_redirect = False
        name: str | None = None
        args: list[str] = []
        for token in tokens:
            if token and all(ch in "();<>|&" for ch in token):
                if ">" in token:
                    pending_redirect = True
                if token in COMMAND_SEPARATORS:
                    self._finalize(name, args)
                    name, args, at_start = None, [], True
                continue
            if pending_redirect:
                pending_redirect = False
                if _is_yml_name(token):
                    block(f"'> {token}' {MSG_YML}")
                continue
            if at_start:
                if ASSIGNMENT_RE.match(token):
                    continue
                if _basename(token) in WRAPPERS:
                    continue
                name = _basename(token)
                at_start = False
                continue
            args.append(token)
        self._finalize(name, args)

    def _finalize(self, name: str | None, args: list[str]) -> None:
        if name is None:
            return
        if name in PIP_COMMANDS:
            block(MSG_PIP)
        if name in NODE_COMMANDS:
            block(MSG_NODE)
        if name == "make":
            block(MSG_MAKE)
        if name == "git" and "push" in args:
            if _force_pushes_protected_ref(args):
                block(MSG_FORCE_PUSH)
        if name == "cd":
            target = args[0] if args else "~"
            self.effective_dir = _resolve_dir(target, self.effective_dir)
            return
        if name == "pnpm":
            self._check_pnpm(args)
        if name in YML_CREATION_COMMANDS:
            self._check_yml_creation(name, args)

    def _check_pnpm(self, args: list[str]) -> None:
        check_dir = self.effective_dir
        for i, arg in enumerate(args):
            if arg in {"-C", "--dir"} and i + 1 < len(args):
                check_dir = _resolve_dir(args[i + 1], self.effective_dir)
                break
            if arg.startswith("--dir="):
                check_dir = _resolve_dir(arg.split("=", 1)[1], self.effective_dir)
                break
        if check_dir is None or not find_pnpm_lock_upward(check_dir):
            block(MSG_PNPM)

    def _check_yml_creation(self, name: str, args: list[str]) -> None:
        positional = [a for a in args if not a.startswith("-")]
        if name in {"touch", "tee"}:
            for arg in positional:
                if _is_yml_name(arg):
                    block(f"'{name} {arg}' {MSG_YML}")
        elif name in {"cp", "mv"} and positional:
            dest = positional[-1]
            if _is_yml_name(dest):
                block(f"'{name} ... {dest}' {MSG_YML}")


def _tokenize(text: str) -> list[str]:
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _legacy_scan(text: str) -> None:
    """Pre-parser behavior, used only when tokenization fails."""
    stripped_lines = []
    for line in text.split("\n"):
        line = re.sub(r'"[^"]*"', "", line)
        line = re.sub(r"'[^']*'", "", line)
        stripped_lines.append(line)
    scan = "\n".join(stripped_lines)
    if re.search(r"(^|[^\w./-])(pip3?|poetry|pipenv)(\s|$)", scan):
        block(MSG_PIP)
    if re.search(r"(^|[^\w./-])(npm|yarn)(\s|$)", scan):
        block(MSG_NODE)
    if re.search(r"(^|[^\w./-])make(\s|$)", scan):
        block(MSG_MAKE)
    if re.search(r"(^|[^\w./-])pnpm(\s|$)", scan) and not find_pnpm_lock_upward(
        os.getcwd()
    ):
        block(MSG_PNPM)


def analyze(text: str, depth: int = 0) -> None:
    if depth > 2:
        return
    cleaned, code_bodies = split_heredocs(text)
    for pattern, reason in RAW_GUARDS:
        if pattern.search(cleaned):
            block(reason)
    try:
        tokens = _tokenize(cleaned)
    except ValueError:
        _legacy_scan(cleaned)
    else:
        _CommandWalker().walk(tokens)
    for body in code_bodies:
        analyze(body, depth + 1)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return EXIT_ALLOW
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str) or not command.strip():
        return EXIT_ALLOW
    analyze(command)
    return EXIT_ALLOW


if __name__ == "__main__":
    sys.exit(main())
