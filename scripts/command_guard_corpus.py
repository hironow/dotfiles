#!/usr/bin/env python3
"""Write the command guard corpus that the agent-hook Go port is tested against.

Each line of tools/agent-hooks/internal/guardcorpus/command-guard.jsonl is one input and
what the Python command guard (ROOT_AGENTS_hooks_block-prohibited-commands.py)
makes of it: the shlex tokens or the tokenizer's error, the heredoc split, and
the verdict (the reason it blocks, or null when it passes). It also records the
guard with its bugs fixed (scripts/old_script_fixes.py), which the Go port
follows: its verdict ("fixed"), the fixes that verdict needs ("difference",
empty when it is the old one), and what its bash lexer reads ("bash": each token an operator, a quoted
word, or a word). The Python guard is
the reference until the agent-hook plan's last PR removes it
(docs/plan/agent-hooks-go.md); the corpus then stays as the Go tests' data.

It also writes Python's \\w as a Go table (WORD_TABLE), which the port uses
in place of Go's newer Unicode tables.

tests/unit/test_command_guard_corpus.py fails when the file no longer matches
the reference, and the Go tests fail when the port no longer matches the file.
Run `just command-guard-corpus` after changing the guard or its tests.

This is Python, not Go, because it runs the Python reference; it goes with it.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import random
import re
import tempfile
import unicodedata
from pathlib import Path
from types import ModuleType

import old_script_fixes

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "ROOT_AGENTS_hooks_block-prohibited-commands.py"
# The guard's fixes (scripts/old_script_fixes.py), which the Go port follows.
COMMAND_FIXES = tuple(
    name for name, fix in old_script_fixes.FIXES.items() if fix.script == REFERENCE.name
)
CORPUS = ROOT / "tools/agent-hooks/internal/guardcorpus/command-guard.jsonl"
# Python's \w as a Go table: the port uses it instead of Go's own Unicode
# tables, which are a newer Unicode version than Python's.
WORD_TABLE = ROOT / "tools/agent-hooks/internal/commandguard/pyword_table.go"
# The Unicode version of the Python the port follows (Python 3.14). Both files
# depend on it, so the script refuses to write them from any other version;
# following a newer Python is a deliberate change of this line.
PYTHON_UNICODE = "16.0.0"
# The guard's own tests: every command they feed it is in the corpus.
GUARD_TESTS = (
    ROOT / "tests/unit/test_agent_hooks.py",
    ROOT / "tests/unit/test_codex_guard_adapter.py",
    ROOT / "tests/unit/test_command_guard_interpreter.py",
)

# Inputs aimed at one behavior each, grouped by the part of the guard they test.
EDGE_CASES = [
    # shlex: empty and adjacent quotes, escapes, unbalanced quotes
    "",
    " ",
    "\n",
    "''",
    '""',
    "'' ''",
    "a''b",
    "'a'\"b\"c",
    "x=''",
    "''x",
    "'abc",
    '"abc',
    "abc'",
    "it's",
    "don't do it",
    "\\",
    "a\\",
    "\\\\",
    "\\a",
    "a\\ b",
    '"a\\"b"',
    '"a\\\\b"',
    '"a\\b"',
    "'a\\b'",
    "'a\\'",
    '"a\\\'b"',
    '"\\$x"',
    "a\\\nb",
    '"a\\\nb"',
    # shlex: comments, also inside a word, and what follows them
    "#x",
    "a #x",
    "a#x",
    "a;#x",
    '"#"',
    "'#'",
    "\\#",
    "a #x\nb",
    "#x\n#y\nz",
    "npm#x",
    "ls #npm i\nmake",
    # shlex: punctuation runs and where they split
    "a;b",
    "a&&b",
    "a||b",
    "a|b",
    "a&b",
    "(a)",
    "a|&b",
    "a;;b",
    "a>b",
    "a>>b",
    "a<b",
    "a<<b",
    "a<<<b",
    "a>&b",
    "a&>b",
    "2>&1",
    "a>|b",
    ";;&",
    ";&",
    "((a))",
    'a;"b"',
    'a";"b',
    '";"',
    "';'",
    # shlex: whitespace it splits on, and Unicode spaces it keeps in a word
    "a\tb",
    "a\rb",
    "a\r\nb",
    "a\u00a0b",
    "a\u3000b",
    "a\x0bb",
    "a\x0cb",
    "a\x1cb",
    "caf\u00e9",
    "\u65e5\u672c\u8a9e",
    "\U0001f680",
    "e\u0301",
    # heredocs: delimiter forms, and lines that open none
    "cat <<EOF\nnpm i\nEOF",
    "cat <<'EOF'\nnpm i\nEOF",
    'cat <<"EOF"\nnpm i\nEOF',
    "cat <<-EOF\nnpm i\nEOF",
    "cat <<- 'EOF'\nnpm i\nEOF",
    "cat <<\tEOF\nnpm i\nEOF",
    "cat << EOF\nnpm i\nEOF",
    "cat <<\u00a0EOF\nnpm i\nEOF",
    "cat <<\u3000EOF\nnpm i\nEOF",
    "cat <<'EOF\nnpm i\nEOF",
    "cat <<\"EOF'\nnpm i\nEOF",
    "cat <<EOF'\nnpm i\nEOF",
    "cat <<1EOF\nnpm i\n1EOF",
    "cat <<_A1\nnpm i\n_A1",
    "cat <<--EOF\nnpm i\nEOF",
    "cat <<<EOF\nnpm i\nEOF",
    'cat <<< "text"\nnpm i\ntext',
    "cat <<<'x'\nnpm i\nx",
    "cat <<<<EOF\nnpm i\nEOF",
    "x<<EOF\nnpm i\nEOF",
    "cat<<EOF\nnpm i\nEOF",
    "cat <<A <<B\nnpm i\nA\nmake\nB",
    "cat <<EOF\nnpm i\n  EOF  ",
    "cat <<EOF\nnpm i\n\u3000EOF",
    "cat <<EOF\nnpm i\n\x1cEOF",
    "cat <<EOF\nnpm i\nEOFX\nEOF",
    "cat <<EOF\nnpm i",
    "bash <<EOF\nnpm i",
    "cat <<'EOF' > /tmp/pr-body.md\nrm -rf /\ngcloud run deploy\nEOF",
    "cat <<EOF > a.yml\nx\nEOF",
    # heredocs: which lines feed an interpreter
    "bash <<EOF\nnpm i\nEOF",
    "python3 <<EOF\nnpm i\nEOF",
    "sh -s <<EOF\nnpm i\nEOF",
    "x | bash <<EOF\nnpm i\nEOF",
    "(bash <<EOF\nnpm i\nEOF",
    ";bash <<EOF\nnpm i\nEOF",
    "&bash <<EOF\nnpm i\nEOF",
    "x bash <<EOF\nnpm i\nEOF",
    "xbash <<EOF\nnpm i\nEOF",
    "bashx <<EOF\nnpm i\nEOF",
    "bash3 <<EOF\nnpm i\nEOF",
    "bash. <<EOF\nnpm i\nEOF",
    "bash\u00e9 <<EOF\nnpm i\nEOF",
    "bash\u3000<<EOF\nnpm i\nEOF",
    "\u3000bash <<EOF\nnpm i\nEOF",
    "\x1cbash <<EOF\nnpm i\nEOF",
    "python3x <<EOF\nnpm i\nEOF",
    "uv run python - <<'PYEOF'\nprint(\"npm\")\nPYEOF",
    "uv run python - <<'PYEOF'\nimport os\nPYEOF",
    "node <<EOF\nconsole.log(1)\nEOF",
    # heredocs: nesting, and the depth past which bodies are not read
    "bash <<A\npython3 <<B\nnpm i\nB\nA",
    "bash <<A\nbash <<B\nbash <<C\nnpm i\nC\nB\nA",
    "bash <<A\nbash <<B\nnpm i\nB\nA",
    "cat <<A\nbash <<B\nnpm i\nB\nA",
    # raw guards: root deletion
    "rm -rf /",
    "rm -fr /",
    "rm -r -f /",
    "rm -Rf /",
    "rm -rf / x",
    "rm -rf /\n",
    "rm -rf /tmp",
    "rm -rf ~/",
    "rm  -rf  /",
    "rm\u00a0-rf\u00a0/",
    "rm\x1c-rf\x1c/",
    'rm -rf "/"',
    'echo "rm -rf /"',
    "rm /",
    "rm -f /",
    "rm -rfv /",
    "xrm -rf /",
    # raw guards: gcloud IAM and IaC mutations
    "gcloud projects add-iam-policy-binding p --member=x --role=y",
    "gcloud\u00a0projects add-iam-policy-binding p",
    "gcloud projects get-iam-policy p",
    "gcloud organizations set-iam-policy o f",
    "gcloud run deploy api",
    "gcloud compute instances resize x",
    "gcloud compute instances set-machine-type x",
    "gcloud sql instances update x",
    "gcloud secrets versions add s",
    "gcloud secrets versions\u3000add s",
    "gcloud secrets versions list s",
    "gcloud run services list",
    "xgcloud run deploy",
    "gcloud  run  deploy",
    "gcloud\nrun deploy",
    'echo "gcloud run deploy"',
    # walker: package managers and task runners, by name and by path
    "pip",
    "pip3 install x",
    "poetry add x",
    "pipenv install",
    "/usr/bin/pip install x",
    "./pip install x",
    "pip.exe install x",
    "PIP install x",
    "python -m pip install x",
    "uv pip install x",
    "npm",
    "yarn add x",
    "pnpm i",
    "npx x",
    "bunx x",
    "/usr/local/bin/npm ci",
    "make",
    "/usr/bin/make -C x",
    "gmake",
    "corepack pnpm i",
    "corepack --cwd /x pnpm i",
    "corepack --cwd",
    "corepack enable",
    "corepack -v",
    "corepack pnpm@9 i",
    "corepack npm@latest i",
    "corepack yarn@stable",
    "corepack prepare pnpm@9 --activate",
    "corepack use pnpm@9",
    # walker: what may stand before the command name
    "env npm i",
    "env -i npm i",
    "sudo npm i",
    "sudo -u x npm i",
    "time make",
    "nohup make &",
    "command npm i",
    "xargs npm i",
    "FOO=1 npm i",
    "A=1 B=2 make",
    "=x npm i",
    "1A=2 npm i",
    "FOO= make",
    # walker: command boundaries
    "npm;ls",
    "ls;npm i",
    "ls && npm i",
    "ls || npm i",
    "ls | npm i",
    "ls & npm i",
    "(npm i)",
    "$(npm i)",
    "`npm i`",
    "ls |& npm i",
    "ls ;& npm i",
    'echo ";" npm i',
    "echo ';' make",
    # walker: redirections and .yml creation
    "echo > a.yml",
    "echo >> a.yml",
    "echo 2> a.yml",
    "echo &> a.yml",
    "echo >| a.yml",
    "echo < a.yml",
    'echo > "a.yml"',
    "echo > x.yaml",
    "echo > docker-compose.yaml",
    "echo > ./docker-compose.yaml",
    "echo > docker-compose.yml",
    "echo >a.yml",
    "echo>a.yml",
    "echo > a.yml npm i",
    "touch -c a.yml",
    "tee -a a.yml",
    "cp -r dir x.yml",
    "cp a.yml",
    "cp a.yml b.yaml",
    "mv x y.yml",
    "mv -f x y.yml z",
    "touch compose.yaml docker-compose.yaml",
    "ls > a.yml; npm i",
    "echo > ; a.yml",
    "echo > && a.yml",
    "echo > | tee x",
    # walker: force pushes to protected branches
    "git push --force-with-lease=main origin main",
    "git push -f origin refs/heads/master",
    "git push origin :main",
    "git push -f origin main:feature",
    "git push origin +main:main",
    "git push --force",
    "git -c x=y push -f origin main",
    "git push origin main -f",
    "git push -f",
    "rtk git push -f origin main",
    "git push origin ++main",
    "git push -f origin feature/main",
    "git fetch -f origin main",
    "git push --force-with-lease origin HEAD:refs/heads/main",
    # walker: rtk, the output proxy, and the commands it runs
    "rtk",
    "rtk --version",
    "rtk run",
    "rtk run -c",
    "rtk run -c ''",
    "rtk run --shell",
    "rtk run --shell bash",
    'rtk run --shell bash "npm i"',
    "rtk run -c \"rtk run -c 'npm i'\"",
    'rtk run -c "cat <<EOF\nnpm i\nEOF"',
    'rtk err -c "bash <<EOF\nnpm i\nEOF"',
    "rtk proxy rtk npm i",
    "rtk sudo npm i",
    "rtk FOO=1 npm i",
    "rtk -- npm i",
    "rtk -c npm i",
    "rtk run -- -c 'npm i'",
    "rtk run -c 'ls' npm i",
    "rtk smart --shell sh 'make' x",
    "rtk run -c 'rm -rf /'",
    'rtk run -c "echo > a.yml"',
    "bash <<A\nrtk run -c 'bash <<B\nbash <<C\nnpm i\nC\nB'\nA",
    "/opt/rtk/bin/rtk pnpm i",
    # a heredoc that only exists once shlex unquotes the shell string, so the
    # string's depth (1) decides how deep its bodies are read
    "rtk run -c bash\\ \\<\\<A\\\nbash\\ \\<\\<B\\\nnpm\\ i\\\nB\\\nA",
    "rtk run -c bash\\ \\<\\<A\\\nnpm\\ i\\\nA",
    # legacy scan: when the tokenizer gives up
    'echo "unclosed npm i',
    "echo 'it''s' npm i \"x",
    'echo "a" npm "b',
    "echo don't npm",
    "npm i \\",
    "./npm i '",
    "my-npm i '",
    "npm.exe i '",
    "pip3 x '",
    "\u00e9pip x '",
    "\u00a0npm x '",
    "npm\u00a0x '",
    "npm\x1cx '",
    "make '",
    "touch a.yml '",
    "git push -f origin main '",
    "corepack pnpm i '",
    "echo '\nnpm i",
    'echo "\nmake',
    "rm -rf / '",
    # realistic commands an agent runs
    'git commit -m "build: switch from npm to bun"',
    "gh pr create --title x --body-file /tmp/body.md",
    "git commit -q -F - <<'EOF'\nfix: drop npm\n\nmake is gone too\nEOF",
    "uv run --frozen pytest -q tests/unit",
    "just ci",
    "rtk git status",
    "cd /repo && git log --oneline -3",
    "find . -name '*.yml' | xargs ls",
    "sed -i 's/npm/bun/' README.md",
    "grep -rn 'pip install' docs",
]

# Pairs of these, joined by a space, cover how the parts meet.
PAIR_ATOMS = [
    "npm i",
    "pip x",
    "make",
    "ls",
    "rtk",
    "rtk run -c",
    "env",
    "FOO=1",
    "'q'",
    '"q"',
    "''",
    "\\",
    "#c",
    ";",
    "&&",
    "|&",
    "(",
    ")",
    ">",
    "a.yml",
    "<<EOF",
    "\n",
    "bash",
    "touch",
    "git push -f origin main",
    "corepack",
    "\u00a0",
    "\x1c",
]
# These also glued together, with nothing between them.
GLUED_ATOMS = ["'", '"', "\\", "#", ";", "&", "|", ">", "<", "(", "\n", "a"]

# Random inputs are built from these fragments.
FRAGMENTS = [
    *PAIR_ATOMS,
    *GLUED_ATOMS,
    "pnpm",
    "yarn",
    "poetry",
    "uv",
    "sudo",
    "xargs",
    "tee",
    "cp",
    "mv",
    "x.yml",
    "docker-compose.yaml",
    "EOF",
    "<<'EOF'",
    "<<-EOF",
    "python3",
    "rm -rf /",
    "gcloud run deploy",
    "+main",
    "-f",
    "--force",
    "--shell",
    "proxy",
    "\u3000",
    "\t",
    "\u00e9",
    "2>",
    "$(",
    "`",
]
RANDOM_SEED = 20261103
RANDOM_COUNT = 600

# Python's whitespace (str.isspace(), and re's \s): what strip() removes and \s
# matches. Not the same as Go's unicode.IsSpace, which leaves out U+001C..U+001F.
PYTHON_SPACES = [chr(code) for code in range(0x110000) if chr(code).isspace()]
# Not whitespace in Python, though they look like it.
SPACE_LOOKALIKES = ["\u200b", "\u180e", "\ufeff"]
# Characters on both sides of Python's \w: letters and numbers of several
# scripts and kinds (Nd, Nl, No), a combining mark, symbols, the characters the
# legacy scan treats as part of a name, and letters new in Unicode 17.0, which
# Go's tables (Go 1.27) count as letters but Python 3.14 (Unicode 16.0) does not.
BOUNDARY_CHARS = [
    "\u1c89",  # new in Unicode 16.0: a word character for Python 3.14, not for 3.12
    "\u088f",
    "\ua7ce",
    "\U00016ea0",
    "\u00e9",
    "\u00df",
    "\u03a9",
    "\u044f",
    "\u65e5",
    "\u0661",
    "\u00bd",
    "\u216b",
    "\u00b2",
    "_",
    "0",
    "\u0301",
    "\u00b7",
    "\u200d",
    "\U0001f680",
    "-",
    ".",
    "/",
]


# What bash itself runs, for the command guard's fixes (scripts/old_script_fixes.py:
# command-split, command-start, shell-string). Each input runs in bash with stub
# programs that log their names (tests/unit/test_command_guard_bash_oracle.py),
# and its kind says what bash does and what the fixed guard must do:
# - "runs": bash runs a banned program or writes a .yml file; the guard blocks;
# - "quiet": bash runs none and writes none; the guard passes;
# - "over": bash runs none, but the guard blocks on purpose (it reads every
#   branch, and a command with a syntax error by its complete lines).
# Every branch of a "runs" input runs. Login shells (bash -l) reset PATH, so
# none is used. A bash detail found later goes here first (Red), then is fixed
# inside the fix ID it belongs to.
BASH_ORACLE: list[tuple[str, str]] = [
    # fixed-command-split: words and operators where bash splits them
    ("cd .\nnpm i", "runs"),
    ("echo x#y; npm i", "runs"),
    ("(cd .);npm i", "runs"),
    ("(cd .)&&npm i", "runs"),
    ("echo |& npm i", "runs"),
    ("< /dev/null npm i", "runs"),
    ("2>/dev/null npm i", "runs"),
    ("echo ';' npm i", "quiet"),
    ("echo 'npm i'", "quiet"),
    ("arr=(npm yarn)", "quiet"),
    ("echo hi > x.yml", "runs"),
    ("cat < /dev/null > x.yml", "runs"),
    # substitutions, which bash runs
    ("echo `npm i`", "runs"),
    ('echo "$(npm i)"', "runs"),
    ("cat <(npm i)", "runs"),
    ('x=$(case y in (b) echo;; esac); "npm" i', "runs"),
    ('echo $(case x in x) "npm" i;; esac)', "runs"),
    ('echo $(case c in a|b) echo;; c) "npm" i;; esac)', "runs"),
    ('echo $(case x in a) "npm" i;; esac)', "over"),
    ("echo \"$(case esac in 'esac') npm i;; esac)\"", "runs"),
    # after a redirection, case is its target, not a reserved word: the ) after
    # a ends the substitution, and the rest is text in the quotes
    ('echo "$(> case x in a) npm i;; esac)"', "quiet"),
    ('printf \'%s\\n\' "<(npm i)" ">(npm i)"', "quiet"),
    (
        "unset AGENT_HOOK_UNSET; printf '%s\\n' \"${AGENT_HOOK_UNSET:-'$(npm i)'}\"",
        "runs",
    ),
    ("unset AGENT_HOOK_UNSET; printf '%s\\n' ${AGENT_HOOK_UNSET:-'$(npm i)'}", "quiet"),
    ("$'n\\x70m' i", "runs"),
    ("$'\\156pm' i", "runs"),
    ("$'np\\u006d' i", "runs"),
    # $'...' decoded as bash decodes it; a NUL ends the value
    # octal escapes above 0x7F (here the UTF-8 bytes of one emoji, so that every
    # file system takes the name)
    ("touch $'\\360\\237\\230\\200.yml'", "runs"),
    ("touch $'\\u00e9\\U0001F600.yml'", "runs"),
    ("touch $'\\cA.yml'", "runs"),
    ("touch $'\\x.yml'", "runs"),
    ("touch $'a\\0b.yml'", "quiet"),
    # heredocs, as bash finds them
    ("cat <<< EOF\nnpm i", "runs"),
    ("cat <<EOF\n$(npm i)\nEOF", "runs"),
    ("cat <<'EOF'\n$(npm i)\nEOF", "quiet"),
    ("cd .\ncat <<EOF\nx\nEOF\nnpm i", "runs"),
    ("echo \"$(cat <<'EOF'\nfix(x): a) b\nEOF\n)\"; npm i", "runs"),
    ('# <<EOF\n"npm" i\nEOF', "runs"),
    ('echo "<<EOF"\nnpm i\nEOF', "runs"),
    ("sh - <<SH\necho x\nSH\nnpm i", "runs"),
    ("cat <<A <<B\nnpm i\nA\nnpm i\nB", "quiet"),
    ("cat <<'EOF'\n  EOF\nnpm i\nEOF", "quiet"),
    ('cat <<EOF\nEO\\\nF\n"npm" i', "runs"),
    ("cat <<'EOF'\nEO\\\nF\n\"npm\" i\nEOF", "quiet"),
    ('cat <<-EOF\n\tEO\\\nF\n"npm" i', "runs"),
    ('cat <<-EOF\n\tEO\\\n\tF\n"npm" i', "quiet"),
    ('cat <<-EOF\n\tEOF\n"npm" i', "runs"),
    ("cat <<EOF\nx \\\n$(npm i)\nEOF", "runs"),
    ("cat <<$(npm i)\nbody\n$(npm i)", "quiet"),
    ('cat <<"$(npm i)"\nbody\n$(npm i)', "quiet"),
    ("bash <<-'EOF'\nnp\\\n\tm i\nEOF", "runs"),
    # found in the code review: a plain { in ${...} does not nest; $(( is
    # arithmetic only when its ( closes on a ) another ) follows; a line
    # continuation is gone before a descriptor or a delimiter is read; \cX
    # takes X's first byte
    ('unset x; echo ${x:-{}; "npm" i', "runs"),
    ("echo $((npm i); :)", "runs"),
    ("echo $((npm i) )", "runs"),
    ("echo $((1+2))", "quiet"),
    ("echo $(( (1+2) * 3 ))", "quiet"),
    ("2\\\n>/dev/null npm i", "runs"),
    ("cat <<EO\\\nF\n$(npm i)\nEOF", "runs"),
    ("eval $'echo \\c\u0100; npm i'", "runs"),
    ("eval $'echo \\c?; npm i'", "runs"),
    # found in the second code review: quotes in $(( count; a line continuation
    # inside an operator is gone too; \c\\ is one control character
    ("echo $((: '))'; \"npm\" i) )", "runs"),
    ("cat <<\\\n-EOF\n\tEOF\nnpm i", "runs"),
    ("a &\\\n& npm i", "over"),
    ("eval $'echo \\c\\\\; npm i'", "runs"),
    ("eval $'echo \\c\\; npm i'", "runs"),
    # a quote or substitution that does not end: the complete lines before it
    ('"npm" i\necho \'unterminated', "runs"),
    ('if true; then\n  "npm" i\n  echo \'unterminated\nfi', "over"),
    # fixed-command-start: the words after which bash starts a command
    ("for d in a; do npm i; done", "runs"),
    ("{ npm i; }", "runs"),
    ("if true; then npm i; fi", "runs"),
    ("! npm i", "runs"),
    ("function f { npm i; }; f", "runs"),
    ("exec npm i", "runs"),
    ("coproc worker { npm i; }; wait", "runs"),
    ("coproc npm i; wait", "runs"),
    # a case's patterns are no commands; its bodies are
    ("case bun in\n  npm) : ;;\n  bun) : ;;\nesac", "quiet"),
    ("case x in\n  (npm|yarn) : ;;\nesac", "quiet"),
    ("case bun in\n  bun) : ;;\n  npm) : ;;\nesac", "quiet"),
    ("case npm in\n  npm) npm i ;;\nesac", "runs"),
    ("case a in a) case b in b) npm i;; esac;; esac", "runs"),
    # a quoted word is never a reserved word (exec is a builtin, no reserved word);
    # a redirection's operand in a case body is no esac
    ('"case" x; npm i', "runs"),
    ('"function"; npm i', "runs"),
    ("case x in 'esac'|npm) :;; esac", "quiet"),
    ('"if" npm i', "quiet"),
    ('"exec" npm i', "runs"),
    ("case x in x) <<<esac npm i;; esac", "runs"),
    # fixed-shell-string: what a shell runs with -c, and eval
    ('bash -c "npm i"', "runs"),
    ("sh -ec 'npm i'", "runs"),
    ('bash -o pipefail -c "npm i"', "runs"),
    ("bash -c -- 'npm i'", "runs"),
    ("zsh -oSH_WORD_SPLIT -c 'npm i'", "runs"),
    ('eval "npm i"', "runs"),
    ('eval -- "npm i"', "runs"),
    ("cd .\nnpm i; bash -c 'npm i'", "runs"),
    ("bash ./script.sh 'npm i'", "quiet"),
]


def load_reference() -> ModuleType:
    """A private copy of the Python guard whose block() raises instead of exiting."""
    return load_guard(REFERENCE, "command_guard_reference")


def load_fixed(directory: Path) -> dict[frozenset[str], ModuleType]:
    """The guard with each set of its fixes, written under directory."""
    copies = {}
    for applied in old_script_fixes.every_set(COMMAND_FIXES):
        name = "+".join(sorted(applied)) or "old"
        written = old_script_fixes.write_scripts(directory / name, applied)
        module = "command_guard_" + re.sub(r"\W", "_", name)
        copies[applied] = load_guard(written / REFERENCE.name, module)
    return copies


def load_guard(path: Path, name: str) -> ModuleType:
    """A copy of a Python guard, as a module whose block() raises."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)

    def block(reason: str) -> None:
        raise Blocked(reason)

    # Loaded from a path, the module's names are only known at run time.
    vars(reference)["block"] = block
    return reference


