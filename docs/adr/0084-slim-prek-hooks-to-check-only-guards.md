# ADR 0084 — dotfiles hooks are read-only guards

- **id**: ADR-0084
- **title**: dotfiles hooks are read-only guards
- **status**: Proposed
- **date**: 2026-11-20
- **decided-date**: pending
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Pi (owner session)
- **author-contact**: @hironow
- **supersedes**: proposed partial exception to [0052](0052-renew-global-agent-instructions.md) Decision 1's platform-binary distribution requirement, for `tools/text-hygiene/` only
- **superseded-by**: none
- **related**: [0019](0019-windows-scoop-dump-record-only.md), [0020](0020-normalize-shell-script-line-endings.md), [0025](0025-justfile-mise-tool-wrap.md), [0051](0051-adopt-decision-queue-for-new-records.md), [0060](0060-frozen-image-generation-has-one-source.md), [0061](0061-version-generator-in-go.md), [0069](0069-type-check-and-lint-for-every-os.md), [0076](0076-browser-ui-platform-first-then-ui-sdk.md), [0083](0083-git-hooks-run-no-whole-repository-check.md)
- **consultation-trace**: owner choices on 2026-11-20, to be recorded in this change's public PR body before filing is complete; see Consultation

## Plain summary

A commit should check for leaks and simple mistakes without changing the files the author staged.
This proposal removes the hooks that rewrite files or run the whole project's checks.
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

Pending owner approval in the PR. The following requirements are proposed, not yet adopted.

### Proposed requirements

- D1: Keep exactly nine read-only hooks: `forbidden-tokens-staged`, `forbidden-tokens-commit-msg`, `check-yaml`, `check-toml`, `check-json`, `check-added-large-files`, `check-merge-conflict`, `detect-private-key`, and `mise-versions-check`.
  The last MUST run only the existing `just mise-versions-check`, with no filenames, on every commit.
  Keep both the pre-commit and commit-message installation types; add no push hook.
- D2: Remove `trailing-whitespace`, `end-of-file-fixer`, `just-fmt`, `just-lint`, `just-check`, and `just-test` from automatic hooks.
  Keep their recipes available explicitly.
  `just check-all` remains the manual gate: prek plus `ci-all`.
- D3: Add a read-only hygiene check to `just check` using `tools/text-hygiene/` (Go, standard library only).
  Check tracked working-tree files, or explicit relative paths, within the chosen Git root.
  Reject trailing ASCII spaces/tabs, missing final newlines, and final blank lines, including CRLF and mixed LF/CRLF endings.
  Skip empty files, non-UTF-8/NUL-containing files, symlinks, Git submodule directories, the existing global exclusions and `site/vendor/`.
  Report Git, path and read errors as failures; never rewrite source files or the Git index.
  This defines the new detector's scope; it does not claim byte-for-byte equivalence with the retired fixers.
- D4: Invoke the hygiene gate through `mise exec -- go run tools/text-hygiene/main.go`.
  Only this repository-local checker is proposed as an exception to ADR-0052 Decision 1's platform-binary distribution requirement.
  Other tools and language rules do not change.
- D5: Preserve every removed recipe's checks in CI, as required by ADR-0083 D3.
  Keep ADR-0069's per-platform gates, ADR-0020's Git line-ending attributes, and ADR-0076's vendor hashes and byte exclusions.

## CI coverage inventory

`.github/workflows/test-just.yaml` runs `just test` for every non-draft PR.
Its sandbox tests run real `just fmt`, `just lint` and `just check` on disposable tracked-only trees.
The sandbox mise wrapper intercepts only the obsolete prettier invocation, not the checks below.

| Removed hook | Retained coverage |
| --- | --- |
| `just-fmt` | Sandbox `test_just_fmt_passes_on_clean_tree`; strict ruff, Markdown and JS format checks in `just check` |
| `just-lint` | Sandbox `test_just_lint_passes_on_clean_tree` and `just check`: ruff, ty, RTTM lint/type checks, shellcheck, Markdown, JS lint/type checks, Pi tests, quarantine, MCP runner and version consistency |
| `just-check` | Sandbox `test_just_check_passes_on_clean_tree`; includes per-platform ty/Go gates |
| `just-test` | Workflow runs `just test` directly |
| Two whitespace fixers | New read-only hygiene leg of `just check`, with CLI tests in Unit Tests |

