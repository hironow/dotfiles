"""The code that the fixed-command-split edit (scripts/old_script_fixes.py)
puts into the Python command guard: a lexer that reads a text as bash does.

The old guard split a command with Python's shlex, which is not bash: a
newline was a space, adjacent operators were one token, a # inside a word
started a comment, and heredocs were found by a line pattern before any
quoting was known. This lexer splits words and operators where bash does,
finds heredocs at real << operators, and returns what bash runs as code: the
bodies of command and process substitutions, and the heredoc bodies fed to an
interpreter. The text without its heredoc bodies is what the guard's raw
patterns read.

Only the text between the two markers goes into the guard, which has its own
`re` and INTERPRETER_WORD_RE; the copy here is for this file's tests
(tests/unit/test_fixed_command_split.py checks that it is the guard's).
"""

from __future__ import annotations

import re

INTERPRETER_WORD_RE = re.compile(
    r"(^|[\s;&|(])(bash|bun|dash|deno|ksh|node|npx|perl|python|python3|ruby|sh|uv|uvx|zsh)\b"
)

# --- fixed-command-split: begin ---


class _Op(str):
    """An operator token, so that a quoted ';' stays a word."""

    __slots__ = ()


class _Quoted(str):
    """A word written with a quote, an escape, or an expansion: bash never
    reads it as a reserved word ("case" is a command's name)."""

    __slots__ = ()


class _Unterminated(ValueError):
    """A quote or substitution that does not end. line_start is where its
    line begins, after the last top-level newline before it: the lines before
    it are complete, and bash runs them."""

    def __init__(self, line_start: int) -> None:
        super().__init__("a quote or substitution does not end")
        self.line_start = line_start


class _Lexed:
    """What the lexer read: the tokens, what bash runs as code (substitution
    bodies, and heredoc bodies fed to an interpreter), and where the heredoc
    bodies are, so that the text without them can be read by the raw
    patterns."""

    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.substitutions: list[str] = []
        self.code_bodies: list[str] = []
        self.removed: list[tuple[int, int]] = []
        self.end = 0

    def cleaned(self, text: str) -> str:
        """The text without its heredoc bodies."""
        kept: list[str] = []
        at = 0
        for start, stop in sorted(self.removed):
            kept.append(text[at : max(at, start)])
            at = max(at, stop)
        kept.append(text[at:])
        return "".join(kept)


# bash's operators, longest first, so that each is read by longest match
_OPERATORS = (
    ";;&", "<<<", "<<-", "&>>",
    "&&", "||", ";;", ";&", "|&", "<<", "<&", "<>", ">>", ">&", ">|", "&>",
    "&", ";", "|", "(", ")", "<", ">",
)  # fmt: skip
_REDIRECTIONS = frozenset(
    {"<<<", "<<-", "&>>", "<<", "<&", "<>", ">>", ">&", ">|", "&>", "<", ">"}
)
_CONTROL_OPERATORS = frozenset(
    {"\n", ";", "&", "&&", "||", "|", "|&", "(", ")", ";;", ";&", ";;&"}
)
# the reserved words after which bash still starts a command
_KEEPS_COMMAND_START = frozenset(
    {"!", "{", "if", "then", "elif", "else", "do", "while", "until", "time"}
)
_ARRAY_OPEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?\+?=")
_DESCRIPTOR = re.compile(r"[0-9]+|\{[A-Za-z_][A-Za-z0-9_]*\}")
# a word written with any of these is quoted, or expanded: never a reserved word
_QUOTING = "'\"\\$`"


def _bash_lex(text: str) -> _Lexed:
    """Lexes a whole text."""
    return _lex(text, 0, False, [0])


