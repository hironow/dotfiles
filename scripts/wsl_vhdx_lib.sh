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
    printf '%s/ext4.vhdx\n' "$(cygpath -u "$_bp")"
    return 0
  done
  return 1
}
