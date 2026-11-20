#!/usr/bin/env bash

# ==============================================================================
# Shared: the PowerShell 7 $PROFILE path that deploy/clean/doctor manage
# ------------------------------------------------------------------------------
# Source this file; it only defines functions. `resolve_ps_profile` prints the
# POSIX path of the CurrentUserCurrentHost profile pwsh actually loads. It is
# NOT always $HOME/Documents/...: when Documents is redirected (OneDrive), the
# profile lives under e.g. OneDrive/ドキュメント, and a hardcoded path made
# `just deploy` write every managed block into a file pwsh never reads
# (tests/unit/test_ps_profile_path.py).
#
# Order: $DOTFILES_PS_PROFILE override -> pwsh's own $PROFILE -> Windows
# PowerShell's MyDocuments (the same folder pwsh uses) -> the legacy path.
# Probes force UTF-8 console output (a Japanese folder name otherwise comes back
# as mojibake), take the last non-empty line, and accept only drive-lettered
# paths. Nothing here fails: callers run under `set -eu`/pipefail.
# ==============================================================================

# This file's directory, for its sibling drop_managed_block.awk. Builtins only:
# callers (and the tests, which isolate PATH) source this with no guarantee
# that `dirname` is on PATH.
case "${BASH_SOURCE[0]}" in
  */*) _PS_PROFILE_LIB_DIR="${BASH_SOURCE[0]%/*}" ;;
  *) _PS_PROFILE_LIB_DIR=. ;;
esac
_PS_PROFILE_LIB_DIR="$(cd "$_PS_PROFILE_LIB_DIR" && pwd)"

ps_profile_legacy() {
  printf '%s\n' "$HOME/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
}

# Last non-empty line of $1 as a POSIX path, or return 1 when it is not an
# absolute Windows path or cygpath is unavailable.
_ps_profile_posix() {
  local line='' l
  while IFS= read -r l || [ -n "$l" ]; do
    l="${l%$'\r'}"
    [ -n "$l" ] && line="$l"
  done <<<"$1"
  case "$line" in
    [A-Za-z]:\\*|[A-Za-z]:/*) ;;
    *) return 1 ;;
  esac
  command -v cygpath >/dev/null 2>&1 || return 1
  cygpath -u "$line" 2>/dev/null
}

resolve_ps_profile() {
  local out posix ps51
  if [ -n "${DOTFILES_PS_PROFILE:-}" ]; then
    printf '%s\n' "$DOTFILES_PS_PROFILE"
    return 0
  fi
  # shellcheck disable=SC2016  # $PROFILE is PowerShell, expanded by pwsh
  if command -v pwsh >/dev/null 2>&1 \
    && out="$(pwsh -NoLogo -NoProfile -NonInteractive -Command \
      '[Console]::OutputEncoding = [Text.Encoding]::UTF8; $PROFILE.CurrentUserCurrentHost' 2>/dev/null)" \
    && posix="$(_ps_profile_posix "$out")"; then
    printf '%s\n' "$posix"
    return 0
  fi
  # Same lookup as doctor.sh: powershell.exe is not always on PATH.
  if command -v powershell.exe >/dev/null 2>&1; then
    ps51=powershell.exe
  else
    ps51="$(cygpath -u "${SYSTEMROOT:-C:\\Windows}" 2>/dev/null || true)/System32/WindowsPowerShell/v1.0/powershell.exe"
  fi
  if { [ "$ps51" = powershell.exe ] || [ -x "$ps51" ]; } \
    && out="$("$ps51" -NoLogo -NoProfile -NonInteractive -Command \
      "[Console]::OutputEncoding = [Text.Encoding]::UTF8; [Environment]::GetFolderPath('MyDocuments')" 2>/dev/null)" \
    && posix="$(_ps_profile_posix "$out")"; then
    printf '%s\n' "${posix%/}/PowerShell/Microsoft.PowerShell_profile.ps1"
    return 0
  fi
  ps_profile_legacy
}

# Line number of a managed block's begin marker in $1, or nothing.
_ps_profile_block_line() {
  grep -nF "# >>> dotfiles managed block: $2 >>>" "$1" 2>/dev/null \
    | head -n 1 | cut -d: -f1 || true
}

# Succeeds when the starship block comes before `mise activate`. starship is
# mise-managed, so its `Get-Command starship` finds it only after mise is
# activated — unless mise's shims are on the persisted PATH, which only the
# self-hosted runner hosts do. Elsewhere the block silently skips.
ps_profile_starship_before_mise() {
  local starship mise
  starship="$(_ps_profile_block_line "$1" 'starship init')"
  mise="$(_ps_profile_block_line "$1" 'mise activate')"
  [ -n "$starship" ] && [ -n "$mise" ] && [ "$starship" -lt "$mise" ]
}

# Removes the managed block named $2 from $1 with drop_managed_block.awk: the
# exact marker lines (CRLF tolerated) and the blank line written before the
# block. Not `sed -i`: GNU and BSD (macOS) sed disagree on its argument.
# Writing back through `cat >` keeps the file itself (mode, owner).
ps_profile_drop_block() {
  local tmp rc=0
  tmp="$(mktemp)" || return 1
  awk -v b="# >>> dotfiles managed block: $2 >>>" -v e="# <<< end dotfiles managed block <<<" \
    -f "$_PS_PROFILE_LIB_DIR/drop_managed_block.awk" "$1" >"$tmp" \
    && cat "$tmp" >"$1" || rc=$?
  rm -f "$tmp"
  return "$rc"
}

# The `mise activate` block deploy writes (ADR 0024, ADR 0086). Inside a
# GitHub Actions job mise is not activated: Actions starts `shell: pwsh` steps
# without -NoProfile, and an activated mise put its tools ahead of the job's
# GITHUB_PATH. Actions sets GITHUB_ACTIONS=true in every step.
ps_profile_mise_block() {
  # shellcheck disable=SC2016  # PowerShell, written into the profile verbatim
  printf '%s\n' \
    '# >>> dotfiles managed block: mise activate >>>' \
    '# Managed by `just deploy` (see ADR 0024, ADR 0086). Edits inside this block are overwritten on next deploy.' \
    "# Not inside a GitHub Actions job: there the job's GITHUB_PATH must come first (ADR 0086)." \
    "if (\$env:GITHUB_ACTIONS -ne 'true' -and (Get-Command mise -ErrorAction SilentlyContinue)) {" \
    '    Invoke-Expression (&mise activate pwsh | Out-String)' \
    '}' \
    '# <<< end dotfiles managed block <<<'
}

# The mise block's state in $1: absent, unclosed, current or stale
# (mise_block.awk). A missing file is absent.
ps_profile_mise_state() {
  if [ ! -f "$1" ]; then
    printf 'absent\n'
    return 0
  fi
  PS_MISE_BLOCK="$(ps_profile_mise_block)" \
    awk -v mode=state -f "$_PS_PROFILE_LIB_DIR/mise_block.awk" "$1"
}

# Succeeds when $1 holds a closed mise block that differs from the current one.
ps_profile_mise_stale() {
  [ "$(ps_profile_mise_state "$1")" = stale ]
}

# Succeeds when $1's mise block has no end marker before the end of the file or
# before another managed block. Nothing may rewrite such a profile.
ps_profile_mise_unclosed() {
  [ "$(ps_profile_mise_state "$1")" = unclosed ]
}

# Rewrites $1's mise block in place with the current one, keeping every other
# line. Fails, leaving the file as it was, when the block is absent or
# unclosed. Written back through `cat >`, like ps_profile_drop_block.
ps_profile_mise_upgrade() {
  local tmp rc=0
  tmp="$(mktemp)" || return 1
  PS_MISE_BLOCK="$(ps_profile_mise_block)" \
    awk -v mode=upgrade -f "$_PS_PROFILE_LIB_DIR/mise_block.awk" "$1" >"$tmp" \
    && cat "$tmp" >"$1" || rc=$?
  rm -f "$tmp"
  return "$rc"
}
