# ADR 0093 — Tests check what code does, never what a file says; file policies are lint rules

- **id**: ADR-0093
- **title**: Tests check what code does, never what a file says; file policies are lint rules
- **status**: Accepted
- **date**: 2026-11-25
- **decided-date**: 2026-11-26
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session)
- **author-contact**: @hironow
- **supersedes**: part of [0092](0092-generated-docs-code-as-spec-provable-glossary.md) D6 (widened from Markdown to every file); part of [0052](0052-renew-global-agent-instructions.md) Decision 1 (a limited distribution exception: `tools/repo-lint` runs with `go run` and ships no binary, as [0061](0061-version-generator-in-go.md) did for `tools/mise-versions`); and, in the records whose guard a migration pull request moves (so far [0041](0041-retire-third-party-claudelint.md), [0045](0045-coder-control-plane-retired.md) and [0089](0089-dev-container-tests-off-pull-requests.md)), only the clauses that name that test as the guard
- **superseded-by**: none
- **related**: [0092](0092-generated-docs-code-as-spec-provable-glossary.md), [0052](0052-renew-global-agent-instructions.md), [0061](0061-version-generator-in-go.md), [0088](0088-ci-speed-standard-for-every-language.md), [0091](0091-review-against-requirements-three-rounds.md)
- **consultation-trace**: the owner's request in a Claude Code session on 2026-11-25 (17:50 JST) and the owner's answers to two questions (between 17:50 and 17:54 JST), quoted in the pull request that adds this record ([PR #689](https://github.com/hironow/dotfiles/pull/689)); D6 from the owner's rulings of 2026-11-25 (19:2x and 23:0x JST), quoted in [PR #692](https://github.com/hironow/dotfiles/pull/692); the owner accepted the record on 2026-11-26 ("どちらも承認します！(0093,94)、続けてください") and, asked about ADR-0052, chose to record the partial supersession as ADR-0061 does, both quoted in [PR #697](https://github.com/hironow/dotfiles/pull/697)

## Plain summary

A test runs code and checks what it does.
A test that only reads a file of this repository (a justfile, a workflow, a config file, a script's source, Markdown) and checks what the file says is not written; a policy about files becomes a lint rule with its own fixtures.
This repository removes such tests one file kind at a time, before the provable glossary comes in.

## Context

- The owner asked (2026-11-25 17:50 JST): "provalble glossaryを入れる前に、このリポジトリにおけるmdファイルなどファイルに対してのテストの撲滅が先だね".
- ADR-0092 D6 forbade tests of what a Markdown file says; #687 removed 53 such tests.
- A first-cut AST scan of `tests/unit/` on main `4fec3b8d` found about 408 test functions that read a repository file and run no code (justfile 110, script source 168, config 65, workflow 36, other 167, Markdown 3), in 115 files.

## Owner's rulings (2026-11-25)

1. Scope: every test that only checks what a file says. What behavior needs is rewritten as a test that runs the code; file policies (Actions pinned to a full SHA, timeouts) move to lint rules (Semgrep, actionlint); a test for authorization, secrets or concurrency is rewritten, never just deleted. One pull request per file kind.
2. The global rule widens from Markdown to every file (this record), and is synced to every agent home.

## Decision

- D1. A test MUST check what code does: it runs the code (a function, a recipe, a script, a binary) and checks the result. A test MUST NOT check what a file says: its text, its lines, its keys or values read as text, its sections, or whether a phrase or a rule is in it. This covers every kind of file: Markdown, justfile, workflow, config, and the source of a script or program.
- D2. A policy about files (every Actions step pinned to a full SHA, every job with a timeout, no `.yml` names, no banned command in a recipe) MUST be a lint rule with its own fixtures (Semgrep with `semgrep --test`, actionlint, or the linter of the file's language), run by the gate; not a test that reads the repository's files.
- D3. These stay, because they do not test what a file says: lint and format checks; link and reference checks (a referenced file, anchor or name exists); size limits; the check that committed generated files equal their generator's output; tests of code that reads or writes files, with fixtures or the real file as input, that check what the code does.
- D4. A test that guards authorization, secrets, migrations or concurrency MUST be rewritten to run the code, never only deleted (ci-speed.md "Fewer tests, on evidence").
- D5. This repository removes its file-text tests one file kind at a time (workflow, config, justfile, script source, other), each in its own pull request that names, for every removed test, the behavior test or lint rule that now holds its requirement, or that none was needed.
- D6. A policy that needs a file's structure or more than one file, which a Semgrep rule cannot hold, is a rule of `tools/repo-lint` (Go, rules tested with in-memory values, owner's ruling of 2026-11-25 19:2x JST). It reads TOML and YAML through the pinned `yq`, so no TOML or YAML library enters the module. It is a repository-local checker that only the gate runs, so the gate runs it with `go run`, like `tools/text-hygiene` (ADR-0085) and `tools/mise-versions` (ADR-0061), and it ships no binary. The owner allowed this exception to "Ship one binary per OS and CPU" on 2026-11-25 (23:0x JST, asked in the session), as for those two tools. CI installs the pinned yq with the other tools of `config/mise/image-tools.toml` (`.devcontainer/ci-bootstrap.sh`).

## Options considered

- A. This record. Benefits: tests break only when behavior breaks; file policies live in one kind of tool. Costs: hundreds of tests to rewrite or move; some guards become lint rules that need fixtures.
- B. Markdown only (ADR-0092 as it was). Benefits: no further work. Costs: the same change-detector tests stay for every other file. Not chosen by the owner.
- C. Delete every file-reading test without rewriting. Benefits: fastest. Costs: real guards (secrets, pins) are lost. Not chosen by the owner.

## Consequences

- Positive: a reworded file no longer breaks a test; policies are visible as lint rules.
- Negative: the migration takes several pull requests; until it ends, the repository still holds file-text tests.
- Neutral: CI time changes with each pull request; each one reports the test count before and after.

## Reversal

Restore the earlier testing rule from git history; removed tests come back from each migration pull request's parent commit.

## Consistency with other decision records

- ADR-0092 D6 (Markdown only) is widened by D1 (owner's ruling 2); on acceptance its status line says so.
- These Accepted records name a test in their Decision as the guard of a rule: 0001, 0019, 0031, 0039, 0041, 0044, 0056, 0070. The rules they guard stay. When a migration pull request replaces such a test because it reads a file's text, only the guard changes (a lint rule or a behavior test), and that record's status line then says so; nothing else in it changes. A test of theirs that runs code is not affected.
- ADR-0088 ("Fewer tests, on evidence"; never delete tests for authorization, privacy, migrations or concurrency) is followed by D4 and D5.
- ADR-0091 (review against the requirements) applies to each migration pull request.
- ADR-0052 Decision 1 ("ship one binary per OS and CPU"): D6 is a limited exception for `tools/repo-lint`, as ADR-0061 made for `tools/mise-versions`; ADR-0052's status line says so (owner's ruling of 2026-11-26). ADR-0085 (Proposed) asks the same for `tools/text-hygiene`; D6 does not depend on it.
- ADR-0041, ADR-0045 and ADR-0089 named, outside their Decision, tests that #690 moved in part to Semgrep rules; their status lines say so. ADR-0041's lost half (the workflow runs the official validator, pinned) was restored as a repo-lint rule in #696.

## Decision (2026-11-26)

- [x] Accept / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-26 02:05 JST. After the migration pull requests #690, #692 and #693 had merged, the owner wrote "どちらも承認します！(0093,94)、続けてください" (translated: I approve both, 0093 and 0094; please continue). Asked how to record the exception to ADR-0052 Decision 1, the owner chose to record it as ADR-0061 does. The decision fields were filled in on the owner's behalf from those rulings, which are quoted in [PR #697](https://github.com/hironow/dotfiles/pull/697).
- Action: ADR-0092 (D6), ADR-0052 (Decision 1), ADR-0041, ADR-0045 and ADR-0089 say on their status lines that this record replaced part of them; nothing else in them changes. The migration continues one file kind at a time (D5).
