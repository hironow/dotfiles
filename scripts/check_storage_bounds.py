#!/usr/bin/env python3
"""Require every OpenTofu storage sink to declare an explicit, bounded limit.

An unbounded sink is how a personal GCP project quietly accumulates cost.
Nothing fails, no alert fires, no review catches it: images and objects just
keep landing, and the bill grows a little every month. This repo already has the
receipt -- the dev container repository in tofu/exe/ reached 20+ versions and
~21 GiB because its only DELETE policy targeted UNTAGGED versions and every
publish tagged its image (ADR 0034). The policy looked like a bound and was not.

Artifact Registry has two traps that read as protection:

* **KEEP beats DELETE.** When both policies match a version, the version
  survives. So a KEEP written to protect a rolling tag silently widens into
  "protect everything" if its condition is broader than intended.
* **`most_recent_versions` is a floor, not a cap.** It says "never delete the
  newest N", not "keep at most N". A repository whose only policy is a
  `most_recent_versions` KEEP therefore deletes *nothing at all*, forever.

A third trap costs an apply instead of money: a single policy block may carry a
`condition` or a `most_recent_versions`, never both, and the rejection comes
from the API at apply time -- `tofu plan` is perfectly happy. Ten policies per
repository is the hard limit, so consolidation pressure is real and the
temptation to merge two KEEPs into one mixed block is exactly how that error
gets written.

GCS is quieter. Uniform bucket-level access and enforced public access
prevention are safety, not cost, but they belong to the same "declared, not
assumed" discipline. The cost item is `soft_delete_policy`: its default keeps
every deleted object for 7 days as billed storage, which nobody asked for and
nobody sees. And the bound itself -- a delete lifecycle rule or a generation cap
-- has exactly one deliberate exception: the snapshots bucket must have no
delete lifecycle at all, because a lifecycle rule cannot tell a referenced
snapshot from an abandoned one, and deleting a referenced snapshot makes a
suspended task impossible to resume. So the snapshot rule is enforced in both
directions: the snapshots bucket must NOT have a delete rule, and every other
bucket MUST have a bound.

The gate reads the HCL rather than trusting the review that wrote it, which
means it needs just enough of an HCL parser. It has a deliberately small block
scanner: comments (`#`, `//`, `/* */`) and heredoc bodies are blanked out,
string literals (including `${...}` interpolations, where quotes nest) are
opaque, and brace depth is tracked over what is left. That string- and
comment-awareness is not polish: a scanner that loses depth inside a string
stops seeing resources and reports a clean scan, which is the one failure mode
a cost gate cannot afford.

What the scanner deliberately does NOT handle, and why that is acceptable here:

* **No expression evaluation.** A `var.` / `local.` / `data.` reference where a
  literal bound is required is reported as "cannot evaluate" -- an unevaluatable
  bound is an unproven bound, never a silent pass.
* **No module expansion.** A sink created by a remote module is invisible. Sinks
  declared in a local module under `tofu/` are scanned, because its `.tf` files
  are.
* **No `count` / `for_each` awareness.** One block is checked once, which is
  what these rules mean anyway (the bound is per declaration).
* **First attribute wins** on a duplicate, and no HCL validity checking at all:
  `tofu validate` owns syntax, this gate owns the bounds.
* **`.tf.json` is not scanned** -- nothing in this repo writes it.

Exit code: 0 = clean, 1 = violations found (listed on stderr). Stdlib only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

EXIT_OK = 0
EXIT_FAIL = 1

# Every stack lives under tofu/; nothing else is scanned.
TOFU_GLOB = "tofu/**/*.tf"

REPOSITORY_TYPE = "google_artifact_registry_repository"
BUCKET_TYPE = "google_storage_bucket"

# The hashicorp/google provider spells the repeatable policy block
# `cleanup_policies` (plural); the plan's prose calls one of them a
# "cleanup_policy". Both spellings are accepted because a gate that matched
# only the prose spelling would find zero policies in every real file and
# report a clean scan -- the exact silent pass this whole file exists to stop.
CLEANUP_POLICY_BLOCK_NAMES = ("cleanup_policies", "cleanup_policy")

# Artifact Registry's own limit. Exceeding it fails the apply, not the plan.
MAX_CLEANUP_POLICIES = 10

# A bucket whose resource label or `name` contains one of these (matched
# case-insensitively) is the snapshots bucket: it must carry no delete
# lifecycle rule, because deleting a referenced snapshot makes a suspended task
# unresumable. Its bound is the task lifetime, enforced by the Substrate GC.
SNAPSHOT_BUCKET_MARKERS = ("snapshot",)

# The value `public_access_prevention` must carry.
REQUIRED_PUBLIC_ACCESS_PREVENTION = "enforced"

# The lifecycle action type that actually removes objects.
DELETE_ACTION_TYPE = "delete"

_HEREDOC_RE = re.compile(r"<<-?([A-Za-z_][A-Za-z0-9_]*)")
_HEADER_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_-]*)((?:\s+"(?:[^"\\]|\\.)*")*)\s*$')
_LABEL_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_QUOTED_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"$')
_BOOLS = {"true": True, "false": False}


class Block(NamedTuple):
    """One HCL block: its keyword, its quoted labels, and its inner text.

    `kind` is the leading keyword (`resource`, `cleanup_policies`, `condition`,
    ...) and `labels` the quoted words after it, so a resource block is
    `Block("resource", ("google_storage_bucket", "ops"), ...)`. `body` excludes
    the braces and is already comment- and heredoc-blanked.
    """

    kind: str
    labels: tuple[str, ...]
    body: str


class ScanResult(NamedTuple):
    """Everything main() needs to print: what failed and what was looked at."""

    violations: list[str]
    repositories: int
    buckets: int
    files: int


class _Span(NamedTuple):
    header: str
    body_start: int
    body_end: int


# --- scrubbing: comments and heredocs out, strings intact -------------------


def _blank(chunk: str) -> str:
    """`chunk` with every character but a newline replaced by a space."""
    return "".join("\n" if char == "\n" else " " for char in chunk)


def _skip_string(text: str, index: int) -> int:
    """Offset just past the closing quote of the string starting at `index`.

    Interpolations are followed rather than ignored: HCL allows nested quotes
    inside `${...}`, so a naive scan would end the string early and then read
    the interpolation's closing `}` as a block close, dropping brace depth by
    one for the rest of the file.
    """
    position = index + 1
    end = len(text)
    while position < end:
        char = text[position]
        if char == "\\":
            position += 2
            continue
        if char == '"':
            return position + 1
        if char == "\n":
            return position  # unterminated: resync instead of eating the file
        if text.startswith("${", position) or text.startswith("%{", position):
            position = _skip_interpolation(text, position + 2)
            continue
        position += 1
    return end


def _skip_interpolation(text: str, index: int) -> int:
    """Offset just past the `}` that closes an interpolation opened before `index`."""
    depth = 1
    position = index
    end = len(text)
    while position < end and depth:
        char = text[position]
        if char == '"':
            position = _skip_string(text, position)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        position += 1
    return position


def _heredoc_end(text: str, start: int, terminator: str) -> int:
    """Offset just past the line that closes a heredoc, or end of text."""
    position = start
    end = len(text)
    while position < end:
        newline = text.find("\n", position)
        line_end = end if newline == -1 else newline
        if text[position:line_end].strip() == terminator:
            return line_end if newline == -1 else newline + 1
        if newline == -1:
            return end
        position = newline + 1
    return end


def scrub(text: str) -> str:
    """`text` with comments and heredoc bodies blanked, same length and lines.

    Offsets and line structure survive, so everything downstream can treat the
    result as the file itself. Strings are copied verbatim because their values
    are read (a bucket `name`, a policy `action`); it is the brace scanner, not
    this pass, that knows strings are opaque.
    """
    out: list[str] = []
    index = 0
    end = len(text)
    while index < end:
        char = text[index]
        if char == '"':
            stop = _skip_string(text, index)
            out.append(text[index:stop])
            index = stop
            continue
        if char == "#" or text.startswith("//", index):
            newline = text.find("\n", index)
            stop = end if newline == -1 else newline
            out.append(_blank(text[index:stop]))
            index = stop
            continue
        if text.startswith("/*", index):
            close = text.find("*/", index + 2)
            stop = end if close == -1 else close + 2
            out.append(_blank(text[index:stop]))
            index = stop
            continue
        heredoc = _HEREDOC_RE.match(text, index)
        if heredoc is not None:
            newline = text.find("\n", heredoc.end())
            stop = (
                end
                if newline == -1
                else _heredoc_end(text, newline + 1, heredoc.group(1))
            )
            out.append(_blank(text[index:stop]))
            index = stop
            continue
        out.append(char)
        index += 1
    return "".join(out)


# --- the block scanner ------------------------------------------------------


def _top_level_spans(text: str) -> list[_Span]:
    """Every brace block at the top level of `text`, as header + body offsets."""
    spans: list[_Span] = []
    index = 0
    end = len(text)
    depth = 0
    header_start = 0
    body_start = 0
    header = ""
    while index < end:
        char = text[index]
        if char == '"':
            index = _skip_string(text, index)
            continue
        if char == "{":
            if depth == 0:
                header = text[header_start:index]
                body_start = index + 1
            depth += 1
            index += 1
            continue
        if char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0:
                    spans.append(_Span(header, body_start, index))
                    header_start = index + 1
            else:
                header_start = index + 1  # stray close brace: resync
            index += 1
            continue
        if depth == 0 and char in "\n;":
            header_start = index + 1
        index += 1
    return spans


def _parse_header(header: str) -> tuple[str, tuple[str, ...]] | None:
    """(keyword, labels) for a block header, or None if it is not one.

    `labels = { ... }` and other object expressions land here too; they have no
    bare keyword before the brace, so they are rejected and never mistaken for
    blocks.
    """
    match = _HEADER_RE.match(header)
    if match is None:
        return None
    labels = tuple(found.group(1) for found in _LABEL_RE.finditer(match.group(2)))
    return match.group(1), labels


def iter_blocks(text: str) -> list[Block]:
    """Every parseable block at the top level of `text` (already scrubbed)."""
    blocks: list[Block] = []
    for span in _top_level_spans(text):
        parsed = _parse_header(span.header)
        if parsed is None:
            continue
        kind, labels = parsed
        blocks.append(Block(kind, labels, text[span.body_start : span.body_end]))
    return blocks


def resource_blocks(text: str, resource_type: str) -> list[Block]:
    """Every `resource "<resource_type>" "<label>" { ... }` block in `text`."""
    return [
        block
        for block in iter_blocks(text)
        if block.kind == "resource"
        and len(block.labels) == 2
        and block.labels[0] == resource_type
    ]


def sub_blocks(body: str, *names: str) -> list[Block]:
    """The direct child blocks of `body` whose keyword is one of `names`."""
    return [block for block in iter_blocks(body) if block.kind in names]


def strip_sub_blocks(body: str) -> str:
    """`body` with every nested block's contents blanked out.

    Attribute reads run on this so that "the bucket's `name`" can never be
    satisfied by a `name` buried in some nested block.
    """
    chars = list(body)
    for span in _top_level_spans(body):
        for position in range(span.body_start, span.body_end):
            if chars[position] != "\n":
                chars[position] = " "
    return "".join(chars)


def read_attribute(body: str, key: str) -> str | None:
    """The raw right-hand side of a direct `key = ...` in `body`, or None.

    Raw on purpose: whether the text is a literal this gate can judge is the
    caller's question, asked through literal_bool / literal_int / literal_string.
    """
    pattern = re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*=(.*)$", re.MULTILINE)
    match = pattern.search(strip_sub_blocks(body))
    if match is None:
        return None
    return match.group(1).strip()


# --- literal readers: "cannot judge it" is never "it is fine" ---------------


def literal_bool(raw: str | None) -> bool | None:
    """True/False for a literal boolean; None for absent or any expression."""
    if raw is None:
        return None
    return _BOOLS.get(raw.strip())


def literal_int(raw: str | None) -> int | None:
    """The value of a literal integer; None for absent or any expression."""
    if raw is None:
        return None
    text = raw.strip()
    try:
        return int(text)
    except ValueError:
        return None


def literal_string(raw: str | None) -> str | None:
    """The value of a plain quoted string; None for absent or any expression.

    A string carrying `${...}` or `%{...}` is an expression, not a literal, so
    it reads as unevaluatable rather than as its own source text.
    """
    if raw is None:
        return None
    match = _QUOTED_RE.match(raw.strip())
    if match is None:
        return None
    value = match.group(1)
    if "${" in value or "%{" in value:
        return None
    return value.replace('\\"', '"').replace("\\\\", "\\")


# --- rules 1-6: Artifact Registry repositories ------------------------------


def _policy_id(policy: Block) -> str:
    return literal_string(read_attribute(policy.body, "id")) or "<no id>"


def check_repository(rel: str, block: Block) -> list[str]:
    """Every cleanup-policy rule for one google_artifact_registry_repository."""
    where = f'{rel}: {REPOSITORY_TYPE} "{block.labels[1]}"'
    violations: list[str] = []
    body = block.body

    # Rule 1: the policies only act when dry-run is explicitly off.
    raw_dry_run = read_attribute(body, "cleanup_policy_dry_run")
    if raw_dry_run is None:
        violations.append(
            f"{where}: cleanup_policy_dry_run is absent. It must be declared "
            f"`false`: a bound nobody wrote down is a bound nobody can check, "
            f"and if it is ever flipped to `true` every policy below goes inert "
            f"while the repository keeps growing."
        )
    else:
        dry_run = literal_bool(raw_dry_run)
        if dry_run is None:
            violations.append(
                f"{where}: cannot evaluate cleanup_policy_dry_run = "
                f"{raw_dry_run} -- it must be the literal `false`. An "
                f"unevaluatable bound is an unproven bound."
            )
        elif dry_run:
            violations.append(
                f"{where}: cleanup_policy_dry_run = true, so every cleanup "
                f"policy is inert and the repository is unbounded. Set it to "
                f"false."
            )

    policies = sub_blocks(body, *CLEANUP_POLICY_BLOCK_NAMES)

    # Rule 6: past the limit the apply fails, not the plan.
    if len(policies) > MAX_CLEANUP_POLICIES:
        violations.append(
            f"{where}: has {len(policies)} cleanup_policy blocks; Artifact "
            f"Registry allows at most {MAX_CLEANUP_POLICIES} per repository "
            f"(MAX_CLEANUP_POLICIES), so the apply is rejected. Merge the "
            f"overlapping ones -- but never by mixing a condition with "
            f"most_recent_versions in one block."
        )

    keeps: list[Block] = []
    deletes: list[Block] = []
    for policy in policies:
        policy_id = _policy_id(policy)
        raw_action = read_attribute(policy.body, "action")
        action = literal_string(raw_action)
        if action is None:
            violations.append(
                f"{where}: cannot evaluate the action of cleanup_policy "
                f"'{policy_id}' ({raw_action if raw_action else 'absent'}) -- "
                f'it must be the literal "KEEP" or "DELETE". A policy whose '
                f"effect cannot be read is a bound that cannot be proven."
            )
        elif action.upper() == "KEEP":
            keeps.append(policy)
        elif action.upper() == "DELETE":
            deletes.append(policy)
        else:
            violations.append(
                f"{where}: cleanup_policy '{policy_id}' has action "
                f'"{action}"; Artifact Registry accepts only "KEEP" or '
                f'"DELETE".'
            )

        # Rule 4: the two condition shapes are mutually exclusive per block.
        has_condition = bool(sub_blocks(policy.body, "condition"))
        has_recent = bool(sub_blocks(policy.body, "most_recent_versions"))
        if has_condition and has_recent:
            violations.append(
                f"{where}: cleanup_policy '{policy_id}' contains both a "
                f"condition block and a most_recent_versions block. Artifact "
                f"Registry accepts one or the other per policy, never both, so "
                f"`tofu apply` is rejected while `tofu plan` looks fine. Split "
                f"it into two policies."
            )

    # Rules 2 and 5: something must actually delete.
    if not deletes:
        only_floors = bool(keeps) and all(
            sub_blocks(keep.body, "most_recent_versions")
            and not sub_blocks(keep.body, "condition")
            for keep in keeps
        )
        if only_floors:
            violations.append(
                f"{where}: every KEEP here is a most_recent_versions policy and "
                f'there is no `action = "DELETE"` policy, so this repository '
                f"deletes nothing at all. most_recent_versions is a floor, not "
                f"a cap: it only promises never to remove the newest N "
                f"versions, it never removes the older ones. Add an age-based "
                f"DELETE policy."
            )
        else:
            violations.append(
                f'{where}: no cleanup_policy with action = "DELETE". Without '
                f"one nothing is ever removed and the repository grows without "
                f"bound."
            )

    # Rule 3: and something must be protected from it.
    if not keeps:
        violations.append(
            f'{where}: no cleanup_policy with action = "KEEP". KEEP beats '
            f"DELETE when both match a version, and that is the only thing "
            f"holding the in-use / rolling tag a running workload pulls; "
            f"declare what must survive rather than relying on the DELETE "
            f"condition staying narrow."
        )

    return violations


# --- rules 7-11: GCS buckets ------------------------------------------------


def is_snapshot_bucket(label: str, raw_name: str | None) -> bool:
    """True when the resource label or `name` marks this as the snapshots bucket.

    The raw right-hand side of `name` is searched, not its evaluated value, so
    `"${var.prefix}-snapshots"` is recognised as well as a plain literal.
    """
    haystack = label.lower()
    if raw_name is not None:
        haystack = f"{haystack} {raw_name.lower()}"
    return any(marker.lower() in haystack for marker in SNAPSHOT_BUCKET_MARKERS)


def _is_delete_rule(rule: Block) -> bool:
    """True when this lifecycle_rule's action actually removes objects."""
    for action in sub_blocks(rule.body, "action"):
        action_type = literal_string(read_attribute(action.body, "type"))
        if action_type is not None and action_type.lower() == DELETE_ACTION_TYPE:
            return True
    return False