class Blocked(Exception):
    """The reference blocked; the reason is what it would print after BLOCKED:."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _payload_commands(text: str) -> list[str]:
    """The command of a JSON hook payload held in a string, if it is one."""
    try:
        payload = json.loads(text)
    except ValueError:
        return []
    if not isinstance(payload, dict):
        return []
    found = []
    for holder in (payload, payload.get("tool_input")):
        if isinstance(holder, dict) and isinstance(holder.get("command"), str):
            found.append(holder["command"])
    return found


def _str_value(node: ast.AST | None) -> str | None:
    """The value of a string literal, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_commands(call: ast.Call) -> list[str]:
    """`_run_hook("cmd", ...)`, `pytest.param("cmd", ...)`, and the strings of
    `@pytest.mark.parametrize("command", [...])`."""
    name = getattr(call.func, "id", getattr(call.func, "attr", ""))
    first = _str_value(call.args[0]) if call.args else None
    if name in {"_run_hook", "param"} and first is not None:
        return [first]
    values = call.args[1] if len(call.args) > 1 else None
    if name == "parametrize" and first == "command" and isinstance(values, ast.List):
        return [text for text in map(_str_value, values.elts) if text is not None]
    return []


def _commands_in(node: ast.AST) -> list[str]:
    """Commands one AST node of a guard test feeds the guard."""
    if isinstance(node, ast.Call):
        return _call_commands(node)
    if isinstance(node, ast.Dict):
        pairs = zip(
            map(_str_value, node.keys), map(_str_value, node.values), strict=True
        )
        return [value for key, value in pairs if key == "command" and value is not None]
    if isinstance(node, ast.Assign):
        value = _str_value(node.value)
        is_cmd = any(getattr(target, "id", "") == "cmd" for target in node.targets)
        return [value] if value is not None and is_cmd else []
    text = _str_value(node)
    return _payload_commands(text) if text is not None else []


