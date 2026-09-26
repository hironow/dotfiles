#!/usr/bin/env python3
"""Keep a set of locally-declared forbidden tokens out of a PUBLIC repo.

One work unit here provisions a private GCP project, and that project's
identifiers -- project id, project number, billing account id, the owning org's
name, a work email domain, any bucket / service-account / Artifact Registry path
built from them -- must never reach a tracked file, a commit message, a PR body
or a public GitHub Actions log. Those strings turn up naturally in `gcloud`
output and in `tofu plan` output, so prose discipline is not a control; this is
the mechanical one.

Three design choices make it a wall rather than theatre:

**The token list lives outside the repo.** `~/.config/dotfiles/forbidden-tokens`
(mode 0600), or `$XDG_CONFIG_HOME/dotfiles/forbidden-tokens`, or whatever
`DOTFILES_FORBIDDEN_TOKENS` points at. Committing the list would publish exactly
what it protects. A checkout without one (CI, a fresh clone) scans nothing and
passes -- so this script is useless as a CI-side secret scanner, and is not one.

**Only ADDED lines are scanned.** Six tracked files and nine `main` commit
messages already contain the org token; cleaning those is a separate work unit.
A whole-file scanner would fail every commit forever and be switched off within
the hour, so the staged scan reads the added lines of the staged diff plus the
staged pathnames, and the branch scan reads the added lines of
`<base>..HEAD` plus each commit message in that range.

**Matched text is never printed.** Output reports `path:line` and the token's
index in the list, because this output can end up in a public log. The list is
local; grep it there.

Unreviewable blobs are the one unconditional leg, independent of the list:
`*.tfplan`, `*.tfstate*`, `terraform.tfvars`, `*.auto.tfvars`, `backend.hcl`,
anything under `.terraform/`, and anything git itself calls binary cannot be
scanned for tokens at all, so staging them is refused outright.
`DOTFILES_ALLOW_BINARY=1` overrides the binary leg deliberately.

Modes:
    staged                 pre-commit: added lines + paths + blob refusal
    commit-msg <file>      commit-msg: the message about to be recorded
    branch [--base REF]    `just ci`: the whole branch diff and every message
    file <path>...         a PR body (or any file) scanned in full

Exit code: 0 = clean, 1 = findings (listed on stderr). Stdlib only, and no `uv`
anywhere in its invocation: a hook that runs `uv run` can rewrite the root
`uv.lock` mid-commit, which is a known trap in this repo.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

EXIT_OK = 0
EXIT_FAIL = 1

TOKENS_ENV = "DOTFILES_FORBIDDEN_TOKENS"
ALLOW_BINARY_ENV = "DOTFILES_ALLOW_BINARY"

# Relative to $XDG_CONFIG_HOME, and to ~/.config as the fallback.
TOKENS_REL = Path("dotfiles") / "forbidden-tokens"

# Artifacts whose content cannot be reviewed for tokens, and which have no
# business being tracked in the first place. Matched against the basename.
UNREVIEWABLE_GLOBS = (
    "*.tfplan",
    "*.tfplan.*",
    "*.tfstate",
    "*.tfstate.*",
    "terraform.tfvars",
    "*.auto.tfvars",
    "backend.hcl",
    "*.tfbackend",
)
# Any path component equal to one of these makes the file unreviewable.
UNREVIEWABLE_DIRS = (".terraform",)

REDACTED = "<redacted>"

# `@@ -old,count +new,count @@` -- the new-side start line is what we count from.
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
# The single-letter path prefix in a `+++ ` header. Normally `b/`, but
# `diff.mnemonicPrefix` (set in this operator's git config) swaps it for the
# side's initial -- `i/` for the index, `w/` for the worktree, `c/` for a commit
# -- which a plain `removeprefix("b/")` leaves glued to the path. The diff calls
# below pass --src-prefix/--dst-prefix to pin it, and this strips whatever a
# caller's config produced anyway.
_DIFF_PREFIX_RE = re.compile(r"^[a-z]/")
# git's scissors line; everything below it is stripped from the recorded message.
_SCISSORS_RE = re.compile(r"^#\s*-+\s*>8\s*-+")

# Diff flags shared by every scan. --src-prefix/--dst-prefix pin the header
# prefixes so `diff.mnemonicPrefix` / `diff.noprefix` in a caller's git config
# cannot change what `added_lines` has to parse.
_DIFF_FLAGS = (
    "--unified=0",
    "--no-color",
    "--no-ext-diff",
    "--src-prefix=a/",
    "--dst-prefix=b/",
)

_LOG_RECORD_SEP = "\x1e"
_LOG_FIELD_SEP = "\x1f"


class Finding(NamedTuple):
    """One token hit, described without reproducing the matched text."""

    where: str
    token_index: int

    def render(self) -> str:
        return f"{self.where} matches forbidden token #{self.token_index}"


# --- the local token list ---------------------------------------------------


def tokens_path(env: Mapping[str, str], home: Path | None = None) -> Path | None:
    """Locate the local token list: explicit env, then XDG, then ~/.config."""
    explicit = env.get(TOKENS_ENV)
    if explicit:
        candidate = Path(explicit)
        return candidate if candidate.is_file() else None

    candidates: list[Path] = []
    xdg = env.get("XDG_CONFIG_HOME")
    if xdg:
        candidates.append(Path(xdg) / TOKENS_REL)
    base = home if home is not None else Path(env.get("HOME", "~")).expanduser()
    candidates.append(base / ".config" / TOKENS_REL)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_tokens(path: Path) -> list[str]:
    """One token per line, `#` comments and blanks dropped, lowercased.

    Lowercasing here is what makes matching case-insensitive in both
    directions: the haystack is lowercased too, at the single comparison site.
    """
    try:
        raw = path.read_text(errors="replace")
    except OSError:
        return []
    tokens: list[str] = []
    for line in raw.splitlines():
        token = line.strip()
        if not token or token.startswith("#"):
            continue
        lowered = token.lower()
        if lowered not in tokens:
            tokens.append(lowered)
    return tokens


def list_permission_warning(path: Path) -> str | None:
    """Warn (never fail) when the list is readable by group or others."""
    if os.name != "posix":
        return None
    try:
        mode = path.stat().st_mode
    except OSError:
        return None
    if mode & 0o077:
        return (
            f"warning: {path} is mode {mode & 0o777:04o}; the forbidden-token "
            f"list should be 0600 (it holds the very strings it protects)."
        )
    return None


# --- matching ---------------------------------------------------------------


def match_indices(haystack: str, tokens: Sequence[str]) -> list[int]:
    """1-based indices of every token found in `haystack` (case-insensitive)."""
    lowered = haystack.lower()
    return [i for i, token in enumerate(tokens, start=1) if token in lowered]


def scan_lines(
    lines: Iterable[tuple[str, str]], tokens: Sequence[str]
) -> list[Finding]:
    """Scan (location, text) pairs; one finding per (location, token)."""
    findings: list[Finding] = []
    for where, text in lines:
        findings.extend(Finding(where, index) for index in match_indices(text, tokens))
    return findings


def redact(text: str, tokens: Sequence[str]) -> str:
    """Replace every token occurrence so a printed pathname cannot leak one."""
    out = text
    for token in tokens:
        if not token:
            continue
        out = re.sub(re.escape(token), REDACTED, out, flags=re.IGNORECASE)
    return out


# --- git plumbing -----------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _git_ok(cwd: Path, *args: str) -> str | None:
    try:
        return _git(cwd, *args)
    except (subprocess.CalledProcessError, OSError):
        return None


def added_lines(diff: str) -> list[tuple[str, int, str]]:
    """(path, new-file line number, text) for every added line of a diff.

    Written against `--unified=0` output but correct for context lines too: a
    ` ` context line advances the new-side counter, a `-` line does not.
    """
    result: list[tuple[str, int, str]] = []
    path: str | None = None
    lineno = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            path = None if target == "/dev/null" else _DIFF_PREFIX_RE.sub("", target, 1)
            continue
        if raw.startswith("--- ") or raw.startswith("diff --git "):
            continue
        hunk = _HUNK_RE.match(raw)
        if hunk:
            lineno = int(hunk.group(1))
            continue
        if path is None:
            continue
        if raw.startswith("+"):
            result.append((path, lineno, raw[1:]))
            lineno += 1
        elif raw.startswith(" "):
            lineno += 1
    return result


def parse_numstat_z(output: str) -> list[tuple[str, str, str]]:
    """(added, deleted, path) from `git diff --numstat -z`.

    A rename emits an empty path field followed by two extra NUL-separated
    fields (pre- and post-image); the post-image is the one that matters.
    """
    fields = output.split("\0")
    entries: list[tuple[str, str, str]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field:
            continue
        parts = field.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], "\t".join(parts[2:])
        if not path:
            if index + 1 >= len(fields):
                continue
            path = fields[index + 1]
            index += 2
        entries.append((added, deleted, path))
    return entries


def staged_paths(cwd: Path) -> list[str]:
    output = _git(
        cwd, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", "-M"
    )
    return [path for path in output.split("\0") if path]


def staged_binary_paths(cwd: Path) -> list[str]:
    output = _git(
        cwd, "diff", "--cached", "--numstat", "-z", "--diff-filter=ACMR", "-M"
    )
    return [
        path
        for added, deleted, path in parse_numstat_z(output)
        if added == "-" and deleted == "-"
    ]


# --- unreviewable blobs -----------------------------------------------------


def unreviewable_reason(path: str) -> str | None:
    """Why this path can never be reviewed for tokens, or None if it can."""
    parts = Path(path).parts
    for directory in UNREVIEWABLE_DIRS:
        if directory in parts:
            return f"lives under {directory}/"
    name = parts[-1] if parts else path
    for pattern in UNREVIEWABLE_GLOBS:
        if fnmatch.fnmatch(name, pattern):
            return f"matches {pattern}"
    return None


def refusals(cwd: Path, env: Mapping[str, str], tokens: Sequence[str]) -> list[str]:
    """Paths whose staging is refused outright, with the reason."""
    messages: list[str] = []
    paths = staged_paths(cwd)
    for path in paths:
        reason = unreviewable_reason(path)
        if reason is not None:
            messages.append(
                f"refusing to stage '{redact(path, tokens)}': unreviewable "
                f"artifact ({reason}); it must never be tracked."
            )
    if env.get(ALLOW_BINARY_ENV) == "1":
        return messages
    refused = {message.split("'")[1] for message in messages}
    for path in staged_binary_paths(cwd):
        if redact(path, tokens) in refused:
            continue
        messages.append(
            f"refusing to stage '{redact(path, tokens)}': git reports it as "
            f"binary, so its content cannot be scanned for tokens (set "
            f"{ALLOW_BINARY_ENV}=1 to override deliberately)."
        )
    return messages


# --- commit message normalisation ------------------------------------------


def recorded_message(raw: str) -> str:
    """What git will actually record: `#` lines dropped, scissors body cut.

    Scanning the stripped part only produces false positives -- the status
    block names the branch and every staged path, and the verbose body repeats
    the whole diff, which the staged scan already covered.
    """
    kept: list[str] = []
    for line in raw.splitlines():
        if _SCISSORS_RE.match(line):
            break
        if line.startswith("#"):
            continue
        kept.append(line)
    return "\n".join(kept)


def message_findings(label: str, message: str, tokens: Sequence[str]) -> list[Finding]:
    return scan_lines(
        (
            (f"{label} line {number}", line)
            for number, line in enumerate(message.splitlines(), start=1)
        ),
        tokens,
    )


# --- modes ------------------------------------------------------------------


def run_staged(
    cwd: Path, env: Mapping[str, str], tokens: Sequence[str]
) -> tuple[list[str], list[Finding]]:
    blocked = refusals(cwd, env, tokens)
    if not tokens:
        return blocked, []
    findings: list[Finding] = []
    for path in staged_paths(cwd):
        findings.extend(
            Finding(f"staged path '{redact(path, tokens)}'", index)
            for index in match_indices(path, tokens)
        )
    diff = _git(cwd, "diff", "--cached", *_DIFF_FLAGS)
    findings.extend(
        scan_lines(
            (
                (f"staged added line {redact(path, tokens)}:{line}", text)
                for path, line, text in added_lines(diff)
            ),
            tokens,
        )
    )
    return blocked, findings


def resolve_base(cwd: Path, requested: str | None) -> str | None:
    """The merge base to rescan from: explicit, else origin/main, else main."""
    if requested:
        resolved = _git_ok(cwd, "rev-parse", "--verify", "--quiet", requested)
        return resolved.strip() if resolved and resolved.strip() else None
    for ref in ("origin/main", "main"):
        if _git_ok(cwd, "rev-parse", "--verify", "--quiet", ref) is None:
            continue
        merge_base = _git_ok(cwd, "merge-base", ref, "HEAD")
        if merge_base and merge_base.strip():
            return merge_base.strip()
    return None


def run_branch(
    cwd: Path, base: str, tokens: Sequence[str]
) -> tuple[list[str], list[Finding]]:
    findings: list[Finding] = []
    diff = _git(cwd, "diff", *_DIFF_FLAGS, "-M", base, "HEAD")
    findings.extend(
        scan_lines(
            (
                (f"branch added line {redact(path, tokens)}:{line}", text)
                for path, line, text in added_lines(diff)
            ),
            tokens,
        )
    )
    log = _git(
        cwd,
        "log",
        f"--format=%H{_LOG_FIELD_SEP}%B{_LOG_RECORD_SEP}",
        f"{base}..HEAD",
    )
    for record in log.split(_LOG_RECORD_SEP):
        if _LOG_FIELD_SEP not in record:
            continue
        sha, message = record.split(_LOG_FIELD_SEP, 1)
        findings.extend(
            message_findings(f"commit message of {sha.strip()[:12]}", message, tokens)
        )
    return [], findings


def run_files(paths: Sequence[str], tokens: Sequence[str]) -> list[Finding]:
    findings: list[Finding] = []
    for raw in paths:
        text = Path(raw).read_text(errors="replace")
        findings.extend(
            scan_lines(
                (
                    (f"{raw}:{number}", line)
                    for number, line in enumerate(text.splitlines(), start=1)
                ),
                tokens,
            )
        )
    return findings


# --- entry point ------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_forbidden_tokens.py", description=__doc__
    )
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("staged", help="scan the staged diff (pre-commit)")
    commit_msg = modes.add_parser("commit-msg", help="scan a commit message file")
    commit_msg.add_argument("message_file")
    branch = modes.add_parser("branch", help="rescan the whole branch")
    branch.add_argument("--base", default=None)
    files = modes.add_parser("file", help="scan whole files (e.g. a PR body)")
    files.add_argument("paths", nargs="+")
    return parser


def _report(
    blocked: Sequence[str],
    findings: Sequence[Finding],
    list_path: Path | None,
    token_count: int,
) -> int:
    if not blocked and not findings:
        return EXIT_OK
    print(
        "check-forbidden-tokens: FAILED -- this repo is PUBLIC; the private "
        "project's identifiers must not enter a tracked file, a commit message "
        "or a PR body:",
        file=sys.stderr,
    )
    for message in blocked:
        print(f"  - {message}", file=sys.stderr)
    for finding in findings:
        print(f"  - {finding.render()}", file=sys.stderr)
    if findings:
        print(
            "The matched text is deliberately not printed (this output can "
            "reach a public log). Token list: "
            f"{list_path} ({token_count} entries) -- grep it locally.",
            file=sys.stderr,
        )
    return EXIT_FAIL


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cwd = Path.cwd()
    env = os.environ

    # Structural problems fail before the no-list shortcut: a hook pointed at a
    # message file that does not exist is broken, not clean.
    if args.mode == "commit-msg" and not Path(args.message_file).is_file():
        print(
            f"check-forbidden-tokens: commit message file not found: "
            f"{args.message_file}",
            file=sys.stderr,
        )
        return EXIT_FAIL
    if args.mode == "file":
        missing = [path for path in args.paths if not Path(path).is_file()]
        if missing:
            for path in missing:
                print(
                    f"check-forbidden-tokens: file not found: {path}", file=sys.stderr
                )
            return EXIT_FAIL

    list_path = tokens_path(env)
    tokens = load_tokens(list_path) if list_path is not None else []
    if list_path is None:
        print(
            "check-forbidden-tokens: no forbidden-token list "
            f"(${TOKENS_ENV}, $XDG_CONFIG_HOME/{TOKENS_REL.as_posix()} or "
            f"~/.config/{TOKENS_REL.as_posix()}); token scan skipped."
        )
    else:
        warning = list_permission_warning(list_path)
        if warning:
            print(f"check-forbidden-tokens: {warning}", file=sys.stderr)

    blocked: list[str] = []
    findings: list[Finding] = []

    if args.mode == "staged":
        blocked, findings = run_staged(cwd, env, tokens)
    elif args.mode == "commit-msg":
        if tokens:
            message = recorded_message(
                Path(args.message_file).read_text(errors="replace")
            )
            findings = message_findings("commit message", message, tokens)
    elif args.mode == "branch":
        base = resolve_base(cwd, args.base)
        if base is None:
            print(
                "check-forbidden-tokens: no merge base to rescan from "
                "(neither origin/main nor main is reachable; pass --base REF); "
                "branch scan skipped."
            )
        elif tokens:
            blocked, findings = run_branch(cwd, base, tokens)
    elif args.mode == "file" and tokens:
        findings = run_files(args.paths, tokens)

    exit_code = _report(blocked, findings, list_path, len(tokens))
    if exit_code == EXIT_OK and tokens:
        print(
            f"check-forbidden-tokens: OK -- {args.mode} scan clean against "
            f"{len(tokens)} forbidden token(s)."
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