def _has_generation_cap(rule: Block) -> bool:
    """True when this lifecycle_rule bounds how many generations survive."""
    return any(
        read_attribute(condition.body, "num_newer_versions") is not None
        for condition in sub_blocks(rule.body, "condition")
    )


def _check_bucket_flags(where: str, body: str) -> list[str]:
    """Rules 7 and 8: the two access settings that must be declared, not assumed."""
    violations: list[str] = []

    raw_ubla = read_attribute(body, "uniform_bucket_level_access")
    if raw_ubla is None:
        violations.append(
            f"{where}: uniform_bucket_level_access is absent; it must be "
            f"declared `true`. Left to the default, per-object ACLs stay live "
            f"and the bucket's access is whatever some past API call made it."
        )
    else:
        ubla = literal_bool(raw_ubla)
        if ubla is None:
            violations.append(
                f"{where}: cannot evaluate uniform_bucket_level_access = "
                f"{raw_ubla} -- it must be the literal `true`. An unevaluatable "
                f"setting is an unproven one."
            )
        elif not ubla:
            violations.append(
                f"{where}: uniform_bucket_level_access = false. Per-object ACLs "
                f"make the bucket's real access unreviewable; it must be `true`."
            )

    raw_prevention = read_attribute(body, "public_access_prevention")
    if raw_prevention is None:
        violations.append(
            f"{where}: public_access_prevention is absent; it must be "
            f'"{REQUIRED_PUBLIC_ACCESS_PREVENTION}". The default is inherited '
            f"from the org, which is not a declaration this repo controls."
        )
    else:
        prevention = literal_string(raw_prevention)
        if prevention is None:
            violations.append(
                f"{where}: cannot evaluate public_access_prevention = "
                f"{raw_prevention} -- it must be the literal "
                f'"{REQUIRED_PUBLIC_ACCESS_PREVENTION}".'
            )
        elif prevention != REQUIRED_PUBLIC_ACCESS_PREVENTION:
            violations.append(
                f'{where}: public_access_prevention = "{prevention}"; it must '
                f'be "{REQUIRED_PUBLIC_ACCESS_PREVENTION}", which no IAM '
                f"binding can override."
            )

    return violations


