"""The old hook scripts' bugs that the agent-hook binary fixes, as named edits.

The owner decided (2026-11-04) that where an old script has a bug, the binary
fixes it, and the tests keep each fix apart from the faithful port. Each fix
here is a small edit to an old script. The corpus generators apply them to
copies of the scripts ("the old script, fixed"), so the fixed behavior is
defined by a script, as the legacy behavior is, never by Go.

Every corpus input runs through the old scripts and through the scripts with
every fix. Where the answers (after the corpus's own noise normalization)
differ, the binary gives the fixed answer, and the run names the fixes it
needs: the smallest set of them that alone gives the full answer.
"""

import itertools
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES_GUARD = "ROOT_AGENTS_hooks_block-prohibited-files.sh"
FORMATTER = "ROOT_AGENTS_hooks_format-after-edit.sh"
COMMAND_GUARD = "ROOT_AGENTS_hooks_block-prohibited-commands.py"


def _inserted(fix: str) -> str:
    """The code a fix inserts: scripts/fixed_<fix>.py between its markers,
    kept there so that it is linted and tested as Python."""
    text = (ROOT / "scripts" / f"fixed_{fix.replace('-', '_')}.py").read_text(
        encoding="utf-8"
    )
    begin, end = f"# --- fixed-{fix}: begin ---\n", f"# --- fixed-{fix}: end ---\n"
    return text[text.index(begin) + len(begin) : text.index(end)]


@dataclass(frozen=True)
class Fix:
    """One fix: edits to one script, each an exact text replaced once."""

    script: str
    edits: tuple[tuple[str, str], ...]
    bug: str


_OLD_OPERATOR = '            if token and all(ch in "();<>|&" for ch in token):\n                if ">" in token:\n                    pending_redirect = True\n                if token in COMMAND_SEPARATORS:\n                    self._finalize(name, args)\n                    name, args, at_start, in_rtk = None, [], True, False\n                    rtk_ran = shell_string = skip_value = False\n                continue\n            if pending_redirect:\n                pending_redirect = False\n                if _is_yml_name(token):\n'
_NEW_OPERATOR = '            if isinstance(token, _Op):\n                # fixed-command-split: an operator is one only where bash reads\n                # one; every redirection takes the next word as its operand,\n                # and the .yml rule reads the operands of those that write.\n                if token in _REDIRECTIONS:\n                    pending_redirect = True\n                    redirect_writes = ">" in token\n                if token in COMMAND_SEPARATORS:\n                    self._finalize(name, args)\n                    name, args, at_start, in_rtk = None, [], True, False\n                    rtk_ran = shell_string = skip_value = False\n                continue\n            if pending_redirect:\n                pending_redirect = False\n                if redirect_writes and _is_yml_name(token):\n'
_OLD_ANALYZE = "    cleaned, code_bodies = split_heredocs(text)\n    for pattern, reason in RAW_GUARDS:\n        if pattern.search(cleaned):\n            block(reason)\n    try:\n        tokens = _tokenize(cleaned)\n    except ValueError:\n        _legacy_scan(cleaned)\n    else:\n        _CommandWalker().walk(tokens)\n    for body in code_bodies:\n        analyze(body, depth + 1)\n"
_NEW_ANALYZE = "    # fixed-command-split: the text as bash reads it: its words and\n    # operators, its heredocs, and the commands of its substitutions.\n    try:\n        lexed = _bash_lex(text)\n    except _Unterminated as unterminated:\n        # A quote or substitution does not end. bash runs the complete lines\n        # before its line: those are walked; the old pipeline reads it all.\n        cleaned, code_bodies = split_heredocs(text)\n        for pattern, reason in RAW_GUARDS:\n            if pattern.search(cleaned):\n                block(reason)\n        before = _bash_lex(text[: unterminated.line_start])\n        _CommandWalker().walk(before.tokens)\n        _legacy_scan(cleaned)\n        for body in code_bodies + before.code_bodies + before.substitutions:\n            analyze(body, depth + 1)\n        return\n    cleaned = lexed.cleaned(text)\n    for pattern, reason in RAW_GUARDS:\n        if pattern.search(cleaned):\n            block(reason)\n    _CommandWalker().walk(lexed.tokens)\n    for body in lexed.code_bodies + lexed.substitutions:\n        analyze(body, depth + 1)\n"