def _lex(text: str, i: int, nested: bool, line_start: list[int]) -> _Lexed:
    """Lexes from i to the end of the text or, nested, to the ) that closes a
    command list opened just before i; end is the index after what was read.
    line_start holds where the current top-level line begins."""
    out = _Lexed()
    word: list[str] = []
    written: list[str] = []  # the word as written, its line continuations gone
    in_word = False  # whether a word is open
    word_start = 0
    depth = 0  # nested: the ( ) opened inside the list
    heredoc_operator: str | None = None  # a << waiting for its delimiter word
    marks = (0, 0, 0)  # what had been read when that << came
    heredocs: list[tuple[str, bool, bool, bool]] = []  # delimiter, <<-, code, expands
    case_states: list[str] = []  # nested: each open case, and where it stands
    command_start = True  # nested: whether a command may start here
    n = len(text)

    def end_word() -> None:
        nonlocal word, written, in_word, heredoc_operator, command_start
        if not in_word:
            return
        value, raw = "".join(word), "".join(written)
        if heredoc_operator is not None:
            # bash does not expand a heredoc's delimiter word
            del out.substitutions[marks[0] :]
            del out.code_bodies[marks[1] :]
            del out.removed[marks[2] :]
            line_begin = text.rfind("\n", 0, word_start) + 1
            line_end = text.find("\n", word_start)
            line = text[line_begin : n if line_end < 0 else line_end]
            heredocs.append(
                (
                    value,
                    heredoc_operator == "<<-",
                    INTERPRETER_WORD_RE.search(line) is not None,
                    not any(q in raw for q in "'\"\\"),
                )
            )
            heredoc_operator = None
        quoted = any(q in raw for q in _QUOTING)
        if nested:
            reserved = "" if quoted else value
            command_start = _follow_case(case_states, reserved, command_start)
        out.tokens.append(_Quoted(value) if quoted else value)
        word, written, in_word = [], [], False

    while i < n:
        c = text[i]
        if c == "\\" and text.startswith("\n", i + 1):
            i += 2  # a line continuation: bash removes it
            continue
        if c in " \t":
            end_word()
            i += 1
            continue
        if c == "\n":
            end_word()
            command_start = True
            out.tokens.append(_Op("\n"))
            i = _read_heredoc_bodies(text, i + 1, heredocs, out)
            heredocs.clear()
            if not nested:
                line_start[0] = i
            continue
        if c == "#" and not in_word:
            newline = text.find("\n", i)
            i = n if newline < 0 else newline
            continue
        if c in "<>" and text.startswith("(", i + 1):
            # a process substitution, also inside a word (x<(true))
            if not in_word:
                in_word, word_start = True, i
            inner = _lex(text, i + 2, True, line_start)
            out.substitutions.append(text[i + 2 : inner.end - 1])
            out.removed.extend(inner.removed)
            word.append(text[i : inner.end])
            written.append(text[i : inner.end])
            i = inner.end
            continue
        if c == "(" and in_word and _ARRAY_OPEN.fullmatch("".join(written)):
            # NAME=(...): an array, one word
            inner = _lex(text, i + 1, True, line_start)
            out.substitutions.extend(inner.substitutions)
            out.code_bodies.extend(inner.code_bodies)
            out.removed.extend(inner.removed)
            word.append(text[i : inner.end])
            written.append(text[i : inner.end])
            i = inner.end
            continue
        if c in "|&;()<>":
            if c in "<>" and in_word and _DESCRIPTOR.fullmatch("".join(written)):
                word, written, in_word = [], [], False  # the redirection's descriptor
            end_word()
            operator, after = _operator_at(text, i)
            top = case_states[-1] if case_states else ""
            if top == "pattern" and operator in ("(", ")", "|"):
                if operator == ")":
                    case_states[-1] = "body"
            elif top == "body" and operator in (";;", ";&", ";;&"):
                case_states[-1] = "pattern"
            elif nested and operator == ")":
                if depth == 0:
                    out.end = i + 1
                    return out
                depth -= 1
            elif nested and operator == "(":
                depth += 1
            command_start = operator in _CONTROL_OPERATORS
            if operator in ("<<", "<<-"):
                heredoc_operator = operator
                marks = (len(out.substitutions), len(out.code_bodies), len(out.removed))
            out.tokens.append(_Op(operator))
            i = after
            continue
        if not in_word:
            in_word, word_start = True, i
        end = _word_part(text, i, word, out, line_start)
        written.append(text[i:end])
        i = end
    if nested:
        raise _Unterminated(line_start[0])
    end_word()
    _read_heredoc_bodies(text, n, heredocs, out)
    out.end = n
    return out