def _check_soft_delete(where: str, body: str) -> list[str]:
    """Rule 9: soft delete is 7 days of billed storage nobody asked for."""
    policies = sub_blocks(body, "soft_delete_policy")
    if not policies:
        violations = [
            f"{where}: no soft_delete_policy block. The default retains every "
            f"deleted object for 7 days as billed storage, so a bucket whose "
            f"lifecycle deletes aggressively still pays for a week of what it "
            f"deleted. Declare a soft_delete_policy block with "
            f"retention_duration_seconds = 0."
        ]
        return violations

    violations = []
    for policy in policies:
        raw = read_attribute(policy.body, "retention_duration_seconds")
        if raw is None:
            violations.append(
                f"{where}: soft_delete_policy declares no "
                f"retention_duration_seconds; it must be 0, or the 7-day "
                f"default applies and is billed."
            )
            continue
        seconds = literal_int(raw)
        if seconds is None:
            violations.append(
                f"{where}: cannot evaluate "
                f"soft_delete_policy.retention_duration_seconds = {raw} -- it "
                f"must be the literal 0."
            )
        elif seconds != 0:
            violations.append(
                f"{where}: soft_delete_policy.retention_duration_seconds = "
                f"{seconds}; it must be 0. Any non-zero retention is billed "
                f"storage for objects this project already decided to delete."
            )
    return violations