def fixture_commands() -> list[str]:
    """Every command the guard's own tests feed it."""
    found: list[str] = []
    for path in GUARD_TESTS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            found += _commands_in(node)
    return found


def pair_inputs() -> list[str]:
    pairs = [f"{a} {b}" for a in PAIR_ATOMS for b in PAIR_ATOMS]
    return pairs + [a + b for a in GLUED_ATOMS for b in GLUED_ATOMS]


def random_inputs() -> list[str]:
    """Inputs of 2 to 7 fragments, the same on every run (random() is stable)."""
    rng = random.Random(RANDOM_SEED)

    def pick(options: list[str]) -> str:
        return options[int(rng.random() * len(options))]

    inputs = []
    for _ in range(RANDOM_COUNT):
        count = 2 + int(rng.random() * 6)
        parts = [pick(FRAGMENTS) for _ in range(count)]
        inputs.append("".join(part + pick([" ", " ", "", "\n"]) for part in parts))
    return inputs


def space_inputs() -> list[str]:
    """Each Python space, and each lookalike, everywhere the guard reads \\s or strip()."""
    return [
        text
        for c in PYTHON_SPACES + SPACE_LOOKALIKES
        for text in (
            f"rm{c}-rf{c}/",
            f"gcloud{c}run{c}deploy",
            f"gcloud{c}secrets versions{c}add s",
            f"cat <<{c}EOF\nnpm i\nEOF",
            f"cat <<EOF\nnpm i\n{c}EOF{c}",
            f"{c}bash <<EOF\nnpm i\nEOF",
            f"npm{c}x '",
        )
    ]


