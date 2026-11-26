# ADR 0095 — A hook can be declared unregistered; the formatter is unregistered

- **id**: ADR-0095
- **title**: A hook can be declared unregistered; the formatter is unregistered
- **status**: Accepted
- **date**: 2026-11-26
- **decided-date**: 2026-11-26
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session)
- **author-contact**: @hironow
- **supersedes**: none
- **superseded-by**: none
- **related**: [0044](0044-python-toolchain-uv-ruff-ty.md), [0037](0037-layered-claude-settings-fragments.md), [0091](0091-review-against-requirements-three-rounds.md)
- **consultation-trace**: the owner's questions and choice in a Claude Code session on 2026-11-26 (05:44 to 05:56 JST), quoted in the pull request that adds this record ([PR #700](https://github.com/hironow/dotfiles/pull/700)); the owner accepted the record on 2026-11-26 ("0095 approveです。"), quoted in [PR #701](https://github.com/hironow/dotfiles/pull/701)

## Plain summary

agent-hook's hooks are data: `tools/agent-hooks/manifest.json` lists them and each harness's `harness.json` says where they register.
A hook in the manifest can now say `"registered": false`. It keeps its code, its support and its block, and the tests still run it, but no agent registers it.
The formatter (ruff on an edited `.py`, gofmt on an edited `.go`, after every Write and Edit) is the first such hook.

## Context

- The owner saw PostToolUse take an unexpectedly long time in a large repository (2026-11-26 05:44 JST). The agent-hook log showed the formatter taking up to 9.3 s on `.py` edits: it runs `uv run --frozen --only-group lint ruff` three times in the edited file's project, in every project, and edits the file.
- The owner asked whether it can be turned off (05:50 JST). It could not: the data had no off state, and `checkBlocks` requires every manifest hook to have a block. Asked to choose between deleting the formatter and adding an off state to the data, the owner chose the off state (05:56 JST: "2. の方がいいか").
- Claude on macOS, Linux and WSL runs the formatter from the fragment `agent-hook render` prints; Claude on native Windows, the script fallback plans and Codex run it from `.claude/settings.hooks.json`. Pi and agy do not run it.

## Decision

- D1. A manifest hook MAY carry `"registered": false` (absent means true). `agent-hook render` MUST leave such a hook out of the fragment; a block left with no hook and an event left with no block MUST NOT be printed. The hook's support and block stay in `harness.json`, so the loader's checks, selftest, the corpora and the conformance suite keep running it.
- D2. The formatter MUST be unregistered, and `.claude/settings.hooks.json` MUST NOT carry its PostToolUse block (`tests/unit/test_agent_hook_render.py` keeps the fragment equal to the render).
- D3. `just doctor` MUST report a missing uv or gofmt only for a home that registers the formatter.
- D4. Turning a hook back on is a data change: `registered` back to true (or removed) and its block back in `.claude/settings.hooks.json`.
- D5. A Claude home that sync plans `keep` (no release this run) keeps its whole registration, the formatter included, until a sync builds a release, as for any hook change; doctor's agent-hook-fresh check reports such a home.

## Options considered

- A. This record. Benefits: one field turns a hook off; its code and tests stay, so turning it back on is safe. Costs: two places (the manifest and `.claude/settings.hooks.json`) for the script fallback, kept equal by a test.
- B. Delete the formatter (manifest, every harness's support and block, its corpora, selftest cases and code). Benefits: less code. Costs: turning it back on means restoring all of it. Not chosen by the owner.
- C. A per-project or per-machine switch read at run time (an environment variable). Benefits: one project could keep it. Costs: the hook still starts on every edit everywhere, and a switch that skips a hook is close to the bypass mode the owner rejected for the guards. Not chosen.

## Consequences

- Positive: no agent formats files behind the user's back or waits on uv after an edit.
- Negative: an edit is no longer formatted until the project's own gate runs (`just fmt`, `just check`).
- Neutral: ADR-0044 names the Claude format-after-edit hook as a consumer of `uv run ruff`; that hook now runs nowhere, and ADR-0044's decisions are unchanged.

## Reversal

Set the formatter's `registered` back to true (or remove the field) and restore its PostToolUse block in `.claude/settings.hooks.json`; run `just sync-agents all`.

## Consistency with other decision records

- ADR-0044 (uv, ruff, ty): unchanged; the hook was one consumer of ruff.
- ADR-0037 (layered Claude settings): `.claude/settings.hooks.json` stays the hook source for the script path.
- The owner's rejection of a guard bypass mode (recorded in the session's memory, 2026-11-05) is about guards; this record changes no guard, and turning the formatter off is a registration change, not a run-time skip.

## Decision (2026-11-26)

- [x] Accept / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-26 17:35 JST. After #700 had merged and `just sync-agents all` had dropped the formatter from every Claude home and emptied Codex's group on the owner's Mac, the owner wrote "0095 approveです。" (translated: I approve 0095). The decision fields were filled in on the owner's behalf from that ruling, which is quoted in [PR #701](https://github.com/hironow/dotfiles/pull/701).
- Action: done in #700. Each other machine drops the formatter on its next `just sync-agents` that builds a release (D5).
