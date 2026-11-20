# ADR 0084 — Git hooks only check: no hook writes a file or runs at pre-push

- **id**: ADR-0084
- **title**: Git hooks only check: no hook writes a file or runs at pre-push
- **status**: Accepted
- **date**: 2026-11-20
- **decided-date**: 2026-11-20
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session, Mac)
- **author-contact**: @hironow
- **supersedes**: part of [ADR-0083](0083-git-hooks-run-no-whole-repository-check.md) (D2, which let a hook run formatters and light linters that may write; D4, the template's `just pre-commit` hook)
- **superseded-by**: none
- **related**: [0019](0019-windows-scoop-dump-record-only.md), [0020](0020-normalize-shell-script-line-endings.md), [0044](0044-python-toolchain-uv-ruff-ty.md), [0051](0051-adopt-decision-queue-for-new-records.md), [0060](0060-frozen-image-generation-has-one-source.md), [0069](0069-type-check-and-lint-for-every-os.md), [0083](0083-git-hooks-run-no-whole-repository-check.md)
- **consultation-trace**: the owner's choices in a Claude Code session on 2026-11-20 (see "Consultation"); transcribed on the public PR ([PR #661 decision](https://github.com/hironow/dotfiles/pull/661#issuecomment-7032878791))

## Plain summary

A Git hook is a check that runs by itself on every commit.
ADR 0083 stopped hooks from running the whole check, but still let a hook rewrite files while you commit.
A rewritten commit fails and has to be staged again, and the files no longer match what you wrote.
From now on a hook only checks: it never rewrites a file, and no checking hook runs at pre-push.
The repo template's hooks become prek hooks that only check, and the rules every agent reads say so.

## Context

- ADR 0083 (Accepted and merged, PR #659, 2026-11-20) says a hook never runs the whole gate, a test suite or a whole-repository type check. Its D2 lets a hook run formatters and light linters, even over the whole repository, and its D4 makes the template's hook run `just pre-commit` (ruff over the whole repository).
- On 2026-11-20, the owner supplied a change from another of the owner's agent sessions that makes dotfiles' own prek hooks check-only, and asked that the rules match it. The owner chose (AskUserQuestion): align the rules to check-only hooks; and (14:51 JST) use prek for the template's hooks, like the owner's other repositories.
- A hook that writes makes the commit fail by construction, and leaves the tree different from what the author (a person or an agent) wrote.
- prek 0.5.4 and newer have a non-writing `--check` mode for the builtin `trailing-whitespace` and `end-of-file-fixer` hooks ("Report files that would change and exit nonzero without modifying them").
- prek stashes unstaged changes while hooks run, so hooks see the staged content; it does not stash untracked files.
- prek runs nested `.pre-commit-config.yaml` files as their own projects unless `.prekignore` excludes their directory.
- prek's builtin hooks name pre-push in their own manifest, so `default_stages: [pre-commit]` alone does not keep them from pre-push (measured with prek 0.5.10: they ran under `prek run --hook-stage pre-push`).
- The template's `check` ran `fmt` (which writes) before `lint`, so CI repaired formatting before checking it, and a badly formatted commit could pass CI.

## Decision

The owner's choice is adopted as these requirements (MUST), replacing ADR 0083's D2 and D4 (its D1, D3 and D5 stand):

- D1: A hook MUST NOT write to a file. It MAY run only:
    - (a) guards against what cannot be undone: secret, forbidden-token and private-key scans, large files;
    - (b) fast, read-only checks of the staged files: syntax checks, and linters and formatters in check mode;
    - (c) commit-message checks;
    - (d) a fast, read-only consistency check over a fixed, named set of files, run only when one of them is staged.

  Formatting is an explicit command (`just fmt`).
- D2: No checking hook runs at the pre-push stage; what must hold before a merge runs in CI. Each checking hook names its stages itself, because a hook's own manifest can add pre-push. A hook that moves data, such as Git LFS's pre-push upload, is not a check and is untouched.
- D3: The template's hooks MUST be the prek config `templates/agent-baseline/.pre-commit-config.yaml`: prek's builtin checks (whitespace and final newline in `--check` mode, YAML/TOML/JSON syntax, large files, merge markers, private keys) and ruff in check mode on the staged Python files (`--no-fix --no-fix-only --force-exclude`), each at `stages: [pre-commit]`. `just install-hooks` installs them, checking `core.hooksPath` and the hooks directory before it changes anything. The template's `check` never writes (no `fmt`; `lint`'s `ruff check` passes `--no-fix --no-fix-only`). dotfiles' root `.prekignore` keeps dotfiles' own prek from running the template's config.
- D4: The enforcement spoke says what D1 and D2 allow.

## Options Considered

What a hook may do:

| Option | What it does | Benefit | Cost | Result |
| --- | --- | --- | --- | --- |
| ADR 0083 as is | Fast hooks; formatters and light linters may fix files; pre-push hooks allowed | Fixes arrive without a command | A rewritten commit fails and must be staged again; the tree no longer matches what the author wrote | Superseded (D2, D4) |
| Check-only hooks | D1 and D2 | What you stage is what lands; one predictable loop | Formatting is a deliberate `just fmt`; whole-file checks over unstaged files move to CI | Chosen |
| No hooks at all | Rely on CI alone | No hook to maintain | A leaked secret or key is in history before CI sees it | Rejected: the irreversible guards must run before the commit exists |

How the template's hooks run:

| Option | What it does | Cost | Result |
| --- | --- | --- | --- |
| prek | The org's tool; stashes unstaged changes so hooks see staged content | Untracked files are not stashed; dotfiles' AGENTS.md records that prek's stash and restore can drop staged changes | Chosen (14:51 ruling) |
| A raw `.githooks/` script with an index copy | Exact staged bytes and configuration | A new tool in Python (against the Go rule) or a Go binary per repository | Rejected |
| A raw script on the working tree | Least code | Wrong verdicts when only part of a file is staged | Rejected |

## Consequences

- **Positive**: In a repository made from the template, a commit waits only for fast checks (seconds), and no hook changes a file. CI catches a formatting violation, because `check` no longer formats first.
- **Negative**: Whole-file problems in files you did not stage are no longer stopped at commit time; CI stops them on a ready pull request. A repository made from the template needs prek 0.5.4 or newer. dotfiles' own hooks do not follow this rule until a separate PR (ADR 0085) lands.
- **Neutral**: What CI runs does not change. The template's `lint` keeps its checks (ADR 0069).

## Reversal

none

## Consistency with other decision records

All ADRs 0001 to 0083 were searched for `pre-commit`, `pre-push`, `prek`, `githooks`, `install-hooks`, `commit hook` and `git hook`; the matches were read for contradiction, duplication, misreading, false relation and mistaken relationship.

- 0083: this ADR replaces its D2 and D4, deliberately; its D1, D3 and D5 stand. On acceptance, 0083's status line says so (the one change allowed to an Accepted record).
- 0069, 0019, 0020: as in 0083, they describe dotfiles' own hooks; ADR 0085 brings those in line. 0020's line-ending discipline is kept by the check-mode hooks. **A finding, put to the owner** (unchanged from 0083).
- 0060: point 3 wires `mise-versions-check` into `lint` so it stops a commit. A fast check over a fixed set of files is allowed by D1(d); ADR 0085 keeps it at commit time as its own hook. No conflict.
- 0044: it set the template's `just lint`. `lint` keeps its checks; `ruff check` gains `--no-fix --no-fix-only`. No conflict.
- 0051: this ADR is registered in the decision queue.

## Consultation

- 2026-11-20 (AskUserQuestion): after the change from the owner's other agent session, the owner chose to align the rules to check-only hooks.
- 2026-11-20 14:51 JST (AskUserQuestion): the owner chose prek for the template's hooks.
- The owner merged ADR 0083's first version (PR #659) at 15:15 JST, before this revision was in it. This ADR therefore supersedes part of 0083 instead of editing it.
- The plan passed independent reviews (Codex and Gemini Neon) over several rounds each, ending in APPROVE from both.
- 2026-11-20 (AskUserQuestion): the owner accepted this ADR and the merge, and chose to distribute the instruction changes after the merge ([PR #661 decision](https://github.com/hironow/dotfiles/pull/661#issuecomment-7032878791)).

## Decision (2026-11-20)

- [x] Accept as proposed / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-20 (about 16:00 JST). Asked in a Claude Code session (AskUserQuestion) whether to accept and merge, with what it replaces in ADR 0083 and the pre-push point (every checking hook, guards included; Git LFS untouched) named; the owner chose "accept and merge" (translated). Filled in on the owner's behalf from that ruling ([PR #661 decision](https://github.com/hironow/dotfiles/pull/661#issuecomment-7032878791)).
- Action: ADR 0083's status line says "Accepted; partly superseded by 0084 (D2, D4)". Merge PR #661. Then, as the owner chose, `just sync-agents-preview all` and `just sync-agents all`. Then the follow-up PR for dotfiles' own hooks (ADR 0085).