def boundary_inputs() -> list[str]:
    """Each character next to a name where the guard reads \\w or \\b."""
    return [
        text
        for c in BOUNDARY_CHARS
        for text in (
            f"bash{c} <<EOF\nnpm i\nEOF",
            f"{c}npm x '",
            f"x {c}make '",
            f"pip{c} x '",
        )
    ]


def inputs() -> list[str]:
    """All inputs, once each, in a fixed order."""
    ordered = (
        fixture_commands()
        + EDGE_CASES
        + [text for text, _ in BASH_ORACLE]
        + space_inputs()
        + boundary_inputs()
        + pair_inputs()
        + random_inputs()
    )
    return list(dict.fromkeys(ordered))


def verdict(guard: ModuleType, text: str) -> str | None:
    """Why a guard blocks the text, or None when it passes."""
    try:
        guard.analyze(text)
    except Blocked as blocked:
        return blocked.reason
    return None


def bash_reading(guard: ModuleType, text: str) -> dict:
    """What the fixed guard's lexer reads in a text: its tokens (each an
    operator or a word), the substitution bodies, the code heredoc bodies,
    and the text without its heredoc bodies; or, where a quote or
    substitution does not end, where its line starts and what the lines
    before it read."""
    try:
        lexed = guard._bash_lex(text)
    except guard._Unterminated as unterminated:
        before = text[: unterminated.line_start]
        return {"error": unterminated.line_start, "before": bash_reading(guard, before)}
    return {
        "tokens": [[_token_kind(guard, token), str(token)] for token in lexed.tokens],
        "substitutions": lexed.substitutions,
        "codeBodies": lexed.code_bodies,
        "cleaned": lexed.cleaned(text),
    }