FIXES: dict[str, Fix] = {
    "dash-line": Fix(
        script=FILES_GUARD,
        edits=(
            (
                '  base="$(basename "$file_path")"\n',
                (
                    "  # fixed-dash-line: no basename(1). On a line that starts with -\n"
                    "  # it failed (or, on GNU, printed a message), the guard exited 1,\n"
                    "  # and no later line was checked. Trailing slashes go, then\n"
                    "  # everything up to the last /.\n"
                    '  base="${file_path%"${file_path##*[!/]}"}"\n'
                    '  base="${base##*/}"\n'
                    '  [ -n "$base" ] || base=/\n'
                ),
            ),
        ),
        bug="A line that starts with - made basename(1) fail; the guard then exited 1 "
        "(no harness blocks on that) and checked no later line, nor that one.",
    ),
    "notebook-path": Fix(
        script=FILES_GUARD,
        edits=(
            (
                '[ -z "$paths" ] && exit 0\n',
                (
                    "# fixed-notebook-path: NotebookEdit names its file notebook_path.\n"
                    "# Check it too, on its own, beside what was read above.\n"
                    "notebook=\"$(printf '%s' \"$input\" | jq -r '.tool_input.notebook_path // empty')\"\n"
                    'if [ -n "$notebook" ]; then\n'
                    "  nl=$'\\n'\n"
                    '  paths="${paths:+$paths$nl}$notebook"\n'
                    "fi\n"
                    '[ -z "$paths" ] && exit 0\n'
                ),
            ),
        ),
        bug="The guard read file_path only, so NotebookEdit's notebook_path was never checked.",
    ),
    "docs-agents-relative": Fix(
        script=FILES_GUARD,
        edits=(
            (
                "    */AGENTS.md|AGENTS.md|*/CLAUDE.md|CLAUDE.md|*/docs/agents/*) return 0 ;;\n",
                (
                    "    # fixed-docs-agents-relative: a relative path under docs/agents/ too,\n"
                    "    # as Codex's patch names its files; a bare AGENTS.md was already exempt.\n"
                    "    */AGENTS.md|AGENTS.md|*/CLAUDE.md|CLAUDE.md|*/docs/agents/*|docs/agents/*) return 0 ;;\n"
                ),
            ),
        ),
        bug="The exemption */docs/agents/* needs a / before docs, so a relative path under "
        "docs/agents/ (as Codex's patch names files) was blocked, though a bare AGENTS.md is exempt.",
    ),
    "one-path": Fix(
        script=FORMATTER,
        edits=(
            (
                'input="$(cat)"\n',
                (
                    'input="$(cat)"\n'
                    "# fixed-one-path: a string file_path names one file, exactly as given:\n"
                    "# a newline inside it or at its end is part of the name, and a NUL\n"
                    "# names none. Only a patch names several files, one per line.\n"
                    "kind=\"$(printf '%s' \"$input\" | jq -r 'try (.tool_input.file_path\n"
                    '  | if type == "string" and . != "" then (if index("\\u0000") then "nul" else "one" end)\n'
                    '    else "other" end) catch "other"\')"\n'
                    '[ "$kind" = nul ] && exit 0\n'
                    'if [ "$kind" = one ]; then\n'
                    "  one=\"$(printf '%s' \"$input\" | jq -j '.tool_input.file_path'; printf x)\"\n"
                    '  one="${one%x}"\n'
                    "fi\n"
                ),
            ),
            (
                "while IFS= read -r file_path; do\n",
                (
                    "# One path is read whole, up to its NUL; lines, one by one.\n"
                    "delim=$'\\n'\n"
                    "[ \"$kind\" = one ] && delim=''\n"
                    'while IFS= read -r -d "$delim" file_path; do\n'
                ),
            ),
            (
                "done < <(printf '%s\\n' \"$paths\")\n",
                (
                    "done < <(\n"
                    '  if [ "$kind" = one ]; then\n'
                    "    printf '%s\\0' \"$one\"\n"
                    "  else\n"
                    "    printf '%s\\n' \"$paths\"\n"
                    "  fi\n"
                    ")\n"
                ),
            ),
        ),
        bug="The formatter formatted each line of file_path, NULs and trailing newlines "
        "dropped, so it could format a file the tool never wrote.",
    ),
    "command-split": Fix(
        script=COMMAND_GUARD,
        edits=(
            (
                'COMMAND_SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", ";;"}\n',
                (
                    "# fixed-command-split: a newline and every control operator end a command.\n"
                    'COMMAND_SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", ";;", "\\n", "|&", ";&", ";;&"}\n'
                ),
            ),
            (_OLD_OPERATOR, _NEW_OPERATOR),
            (
                "def _tokenize(text: str) -> list[str]:\n",
                _inserted("command-split")
                + "\n\ndef _tokenize(text: str) -> list[str]:\n",
            ),
            (_OLD_ANALYZE, _NEW_ANALYZE),
        ),
        bug="The guard split a command with Python's shlex, not as bash does: a newline, "
        "operators written together (`);`), a # inside a word, a redirection before the "
        "name, command and process substitutions, a heredoc body bash expands, and the "
        "lines after a << in a comment or in quotes hid a command; a quoted ; was a separator.",
    ),
    "command-start": Fix(
        script=COMMAND_GUARD,
        edits=(
            (
                "        at_start = True\n        pending_redirect = False\n",
                (
                    "        at_start = True\n        pending_redirect = False\n"
                    "        function_name = False  # fixed-command-start: the word after `function`\n"
                    "        def unquoted(token: str) -> bool:\n"
                    '            """fixed-command-start: a quoted word is never a reserved word."""\n'
                    '            return type(token).__name__ != "_Quoted"\n'
                    "\n"
                    "        case_states: list[str] = []  # fixed-command-start: each open case\n"
                    "        # fixed-command-start: coproc NAME before a compound command names it\n"
                    "        tokens = [\n"
                    "            token\n"
                    "            for k, token in enumerate(tokens)\n"
                    '            if not (k and tokens[k - 1] == "coproc" and unquoted(tokens[k - 1]) and k + 1 < len(tokens)\n'
                    "                    and unquoted(tokens[k + 1])\n"
                    '                    and tokens[k + 1] in {"{", "(", "if", "while", "until", "for", "case", "select", "[["})\n'
                    "        ]\n"
                ),
            ),
            (
                "                if ASSIGNMENT_RE.match(token):\n                    continue\n",
                (
                    "                if ASSIGNMENT_RE.match(token):\n                    continue\n"
                    "                # fixed-command-start: bash starts a command after these\n"
                    "                # reserved words and after exec; `function NAME` names one.\n"
                    "                if function_name:\n"
                    "                    function_name = False\n"
                    "                    continue\n"
                    '                if token == "function" and unquoted(token):\n'
                    "                    function_name = True\n"
                    "                    continue\n"
                    '                if token == "case" and unquoted(token):\n'
                    '                    case_states.append("subject")\n'
                    "                    continue\n"
                    "                # exec is a builtin, no reserved word: quoted, it is still exec\n"
                    '                if token == "exec" or (unquoted(token) and token in {"!", "{", "if", "then", "elif", "else", "do", "while", "until", "coproc"}):\n'
                    "                    continue\n"
                ),
            ),
            (
                "        for token in tokens:\n",
                (
                    "        for token in tokens:\n"
                    "            # fixed-command-start: in a case, the subject and the\n"
                    "            # patterns are no commands; the bodies are.\n"
                    '            is_op = type(token).__name__ == "_Op" or (\n'
                    '                "_Op" not in globals()\n'
                    "                and bool(token)\n"
                    '                and all(ch in "();<>|&" for ch in token)\n'
                    "            )\n"
                    "            # a redirection's operand comes first (<<<esac in a body is no esac)\n"
                    "            operand = pending_redirect and not is_op\n"
                    '            top = case_states[-1] if case_states and not operand else ""\n'
                    '            if top in ("subject", "in") and not is_op:\n'
                    '                if top == "subject" or (token == "in" and unquoted(token)):\n'
                    '                    case_states[-1] = "in" if top == "subject" else "pattern"\n'
                    "                continue\n"
                    '            if top == "pattern":\n'
                    "                if not is_op:\n"
                    '                    if token == "esac" and unquoted(token):\n'
                    "                        case_states.pop()\n"
                    "                    continue\n"
                    '                if token == ")":\n'
                    '                    case_states[-1] = "body"\n'
                    "                    continue\n"
                    '                if token in ("(", "|", "\\n"):\n'
                    "                    continue\n"
                    '            if top == "body" and is_op and token in (";;", ";&", ";;&"):\n'
                    '                case_states[-1] = "pattern"\n'
                    '            if top == "body" and not is_op and at_start and token == "esac" and unquoted(token):\n'
                    "                case_states.pop()\n"
                    "                continue\n"
                ),
            ),
        ),
        bug="After the reserved words that start a command (do, then, {, !, if ...), after "
        "exec, and after coproc's name, the guard took that word as the command's name, so "
        "the command itself went unchecked.",
    ),
    "shell-string": Fix(
        script=COMMAND_GUARD,
        edits=(
            (
                'class _CommandWalker:\n    """Token walk with the minimal shell grammar from enforcement.md."""\n',
                (
                    'class _CommandWalker:\n    """Token walk with the minimal shell grammar from enforcement.md."""\n\n'
                    "    # fixed-shell-string: the depth of the text a walker reads, set by\n"
                    "    # analyze() just before it makes one.\n"
                    "    next_depth = 0\n\n"
                    "    def __init__(self) -> None:\n"
                    "        self.depth = _CommandWalker.next_depth\n"
                ),
            ),
            (
                "def analyze(text: str, depth: int = 0) -> None:\n    if depth > 2:\n        return\n",
                (
                    "def analyze(text: str, depth: int = 0) -> None:\n    if depth > 2:\n        return\n"
                    "    _CommandWalker.next_depth = depth  # fixed-shell-string\n"
                ),
            ),
            (
                "        if name in YML_CREATION_COMMANDS:\n            self._check_yml_creation(name, args)\n",
                (
                    "        if name in YML_CREATION_COMMANDS:\n            self._check_yml_creation(name, args)\n"
                    "        # fixed-shell-string: a shell's -c string and eval's words are commands.\n"
                    '        if name in {"sh", "bash", "zsh", "dash", "ksh"}:\n'
                    "            command = self._shell_string(args)\n"
                    "            if command is not None:\n"
                    "                analyze(command, self.depth + 1)\n"
                    '        if name == "eval":\n'
                    '            words = args[1:] if args[:1] == ["--"] else args\n'
                    "            if words:\n"
                    '                analyze(" ".join(words), self.depth + 1)\n\n'
                    "    @staticmethod\n"
                    "    def _shell_string(args: list[str]) -> str | None:\n"
                    '        """The operand a shell runs with -c: its first after the options."""\n'
                    "        has_c, i = False, 0\n"
                    "        while i < len(args):\n"
                    "            arg = args[i]\n"
                    '            if arg in ("--", "-"):\n'
                    "                i += 1\n"
                    "                break\n"
                    '            if arg.startswith("--"):\n'
                    '                i += 2 if arg in ("--rcfile", "--init-file") else 1\n'
                    "                continue\n"
                    '            if len(arg) > 1 and arg[0] in "-+":\n'
                    "                # a letter that takes a value takes the rest of the word,\n"
                    "                # or the next word when nothing follows it (zsh -oNAME)\n"
                    "                i += 1\n"
                    "                for k, letter in enumerate(arg[1:], 1):\n"
                    '                    if letter in "oO":\n'
                    "                        i += 1 if k == len(arg) - 1 else 0\n"
                    "                        break\n"
                    '                    has_c = has_c or (arg[0] == "-" and letter == "c")\n'
                    "                continue\n"
                    "            break\n"
                    "        return args[i] if has_c and i < len(args) else None\n"
                ),
            ),
        ),
        bug="The strings a shell runs with -c (sh, bash, zsh, dash, ksh) and the words eval "
        "runs were never read as commands.",
    ),
}