def check_bucket(rel: str, block: Block) -> list[str]:
    """Every bound rule for one google_storage_bucket, snapshot case included."""
    label = block.labels[1]
    where = f'{rel}: {BUCKET_TYPE} "{label}"'
    body = block.body

    violations = _check_bucket_flags(where, body)
    violations.extend(_check_soft_delete(where, body))

    rules = sub_blocks(body, "lifecycle_rule")
    delete_rules = [rule for rule in rules if _is_delete_rule(rule)]
    capped = any(_has_generation_cap(rule) for rule in rules)

    # Rules 10 and 11: the bound, and its one deliberate exception.
    if is_snapshot_bucket(label, read_attribute(body, "name")):
        if delete_rules:
            violations.append(
                f"{where}: is a snapshot bucket (matched "
                f"{SNAPSHOT_BUCKET_MARKERS}) and declares "
                f"{len(delete_rules)} delete lifecycle_rule(s). A lifecycle "
                f"rule cannot tell a referenced snapshot from an abandoned "
                f"one, and deleting a referenced one leaves a suspended task "
                f"impossible to resume. This bucket carries no delete "
                f"lifecycle at all; its bound is the task lifetime, collected "
                f"by the Substrate GC."
            )
    elif not delete_rules and not capped:
        violations.append(
            f"{where}: is unbounded -- no lifecycle_rule with action.type = "
            f'"Delete" and no num_newer_versions generation cap. Every bucket '
            f"but the snapshots one declares how it stops growing (matched "
            f"against {SNAPSHOT_BUCKET_MARKERS})."
        )

    return violations