def _token_kind(guard: ModuleType, token: str) -> str:
    """An operator, a quoted word (never a reserved word), or a plain word."""
    if isinstance(token, guard._Op):
        return "op"
    return "quoted" if isinstance(token, guard._Quoted) else "word"


def entry(
    reference: ModuleType, fixed: dict[frozenset[str], ModuleType], text: str
) -> dict:
    """What the reference, and the reference with its fixes, make of one input."""
    try:
        tokens, token_error = reference._tokenize(text), None
    except ValueError as error:
        tokens, token_error = None, str(error)
    cleaned, code_bodies = reference.split_heredocs(text)
    reason = verdict(reference, text)
    full = fixed[frozenset(COMMAND_FIXES)]
    fixed_reason = verdict(full, text)
    difference = ""
    if fixed_reason != reason:
        needed = old_script_fixes.needed(
            COMMAND_FIXES, lambda applied: verdict(fixed[applied], text)
        )
        difference = old_script_fixes.difference(needed, "")
    return {
        "input": text,
        "tokens": tokens,
        "tokenError": token_error,
        "cleaned": cleaned,
        "codeBodies": code_bodies,
        "reason": reason,
        "fixed": fixed_reason,
        "difference": difference,
        "bash": bash_reading(full, text),
    }


def render() -> str:
    """The corpus file's content: one JSON object per line, ASCII only."""
    reference = load_reference()
    with tempfile.TemporaryDirectory() as scratch:
        fixed = load_fixed(Path(scratch))
        return "".join(
            json.dumps(entry(reference, fixed, text), ensure_ascii=True) + "\n"
            for text in inputs()
        )