def apply_fixes(text: str, fixes: Iterable[Fix]) -> str:
    """The script's text with the fixes' edits made. Each edit's old text must
    be there exactly once, so a change to the old script fails loudly."""
    for fix in fixes:
        for old, new in fix.edits:
            if text.count(old) != 1:
                msg = (
                    f"{fix.script}: {old!r} is there {text.count(old)} times, not once"
                )
                raise ValueError(msg)
            text = text.replace(old, new)
    return text


def write_scripts(directory: Path, names: frozenset[str]) -> Path:
    """Copies of every old hook script (ROOT_AGENTS_hooks_*) in directory,
    under their own names, with the named fixes made. Scripts that call each
    other by name (guard-codex.sh runs "$dir/$1") work there as in the repo,
    and bash's warnings name the same scripts. A copy with edits must start:
    one that does not would answer with its error, as if a fix did it."""
    unknown = names - FIXES.keys()
    if unknown:
        msg = f"no such fixes: {sorted(unknown)}"
        raise ValueError(msg)
    directory.mkdir(parents=True, exist_ok=True)
    for source in sorted(ROOT.glob("ROOT_AGENTS_hooks_*")):
        target = directory / source.name
        mine = [
            FIXES[name] for name in sorted(names) if FIXES[name].script == source.name
        ]
        if mine:
            target.write_text(
                apply_fixes(source.read_text(encoding="utf-8"), mine), encoding="utf-8"
            )
            shutil.copymode(source, target)
            _refuse_a_copy_that_does_not_start(target)
        else:
            shutil.copy2(source, target)
    return directory


