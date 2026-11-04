"""The old hook scripts' bugs that the agent-hook binary fixes, as named edits.

The owner decided (2026-11-04) that where an old script has a bug, the binary
fixes it, and the tests keep each fix apart from the faithful port. Each fix
here is a small edit to an old script. The corpus generators apply them to
copies of the scripts ("the old script, fixed"), so the fixed behavior is
defined by a script, as the legacy behavior is, never by Go.

Every corpus input runs through the old scripts and through the scripts with
every fix. Where the answers (after the corpus's own noise normalization)
differ, the binary gives the fixed answer, and the run names the fixes it
needs: those whose absence from the full set changes the answer.
"""

import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES_GUARD = "ROOT_AGENTS_hooks_block-prohibited-files.sh"
FORMATTER = "ROOT_AGENTS_hooks_format-after-edit.sh"


@dataclass(frozen=True)
class Fix:
    """One fix: edits to one script, each an exact text replaced once."""

    script: str
    edits: tuple[tuple[str, str], ...]
    bug: str


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
    and bash's warnings name the same scripts."""
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
        else:
            shutil.copy2(source, target)
    return directory


def needed(
    names: Iterable[str], answer_of: Callable[[frozenset[str]], object]
) -> list[str]:
    """The fixes a run needs, sorted: with every fix the answer differs from
    the old script's, and leaving the fix out changes the full answer. A
    difference that no single fix's absence undoes is refused: its fixes each
    make it alone, and the run would name none."""
    names = tuple(names)
    everything = frozenset(names)
    full = answer_of(everything)
    if full == answer_of(frozenset()):
        return []
    found = sorted(name for name in names if answer_of(everything - {name}) != full)
    if not found:
        msg = f"the fixes {sorted(names)} change the answer, but no fix's absence undoes it"
        raise ValueError(msg)
    return found


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
