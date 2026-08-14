# 0038. Declarative third-party skills (skill-lock dump, no re-vendoring)

**Date:** 2026-08-14
**Status:** Accepted

## Context

Agent skills reached this machine through two competing managers:

- the **bunx skills CLI**, which owns `~/.agents/skills` (the real store) and
  records every install in `~/.agents/.skill-lock.json` with source repo,
  skill path, and folder hash;
- the **dotfiles sync** (`just sync-agents`), which imported skills found in
  agent homes back into the `skills/` submodule (`hironow/skills`) and
  distributed them to every home.

Because the import path copied CLI-installed third-party skills into the
submodule, the repo accumulated vendored snapshots that immediately started
drifting behind upstream. Measured on 2026-08-14: 53 vendored third-party
skills in the submodule, with e.g. `gke-basics` 3,180 lines and
`wandb-primary` 6,735 lines behind the CLI store; the codex home carried 45
conflicting stale copies of its own. Every sync widened the gap.

The machine lock itself is not directly consumable: its keys mix display
names ("Create MCP App") and dir names, three skills were double-registered,
and six skills install under their SKILL.md frontmatter name, which differs
from the repo path (`vercel-composition-patterns` ←
`skills/composition-patterns/`).

## Decision

1. **Git declares third-party skills; the CLI owns their bytes.**
   `scripts/skills_lock.py dump` normalizes the machine lock (two-stage
   name resolution: lock key if it is an installed dir, else the skillPath
   parent; deduped; unresolved entries fail loudly when they overlap the
   submodule) into the committed declaration
   `dump/harness/skill-lock.json`. `restore` reinstalls every declared skill
   via the pinned CLI (`just restore-skills-lock`).
2. **The skills submodule carries only self-authored skills.** The 53
   vendored third-party skills were removed; `hironow/skills`-sourced
   entries (4) stay by definition.
3. **The home→repo import path for skills is abolished** (only the exempt
   `skills/learned` workspace keeps its round-trip). Self-authored skills
   are edited in the submodule directly.
4. **CI blocks re-vendoring**: `just skills-lock-check` (part of the fast
   `ci` gate) fails when any lock-managed name — installed dir or upstream
   name — reappears in the submodule.

## Consequences

- Restore is **best-effort, not reproducible**: the CLI lock pins no
  commit, so `restore-skills-lock` fetches upstream HEAD. Folder-hash
  mismatches surface as warnings. If strict pinning ever becomes a
  requirement, that needs CLI support or a deliberate return to vendoring —
  revisit this ADR then.
- The declaration is a snapshot of one machine's store. Run
  `just dump-skills-lock` after `bunx skills add/update/remove` so the
  committed declaration follows the store.
- Existing homes may keep stale real-directory copies of formerly vendored
  skills (additive sync never deletes). They are harmless but shadow the
  CLI symlinks; this machine's claude-family homes were converted to
  symlinks into `~/.agents/skills` as a one-time cleanup. gemini/codex
  homes were deliberately left untouched (no verified CLI restore path).
- New machines bootstrap third-party skills with `just restore-skills-lock`
  instead of receiving them from the submodule.
