# 0039. Windows native bootstrap via `bootstrap.ps1` one-liner

**Date:** 2026-08-15
**Status:** Accepted

## Context

ADR 0018 delivered the Windows-native minimum-viable deploy but declared the
zero-to-scoop bootstrap explicitly out of scope: `install.sh` skips every
provisioning step on Windows with `_skip_windows`, on the assumption that an
operator hand-installs scoop, git, and just before `just deploy` can run.

Since then the just-side has filled in completely: `add-scoop` restores the
recorded scoop manifest (ADR 0032), `deploy` places the Windows subset and
installs the global mise toolset (ADR 0033), `harden-env` writes the uv
quarantine config (`%APPDATA%\uv\uv.toml` — without it `uv run` rewrites
committed lockfiles), `sync-agents` distributes agent instructions and
layered settings (ADR 0037), and `restore-skills-lock` reinstalls
third-party skills (ADR 0038). The only missing piece is the first step, and
doing it by hand reproduces known traps every time:

- WSL's `System32\bash.exe` shadows Git Bash for a bare `bash`, and a
  non-login Git Bash lacks `/usr/bin` (cygpath) on PATH — either way the
  shebang recipes (`deploy`, `add-scoop`) die.
- A stale scoop `just` (<= 1.45) resolves `bash` to WSL and rejects this
  repo's justfile attributes.
- `.gitmodules` and origin use SSH URLs (34 of 35 submodules); a bare
  machine has no keys, so any submodule step fails on authentication.
- `just deploy` writes the PowerShell 7 profile path
  (`Documents/PowerShell/...`); on a stock Windows 11 without `pwsh` the
  injected starship/mise/corepack config is dead.
- Without mise, every `UV_RUN` recipe (`sync-agents`,
  `restore-skills-lock`) has no interpreter to run through.

## Decision

Add `bootstrap.ps1` at the repo root, runnable on a bare machine as

```powershell
irm https://raw.githubusercontent.com/hironow/dotfiles/main/bootstrap.ps1 | iex
```

partially superseding ADR 0018's out-of-scope stance: the zero-to-chain
connection is now in scope; `install.sh`'s Windows branch stays untouched
(the POSIX installer does not grow Windows provisioning logic).

The script is idempotent, PowerShell 5.1-compatible, ASCII-only (5.1 reads
BOM-less UTF-8 as ANSI, and `irm | iex` decodes without a charset), and:

1. sets the CurrentUser execution policy to RemoteSigned if needed (scoop's
   installer aborts under Restricted), installs scoop, then scoop-installs
   whichever of git / just / jq / mise / pwsh are **missing from PATH** (an
   unconditional install would add a second copy next to an existing
   Program Files git/pwsh and let scoop shims shadow it) — refreshing the
   process PATH from the registry after each install wave;
2. runs `scoop update just` when scoop owns a just copy (a stale shadowed
   one still lurks for mise-less shells) and hard-fails below just 1.51;
3. clones over **HTTPS** into `~/dotfiles` (never SSH; switching the remote
   and initializing submodules are documented operator steps afterwards),
   and refuses to proceed if an existing `~/dotfiles` does not point at
   `hironow/dotfiles` — the justfile hardcodes that path;
4. runs the chain through Git Bash as a **login shell**
   (`<scoop prefix git>\bin\bash.exe -lc`, Program Files fallback):
   `add-scoop <host>` -> `deploy` -> `harden-env` -> `sync-agents` ->
   `restore-skills-lock` -> `doctor`. The manifest host comes from
   `$env:DOTFILES_HOST` (dump_host.sh's primary interface — `irm | iex`
   cannot bind parameters), defaulting to `windows`.

Failure policy per step: `deploy` / `harden-env` / `sync-agents` hard-fail;
`add-scoop` and `restore-skills-lock` warn and continue (the manifest may
not cover a brand-new host; skill restore is best-effort upstream HEAD by
design); `doctor` is reported but does not decide bootstrap's exit.

`tests/unit/test_bootstrap_ps1.py` pins each trap above statically (chain
order, HTTPS-only, no submodule step, `-lc` login shell, `scoop prefix git`
resolution, just version gate, pwsh/mise in the base set, execution policy,
PATH refresh, clone-identity guard, DOTFILES_HOST, no npm/yarn/pnpm,
ASCII-only, and a PowerShell parse check).

## Consequences

- A new Windows machine goes from zero to a doctor-checked environment with
  one PowerShell line; re-running on a provisioned machine is a no-op pass.
- PowerShell 7 becomes part of the Windows base set. Bootstrap ends by
  telling the operator to open a new pwsh session — the deployed `$PROFILE`
  only applies there.
- Submodules and the SSH remote stay operator steps (documented in the
  README): bootstrap never needs them, and keeping SSH out of the script
  keeps the bare-machine path credential-free.
- Two `just` copies coexist (scoop for bootstrap, mise for steady state);
  the version gate keeps the scoop copy from regressing below the
  known-good floor when it wins the PATH race.
- ADR 0018's Status line records the partial supersede; its
  `_skip_windows` markers in `install.sh` remain accurate (the POSIX
  installer still skips — the bootstrap simply lives elsewhere).