This inventory does not claim that CI runs each check only once.

## Options considered

| Option | Benefit | Cost / risk | Status |
| --- | --- | --- | --- |
| A: nine read-only hooks, Go hygiene gate through `go run` | Preserves leak guards and commit-time version consistency; removes rewrites and heavy hook runs | Hygiene errors are found later; Go is required; first compilation can take longer; a narrowly scoped distribution exception is needed | Owner chose to propose A |
| B: supplied eight-hook design | Smallest hook set | Contradicts the retained version check in 0060/0083; the supplied Python checker also needs a language exception | Not selected for the proposal |
| C: nine hooks and platform-specific hygiene binaries | Follows 0052's distribution requirement without an exception | Adds binary distribution and root-selection maintenance for a repository-local gate | Not selected for the proposal |
| D: leave current hooks | No migration work | Rewriting and whole-project hook runs continue, contrary to 0083 | Available only if the proposal is rejected or deferred with an explicit follow-up |

## Consequences

- **Positive**: Hooks no longer change staged source files or run the full gate. Confidentiality guards remain first. Version drift is still checked before a commit.
- **Negative**: Hygiene errors are caught by an explicit full check or CI rather than during commit. Authors must fix them explicitly; `just fmt` does not cover every text format. The scanner checks all tracked working-tree text, not only changed files. The Go toolchain remains a local prerequisite.
- **Neutral**: `just fmt`, `just lint`, `just check`, `just test` and `just check-all` stay available. No shared hook reinstall or global agent synchronization is part of this PR.

## Reversal

If accepted, only ADR-0052 Decision 1's platform-specific binary distribution requirement would gain an exception for `tools/text-hygiene/` through `go run`.
The tool remains Go; no general Python exception or distribution exception is introduced.
ADR-0060's commit-time check and ADR-0083's retained check are preserved, not superseded.
Older Accepted records remain unchanged while this record is Proposed.

## Consistency with other decision records

The complete ADR index and relationship keywords were scanned; relevant records were read in full, supplementing the prior review of the hook patch.
The independent plan review included 0019, 0020, 0025, 0052, 0060, 0061, 0069, 0076 and 0083, and found no remaining plan blocker after the owner choices below.
This is not a claim that every ADR body was read in full.

- **Contradiction**: The eight-hook patch lost 0060/0083's commit-time version check. The owner chose nine. The remaining proposed contradiction is only 0052's distribution requirement, explicitly scoped in D4 and put to its author and decision-maker, @hironow.
- **Duplication**: 0083 records the global rule; 0084 records this repository's follow-up. The append-only number 0084 was unused when filing began.
- **Misreading**: 0020 governs `.gitattributes`, not trailing-whitespace fixers. Its attributes stay unchanged. Historical hook descriptions in 0019/0020 are not mandates to keep `just lint` as a hook.
- **False relation**: 0061 is a precedent, not permission for this gate's exception. 0025's mise invocation rule is preserved.
- **Mistaken relationship**: 0069's normative platform checks remain. 0076's vendored bytes remain excluded and hash-checked. Neither record is superseded.

## Consultation

- 2026-11-20: the owner requested a PR applying the supplied hook patch after PR #659 merged, with a new Proposed ADR and CLI/configuration tests.
- Shown the conflict with 0060/0083, the owner chose nine hooks and approved recording that choice in the new PR body, mentioning @hironow.
- Shown 0052's Go/platform-binary requirement, the owner chose Go, then repository-local `go run` as a proposed distribution-only exception, and approved recording that choice in the same PR body.
  The original author and decision-maker contacts for 0052, 0060 and 0083 are all @hironow.
- These choices authorize the implementation and proposal, not acceptance of this ADR. No consent attributed to another agent session is imported from the patch.

## Decision (pending)

- [ ] Accept A: finalize D1–D5, record the public ruling, move the queue row to the decision log, and update only 0052's supersession metadata for the narrowly scoped distribution exception.
- [ ] Accept with changes: specify the changes, revise implementation/tests and re-run consistency review before settlement.
- [ ] Reject: remove this proposal's implementation, retain the prior hooks, and record the outcome and the remaining 0083 follow-up.
- [ ] Defer: remove or split unaccepted implementation, name a revisit condition and keep the 0083 follow-up visible.

Decision-maker: ____ (@hironow). Decision date: ____. Public ruling: ____.
