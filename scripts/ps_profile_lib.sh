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

# This file's directory, for its sibling drop_managed_block.awk.
_PS_PROFILE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
