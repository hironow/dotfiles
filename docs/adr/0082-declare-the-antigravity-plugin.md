# ADR 0082 — Declare the Antigravity plugin for Claude Code at v0.31.1 without the 7-day wait

- **id**: ADR-0082
- **title**: Declare the Antigravity plugin for Claude Code at v0.31.1 without the 7-day wait
- **status**: Accepted
- **date**: 2026-11-20
- **decided-date**: 2026-11-19
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session, Windows machine)
- **author-contact**: @hironow
- **supersedes**: part of [ADR-0056](0056-common-claude-plugin-set.md) (Decision 4, "a tag at least 7 days old", is lifted for `antigravity-for-claude-code` at `v0.31.1` only)
- **superseded-by**: none
- **related**: [0048](0048-required-claude-plugins.md), [0057](0057-shared-plugins-need-no-per-home-settings.md), [0073](0073-mwg-v1-before-the-plugin-cooldown.md), [0074](0074-bump-declared-agent-plugins-without-the-wait.md)
- **consultation-trace**: the owner's instruction and choice in this session on 2026-11-19 (see "Consultation"); the same record goes in the public PR

## Plain summary

Claude Code hands work to the Antigravity CLI (agy, Gemini) through a plugin.
The owner installed that plugin by hand on h-nn.
dotfiles now declares it, so `just deploy` installs the same version on every machine.
The tag is three days old, so the owner made a named exception to the 7-day wait.

## Context

- 2026-11-19 21:04 JST: the owner installed `antigravity@antigravity-for-claude-code` 0.31.1 on h-nn by hand, from the marketplace `yuting0624/antigravity-for-claude-code` at main (commit `6f9b383`).
- 21:21 JST: the owner asked that Claude Code use the newly installed plugins when it uses codex, agy, pi or claude as a subagent (translated).
- 22:50 JST: the owner asked to add the new plugin to dotfiles.
- The plugin:
    - an MIT-licensed third-party repository with 507 stars, created 2026-06-19;
    - it ships the `antigravity-delegate` subagent, the `/antigravity:*` commands, and a `PreToolUse` gate that lets that subagent run only its delegation wrapper.
    - `agy-doctor` passed on h-nn: agy 1.5.12 is signed in and lists 23 models. The `pro` tier falls back to Gemini 4 Argon (High) because Gemini 4 Carbon (High) is not on this plan.
- The newest tag, `v0.31.1` (commit `1615e6f`), was published on 2026-11-16. ADR-0056 Decision 4 asks for a tag at least 7 days old when a marketplace is first declared; this one is old enough on 2026-11-23. ADR-0074 lifts the wait only for marketplaces already declared, and this one is new.

## Decision

The owner's choice is adopted as these requirements (MUST):

- D1: `dump/harness/claude-plugins.json` declares the marketplace `antigravity-for-claude-code` as `yuting0624/antigravity-for-claude-code#v0.31.1`, and the plugin `antigravity@antigravity-for-claude-code`. That this tag is under 7 days old does not breach ADR-0056 Decision 4 for this tag only.
- D2: Apart from D1, ADR-0056 Decision 4 still applies to any marketplace declared for the first time. Once declared, this marketplace moves through `just agent-bump` like the others (ADR-0074).
- D3: Claude Code delegates to agy through this plugin, not through a raw `agy` call. The plugin's gate and digest contract hold, and agy's output is verified by the caller before it is trusted.

## Options Considered

| Option | Result | Why |
| --- | --- | --- |
| A: declare `v0.31.1` now, as a named exception | Chosen | It is the version the owner already runs; the exception names one marketplace and one tag (the ADR-0073 pattern) |
| B: declare `v0.29.0` now (published 2026-10-19, past the wait) | Rejected | `just deploy` would move h-nn back from the 0.31.1 the owner chose |
| C: wait until 2026-11-23, then declare `v0.31.1` | Rejected | The owner wants the delegation path in dotfiles now |

## Consequences

- `just deploy` and `just claude-plugins-install` now reconcile this plugin in every Claude home. On h-nn the main-HEAD install is replaced by the `v0.31.1` tag.
- `just agent-bump` lists the marketplace and can move it without the wait (ADR-0074).
- A third-party plugin runs code on the machine through its hooks and wrapper. It is pinned to a tag, and a tag change goes through review like any other bump.

## Consultation

- 2026-11-19 22:5x JST (AskUserQuestion): asked which version to declare, given the 7-day wait. The owner chose "v0.31.1 now (an individual exception), recorded in an ADR" (the recommended option).
- DR consistency check: this ADR conflicts with ADR-0056 Decision 4 for one tag. The owner decided it knowingly, in the same way as ADR-0073; the supersession is recorded above. It is consistent with 0048, 0057 and 0074.
