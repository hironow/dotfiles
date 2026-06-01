# 0022. PowerShell `$PROFILE` starship init from `just deploy` (Windows native)

**Date:** 2026-06-02
**Status:** Accepted

## Context

ADR 0018 (PR #128) made `just deploy` on Windows native place
`~/dotfiles/starship.toml` to `~/.config/starship.toml`. But the
`starship.toml` is a config file: it does nothing until PowerShell runs
`Invoke-Expression (&starship init powershell)` at session start. On
Windows that init line lives in `$PROFILE`
(`~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1` for PowerShell
7), which `just deploy` did not touch — operators had to add the line by
hand on every new host.

The Linux/macOS path already has the symmetric piece: `.zshrc` L41-44
gates the init behind `_cmd_exists starship`, so the prompt activates
automatically wherever `.zshrc` is sourced. PowerShell is missing the
equivalent.

Host audit on this maintainer's machine:

- `~/Documents/PowerShell/` exists (only `powershell.config.json` inside);
  the profile script is absent until first deploy.
- No OneDrive Documents redirect (`~/Documents` resolves to the local
  drive).
- `pwsh.exe` (PowerShell 7) is installed.
- No marker-block precedent (`# >>> ... # <<<`) exists anywhere in the
  repo, so this ADR establishes the convention.

## Decision

Extend the `just deploy` Windows branch to write a marker-delimited
starship-init block to PowerShell 7's `$PROFILE`, and extend `just clean`
to remove it. The whole exchange is idempotent on both sides.

Concretely, the deploy branch appends (only if the begin marker is
absent):

```powershell
# >>> dotfiles managed block: starship init >>>
# Managed by `just deploy` (see ADR 0022). Edits inside this block are overwritten on next deploy.
if (Get-Command starship -ErrorAction SilentlyContinue) {
    Invoke-Expression (&starship init powershell)
}
# <<< end dotfiles managed block <<<
```

Decisions that matter:

- **PowerShell 7 only.** Path is hardcoded to
  `~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1`. PowerShell 5
  (`WindowsPowerShell/`), OneDrive-redirected Documents, and `pwsh -Command
  '$PROFILE.CurrentUserCurrentHost'`-style dynamic resolution are
  deliberately out of scope. The maintainer's host fits this assumption;
  if a second host doesn't, a follow-up ADR handles dynamic resolution
  without re-litigating the marker design.
- **`Get-Command starship` guard.** Mirrors the `.zshrc` `_cmd_exists
  starship` pattern. PowerShell startup must not error on hosts where
  `starship` is not yet installed (scoop bootstrap is still ADR 0018
  future work).
- **Marker-delimited block.** Lets `just clean` remove only what `just
  deploy` placed, leaving any other operator-authored profile content
  untouched. Idempotency on deploy is checked with `grep -qF` on the
  begin marker; removal in clean is a `sed -i '/begin/,/end/d'` range
  deletion (MSYS GNU sed accepts `-i` without an argument).
- **LF, not CRLF.** PowerShell 7 reads `$PROFILE` correctly regardless of
  line ending. Writing LF from bash matches what `.zshrc` and every other
  shell artifact in this repo uses. `$PROFILE` is outside the repo so
  ADR 0020's `.gitattributes` rules do not apply.

## Enforcement inventory

- **`justfile`** — `deploy` Windows branch (around line 63) gains the
  $PROFILE block-write logic; `clean` Windows branch (around line 150)
  gains the symmetric sed-range removal. Both keep their existing `exit
  0` so the Unix-only tail of each recipe never runs on Windows.
- **`tests/test_justfile_windows_subset.py`** — three new tests pin the
  contract:
    - `test_deploy_windows_writes_powershell_profile_init` checks the
      profile path, both markers, the `Invoke-Expression` line, and the
      `Get-Command` guard are present in the deploy Windows branch.
    - `test_deploy_windows_powershell_init_is_idempotent` checks the
      `grep -qF` marker guard exists and the writing path uses append
      (`>>`) not overwrite (`>`).
    - `test_clean_windows_removes_powershell_profile_init` checks the
      `sed -i` range removal, both markers, the PS7 profile path, and
      that the existing `exit 0` from ADR 0018 is still present after
      the new block.
- **`README.md`** — L68 cross-reference list is extended with ADR 0022.
- **`.gitattributes`** — unchanged. `$PROFILE` lives outside the repo, so
  ADR 0020's `.sh`/`.bash` LF rules do not cover it. A `.ps1` rule
  belongs in a future ADR if a tracked `.ps1` file is ever added.

## Consequences

**Positive**

- A fresh Windows host gets a working starship prompt from `just deploy`
  alone — no manual `$PROFILE` edit, no follow-up instructions in the
  README. This closes the loop opened by ADR 0018 (which placed
  `starship.toml` but did not activate it).
- `just clean` is now a true inverse of `just deploy` on the Windows
  subset: a deploy/clean roundtrip leaves `$PROFILE` byte-identical to
  its pre-deploy state, minus the managed block.
- The `Get-Command` guard makes the init line safe to ship before
  `starship` itself is installed. ADR 0018's "scoop bootstrap is future
  work" stance is preserved without breaking PowerShell startup.
- The marker convention (`# >>> ... # <<<`) is now established and can
  be reused for any future managed-block injection (zsh, nu, fish, etc.)
  without re-deciding the shape.

**Negative**

- Hardcoded `~/Documents/PowerShell/...` will not match hosts where
  OneDrive has redirected the Documents folder, or hosts that only have
  PowerShell 5. Those hosts get a no-op deploy (file ends up somewhere
  the operator's PowerShell does not read). A follow-up ADR is the
  intended fix; a louder failure mode (detecting OneDrive redirect or
  PS 5 and skipping with a hint) is one possible direction.
- If an operator has already written `Invoke-Expression (&starship init
  powershell)` to `$PROFILE` manually outside the markers, both lines
  will run on shell start. `starship init` is idempotent, so the only
  visible effect is a tiny startup overhead.

**Neutral**

- The ADR 0019 `dump/scoop.json` and ADR 0020 `.gitattributes` rules are
  independent of this change; ADR 0022 cross-references both for the
  EOL-governance discussion but does not modify them.
- The marker convention is repo-internal; nothing prevents an operator
  from copying it for their own injections, but no policy is created
  here for those copies.
