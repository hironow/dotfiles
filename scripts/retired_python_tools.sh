#!/usr/bin/env bash
# Detect / prune the Python tools retired by ADR 0044.
#
# The Python toolchain is uv + ruff + ty, with mise as the single provider of
# the interactive ruff / ty copies. A machine that predates the switch still
# carries: mypy / pyright executables on PATH (pyright typically as a rogue npm
# global under <prefix>/lib/node_modules), `uv tool` installs of mypy and ruff,
# a Homebrew ruff or pyright, mise ruff / ty versions the config no longer
# pins, and the mypy VS Code extension. `just doctor` runs `detect` (label
# `python-retired`); `just prune-retired-python-tools` runs `prune`.
#
# Usage:  retired_python_tools.sh [detect|prune]
#   detect : one `<kind>:<name>[:<path>]` line per artefact; exit 0.
#   prune  : remove every artefact detect lists EXCEPT the VS Code extension
#            (reported, left to the editor) and PATH entries whose provider it
#            cannot name (reported, left alone); exit 1 if a removal failed.
#
# Injection points (tests run host-side with stubs on PATH):
#   UV_TOOL_DIR                  uv's own variable: where `uv tool` envs live
#   RETIRED_TOOLS_MISE_CONFIG    mise config to read the ruff / ty pins from
#   RETIRED_TOOLS_MISE_INSTALLS  mise `installs/` dir (<tool>/<version>/)
set -euo pipefail

UV_TOOLS="${UV_TOOL_DIR:-$HOME/.local/share/uv/tools}"
MISE_CFG="${RETIRED_TOOLS_MISE_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/mise/config.toml}"
MISE_INSTALLS="${RETIRED_TOOLS_MISE_INSTALLS:-${MISE_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mise}/installs}"

RETIRED_EXES='mypy dmypy pyright pyright-langserver'
RETIRED_UV_TOOLS='mypy ruff'
RETIRED_BREW='ruff pyright'
MISE_PINNED='ruff ty'
VSCODE_EXT='ms-python.mypy-type-checker'

# Exact version the mise config pins for $1 (empty + non-zero if none).
mise_pin() {
  [ -f "$MISE_CFG" ] || return 1
  sed -n "s/^$1 = \"\([0-9][0-9A-Za-z.]*\)\"[[:space:]]*$/\1/p" "$MISE_CFG" | head -n 1 | grep .
}

detect() {
  local exe p name pin d ver
  for exe in $RETIRED_EXES; do
    if p="$(command -v "$exe" 2>/dev/null)"; then
      printf 'path:%s:%s\n' "$exe" "$p"
    fi
  done
  for name in $RETIRED_UV_TOOLS; do
    [ -d "$UV_TOOLS/$name" ] && printf 'uv-tool:%s\n' "$name"
  done
  if command -v brew >/dev/null 2>&1; then
    for name in $RETIRED_BREW; do
      if brew list --formula 2>/dev/null | grep -qx "$name"; then
        printf 'brew:%s\n' "$name"
      fi
    done
  fi
  for name in $MISE_PINNED; do
    pin="$(mise_pin "$name")" || continue   # unpinned: nothing to compare against
    [ -d "$MISE_INSTALLS/$name" ] || continue
    for d in "$MISE_INSTALLS/$name"/*/; do
      [ -d "$d" ] || continue
      [ -L "${d%/}" ] && continue           # mise alias links (e.g. `latest`)
      ver="$(basename "$d")"
      [ "$ver" = "$pin" ] || printf 'mise-unmanaged:%s@%s\n' "$name" "$ver"
    done
  done
  if command -v code >/dev/null 2>&1; then
    if code --list-extensions 2>/dev/null | grep -qx "$VSCODE_EXT"; then
      printf 'vscode:%s\n' "$VSCODE_EXT"
    fi
  fi
  return 0
}

# path:<exe>:<p> -- only the rogue npm-global pyright layout is removed here;
# uv-tool and brew providers are handled by their own lines, anything else is
# reported and left alone (never delete what we cannot name).
prune_path() {
  local exe="$1" p="$2" target pkgdir
  target="$(readlink -f "$p" 2>/dev/null || printf '%s' "$p")"
  case "$target" in
    */node_modules/pyright/*)
      pkgdir="${target%%/node_modules/pyright/*}/node_modules/pyright"
      rm -rf "$pkgdir" && rm -f "$p" && printf 'pruned path:%s:%s (npm global %s)\n' "$exe" "$p" "$pkgdir"
      ;;
    "$UV_TOOLS"/*)
      printf 'skip path:%s:%s (removed with its uv tool)\n' "$exe" "$p"
      ;;
    *)
      printf 'left path:%s:%s (unknown provider -- remove by hand)\n' "$exe" "$p"
      ;;
  esac
}

prune() {
  local findings line kind rest rc=0
  findings="$(detect)"
  if [ -z "$findings" ]; then
    echo 'retired-python-tools: nothing to prune'
    return 0
  fi
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    kind="${line%%:*}"
    rest="${line#*:}"
    case "$kind" in
      uv-tool)
        if uv tool uninstall "$rest"; then printf 'pruned %s\n' "$line"; else printf 'could NOT prune %s\n' "$line" >&2; rc=1; fi ;;
      brew)
        if brew uninstall "$rest"; then printf 'pruned %s\n' "$line"; else printf 'could NOT prune %s\n' "$line" >&2; rc=1; fi ;;
      mise-unmanaged)
        if mise uninstall "$rest"; then printf 'pruned %s\n' "$line"; else printf 'could NOT prune %s\n' "$line" >&2; rc=1; fi ;;
      path)
        prune_path "${rest%%:*}" "${rest#*:}" || rc=1 ;;
      vscode)
        printf 'left %s (editor extension -- uninstall it in VS Code)\n' "$line" ;;
      *)
        printf 'left %s (unhandled kind)\n' "$line" ;;
    esac
  done <<< "$findings"
  return "$rc"
}

case "${1:-}" in
  detect) detect ;;
  prune) prune ;;
  *) echo 'usage: retired_python_tools.sh [detect|prune]' >&2; exit 2 ;;
esac