def _word_part(
    text: str, i: int, word: list[str], out: _Lexed, line_start: list[int]
) -> int:
    """Reads one part of a word at i into word: an escaped character, a quoted
    string, an expansion, or a plain character. Returns the index after it."""
    n = len(text)
    c = text[i]
    if c == "\\":
        if i + 1 == n:
            word.append("\\")  # a backslash at the very end is itself
            return i + 1
        word.append(text[i + 1])
        return i + 2
    if c == "'":
        close = text.find("'", i + 1)
        if close < 0:
            raise _Unterminated(line_start[0])
        word.append(text[i + 1 : close])
        return close + 1
    if c == '"':
        return _double_quoted(text, i + 1, word, out, line_start)
    if c == "$" and text.startswith("'", i + 1):
        return _ansi_c(text, i + 2, word, line_start)
    if c == "$" and text.startswith('"', i + 1):
        return _double_quoted(text, i + 2, word, out, line_start)
    if _expansion_starts(text, i):
        end = _expansion_end(text, i, out, line_start, in_double=False)
        word.append(text[i:end])
        return end
    word.append(c)
    return i + 1


def _operator_at(text: str, i: int) -> tuple[str, int]:
    """The longest operator at i, and the index after it. bash removes a line
    continuation before it reads an operator, also inside one (<<\\ newline
    -EOF is <<-, and && may be written &\\ newline &)."""
    chars: list[str] = []
    ends: list[int] = []
    j = i
    while j < len(text) and len(chars) < 3:
        if text.startswith("\\\n", j):
            j += 2
            continue
        chars.append(text[j])
        j += 1
        ends.append(j)
    seen = "".join(chars)
    operator = next(o for o in _OPERATORS if seen.startswith(o))
    return operator, ends[len(operator) - 1]


def _follow_case(states: list[str], word: str, command_start: bool) -> bool:
    """Follows case ... esac through one word of a nested command list, so
    that a pattern's ) does not end the list (bash reads $(case x in a) ...;;
    esac)). word is "" when it was quoted, since a quoted word is never a
    reserved word. Returns whether a command may start after it."""
    top = states[-1] if states else ""
    if top == "subject":
        states[-1] = "in"
    elif top == "in":
        if word == "in":
            states[-1] = "pattern"
    elif top == "pattern":
        if word == "esac":
            states.pop()
    elif command_start and word == "case":
        states.append("subject")
    elif top == "body" and command_start and word == "esac":
        states.pop()
    return word in _KEEPS_COMMAND_START


def _read_heredoc_bodies(
    text: str, i: int, heredocs: list[tuple[str, bool, bool, bool]], out: _Lexed
) -> int:
    """Reads the bodies of the heredocs opened on the line before i, in order.
    Where the delimiter is not quoted, bash first joins a line that ends in an
    unescaped backslash to the next. Then <<- strips the leading tabs, the
    body's too, and a body ends at the line that is its delimiter, or at the
    end. Returns the index after the last body."""
    n = len(text)
    for delimiter, tabs, code, expands in heredocs:
        start = i
        lines: list[str] = []
        while i < n:
            line, i = _physical_line(text, i)
            while expands and _ends_in_backslash(line) and i < n:
                following, i = _physical_line(text, i)
                line = line[:-1] + following
            if tabs:
                line = line.lstrip("\t")
            if line == delimiter:
                break
            lines.append(line)
        out.removed.append((start, i))
        body = "\n".join(lines)
        if code:
            out.code_bodies.append(body)
        elif expands:
            out.substitutions.extend(_heredoc_substitutions(body))
    return i


def _physical_line(text: str, i: int) -> tuple[str, int]:
    """The line at i without its newline, and the index after it."""
    newline = text.find("\n", i)
    if newline < 0:
        return text[i:], len(text)
    return text[i:newline], newline + 1