def _refuse_a_copy_that_does_not_start(path: Path) -> None:
    """A Python copy must compile, and a shell copy must pass bash -n."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        try:
            compile(text, str(path), "exec")
        except SyntaxError as error:
            msg = f"{path.name}: the fixed copy does not start: {error}"
            raise ValueError(msg) from error
        return
    checked = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if checked.returncode != 0:
        msg = f"{path.name}: the fixed copy does not start: {checked.stderr.strip()}"
        raise ValueError(msg)


def every_set(names: Iterable[str]) -> list[frozenset[str]]:
    """Every set of the named fixes, the empty one and the full one included:
    the copies a generator writes, since needed() may ask for any of them."""
    names = sorted(names)
    return [
        frozenset(subset)
        for size in range(len(names) + 1)
        for subset in itertools.combinations(names, size)
    ]


def needed(
    names: Iterable[str], answer_of: Callable[[frozenset[str]], object]
) -> list[str]:
    """The fixes a run needs, sorted: when the answer with every fix differs
    from the old script's, the smallest set of fixes that alone gives that
    answer, the first by name among sets of that size. Where one fix gives
    it, or several are needed together, this is the set whose every member's
    absence changes it; where fixes each give it alone, it is the first."""
    names = tuple(sorted(names))
    full = answer_of(frozenset(names))
    if full == answer_of(frozenset()):
        return []
    for size in range(1, len(names) + 1):
        for subset in itertools.combinations(names, size):
            if answer_of(frozenset(subset)) == full:
                return list(subset)
    msg = "unreachable: the full set gives the full answer"
    raise AssertionError(msg)


def difference(fixes: Iterable[str], noise: str) -> str:
    """A run's difference: each needed fix as fixed-<name>, and the reference
    run's noise ID, sorted and joined by +."""
    parts = [f"fixed-{name}" for name in fixes]
    if noise:
        parts.append(noise)
    return "+".join(sorted(parts))


def refuse_a_base_that_needs_a_fix(name: str, base_name: str, base_run: dict) -> None:
    """A derived input (its base plus an unused member) takes its base's
    answer, so its base must be one the binary answers as the old script, or
    differing only in noise: a base run that names a fix is refused."""
    if any(part.startswith("fixed-") for part in base_run["difference"].split("+")):
        msg = f"{name}: its base {base_name} needs a fix of the old script"
        raise ValueError(msg)
