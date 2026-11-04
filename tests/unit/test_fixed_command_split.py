"""scripts/fixed_command_split.py holds the code the fixed-command-split edit
puts into the Python command guard (scripts/old_script_fixes.py). It is
linted and tested here as Python; what the guard does with it is tested on the
corpus and against bash (test_command_guard_bash_oracle.py)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import fixed_command_split as lexer
import old_script_fixes

GUARD = ROOT / "ROOT_AGENTS_hooks_block-prohibited-commands.py"


def _guard():
    spec = importlib.util.spec_from_file_location("command_guard_for_lexer", GUARD)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_its_interpreter_pattern_is_the_guards():
    # Only the text between the markers goes into the guard, which uses its
    # own INTERPRETER_WORD_RE; the copy here must say the same.
    assert lexer.INTERPRETER_WORD_RE.pattern == _guard().INTERPRETER_WORD_RE.pattern


def test_the_edit_inserts_the_text_between_the_markers():
    inserted = old_script_fixes._inserted("command-split")
    source = (ROOT / "scripts/fixed_command_split.py").read_text(encoding="utf-8")
    assert inserted in source
    assert "INTERPRETER_WORD_RE = re.compile(" not in inserted
    assert inserted.lstrip().startswith("class _Op(str):")


def _read(text: str) -> list[str]:
    return [
        ("op:" if isinstance(token, lexer._Op) else "") + token
        for token in lexer._bash_lex(text).tokens
    ]


def test_it_splits_words_and_operators_where_bash_does():
    assert _read("cd x\nnpm i") == ["cd", "x", "op:\n", "npm", "i"]
    assert _read("(cd x);npm i") == ["op:(", "cd", "x", "op:)", "op:;", "npm", "i"]
    assert _read("echo ';' x#y # c") == ["echo", ";", "x#y"]
    assert _read("2>/dev/null npm i") == ["op:>", "/dev/null", "npm", "i"]
    assert _read("arr=(npm yarn)") == ["arr=(npm yarn)"]
    assert _read("$'n\\x70m' i") == ["npm", "i"]


def test_it_returns_what_bash_runs_as_code():
    read = lexer._bash_lex('echo "$(npm i)" `make` <(pip x)')
    assert read.substitutions == ["npm i", "make", "pip x"]
    read = lexer._bash_lex("# <<EOF\nbash <<'PY'\nnpm i\nPY\nmake")
    assert read.code_bodies == ["npm i"]
    assert (
        read.cleaned("# <<EOF\nbash <<'PY'\nnpm i\nPY\nmake")
        == "# <<EOF\nbash <<'PY'\nmake"
    )


def test_an_unterminated_quote_tells_where_its_line_starts():
    try:
        lexer._bash_lex("echo a\necho 'x")
    except lexer._Unterminated as unterminated:
        assert unterminated.line_start == len("echo a\n")
    else:
        raise AssertionError("the quote does not end")
