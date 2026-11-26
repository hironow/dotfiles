# ADR 0096 — Retire hookify from the shared Claude plugin set

- **id**: ADR-0096
- **title**: Retire hookify from the shared Claude plugin set
- **status**: Accepted
- **date**: 2026-11-26
- **decided-date**: 2026-11-26
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session)
- **author-contact**: @hironow
- **supersedes**: part of [0057](0057-shared-plugins-need-no-per-home-settings.md) D3 (hookify leaves the declared set)
- **superseded-by**: none
- **related**: [0056](0056-common-claude-plugin-set.md), [0057](0057-shared-plugins-need-no-per-home-settings.md), [0095](0095-agent-hook-unregistered-formatter.md)
- **consultation-trace**: the owner's request in a Claude Code session on 2026-11-26 (17:36 JST), quoted in the pull request that adds this record ([PR #702](https://github.com/hironow/dotfiles/pull/702)); the owner accepted the record on 2026-11-26 ("0096もacceptedです"), quoted in the same pull request

## Plain summary

The shared Claude plugin set no longer includes hookify.
`dump/harness/claude-plugins.json` drops it from `plugins` and retires it once per home, so the plugin sync switches it off in every existing Claude home; a user who wants it can switch it back on.

## Context

- The owner saw PostToolUse take an unexpectedly long time in a large repository (2026-11-26 05:44 JST). hookify registers a PreToolUse and a PostToolUse hook on every tool; each call starts `python3` (timeout 10 s). No home has a hookify rule file (`.claude/hookify.*.local.md`), so every call starts Python to match nothing.
- hookify came in with the union of the plugins the five Claude homes used (ADR-0056 D1); ADR-0057 D3 fixed the declared set.
- After ADR-0095 unregistered the agent-hook formatter, the owner asked to remove the hookify declaration too (17:36 JST: "hookifyの宣言も外しましょうか").
- ADR-0057: a plugin in neither `plugins`, `disabled` nor `retired` is left as it is, so removing hookify from `plugins` alone would leave it enabled in every home that has it.

## Decision

- D1. `dump/harness/claude-plugins.json` MUST NOT declare `hookify@claude-plugins-official` in `plugins`.
- D2. It MUST be retired by the migration `2026-11-26-hookify` (ADR-0057 D5): the plugin sync switches it off at user scope once per home and records the id, and never touches it again.
- D3. It MUST NOT be put in `disabled`: no rule forbids hookify, and a user who writes hookify rules may switch it back on in a home.

## Options considered

- A. This record (retired). Benefits: every home stops running hookify's hooks; a user can turn it back on. Costs: one migration id stays in the declaration.
- B. Disabled. Benefits: it stays off everywhere. Costs: it switches off a plugin the user turned on, every run; `disabled` is for what a rule forbids (pyright-lsp, ADR-0044). Not chosen.
- C. Remove it from `plugins` only. Benefits: smallest edit. Costs: it stays enabled in every existing home, so nothing changes where the delay is (ADR-0057). Not chosen.

## Consequences

- Positive: no Python start-up before and after every tool call for a plugin with no rules.
- Negative: hookify's skills and commands leave the shared set; a user who wants rules enables it in that home.
- Neutral: a home that has not recorded an earlier retired migration still runs it too, as the declaration already does.

## Reversal

Add hookify back to `plugins`. The migration stays recorded, so the plugin sync then installs and enables it in every home.

## Consistency with other decision records

- ADR-0057 D3 (the declared set) loses hookify; on acceptance its status line says so. D4 and D5 are used as written.
- ADR-0056 (the union of the homes' plugins): its D1 set was already replaced by ADR-0057; unchanged.
- ADR-0095 (the agent-hook formatter): a separate cause of the same delay; unchanged.

## Decision (2026-11-26)

- [x] Accept / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-26 17:55 JST. While the pull request that adds this record ([PR #702](https://github.com/hironow/dotfiles/pull/702)) was in CI, the owner wrote "0096もacceptedです" (translated: 0096 is accepted too). The decision fields were filled in on the owner's behalf from that ruling, which is quoted in that pull request.
- Action: ADR-0057's status line says this record replaced part of D3; nothing else in it changes. The plugin sync retires hookify on each machine's next run.