def word_ranges() -> list[tuple[int, int]]:
    """Python re's \\w on str patterns, as ranges of code points (no surrogates)."""
    ranges: list[tuple[int, int]] = []
    for code in range(0x110000):
        if 0xD800 <= code <= 0xDFFF or re.fullmatch(r"\w", chr(code)) is None:
            continue
        if ranges and ranges[-1][1] == code - 1:
            ranges[-1] = (ranges[-1][0], code)
        else:
            ranges.append((code, code))
    return ranges


def render_word_table() -> str:
    """WORD_TABLE's content: Python's \\w as a unicode.RangeTable."""
    r16: list[tuple[int, int]] = []
    r32: list[tuple[int, int]] = []
    for lo, hi in word_ranges():
        if hi <= 0xFFFF:
            r16.append((lo, hi))
        elif lo > 0xFFFF:
            r32.append((lo, hi))
        else:
            r16.append((lo, 0xFFFF))
            r32.append((0x10000, hi))
    latin_offset = sum(1 for _, hi in r16 if hi <= 0xFF)
    version = PYTHON_UNICODE
    return "\n".join(
        [
            f"// Code generated by scripts/command_guard_corpus.py from Python's re (Unicode {version}); DO NOT EDIT.",
            "",
            "package commandguard",
            "",
            'import "unicode"',
            "",
            "// pythonUnicodeVersion is the Unicode version of the Python whose \\w",
            "// pythonWordTable is.",
            f'const pythonUnicodeVersion = "{version}"',
            "",
            '// pythonWordTable is Python re\'s \\w on str patterns: str.isalnum() or "_".',
            "var pythonWordTable = &unicode.RangeTable{",
            "\tR16: []unicode.Range16{",
            *[f"\t\t{{0x{lo:04x}, 0x{hi:04x}, 1}}," for lo, hi in r16],
            "\t},",
            "\tR32: []unicode.Range32{",
            *[f"\t\t{{0x{lo:x}, 0x{hi:x}, 1}}," for lo, hi in r32],
            "\t},",
            f"\tLatinOffset: {latin_offset},",
            "}",
            "",
        ]
    )


def main() -> None:
    if unicodedata.unidata_version != PYTHON_UNICODE:
        raise SystemExit(
            f"this Python has Unicode {unicodedata.unidata_version}; the corpus "
            f"follows {PYTHON_UNICODE} (Python 3.14): run `just command-guard-corpus`"
        )
    CORPUS.parent.mkdir(parents=True, exist_ok=True)
    CORPUS.write_text(render(), encoding="utf-8", newline="\n")
    WORD_TABLE.write_text(render_word_table(), encoding="utf-8", newline="\n")
    for path in (CORPUS, WORD_TABLE):
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
