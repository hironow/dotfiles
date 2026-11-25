# ADR 0094 — Vendor the semgrep-guardrails rules into dotfiles

- **id**: ADR-0094
- **title**: Vendor the semgrep-guardrails rules into dotfiles
- **status**: Accepted
- **date**: 2026-11-25
- **decided-date**: 2026-11-26
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session)
- **author-contact**: @hironow
- **supersedes**: none
- **superseded-by**: none
- **related**: [0014](0014-vendor-emulator-telemetry-from-submodules.md), [0090](0090-keep-one-justfile-no-modules.md), [0092](0092-generated-docs-code-as-spec-provable-glossary.md), [0093](0093-tests-check-code-not-file-text.md)
- **consultation-trace**: the owner's requests in a Claude Code session on 2026-11-25 (19:34 and 21:25 JST), quoted in the pull request that adds this record ([PR #691](https://github.com/hironow/dotfiles/pull/691)); the owner accepted the record on 2026-11-26 ("どちらも承認します！(0093,94)、続けてください"), quoted in [PR #NNN](https://github.com/hironow/dotfiles/pull/NNN)

## Plain summary

The architecture rules of hironow/semgrep-guardrails move from a submodule into dotfiles, next to dotfiles' own Semgrep rules.
The old repository is archived once the move is merged.

## Context

- The owner asked (2026-11-25 19:34 JST): "dotfiles にもう <https://github.com/hironow/semgrep-guardrails> のrepoの全部を取り込んでしまいましょうか。semgrep ruleがdotfilesにおいて充実してきたので、分けて管理よりも有益です", and (21:25 JST): "semgrep-guardrails が dotfiles に取り込めたら、 semgrep-guardrails の repo は archive にします".
- dotfiles pinned the repository as the submodule `guardrails/semgrep` at `3754cfe` (`update = none`). The repository is the owner's own, public, 14 commits, last pushed 2026-06-10, with no other repository using it as a submodule.
- It holds 116 rules in 59 files for Go, Python and TypeScript, in 11 categories, with fixtures under `.semgrep/tests/` that do not pair with the rule files by name. Its own gate was `semgrep --validate` plus "the fixtures give at least one finding". Its rules implement the architecture rules of j5ik2o/ai-tools (Apache-2.0), recorded there as a submodule.
- The autoreview plugin reads the rules through `plugins/autoreview/scripts/resolve-guardrails.sh` and treats each directory except `tests/` as a rule category.
- ADR-0014 vendored two of the owner's repositories the same way, for the same reasons.

## Decision

- D1. The rules and their fixtures MUST live at `.semgrep/rules/guardrails/`, one directory per category and `tests/` for the fixtures, copied unchanged from `3754cfe`. The `guardrails/semgrep` submodule is removed.
- D2. `just semgrep-test` MUST validate these rules and fail when their fixtures give no finding, which is the check the old repository ran.
- D3. The parts of the old repository that dotfiles already has, or that its rules forbid, are not copied: its justfile (ADR-0090), `mise.toml`, prek and markdownlint configs, `.gitmodules`, `.semgrepignore`, its READMEs (ADR-0092 D3; each rule's message keeps its `[WHY]` and `[HOW]`), and its `docs/intent.md` and `docs/handover.md`. The upstream of the rules (j5ik2o/ai-tools) is named in `.semgrep/README.md`.
- D4. `resolve-guardrails.sh` MUST find the rules at `.semgrep/rules/guardrails/`, in the current repository first and then in the repository that holds the plugin. The plugin's version goes up (0.4.0).
- D5. The fixtures are excluded from the JS/TS lint (oxlint) for the reason ruff already excludes `.semgrep/`: they break rules on purpose.
- D6. After the merge, the owner archives hironow/semgrep-guardrails.

## Options considered

- A. This record. Benefits: one place and one gate for every Semgrep rule; no submodule step. Costs: dotfiles grows by 97 files; the history stays in the archived repository, not in dotfiles (a squash merge keeps none).
- B. Keep the submodule. Benefits: no change. Costs: two places for Semgrep rules, and a pointer bump for every rule change. Not chosen by the owner.
- C. Keep the old path `guardrails/semgrep/` as a plain directory. Benefits: the plugin needs no change. Costs: the rules stay apart from `.semgrep/rules/`, which the owner wants to manage as one. Not chosen.

## Consequences

- Positive: rule changes and their consumers change in one pull request.
- Negative: 58 of the 116 rules give no finding on the current fixtures; the gate only proves that some rules fire. Adding a paired fixture with `ruleid:` annotations per rule is separate work.
- Neutral: a repository that still has the old submodule finds no rules through the plugin; none was found.

## Reversal

Restore the submodule from git history and unarchive the repository.

## Consistency with other decision records

- ADR-0014: the same move for two other repositories of the owner; consistent.
- ADR-0090 (one justfile): the old justfile's checks move into `semgrep-test`; no second justfile.
- ADR-0092 D3 (no new hand-written docs): the old READMEs are not copied; one row in the existing `.semgrep/README.md` table.
- ADR-0093 (tests check code): the fixtures are inputs of the rules, and the gate runs the rules on them.

## Decision (2026-11-26)

- [x] Accept / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-26 02:05 JST. After #691 had merged, the owner wrote "どちらも承認します！(0093,94)、続けてください" (translated: I approve both, 0093 and 0094; please continue). The decision fields were filled in on the owner's behalf from that ruling, which is quoted in [PR #NNN](https://github.com/hironow/dotfiles/pull/NNN).
- Action: done. #691 moved the rules, and the owner archived hironow/semgrep-guardrails (D6; the repository reads `archived: true` on 2026-11-26).
