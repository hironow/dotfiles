#!/usr/bin/env bash

# ==============================================================================
# Shared: resolve a WSL2 distro's ext4.vhdx from the Lxss registry (ADR 0035)
# ------------------------------------------------------------------------------
# Source this file; it only defines `wsl_vhdx_path <distro>` (prints the POSIX
# path of the distro's ext4.vhdx, or nothing and returns 1 when the distro has
# no registry entry). Taking the first ext4.vhdx that a directory walk happens
# to list grabs whichever distro enumerates first — on a multi-distro host that
# measured Debian's 366 MB disk and declared "0 GB slack" while Ubuntu sat at
# 432 GB — so the path must come from the Lxss BasePath keyed by
# DistributionName. reg.exe runs with MSYS_NO_PATHCONV: Git Bash would rewrite
# the `/v` flag into a Windows path before reg.exe sees it.
# ==============================================================================

wsl_vhdx_path() {
  local distro="$1" _key _name _bp
  local _lxss='HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss'
  for _key in $(MSYS_NO_PATHCONV=1 reg.exe query "$_lxss" 2>/dev/null | tr -d '\r' | grep '^HKEY' || true); do
    _name="$(MSYS_NO_PATHCONV=1 reg.exe query "$_key" /v DistributionName 2>/dev/null | tr -d '\r' \
      | sed -n 's/.*REG_SZ[[:space:]]*//p')"
    [ "$_name" = "$distro" ] || continue
    _bp="$(MSYS_NO_PATHCONV=1 reg.exe query "$_key" /v BasePath 2>/dev/null | tr -d '\r' \
      | sed -n 's/.*REG_SZ[[:space:]]*//p')"
    # Store installs prefix the path with \\?\ — strip it before converting.
    _bp="${_bp#\\\\?\\}"
    [ -n "$_bp" ] || return 1
    _vf="$(MSYS_NO_PATHCONV=1 reg.exe query "$_key" /v VhdFileName 2>/dev/null | tr -d '\r' \
      | sed -n 's/.*REG_SZ[[:space:]]*//p')"
    printf '%s/%s\n' "$(cygpath -u "$_bp")" "${_vf:-ext4.vhdx}"
    return 0
  done
  return 1
}

# What to run when wsl_vhdx_path finds nothing. One copy, so a stale hint is
# fixed in one place (`wsl --manage --get-location` once sat in two scripts
# and exists in no WSL this repo runs on).
wsl_vhdx_locate_hint() {
  echo "    List every registered distro with its BasePath and VhdFileName:"
  echo "      reg query \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Lxss\" /s"
}

# Prints raw facts about the vhdx at the Windows path $1, one per line:
#   sparse 0|1|?   user <SID>   owner <SID>|?   allow <SID>|?  (one per Allow ACE)
# Uses .NET, not Get-Acl or Get-Item: started from Git Bash, Windows PowerShell
# inherits pwsh 7's PSModulePath and Get-Acl fails to autoload; the module path
# is reset anyway. The attribute and the ACL are read separately, so an
# unreadable ACL does not hide the sparse flag. No SID is turned into a name:
# WSL's AppContainer SID does not translate and would take the whole ACL down.
wsl_vhdx_facts() {
  # shellcheck disable=SC2016  # PowerShell variables; bash must not expand them
  DOTFILES_VHDX="$1" MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' powershell.exe -NoProfile -NonInteractive -Command \
    '$env:PSModulePath=[IO.Path]::Combine($PSHOME,"Modules"); $p=$env:DOTFILES_VHDX; $s=[Security.Principal.SecurityIdentifier]; try { "sparse " + [int][bool]([IO.File]::GetAttributes($p) -band [IO.FileAttributes]::SparseFile) } catch { "sparse ?" }; "user " + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value; try { $a=[IO.File]::GetAccessControl($p); "owner " + $a.GetOwner($s).Value; $a.GetAccessRules($true,$true,$s) | Where-Object { $_.AccessControlType -eq "Allow" } | ForEach-Object { "allow " + $_.IdentityReference.Value } } catch { "owner ?"; "allow ?" }' \
    2>/dev/null | tr -d '\r'
}

# Trusted to hold a distro's disk: the user, SYSTEM, Administrators, and the
# SIDs WSL itself adds (NT VIRTUAL MACHINE\<vm>, and an AppContainer SID that
# only narrows access). Everything else - Users, Authenticated Users, Everyone,
# a sandbox group, another account - is not. An allowlist, like
# scripts/jev_core.py's windows_acl_is_private: a denylist misses whatever SID
# this machine happens to mint.
_wsl_vhdx_trusted() { # $1 sid, $2 user sid
  case "$1" in
    "$2" | S-1-5-18 | S-1-5-32-544 | S-1-5-83-* | S-1-15-*) return 0 ;;
  esac
  return 1
}

# Reads wsl_vhdx_facts on stdin and prints every untrusted SID that owns or may
# open the vhdx, or a lone `?` when the ACL could not be read. No I/O besides
# stdin and stdout.
wsl_vhdx_untrusted_sids() {
  local _tag _sid _rest _user="" _owner="" _allow="" _unknown=0
  while read -r _tag _sid _rest; do
    # Windows writers end lines with CR; "S-1-5-18<CR>" would fail the allowlist.
    _sid="${_sid%$'\r'}"
    case "$_tag" in
      user) _user="$_sid" ;;
      owner) _owner="$_sid" ;;
      allow) _allow="${_allow} ${_sid}" ;;
    esac
  done
  case " $_owner ${_allow} " in *" ? "*) _unknown=1 ;; esac
  [ -n "$_owner" ] || _unknown=1
  if [ "$_unknown" -eq 1 ]; then
    echo "?"
    return 0
  fi
  {
    _wsl_vhdx_trusted "$_owner" "$_user" || echo "$_owner"
    for _sid in $_allow; do
      # OWNER RIGHTS names the actual owner, not another principal.
      [ "$_sid" != "S-1-3-4" ] || _sid="$_owner"
      _wsl_vhdx_trusted "$_sid" "$_user" || echo "$_sid"
    done
  } | sort -u
}