def _ends_in_backslash(line: str) -> bool:
    """Whether a line ends in a backslash that no backslash escapes."""
    return (len(line) - len(line.rstrip("\\"))) % 2 == 1


def _heredoc_substitutions(body: str) -> list[str]:
    """The command substitutions bash expands in a heredoc body whose
    delimiter is not quoted: quotes are plain characters there, and a
    backslash escapes $, backquote, and itself. One that does not end runs to
    the end of the body."""
    found = _Lexed()
    i, n = 0, len(body)
    while i < n:
        if body[i] == "\\":
            i += 2
            continue
        if _expansion_starts(body, i):
            try:
                i = _expansion_end(body, i, found, [0], in_double=False)
            except _Unterminated:
                found.substitutions.append(body[i + (1 if body[i] == "`" else 2) :])
                break
            continue
        i += 1
    return found.substitutions


def _expansion_starts(text: str, i: int) -> bool:
    """Whether $(, ${, or a backquote starts at i."""
    return text[i] == "`" or text.startswith(("$(", "${"), i)


def _expansion_end(
    text: str, i: int, out: _Lexed, line_start: list[int], *, in_double: bool
) -> int:
    """The index after the $(...), $((...)), ${...}, or backquote at i; the
    bodies of the command substitutions go to out."""
    if text[i] == "`":
        end, body = _backquote(text, i + 1, line_start)
        out.substitutions.append(body)
        return end
    if text.startswith("$((", i):
        end = _arithmetic_end(text, i + 3, out, line_start)
        if end is not None:
            return end
    if text.startswith("$(", i):
        inner = _lex(text, i + 2, True, line_start)
        out.substitutions.append(text[i + 2 : inner.end - 1])
        out.removed.extend(inner.removed)
        return inner.end
    return _brace_end(text, i + 2, out, line_start, in_double=in_double)


def _double_quoted(
    text: str, i: int, word: list[str], out: _Lexed, line_start: list[int]
) -> int:
    """Reads "..." from after its opening quote into word; returns the index
    after it. A backslash escapes $, backquote, ", itself, and a newline."""
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            return i + 1
        if c == "\\" and i + 1 < n:
            following = text[i + 1]
            if following == "\n":
                i += 2
            elif following in '$`"\\':
                word.append(following)
                i += 2
            else:
                word.append("\\")
                i += 1
            continue
        if _expansion_starts(text, i):
            end = _expansion_end(text, i, out, line_start, in_double=True)
            word.append(text[i:end])
            i = end
            continue
        word.append(c)
        i += 1
    raise _Unterminated(line_start[0])


_ANSI_C_SIMPLE = {
    "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n",
    "r": "\r", "t": "\t", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?",
}  # fmt: skip
_ANSI_C_HEX = {"x": 2, "u": 4, "U": 8}  # the most hex digits each takes


def _ansi_c(text: str, i: int, word: list[str], line_start: list[int]) -> int:
    """Reads $'...' from after its opening quote into word, decoding its
    escapes as bash does: the simple ones, \\nnn (octal), \\xHH, \\uHHHH,
    \\UHHHHHHHH, and \\cX. Others stay as written, and a NUL ends the value.
    Returns the index after the closing quote."""
    n = len(text)
    value: list[str] = []
    ended = False  # past a NUL: the rest is read, then dropped
    while i < n:
        c = text[i]
        if c == "'":
            word.extend(value)
            return i + 1
        if c != "\\" or i + 1 == n:
            if not ended:
                value.append(c)
            i += 1
            continue
        following = text[i + 1]
        if following in _ANSI_C_SIMPLE:
            decoded, i = _ANSI_C_SIMPLE[following], i + 2
        elif following in "01234567":
            j = i + 1
            while j < min(n, i + 4) and text[j] in "01234567":
                j += 1
            decoded, i = chr(int(text[i + 1 : j], 8) & 0xFF), j
        elif following in _ANSI_C_HEX:
            j = i + 2
            while (
                j < min(n, i + 2 + _ANSI_C_HEX[following])
                and text[j] in "0123456789abcdefABCDEF"
            ):
                j += 1
            if j == i + 2:
                decoded, i = "\\" + following, i + 2
            else:
                code = int(text[i + 2 : j], 16)
                valid = code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF
                decoded, i = (chr(code) if valid else text[i:j]), j
        elif following == "c" and text.startswith("\\\\", i + 2):
            decoded, i = "\x1c", i + 4  # \c and an escaped backslash: FS
        elif following == "c" and i + 2 < n:
            decoded, i = _control(text[i + 2]), i + 3
        else:
            decoded, i = "\\" + following, i + 2
        if not ended:
            head, nul, _ = decoded.partition("\x00")
            value.append(head)
            ended = bool(nul)
    raise _Unterminated(line_start[0])


