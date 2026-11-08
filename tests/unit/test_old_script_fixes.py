"""Tests for scripts/old_script_fixes.py: the named fixes the binary makes to
the old hook scripts' bugs, applied to copies of those scripts.

The corpora (files guard, payloads, tool hooks) run each input through the old
script and through the old script with every fix applied. Where the answers
differ, the binary gives the fixed one, and the run names the fixes it needs.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import old_script_fixes as fixes

FILES_GUARD = "ROOT_AGENTS_hooks_block-prohibited-files.sh"
FORMATTER = "ROOT_AGENTS_hooks_format-after-edit.sh"

# The tests that run the old scripts need bash and jq, and the formatter's
# makes a file whose name holds a newline: POSIX only. The rest run anywhere.
runs_the_scripts = pytest.mark.skipif(
    sys.platform == "win32"
    or shutil.which("bash") is None
    or shutil.which("jq") is None,
    reason="the old scripts need bash and jq on a POSIX file system",
)


def run(directory: Path, script: str, payload: dict) -> int:
    done = subprocess.run(
        ["bash", script],
        input=json.dumps(payload),
        cwd=directory,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return done.returncode


def variant(tmp_path: Path, names: set[str]) -> Path:
    directory = tmp_path / "-".join(sorted(names) or ["old"])
    fixes.write_scripts(directory, frozenset(names))
    return directory


def test_every_fix_names_a_script_and_applies_exactly_once():
    for name, fix in fixes.FIXES.items():
        text = (ROOT / fix.script).read_text(encoding="utf-8")
        assert fix.edits, name
        for old, new in fix.edits:
            assert text.count(old) == 1, (name, old)
            assert old != new, name


def test_a_fix_whose_text_moved_fails_loudly(tmp_path: Path):
    broken = fixes.Fix(script=FILES_GUARD, edits=(("no such text", "x"),), bug="b")
    with pytest.raises(ValueError, match="no such text"):
        fixes.apply_fixes("text", [broken])


@runs_the_scripts
@pytest.mark.parametrize(
    ("payload", "old", "dash", "notebook", "both"),
    [
        # A "-" line stopped the old guard (basename failed, exit 1).
        ({"tool_input": {"file_path": "ok\n--bogus\nbad.yml"}}, 1, 2, 1, 2),
        ({"tool_input": {"file_path": "--x.yml"}}, 1, 2, 1, 2),
        # The old guard never read notebook_path.
        ({"tool_input": {"file_path": "", "notebook_path": "bad.yml"}}, 0, 0, 2, 2),
        (
            {"tool_input": {"file_path": "safe.md", "notebook_path": "bad.yml"}},
            0,
            0,
            2,
            2,
        ),
        # Both fixes at once: neither alone blocks.
        ({"tool_input": {"notebook_path": "--x.yml"}}, 0, 0, 1, 2),
        # What blocked before still blocks.
        (
            {"tool_input": {"file_path": "bad.yml", "notebook_path": "safe.ipynb"}},
            2,
            2,
            2,
            2,
        ),
        ({"tool_input": {"file_path": "a/b.yml/"}}, 2, 2, 2, 2),
        # A path of slashes, and a trailing slash, as basename(1) reads them.
        ({"tool_input": {"file_path": "///"}}, 0, 0, 0, 0),
        ({"tool_input": {"file_path": "a/docker-compose.yml//"}}, 2, 2, 2, 2),
    ],
)
def test_the_files_guard_fixes(tmp_path: Path, payload, old, dash, notebook, both):
    got = [
        run(variant(tmp_path, names), FILES_GUARD, payload)
        for names in (
            set(),
            {"dash-line"},
            {"notebook-path"},
            {"dash-line", "notebook-path"},
        )
    ]
    assert got == [old, dash, notebook, both]


def test_needed_leaves_each_fix_out_of_the_full_set():
    # notebook_path "--x.yml": the full set blocks, and either fix left out passes.
    answers = {
        frozenset(): "pass",
        frozenset({"dash-line"}): "pass",
        frozenset({"notebook-path"}): "pass",
        frozenset({"dash-line", "notebook-path"}): "block",
    }
    names = ("dash-line", "notebook-path")
    assert fixes.needed(names, lambda applied: answers[applied]) == [
        "dash-line",
        "notebook-path",
    ]
    # A fix whose absence changes nothing is not needed.
    answers[frozenset({"notebook-path"})] = "block"
    assert fixes.needed(names, lambda applied: answers[applied]) == ["notebook-path"]
    # No difference at all: nothing is needed.
    assert fixes.needed(names, lambda applied: "pass") == []


def test_needed_refuses_a_difference_no_fix_explains():
    # The full set differs from the old script, but leaving any one fix out
    # changes nothing: two fixes each make the change alone.
    answers = {
        frozenset(): "pass",
        frozenset({"a"}): "block",
        frozenset({"b"}): "block",
        frozenset({"a", "b"}): "block",
    }
    with pytest.raises(ValueError, match="no fix"):
        fixes.needed(("a", "b"), lambda applied: answers[applied])


def test_a_derived_input_is_refused_only_when_its_base_needs_a_fix():
    # A derived input (its base plus an unused member) takes its base's
    # answer, so a base the binary answers apart from the old script, on
    # purpose, cannot be one. A base whose fixed run changed only the noise
    # is fine: it names no fix.
    noise_only = {"difference": "", "fixed": {"exit": 0}}
    fixes.refuse_a_base_that_needs_a_fix("derived", "base", noise_only)
    fixes.refuse_a_base_that_needs_a_fix(
        "derived", "base", {"difference": "nul-warning"}
    )
    for difference in ("fixed-dash-line", "fixed-dash-line+nul-warning"):
        with pytest.raises(ValueError, match="needs a fix"):
            fixes.refuse_a_base_that_needs_a_fix(
                "derived", "base", {"difference": difference, "fixed": {}}
            )


def test_difference_joins_the_needed_fixes_and_the_noise_sorted():
    assert fixes.difference(["notebook-path", "dash-line"], "nul-warning") == (
        "fixed-dash-line+fixed-notebook-path+nul-warning"
    )
    assert fixes.difference(["one-path"], "") == "fixed-one-path"
    assert fixes.difference([], "nul-warning") == "nul-warning"
    assert fixes.difference([], "") == ""


@runs_the_scripts
def test_the_formatter_reads_file_path_as_one_path(tmp_path: Path):
    # The old formatter formats each line of file_path, NULs and trailing
    # newlines dropped; fixed, the whole string names one file. A gofmt stub
    # records each path it is asked to format, NUL-terminated.
    fixed = variant(tmp_path, {"one-path"})
    old = variant(tmp_path, set())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gofmt.log"
    stub = bin_dir / "gofmt"
    stub.write_text(f'#!/bin/sh\nprintf "%s\\0" "$2" >> "{log}"\n', encoding="utf-8")
    stub.chmod(0o755)
    jq = shutil.which("jq")
    assert jq is not None
    (bin_dir / "jq").symlink_to(jq)  # jq may live outside /usr/bin (homebrew)
    for name in ("victim.go", "a\nb.go", "a.go"):
        (tmp_path / name).write_text("package p\n", encoding="utf-8")

    def formatted(directory: Path, file_path: str) -> list[str]:
        log.unlink(missing_ok=True)
        subprocess.run(
            ["bash", FORMATTER],
            input=json.dumps({"tool_input": {"file_path": file_path}}),
            cwd=directory,
            env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if not log.exists():
            return []
        return log.read_text(encoding="utf-8").split("\0")[:-1]

    victim = str(tmp_path / "victim.go")
    # A line of the path names another file: the old script formats it.
    assert formatted(old, f"/nowhere/dir\n{victim}") == [victim]
    assert formatted(fixed, f"/nowhere/dir\n{victim}") == []
    # A trailing newline is part of the name: "victim.go\n" is no Go file.
    assert formatted(old, f"{victim}\n") == [victim]
    assert formatted(fixed, f"{victim}\n") == []
    # A newline inside a Go file's name: only that one file.
    inside = str(tmp_path / "a\nb.go")
    assert formatted(old, inside) == []
    assert formatted(fixed, inside) == [inside]
    # A NUL names no file; the old script dropped it and formatted a.go.
    assert formatted(old, f"{tmp_path}/a.\u0000go") == [str(tmp_path / "a.go")]
    assert formatted(fixed, f"{tmp_path}/a.\u0000go") == []
    # A plain path, and a patch when file_path is empty, are as before.
    assert formatted(fixed, victim) == [victim]