# --- scanning ---------------------------------------------------------------


def check_text(rel: str, text: str) -> tuple[list[str], int, int]:
    """Check one .tf file's text. Returns (violations, repositories, buckets)."""
    scrubbed = scrub(text)
    repositories = resource_blocks(scrubbed, REPOSITORY_TYPE)
    buckets = resource_blocks(scrubbed, BUCKET_TYPE)

    violations: list[str] = []
    for repository in repositories:
        violations.extend(check_repository(rel, repository))
    for bucket in buckets:
        violations.extend(check_bucket(rel, bucket))
    return violations, len(repositories), len(buckets)


def scan_tofu(root: Path) -> ScanResult:
    """Check every tofu/**/*.tf under `root`. Zero sinks is clean, and counted."""
    violations: list[str] = []
    repositories = 0
    buckets = 0
    files = 0
    for path in sorted(root.glob(TOFU_GLOB)):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            violations.append(
                f"{rel}: cannot be read as UTF-8 ({exc}). An unreadable stack "
                f"file is an unchecked sink, which this gate reports rather "
                f"than skips."
            )
            continue
        file_violations, repository_count, bucket_count = check_text(rel, text)
        violations.extend(file_violations)
        repositories += repository_count
        buckets += bucket_count
    return ScanResult(violations, repositories, buckets, files)


def summary_line(result: ScanResult) -> str:
    """The one OK line. An empty scan says so rather than looking like a pass."""
    if result.repositories == 0 and result.buckets == 0:
        return (
            f"check-storage-bounds: OK -- no storage sinks declared in "
            f"{TOFU_GLOB} ({result.files} .tf file(s) scanned), so nothing was "
            f"checked: this is an empty pass, not a proven bound."
        )
    repositories = "repository" if result.repositories == 1 else "repositories"
    buckets = "bucket" if result.buckets == 1 else "buckets"
    return (
        f"check-storage-bounds: OK -- {result.repositories} {repositories} and "
        f"{result.buckets} {buckets} declare an explicit bound "
        f"({result.files} .tf file(s) in {TOFU_GLOB})."
    )


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    result = scan_tofu(root)

    if result.violations:
        print(
            "check-storage-bounds: FAILED -- every storage sink must declare an "
            "explicit bound (docs/plan/exe-google-ax.md section 3.3):",
            file=sys.stderr,
        )
        for violation in result.violations:
            print(f"  - {violation}", file=sys.stderr)
        return EXIT_FAIL

    print(summary_line(result))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
