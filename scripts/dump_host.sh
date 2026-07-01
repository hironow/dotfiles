#!/usr/bin/env bash
# ADR 0030: resolve the per-host alias that selects which dump/<host>/ manifest
# `just dump` writes and `just add-*` restore from.
#
# `just dump` used to overwrite a single dump/Brewfile (last-writer-wins), so
# two same-OS machines could not coexist. Manifests now live under a per-host
# alias directory. The alias is machine-local, NOT the raw hostname (dotfiles is
# a public repo — we do not commit LocalHostName). It comes from, in order:
#
#   1. $DOTFILES_HOST         (env; primary interface, also flows into install.sh)
#   2. dump/.host            (untracked, machine-local; written by `just set-host`)
#
# Both sources pass the SAME validator here so a hand-edited dump/.host cannot
# smuggle whitespace, newlines, or a path-traversal alias into a `dump/$host`
# path. dump/.host is deliberately untracked (see .gitignore); env wins over it.
#
# Subcommands:
#   validate <value>          exit 0 iff <value> is a valid alias slug
#   resolve-dump              print the alias to dump AS (env -> .host -> fail)
#   resolve-restore [host]    print the alias to restore FROM
#                             (arg -> env -> .host -> lone host dir -> fail)
#   set <alias>               validate <alias> and write it to dump/.host
#
# resolve-dump does not require dump/<host> to pre-exist (dump creates it).
# resolve-restore does: you can only restore from a host that was recorded.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
# DOTFILES_DUMP_DIR overrides the dump root for isolated tests (point it at a
# tempdir so resolution/validation can be exercised without touching the real
# tracked dump/ — critical because CI bind-mounts the live checkout).
DUMP_DIR="${DOTFILES_DUMP_DIR:-$REPO_ROOT/dump}"
HOST_FILE="$DUMP_DIR/.host"

# A safe alias is a single lowercase slug: no whitespace, no slashes, no dots,
# so it can never escape dump/ (rejects "", "../x", "a b", multi-line).
readonly SLUG_RE='^[a-z0-9][a-z0-9-]*$'

die() {
    printf '❌ %s\n' "$1" >&2
    exit 1
}

# Validate a candidate alias. `origin` only sharpens the error message.
validate() {
    local value="$1" origin="${2:-alias}"
    if [[ -z "$value" ]]; then
        die "empty $origin — set a host alias: just set-host <alias>"
    fi
    if [[ "$value" == *$'\n'* ]]; then
        die "$origin must be a single line (got multiple)"
    fi
    if [[ ! "$value" =~ $SLUG_RE ]]; then
        die "invalid $origin '$value' — must match ${SLUG_RE} (lowercase, digits, dashes)"
    fi
    printf '%s\n' "$value"
}

# Read the WHOLE dump/.host if present. Command substitution strips only
# trailing newlines, so a multi-line hand-edit keeps its internal newline and
# validate() rejects it (reading just the first line would silently ignore the
# rest and defeat the one-line contract).
read_host_file() {
    [[ -f "$HOST_FILE" ]] || return 1
    local content
    content="$(cat -- "$HOST_FILE")" || return 1
    [[ -n "$content" ]] || return 1
    printf '%s' "$content"
}

# List recorded host directories (subdirs of dump/), one basename per line.
list_host_dirs() {
    find "$DUMP_DIR" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; 2>/dev/null | sort
}

resolve_dump() {
    local from_file
    if [[ -n "${DOTFILES_HOST:-}" ]]; then
        validate "$DOTFILES_HOST" "DOTFILES_HOST"
        return
    fi
    if from_file="$(read_host_file)"; then
        validate "$from_file" "dump/.host"
        return
    fi
    die "no host alias set — run: just set-host <alias> (e.g. macbook), or export DOTFILES_HOST"
}

resolve_restore() {
    local host_arg="${1:-}" host from_file candidates count
    if [[ -n "$host_arg" ]]; then
        host="$(validate "$host_arg" "host argument")"
    elif [[ -n "${DOTFILES_HOST:-}" ]]; then
        host="$(validate "$DOTFILES_HOST" "DOTFILES_HOST")"
    elif from_file="$(read_host_file)"; then
        host="$(validate "$from_file" "dump/.host")"
    else
        candidates="$(list_host_dirs)"
        count="$(printf '%s' "$candidates" | grep -c . || true)"
        if [[ "$count" -eq 1 ]]; then
            printf '%s\n' "$candidates"
            return
        fi
        if [[ "$count" -eq 0 ]]; then
            die "no recorded host under dump/ — run 'just dump' on a source machine first"
        fi
        die "multiple hosts under dump/ ($(printf '%s' "$candidates" | paste -sd', ' -)); pass one: just add-brew <host>, or export DOTFILES_HOST"
    fi
    # Require a *plain* directory: a symlinked dump/<host> would let brew bundle
    # read a manifest from outside the tree (slug validation already blocks ../).
    if [[ ! -d "$DUMP_DIR/$host" || -L "$DUMP_DIR/$host" ]]; then
        candidates="$(list_host_dirs | paste -sd', ' - || true)"
        die "no plain dump/$host/ directory recorded (available: ${candidates:-none})"
    fi
    printf '%s\n' "$host"
}

set_host() {
    local alias validated
    alias="${1:-}"
    validated="$(validate "$alias" "alias")"
    mkdir -p "$DUMP_DIR"
    printf '%s\n' "$validated" >"$HOST_FILE"
    printf '✅ host alias set to %s (dump/.host, untracked)\n' "$validated"
}

main() {
    local cmd="${1:-}"
    shift || true
    case "$cmd" in
        validate)        validate "${1:-}" "alias" >/dev/null ;;
        resolve-dump)    resolve_dump ;;
        resolve-restore) resolve_restore "${1:-}" ;;
        set)             set_host "${1:-}" ;;
        *) die "usage: dump_host.sh {validate|resolve-dump|resolve-restore|set} [arg]" ;;
    esac
}

main "$@"
