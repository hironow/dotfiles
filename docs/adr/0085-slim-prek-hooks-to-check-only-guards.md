# ADR 0085 — dotfiles hooks are read-only guards

- **id**: ADR-0085
- **title**: dotfiles hooks are read-only guards
- **status**: Accepted
- **date**: 2026-11-20
- **decided-date**: 2026-11-26
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Pi (owner session)
- **author-contact**: @hironow
- **supersedes**: partial exception to [0052](0052-renew-global-agent-instructions.md) Decision 1's platform-binary distribution requirement, for `tools/text-hygiene/` only
- **superseded-by**: none
- **related**: [0019](0019-windows-scoop-dump-record-only.md), [0020](0020-normalize-shell-script-line-endings.md), [0025](0025-justfile-mise-tool-wrap.md), [0051](0051-adopt-decision-queue-for-new-records.md), [0060](0060-frozen-image-generation-has-one-source.md), [0061](0061-version-generator-in-go.md), [0069](0069-type-check-and-lint-for-every-os.md), [0076](0076-browser-ui-platform-first-then-ui-sdk.md), [0083](0083-git-hooks-run-no-whole-repository-check.md), [0084](0084-git-hooks-only-check.md), [0089](0089-dev-container-tests-off-pull-requests.md), [0093](0093-tests-check-code-not-file-text.md)
- **consultation-trace**: owner choices on 2026-11-20, recorded in the [PR #662 consultation](https://github.com/hironow/dotfiles/pull/662); the owner accepted the record on 2026-11-26 ("3件承認します"), quoted in [PR #RULING](https://github.com/hironow/dotfiles/pull/RULING); see Consultation

## Plain summary

A commit should check for leaks and simple mistakes without changing the files the author staged.
This record removes the hooks that rewrite files or run the whole project's checks.
Nine checks stay, including the quick check that generated tool versions agree with their source.
Whitespace and final-newline errors move to a read-only command in the full check, which CI also runs.

## Context

- ADR-0083 prohibits whole-project gates, heavy type checks and test suites in automatic hooks.
  It leaves dotfiles' own hook changes to a follow-up, after checking CI coverage.
- `.pre-commit-config.yaml` declares 14 hooks: two confidentiality guards, eight builtins and four whole-project recipes.
  The builtin whitespace and end-of-file fixers, `just fmt` and `just lint` can rewrite files.
  `just lint` also runs type checks and Pi tests.
  The declared `just check` and `just test` push hooks are not installed by default.
- The supplied patch retained eight guards but removed commit-time version checking.
  ADR-0060 Decision 3 and ADR-0083 explicitly preserve that check.
  The owner chose nine hooks instead: the eight guards plus a dedicated `mise-versions-check` hook.
- ADR-0052 Decision 1 requires new tools to use Go and platform-specific binaries.
  The owner chose Go instead of the supplied Python checker, with a proposed distribution exception for running this gate inside the repository through `go run`.
  ADR-0061's existing exception applies only to mise-versions; it does not authorize this new exception.

## Decision

The owner accepted option A on 2026-11-26. These requirements are adopted (MUST).

### Requirements

- D1: dotfiles MUST keep exactly nine read-only hooks: `forbidden-tokens-staged`, `forbidden-tokens-commit-msg`, `check-yaml`, `check-toml`, `check-json`, `check-added-large-files`, `check-merge-conflict`, `detect-private-key`, and `mise-versions-check`.
  The last MUST run only the existing `just mise-versions-check`, with no filenames, and only when one of its named files is staged: `config/mise/image-tools.toml`, `config/mise/config.toml`, `.devcontainer/features/dotfiles-tools/install.sh`, `install.sh`, or a file under `tools/mise-versions/` (ADR-0084 D1(d)).
  Every hook MUST name its own stage: `commit-msg` for the commit-message guard, `pre-commit` for the rest (ADR-0084 D2).
  Both the pre-commit and commit-message installation types MUST stay; no push hook may be added.
- D2: `trailing-whitespace`, `end-of-file-fixer`, `just-fmt`, `just-lint`, `just-check`, and `just-test` MUST NOT run as automatic hooks.
  Their recipes MUST stay available to run by hand.
  `just check-all` remains the manual gate: prek plus `ci-all`.
- D3: `just check` MUST include a read-only hygiene check, `tools/text-hygiene/` (Go, standard library only).
  It MUST check tracked working-tree files, or explicit relative paths, within the chosen Git root.
  It MUST reject trailing ASCII spaces/tabs, missing final newlines, and final blank lines, including CRLF and mixed LF/CRLF endings.
  It skips empty files, non-UTF-8/NUL-containing files, symlinks, Git submodule directories, the existing global exclusions and `site/vendor/`.
  It MUST report Git, path and read errors as failures, and MUST NOT rewrite source files or the Git index.
  This defines the new detector's scope; it does not claim byte-for-byte equivalence with the retired fixers.
- D4: The hygiene gate MUST run through `mise exec -- go run tools/text-hygiene/main.go`.
  This repository-local checker is the only exception this record makes to ADR-0052 Decision 1's platform-binary distribution requirement.
  Other tools and language rules do not change.
- D5: Every removed recipe's checks MUST still run in CI, as required by ADR-0083 D3.
  ADR-0069's per-platform gates, ADR-0020's Git line-ending attributes, and ADR-0076's vendor hashes and byte exclusions MUST stay.

## CI coverage inventory

Updated at acceptance (2026-11-26) for ADR-0089, which changed when the dev container tests run.
`.github/workflows/check.yaml` runs `just check` without a container on every ready pull request (three parallel jobs behind one gate).
`.github/workflows/test-just.yaml` runs `just test` on pushes to main, on demand, and on the ready pull requests that change anything outside its `paths-ignore` (ADR-0089).
Its sandbox tests run real `just fmt`, `just lint` and `just check` on disposable tracked-only trees.
The sandbox mise wrapper intercepts only the obsolete prettier invocation, not the checks below.
The nine-hook set of D1 is also held by a repo-lint rule (`tools/repo-lint/internal/rules/prek.go`, ADR-0093 D6).

| Removed hook | Retained coverage |
| --- | --- |
| `just-fmt` | Strict ruff, Markdown and JS format checks in `just check` (`check.yaml`); sandbox `test_just_fmt_passes_on_clean_tree` |
| `just-lint` | `just check` (`check.yaml`): ruff, ty, RTTM lint/type checks, shellcheck, Markdown, JS lint/type checks, Pi tests, quarantine, MCP runner and version consistency; sandbox `test_just_lint_passes_on_clean_tree` |
| `just-check` | `check.yaml` on every ready pull request, including the per-platform ty/Go gates; sandbox `test_just_check_passes_on_clean_tree` |
| `just-test` | `test-just.yaml` runs `just test` on main, on demand, and on the pull requests that can break it (ADR-0089) |
| Two whitespace fixers | New read-only hygiene leg of `just check`, with CLI tests in Unit Tests |

This inventory does not claim that CI runs each check only once.

## Options considered

| Option | Benefit | Cost / risk | Status |
| --- | --- | --- | --- |
| A: nine read-only hooks, Go hygiene gate through `go run` | Preserves leak guards and commit-time version consistency; removes rewrites and heavy hook runs | Hygiene errors are found later; Go is required; first compilation can take longer; a narrowly scoped distribution exception is needed | Chosen (accepted 2026-11-26) |
| B: supplied eight-hook design | Smallest hook set | Contradicts the retained version check in 0060/0083; the supplied Python checker also needs a language exception | Rejected: it loses the commit-time version check that 0060 and 0083 keep |
| C: nine hooks and platform-specific hygiene binaries | Follows 0052's distribution requirement without an exception | Adds binary distribution and root-selection maintenance for a repository-local gate | Rejected: binaries for a gate that only runs inside this repository cost more than the narrow `go run` exception |
| D: leave current hooks | No migration work | Rewriting and whole-project hook runs continue, contrary to 0083 | Rejected: it keeps hooks that 0083 and 0084 forbid |

## Consequences

- **Positive**: Hooks no longer change staged source files or run the full gate. Confidentiality guards remain first. Version drift is still checked before a commit.
- **Negative**: Hygiene errors are caught by an explicit full check or CI rather than during commit. Authors must fix them explicitly; `just fmt` does not cover every text format. The scanner checks all tracked working-tree text, not only changed files. The Go toolchain remains a local prerequisite.
- **Neutral**: `just fmt`, `just lint`, `just check`, `just test` and `just check-all` stay available. No shared hook reinstall or global agent synchronization is part of this PR.

## Reversal

ADR-0052 Decision 1's platform-specific binary distribution requirement gains an exception for `tools/text-hygiene/` through `go run`, and nothing else.
The tool remains Go; no general Python exception or distribution exception is introduced.
ADR-0060's commit-time check and ADR-0083's retained check are preserved, not superseded.
Only ADR-0052's status line changes; no other Accepted record is edited.

## Consistency with other decision records

The complete ADR index and relationship keywords were scanned; relevant records were read in full, supplementing the prior review of the hook patch.
The independent plan review included 0019, 0020, 0025, 0052, 0060, 0061, 0069, 0076 and 0083, and found no remaining plan blocker after the owner choices below.
This is not a claim that every ADR body was read in full.

- **Contradiction**: The eight-hook patch lost 0060/0083's commit-time version check. The owner chose nine. The remaining contradiction is only 0052's distribution requirement, explicitly scoped in D4 and put to its author and decision-maker, @hironow, who accepted it.
- **Duplication**: 0083 and 0084 record the global rules; 0085 records this repository's follow-up. The append-only number 0084 was unused when filing began.
- **Misreading**: 0020 governs `.gitattributes`, not trailing-whitespace fixers. Its attributes stay unchanged. Historical hook descriptions in 0019/0020 are not mandates to keep `just lint` as a hook.
- **False relation**: 0061 is a precedent, not permission for this gate's exception. 0025's mise invocation rule is preserved.
- **Mistaken relationship**: 0069's normative platform checks remain. 0076's vendored bytes remain excluded and hash-checked. Neither record is superseded.

At acceptance (2026-11-26) the records filed after this one (0086 to 0096) were checked again; those that mention hooks, prek or the hygiene gate were read:

- 0088 and 0089 govern CI jobs, not hooks. 0089 changed when `just test` runs on pull requests, so the CI coverage inventory above was updated; D5 still holds because `check.yaml` runs `just check` on every ready pull request.
- 0093 D6 gives `tools/repo-lint` the same `go run` exception, and its prek rule holds D1's nine hooks. No conflict.
- 0094 does not copy the old repository's prek config; 0095 governs agent hooks, not Git hooks; 0086, 0087, 0090, 0091, 0092 and 0096 do not touch Git hooks.
- 0084's body says dotfiles' own hooks follow its rule once 0085 lands; #662 did that. 0084 is not edited.

## Consultation

- 2026-11-20: the owner requested a PR applying the supplied hook patch after PR #659 merged, with a new Proposed ADR and CLI/configuration tests.
- Shown the conflict with 0060/0083, the owner chose nine hooks and approved recording that choice in the new PR body, mentioning @hironow.
- Shown 0052's Go/platform-binary requirement, the owner chose Go, then repository-local `go run` as a proposed distribution-only exception, and approved recording that choice in the same PR body.
  The original author and decision-maker contacts for 0052, 0060 and 0083 are all @hironow.
- The owner choices and the consistency findings are recorded in the [public PR #662 body](https://github.com/hironow/dotfiles/pull/662), mentioning @hironow. These choices authorize the implementation and proposal, not acceptance of this ADR. No consent attributed to another agent session is imported from the patch.
- 2026-11-26 22:59 JST: shown Claude's recommendation (accept option A; update the CI coverage inventory for ADR-0089), the owner wrote "3件承認します" (translated: I approve all three), quoted in [PR #RULING](https://github.com/hironow/dotfiles/pull/RULING).

## Decision (2026-11-26)

- [x] Accept A / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-26 22:59 JST. Asked which records were still Proposed and shown Claude's recommendation for each, the owner wrote "3件承認します" (translated: I approve all three), approving ADR-0065, ADR-0085 and ADR-0087 together. The decision fields were filled in on the owner's behalf from that ruling, which is quoted in [PR #RULING](https://github.com/hironow/dotfiles/pull/RULING).
- Action: the implementation landed in #662. At acceptance the queue row moves to the decision log, the CI coverage inventory is updated for ADR-0089, and ADR-0052's status line names this exception. No reinstall is needed: the hooks have been read-only since #662.
