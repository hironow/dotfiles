#!/usr/bin/env bash
# Detect / prune rogue global installs of mise-managed npm CLIs.
#
# The AI CLIs (codex, claude-code, copilot, pi) are managed by mise's `npm:`
# backend under `<mise>/installs/npm-<slug>/`. A stray `npm install -g <pkg>`
# — most notably codex's built-in `codex update` — installs the package into
# whatever node version is active at the time, i.e. into that node's global
# (`<mise>/installs/node/<ver>/...`). That copy then shadows the mise
# npm-backend version on PATH (per node version, so cleaning one node dir
# leaves others), and on Windows its running `.exe` cannot be replaced
# (EPERM). This never belongs in a node global, so any such copy is "rogue".
#
# Usage:  rogue_npm_globals.sh [detect|prune]
#   detect : print one `<node-ver>:<pkg>:<bin>` line per rogue install; exit 0.
#            Non-zero exit ONLY when the node-installs dir cannot be resolved
#            (so the caller can warn instead of falsely reporting "clean").
#   prune  : remove every rogue install found; reshim mise; exit 0.
#
# ROGUE_NODE_INSTALLS_DIR overrides the scanned `installs/node` directory
# (test injection point). When unset it is derived from `mise where node`,
# and only accepted if it looks like `.../installs/node` — never an empty or
# CWD-relative path, so a `mise where` failure can never point prune at the
# working tree.
set -euo pipefail

# package:bin for each mise-managed npm CLI with a global-install shadow risk.
MANAGED='@openai/codex:codex @anthropic-ai/claude-code:claude @github/copilot:copilot @earendil-works/pi-coding-agent:pi'

# Resolve the `installs/node` dir. Prints it on success (return 0).
# return 10 = no mise (benign: nothing to scan). return 2 = cannot determine
# (must NOT delete anything — surfaced as an error/warn by the caller).
resolve_installs_dir() {
  local dir nw
  if [ -n "${ROGUE_NODE_INSTALLS_DIR:-}" ]; then
    dir="$ROGUE_NODE_INSTALLS_DIR"
    [ -d "$dir" ] || return 2
    printf '%s' "$dir"
    return 0
  fi
  command -v mise >/dev/null 2>&1 || return 10
  nw="$(mise where node 2>/dev/null)" || return 2
  [ -n "$nw" ] || return 2
  # mise emits a native path; on Windows that is backslash-separated, which
  # POSIX dirname/glob treat as a single component (dirname -> "."). Normalise
  # to forward slashes so the `*/installs/node` guard and the scan glob work.
  nw="${nw//\\//}"
  dir="$(dirname "$nw")"
  case "$dir" in
    */installs/node) ;;
    *) return 2 ;;
  esac
  [ -d "$dir" ] || return 2
  printf '%s' "$dir"
  return 0
}

# Echo the package-dir path for <ver-dir> <pkg> if a rogue copy exists, trying
# both the Windows prefix layout (<ver>/node_modules/<pkg>) and the Unix one
# (<ver>/lib/node_modules/<pkg>).
rogue_pkg_dir() {
  local verdir="$1" pkg="$2" cand
  for cand in "${verdir}node_modules/${pkg}" "${verdir}lib/node_modules/${pkg}"; do
    if [ -e "${cand}/package.json" ] || [ -d "$cand" ]; then
      printf '%s' "$cand"
      return 0
    fi
  done
  return 1
}

# Print `<ver>:<pkg>:<bin>` for every rogue install under $1 (installs/node).
scan() {
  local installs="$1" verdir ver pair pkg bin
  for verdir in "$installs"/*/; do
    [ -d "$verdir" ] || continue
    ver="$(basename "$verdir")"
    for pair in $MANAGED; do
      pkg="${pair%%:*}"
      bin="${pair##*:}"
      if rogue_pkg_dir "$verdir" "$pkg" >/dev/null; then
        printf '%s:%s:%s\n' "$ver" "$pkg" "$bin"
      fi
    done
  done
}

# Remove the rogue install for one `<ver>:<pkg>:<bin>` finding under $1.
prune_one() {
  local installs="$1" ver="$2" pkg="$3" bin="$4"
  local verdir="${installs}/${ver}/" scope base pkgdir
  scope="${pkg%%/*}"
  base="${pkg##*/}"
  # package dir (whichever layout) + npm's failed-cleanup temp dirs.
  if pkgdir="$(rogue_pkg_dir "$verdir" "$pkg")"; then
    rm -rf "$pkgdir"
  fi
  rm -rf "${verdir}node_modules/${scope}/.${base}-"* "${verdir}lib/node_modules/${scope}/.${base}-"* 2>/dev/null || true
  rmdir "${verdir}node_modules/${scope}" "${verdir}lib/node_modules/${scope}" 2>/dev/null || true
  # bin shims: Windows prefix-root (<ver>/<bin>{,.cmd,.ps1}) + Unix (<ver>/bin/<bin>).
  rm -f "${verdir}${bin}" "${verdir}${bin}.cmd" "${verdir}${bin}.ps1" "${verdir}bin/${bin}" 2>/dev/null || true
}

main() {
  local mode="${1:-detect}" installs rc
  if installs="$(resolve_installs_dir)"; then
    rc=0
  else
    rc=$?
  fi

  case "$mode" in
    detect)
      if [ "$rc" -eq 10 ]; then exit 0; fi          # no mise: nothing to scan
      if [ "$rc" -ne 0 ]; then
        echo "rogue_npm_globals: cannot resolve installs/node dir (rc=$rc)" >&2
        exit "$rc"
      fi
      scan "$installs"
      ;;
    prune)
      if [ "$rc" -eq 10 ]; then echo 'mise not found; nothing to prune'; exit 0; fi
      if [ "$rc" -ne 0 ]; then
        echo "rogue_npm_globals: refusing to prune — cannot resolve installs/node dir (rc=$rc)" >&2
        exit "$rc"
      fi
      local removed=0 line ver pkg bin
      while IFS= read -r line; do
        [ -n "$line" ] || continue
        ver="${line%%:*}"
        pkg="${line#*:}"; pkg="${pkg%%:*}"
        bin="${line##*:}"
        prune_one "$installs" "$ver" "$pkg" "$bin"
        printf 'pruned %s from node %s\n' "$pkg" "$ver"
        removed=$((removed + 1))
      done < <(scan "$installs")
      if [ "$removed" -gt 0 ] && [ -z "${ROGUE_NODE_INSTALLS_DIR:-}" ] && command -v mise >/dev/null 2>&1; then
        mise reshim 2>/dev/null || true
      fi
      printf 'rogue npm globals pruned: %d\n' "$removed"
      ;;
    *)
      echo "usage: rogue_npm_globals.sh [detect|prune]" >&2
      exit 2
      ;;
  esac
}

main "$@"
