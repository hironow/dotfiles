# ADR 0086 — The PowerShell mise block does not activate mise inside a GitHub Actions job

- **id**: ADR-0086
- **title**: The PowerShell mise block does not activate mise inside a GitHub Actions job
- **status**: Accepted
- **date**: 2026-11-20
- **decided-date**: 2026-11-20
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session, Mac)
- **author-contact**: @hironow
- **supersedes**: part of [ADR-0024](0024-powershell-mise-activate-profile.md) (its block text; for this block only, the append-only rule; and its order, "mise block placed after starship")
- **superseded-by**: none
- **related**: [0022](0022-powershell-starship-profile-init.md), [0023](0023-mise-activate-only-no-shims-path.md), [0025](0025-justfile-mise-tool-wrap.md), [0031](0031-disable-mise-corepack-on-windows.md), [0051](0051-adopt-decision-queue-for-new-records.md)
- **consultation-trace**: the owner's choice in a Claude Code session on 2026-11-20 (see "Consultation"); transcribed on the public PR ([PR #664 decision](https://github.com/hironow/dotfiles/pull/664#issuecomment-7033807148))

## Plain summary

`just deploy` puts a few lines into the PowerShell profile that turn mise on in every PowerShell window.
GitHub Actions also starts PowerShell with that profile on the owner's Windows machines that run CI jobs.
There, mise put its own tools ahead of the tools a job had chosen, so a job could run the wrong version.
From now on the block turns mise on everywhere except inside a GitHub Actions job, and `just deploy` updates the block in profiles that already have it.

## Context

- ADR 0024 makes `just deploy` append this block to the PowerShell 7 profile, and never rewrite a block already present:

  ```powershell
  # >>> dotfiles managed block: mise activate >>>
  if (Get-Command mise -ErrorAction SilentlyContinue) {
      Invoke-Expression (&mise activate pwsh | Out-String)
  }
  # <<< end dotfiles managed block <<<
  ```

- Two of the owner's Windows machines run self-hosted GitHub Actions runners as the owner's account. Actions starts a `shell: pwsh` step as `pwsh -command ". '{0}'"`, without `-NoProfile`, so the profile loads and mise activates in every PowerShell step.
- On 2026-11-20 a check on both machines put an empty directory on `GITHUB_PATH` and read `PATH` in a PowerShell step without and with the profile:
    - without the profile, the directory was entry 1, behind PowerShell's own directory;
    - with it, entry 60, behind mise and the tools it manages (bun, go, node, just, uv, ruff, ty, opentofu and others); mise's function `_mise_hook` existed;
    - on one machine the check found this block in the CurrentUserCurrentHost profile.
- Effect: a job that pins a tool through `GITHUB_PATH` runs mise's version instead in PowerShell steps. A job that put bun 1.4.2 on `GITHUB_PATH` ran bun 1.4.4 in its next PowerShell step.
- Actions sets `GITHUB_ACTIONS=true` in every step's environment.
- Since #401, `deploy.sh` writes the mise block before the starship block and moves a misordered starship block after it (starship is mise-managed, so it needs mise first). ADR 0024's "mise block placed after starship" no longer describes the code, and no record says so.

## Decision

The owner's choice is adopted as these requirements (MUST):

- D1: The mise block MUST activate mise only when `$env:GITHUB_ACTIONS` is not `'true'` (and `mise` is found). Its text lives in one place, `ps_profile_mise_block` in `scripts/ps_profile_lib.sh`.
- D2: `just deploy` MUST rewrite an existing mise block in place when it differs from that text, keeping every other line of the profile and its line endings. A block whose end marker is missing (before the end of the file or before another managed block) MUST be left untouched and reported, so no user line is lost.
- D3: The mise block MUST come before the starship block (the order `deploy.sh` already keeps).
- D4: `just doctor` MUST warn when the block is out of date or unclosed, and MUST NOT write the profile.

## Options Considered

| Option | What it does | Benefit | Cost | Result |
| --- | --- | --- | --- | --- |
| A: skip activation inside Actions, rewrite old blocks in place | D1 to D4 | Fixes every job on these machines; the interactive shell is unchanged | `deploy.sh` gains an in-place rewrite of one block | Chosen |
| B: start the runners under another account without the profile | No dotfiles change | Isolates CI from the owner's shell setup | Infrastructure work per machine; tools the runner needs must be provisioned again | Not chosen |
| C: ask every workflow to use `pwsh -NoProfile` | No dotfiles change | Per-job control | Every workflow in every repository changes, and one that forgets still breaks | Rejected |
| D: drop and re-append the block | Simple | — | Moves the mise and starship blocks below the user's own lines, so a user line that needs mise breaks | Rejected (review) |

## Consequences

- **Positive**: On a machine that runs CI jobs, a PowerShell step uses the tools its job chose. Interactive PowerShell windows still activate mise. Old profiles get the guard on the next `just deploy`.
- **Negative**: The block is no longer append-only, so an edit a user made inside it is overwritten on `deploy` (its comment already said so). A profile with a broken block needs a manual fix before `deploy` updates it.
- **Neutral**: zsh (ADR 0023) is unchanged; jobs on these machines run PowerShell or Git Bash. Running `just deploy` on each Windows machine after the merge is the owner's step.

## Reversal

none

## Consistency with other decision records

All ADRs 0001 to 0085 were searched for `PROFILE`, `mise activate`, `managed block`, `starship` and `GITHUB_ACTIONS`; the matches were read for contradiction, duplication, misreading, false relation and mistaken relationship.

- 0024: this ADR replaces its block text, its append-only rule for this block, and its order (deliberately; recorded in `supersedes`). On acceptance, 0024's status line says so.
- 0022: the starship block stays append-only; only its position relative to mise is recorded (D3). No conflict.
- 0023: mise activation in interactive shells only, unchanged (a CI step is not interactive). No conflict.
- 0025: recipes wrap tools with `mise exec`, so they do not depend on activation. No conflict.
- 0031: the corepack block is a separate managed block, untouched. No conflict.
- 0033 and 0047 mention managed blocks of other files (git config, agent settings). Not related.
- 0051: this ADR is registered in the decision queue.

## Consultation

- 2026-11-20 (AskUserQuestion): asked whether to fix the PowerShell profile so that mise does not activate inside a GitHub Actions job, after the check above found it on both machines; the owner chose "implement it and open a PR" (translated).
- The plan passed independent reviews (Codex and Gemini Neon) over several rounds each, ending in APPROVE from both.
- 2026-11-20 16:56 JST: shown PR #664, the owner accepted this ADR ([PR #664 decision](https://github.com/hironow/dotfiles/pull/664#issuecomment-7033807148)).

## Decision (2026-11-20)

- [x] Accept as proposed / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-20 16:56 JST. Shown PR #664, the owner answered "OK, acceptします" (translated: OK, I accept it). Filled in on the owner's behalf from that ruling ([PR #664 decision](https://github.com/hironow/dotfiles/pull/664#issuecomment-7033807148)).
- Action: ADR 0024's status line says "Accepted; partly superseded by 0086". Merge PR #664. Then the owner runs `just deploy` on each Windows machine that runs CI jobs, and the runner check is rerun there.
