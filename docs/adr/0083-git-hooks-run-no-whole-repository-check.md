# ADR 0083 — Git hooks run no whole-repository check

- **id**: ADR-0083
- **title**: Git hooks run no whole-repository check
- **status**: Accepted; partly superseded by [ADR-0084](0084-git-hooks-only-check.md) (D2, D4)
- **date**: 2026-11-20
- **decided-date**: 2026-11-20
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session, Mac)
- **author-contact**: @hironow
- **supersedes**: none
- **superseded-by**: [ADR-0084](0084-git-hooks-only-check.md) (D2, D4 only)
- **related**: [0003](0003-actions-pin-sha.md), [0019](0019-windows-scoop-dump-record-only.md), [0020](0020-normalize-shell-script-line-endings.md), [0044](0044-python-toolchain-uv-ruff-ty.md), [0051](0051-adopt-decision-queue-for-new-records.md), [0060](0060-frozen-image-generation-has-one-source.md), [0069](0069-type-check-and-lint-for-every-os.md)
- **consultation-trace**: the owner's instructions and choice in a Claude Code session on 2026-11-20 (see "Consultation"); the ruling is transcribed on the public PR ([PR #659 decision](https://github.com/hironow/dotfiles/pull/659#issuecomment-7031072308))

## Plain summary

A Git hook is a check that runs by itself on every commit.
The repo template's hook ran the whole check of the repository on every commit.
That takes minutes, and the pull request's CI runs the same check anyway.
From now on a hook runs only fast checks; you run the whole check before you commit, and CI runs it.
The rules every agent reads, and the template for new repositories, say so.

## Context

- On 2026-11-20 the owner gave these instructions in a Claude Code session, about another set of repositories (translated):
    - "If prek runs `just check` or `just ci` at pre-commit, it slows development down, so remove it."
    - "pre-push is fine, but I want a rule that refuses whole checks such as `just check` (the ones that surely take long)."
    - "Tests count as long too. They are not something to run in prek."
    - For lint and type checks, only the heavy kinds come out of hooks.
- The same day the owner asked to put the rule in dotfiles' global rules too, and chose the scope "every repository" (AskUserQuestion).
- On main at `8562c79`, four spokes (the guides an agent reads when needed) and the template say the commit hook runs the whole check:
    - `ROOT_AGENTS_docs_agents_commit-discipline.md`: "The git pre-commit hook runs it too, so you cannot commit a red tree".
    - `ROOT_AGENTS_docs_agents_enforcement.md`: "Git pre-commit (`.githooks/pre-commit` → `just check`) is the gate".
    - `ROOT_AGENTS_docs_agents_python-tooling.md`: "`just check`, which CI and the pre-commit hook run".
    - `ROOT_AGENTS_docs_agents_semgrep.md`: "Pre-commit runs semgrep together with ruff and ty."
- The template's `templates/agent-baseline/.githooks/pre-commit` runs `just check`: fmt, lint (ruff, and ty once per OS, three times), semgrep, and every test.
- The template's CI (`templates/agent-baseline/.github/workflows/quality-gate.yaml`, line 39) runs `just check` on every pull request that is not a draft. Every check taken out of the hook stays in CI.
- dotfiles' own prek pre-commit runs `just fmt` and `just lint`. `just lint` includes ty (once), the RTTM and JS type checks, and the Pi extension's tests. The pre-push `just check` and `just test` hooks are configured, but their shim is not installed, so they do not run (the header of `.pre-commit-config.yaml`).

## Decision

Option B is adopted as these requirements:

- D1: A Git hook that runs on its own (prek or `.githooks/`, any stage but `manual`) MUST NOT run:
    - the full gate (`just check`, `just ci`, `just check-all` and the like);
    - a test suite (`just test`, or a test runner not limited to staged files or to fixed test files);
    - a whole-repository type check or heavy static analysis (`ty check`, `tsc`, `golangci-lint run`, `cargo clippy` and the like);
    - a recipe that reaches any of these.
- D2: A hook MAY run checks of the staged files, secret and forbidden-token scans, commit-message checks, designed fast subsets, and formatters and light linters (`ruff`, `markdownlint`, `shellcheck`, `oxlint`), even over the whole repository.
- D3: Removing a hook MUST lose no check: whatever it ran must already run in the repository's CI.
- D4: The template's commit hook MUST run `just pre-commit` (ruff format --check and ruff check only). The full gate stays in `just check`, which the template's CI runs.
- D5: The four spokes MUST NOT say a hook runs the whole check. They say to run `just check` before a commit, and that CI runs it on every pull request that is ready for review.

