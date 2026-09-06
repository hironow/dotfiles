# 0043. Self-authored skills go through the skills CLI; the `skills/` submodule is retired

**Date:** 2026-09-06
**Status:** Accepted (supersedes decisions 2–4 of ADR 0038 and the "submodule" half of ADR 0026's skills paragraph)

## Context

ADR 0038 split skills into two managers: third-party skills declared in
`dump/harness/skill-lock.json` and installed by the `bunx skills` CLI into its
store `~/.agents/skills`, and self-authored skills vendored in the `skills/`
submodule (hironow/skills) and distributed by `just sync-agents` as real
directories into every agent home, additively.

One day of skill maintenance (2026-09-06) measured the cost of the split:

- every change in hironow/skills needed a gitlink bump pull request in dotfiles
  (seven in one day), and the additive sync never refreshed the home copies, so
  a per-skill `rsync` into eight homes was needed on every machine on top;
- the sync carried skills-only special cases (`ADDITIVE_DIRECTORIES`, the
  `learned/` skill-creator workspace round-trip, a denylist TOML, `--no-skills`,
  a structural SKILL.md gate) plus 24 sandbox tests and a CI gate
  (`skills-lock-check`) whose only purpose was keeping the two managers from
  overlapping;
- hironow/skills was recreated with a clean history before publishing, which
  made the submodule pointer a liability rather than a convenience.

The CLI already handled a self-authored source without special treatment:
three hironow/skills entries had been in the lock since ADR 0038.

## Decision

1. **One manager.** Every skill, self-authored or third-party, is declared in
   `dump/harness/skill-lock.json` and lives in the CLI store `~/.agents/skills`.
   The `skills/` submodule, `skills/learned`, and every skills code path in
   `scripts/sync_agents.py` are removed; `just sync-agents` distributes
   instructions, hooks, settings, commands, and agents only, and a manifest that
   still lists skills items is pruned instead of turned into deletions.
2. **The CLI writes the store only.** `scripts/skills_lock.py restore` installs
   with `bunx skills@<pinned> add <source> -g -s <name> -y -a universal`; the
   CLI never touches a consumer home (it would delete a same-named directory
   there without comparing it).
3. **Consumers are placed by us.** `skills_lock.py place` makes
   `~/.claude/skills/<name>`, `~/.claude-work-{a..d}/skills/<name>`,
   `~/.codex/skills/<name>`, and `~/.gemini/skills/<name>` relative symlinks to
   `../../.agents/skills/<name>` (pi reads the store directly). A real
   directory in the way is replaced only when byte-identical to the store or
   when it is a copy `place` made and nobody edited (`--force` overrides). Where
   the OS refuses symlinks (Windows without Developer Mode) the consumer gets a
   copy tracked in `<home>/skills/.skills-lock-state.json` and refreshed while
   unedited. An existing profile home without `skills/` gets one; a missing
   home is left alone.
4. **hironow/skills wins a name collision.** `dump` keeps the hironow/skills
   record when two sources resolve to the same directory, refuses to commit a
   declaration in which a previously declared hironow/skills record vanished or
   changed source (the CLI's machine lock replaces same-named keys silently;
   `--allow-self-drop` overrides), `check` (`just skills-lock-check`, in `ci`)
   fails when a third-party record collides by installed or upstream name, and
   `restore` installs hironow/skills records last and reinstalls one whose
   machine-lock source is not hironow/skills.
5. **Authoring happens in a clone of hironow/skills** (its own `just check`
   and CI); after a merge, `just skills-update` refreshes the store
   (`bunx skills update -g -y`) and re-runs `place`.

## Consequences

- No gitlink bump, no manual rsync: a merged hironow/skills change reaches
  every home with `just skills-update`; a new machine gets everything with
  `just restore-skills-lock` (store restore + place).
- The declaration is still best-effort upstream HEAD (ADR 0038's caveat
  stands); for hironow/skills that is the intended behaviour.
- `SKILLS_LOCK_HOME` redirects the script and the CLI's `HOME` (agent env such
  as `CLAUDE_CONFIG_DIR` and `XDG_*` is dropped for the child) so a restore can
  be rehearsed in a scratch home; a full rehearsal still belongs in a container
  or a dedicated user.
- Skills are no longer visible in the dotfiles checkout; the maintenance
  tooling, credits, and provenance live in hironow/skills (its README and
  `docs/`), and the procedure around them stays in
  `docs/agents/skills-maintenance.md`.
- Local edits inside a home's `skills/` are not a supported workflow: `place`
  keeps and reports a differing real directory, and the CLI's own `update`
  would overwrite it. Edit skills in the repository.
