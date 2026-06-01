# 0024. PowerShell `$PROFILE` mise activate from `just deploy` (Windows native)

**Date:** 2026-06-02
**Status:** Accepted

## Context

ADR 0022 (PR #135) established the marker-delimited managed-block pattern
for injecting startup code into PowerShell 7's `$PROFILE` from
`just deploy`. The first injected block was starship's prompt init. The
same approach now extends to **mise activation**, closing a parallel gap.

On Windows native, mise is installed (`scoop install mise` in
`dump/scoop.json`), `mise.toml` pins node 24.15.0, but PowerShell never
calls `mise activate`. As a result `where.exe node` returns
`C:\Program Files\nodejs\node.exe` (v23.3.0) first, then the scoop copy
(v24.10) — the mise-pinned 24.15.0 is functionally invisible from
PowerShell. zsh side already runs `eval "$(mise activate zsh)"` in
`.zshrc` (L269-271) per ADR 0023's "activate only, no shims PATH dance"
decision.

The fix is small and symmetrical: add a second managed block to
`$PROFILE` that calls `mise activate pwsh`. The marker convention from
ADR 0022 is reused verbatim (only the service name in the begin marker
differs); the end marker `# <<< end dotfiles managed block <<<` is
shared because sed's range deletion identifies blocks by their begin
marker — each `clean` sed targets the correct begin and stops at the
first end thereafter.

## Decision

Extend the existing `just deploy` Windows branch to append (idempotently)
a second managed block immediately after the starship block:

```powershell
# >>> dotfiles managed block: mise activate >>>
# Managed by `just deploy` (see ADR 0024). Edits inside this block are overwritten on next deploy.
if (Get-Command mise -ErrorAction SilentlyContinue) {
    Invoke-Expression (&mise activate pwsh | Out-String)
}
# <<< end dotfiles managed block <<<
```

And extend `just clean` to remove this block via the same sed
range-deletion pattern. Both halves reuse the `$ps_profile` and
`$ps_marker_end` shell variables already defined for the starship
block earlier in the recipe.

Decisions that matter:

- **PowerShell 7 only, hardcoded profile path.** Same constraint as
  ADR 0022. OneDrive Documents redirect and PS 5 remain out of scope.
- **`Get-Command mise` guard.** Mirrors `.zshrc`'s `_cmd_exists mise`
  (ADR 0023 EOF activation block). PowerShell startup must not error
  if mise is not yet installed, since `scoop install mise` is operator
  setup and may precede any first `just deploy`.
- **End marker shared with ADR 0022.** sed's `/begin/,/end/d` deletes
  from a specific begin marker to the **next** end marker — block A's
  begin paired with block A's end, block B's begin paired with block B's
  end. The shared end string is safe because the begin markers are
  distinct. Tests assert two distinct `sed -i` invocations are present in
  the clean branch.
- **mise block placed after starship.** Order is functionally irrelevant
  (each init is independent), but appending after the existing block
  keeps the `$PROFILE` diff for an upgrade-from-ADR-0022 host minimal —
  the starship block is byte-identical, only the new mise block follows.
- **Program Files / scoop Node retirement deferred.** ADR 0024 only
  *promotes* mise to the front of PATH (by activating it), it does not
  remove other Node installs. The follow-up to retire Program Files
  Node (admin required) and scoop nodejs (orphan from dump perspective)
  is intentionally a separate ADR.

## Enforcement inventory

- **`justfile`** — `deploy` Windows branch (around L89) gains the
  mise-activate block-write logic after the starship block. `clean`
  Windows branch (around L200) gains a second sed range removal. Both
  reuse variables already declared by the starship block.
- **`tests/test_justfile_windows_subset.py`** — three new tests pin the
  contract:
    - `test_deploy_windows_writes_powershell_mise_activate` checks the
      mise marker, the `Invoke-Expression (&mise activate pwsh | Out-String)` line,
      and the `Get-Command mise` guard.
    - `test_deploy_windows_mise_activate_is_idempotent` asserts the
      deploy branch contains at least two `grep -qF` calls (one per
      managed block) and two append (`>>`) redirections.
    - `test_clean_windows_removes_powershell_mise_activate` asserts
      the clean branch contains at least two `sed -i` invocations and
      that `exit 0` is still in place.
- **`README.md`** — L68 cross-reference list extended with ADR 0024.

## Consequences

**Positive**

- PowerShell `node --version` returns mise-managed 24.15.0 instead of
  the stale Program Files 23.3.0 (without uninstalling anything — mise's
  activation prepends its bin dir to PATH for the running shell).
- The zsh and PowerShell activation stories are now symmetric: both
  use the `mise activate` path, both are guarded by a "command exists?"
  check, both can be removed cleanly by their respective deploy-clean
  inverse.
- The marker-block pattern from ADR 0022 is exercised a second time,
  which validates the convention and makes future managed blocks (e.g.,
  a future PowerShell prompt customization, or a third tool's init)
  trivial to add — copy/paste with new marker + new service name.

**Negative**

- Two Node installs (Program Files v23.3.0 and scoop v24.10.0) remain
  on the host. They are no longer first on PATH for PowerShell, but
  they still consume disk and can confuse operators who run
  `where.exe node` expecting a single hit. A follow-up cleanup ADR is
  the explicit fix; this ADR's scope ends at "make mise win the PATH
  race".
- `$PROFILE` is now two blocks wider. An operator who runs
  `just clean` without re-running `just deploy` will have an empty
  `$PROFILE` until the next deploy. (Same as ADR 0022; reiterated for
  clarity.)

**Neutral**

- ADR 0023 (zsh side) is the spiritual peer of this ADR. It does not
  change behavior on Windows but is the canonical reference for "why
  activate, not shims PATH" — anyone touching either ADR should read
  the other.
- The `mise activate pwsh` shell name is mise's preferred form (per
  `mise activate --help`); `powershell` is also accepted as an alias.