## Options Considered

| Option | What it does | Benefit | Cost | Result |
| --- | --- | --- | --- | --- |
| A: only the org's repositories | The public guides set no rule; they only stop saying the hook runs the whole check. The rule lives in the org's own records | Personal repositories keep their hooks | A public guide cannot name the org, so a rule with the same reason cannot be written in the global rules. Commits in personal repositories keep waiting | Rejected: the reason applies to every repository, and the owner chose B |
| B: every repository (recommended) | D1 to D5, written out in full in the public rules | The reason (a commit waits minutes for what CI runs) does not depend on who owns the repository. Agents read one rule | dotfiles' own hooks need a separate PR, with an inventory, before they follow the rule | Chosen |
| C: no change | Nothing changes | No effort | Goes against the owner's instruction. Every repository made from the template waits for the whole check on every commit | Rejected: it keeps the wait the owner asked to remove |

## Consequences

- **Positive**: In a repository made from the template, a commit waits only for ruff (seconds). The rules agents read describe what hooks and CI each do.
- **Negative**: ty, test and semgrep failures are no longer stopped at commit time. Running `just check` before a commit becomes the discipline of people and agents; CI stops the failure on a ready pull request. dotfiles' own hooks do not follow this rule until the separate PR lands.
- **Neutral**: What CI runs does not change. The template's `just check` and `just lint` (ty once per OS, ADR-0069) do not change.

## Reversal

none

## Consistency with other decision records

All ADRs 0001 to 0082 were searched for `pre-commit`, `pre-push`, `prek`, `githooks`, `install-hooks`, `commit hook` and `git hook`. The 12 records that matched were read for contradiction, duplication, misreading, false relation and mistaken relationship. 0005, 0006, 0031, 0050, 0072, 0076 and 0079 mention hooks only in tool lists or recipe names and are not related. The rest:

- 0069: its decisions (D1 to D4) do not change. Its Negative consequence says "the template's pre-commit runs `just check`", and its Neutral one says "dotfiles itself runs ty once in the pre-commit `just lint`". The first stops being true with this ADR. The second stays as a state that breaks D1 until the separate PR. **A finding, put to the owner.**
- 0019 and 0020: they assume dotfiles' own prek hook (`just lint`). Also the separate PR's subject. **A finding, put to the owner.**
- 0060: point 3 wires the generated-file check (`mise-versions-check`) into `lint` so it stops a commit. It is a fast check, allowed by D2, and stays at commit time in the separate PR. No conflict.
- 0003: the prek `conventional-commits` hook (a commit-message check). Allowed by D2. No conflict.
- 0044: it set the template's `just lint`. This ADR does not change `lint`. No conflict.
- 0051: this ADR is registered in the decision queue.

## Consultation

- 2026-11-20 (Claude Code session): the owner gave the instructions in Context and chose to record the rule for the org.
- 2026-11-20 (AskUserQuestion): asked the scope of the dotfiles rule; the owner chose "B: every repository".
- 2026-11-20 14:09 JST (AskUserQuestion): asked whether to accept option B and merge, with the consistency findings named; the owner chose "accept option B and merge" ([PR #659 decision](https://github.com/hironow/dotfiles/pull/659#issuecomment-7031072308)).
- The plan passed independent reviews: Codex APPROVE after 3 rounds, Gemini (Neon) APPROVE after 4.

## Decision (2026-11-20)

- [x] Accept option B / [ ] Accept option A / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-20 14:09 JST. Asked in a Claude Code session (AskUserQuestion) whether to accept option B and merge, with the consistency findings on 0069, 0019 and 0020 named; the owner chose "accept option B and merge" (translated). Filled in on the owner's behalf from that ruling ([PR #659 decision](https://github.com/hironow/dotfiles/pull/659#issuecomment-7031072308)).
- Action: merge PR #659. With the owner's yes, run `just sync-agents-preview all`, then `just sync-agents all`. Open the follow-up PR for dotfiles' own hooks: per D3, first confirm that each check in `lint` runs in CI, then move ty, the RTTM and JS type checks and the Pi tests out of the commit hook, keeping ADR 0060's `mise-versions-check`.