def _control(c: str) -> str:
    """bash's \\cX: X's first byte as a control character (\\c? is DEL). bash
    reads bytes, so the later bytes of a multi-byte X stay as they are; here
    each is U+FFFD (bash runs the npm in $'echo \\c\u0100; npm i')."""
    if c == "?":
        return "\x7f"
    encoded = ("\ufffd" if 0xD800 <= ord(c) <= 0xDFFF else c).encode("utf-8")
    return chr(encoded[0] & 0x1F) + "\ufffd" * (len(encoded) - 1)


def _backquote(text: str, i: int, line_start: list[int]) -> tuple[int, str]:
    """Reads `...` from after its opening backquote: the index after it, and
    its body, where a backslash before a backquote, $, or itself is dropped."""
    body: list[str] = []
    n = len(text)
    while i < n:
        c = text[i]
        if c == "`":
            return i + 1, "".join(body)
        if c == "\\" and i + 1 < n and text[i + 1] in "`\\$":
            body.append(text[i + 1])
            i += 2
            continue
        body.append(c)
        i += 1
    raise _Unterminated(line_start[0])


def _arithmetic_end(
    text: str, i: int, out: _Lexed, line_start: list[int]
) -> int | None:
    """The index after the )) of a $(( read from i, or None when it is no
    arithmetic: bash takes $(( as one when the ( after $( closes on a ) that
    another ) follows, and else as $( with a subshell first (it runs the npm in
    $((npm i); :)). The command substitutions inside go to out."""
    depth = 1
    found = _Lexed()
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        # quotes hide a ) (bash runs the npm in $((: '))'; "npm" i) ))
        if c == "'":
            close = text.find("'", i + 1)
            if close < 0:
                raise _Unterminated(line_start[0])
            i = close + 1
            continue
        if c == '"':
            i = _double_quoted(text, i + 1, [], found, line_start)
            continue
        if c == "$" and text.startswith("'", i + 1):
            i = _ansi_c(text, i + 2, [], line_start)
            continue
        if _expansion_starts(text, i):
            i = _expansion_end(text, i, found, line_start, in_double=False)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                if not text.startswith(")", i + 1):
                    return None
                out.substitutions.extend(found.substitutions)
                out.removed.extend(found.removed)
                return i + 2
        i += 1
    raise _Unterminated(line_start[0])


def _brace_end(
    text: str, i: int, out: _Lexed, line_start: list[int], *, in_double: bool
) -> int:
    """The index after the } of a ${ read from i; the command substitutions
    inside it go to out. A plain { does not nest (${x:-{} is "{"); inside
    "...", a single quote is a plain character there (bash runs the $(...) in
    "${x:-'$(...)'}", and not unquoted)."""
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "'" and not in_double:
            close = text.find("'", i + 1)
            if close < 0:
                raise _Unterminated(line_start[0])
            i = close + 1
            continue
        if c == '"':
            i = _double_quoted(text, i + 1, [], out, line_start)
            continue
        if _expansion_starts(text, i):
            i = _expansion_end(text, i, out, line_start, in_double=in_double)
            continue
        if c == "}":
            return i + 1
        i += 1
    raise _Unterminated(line_start[0])


# --- fixed-command-split: end ---
