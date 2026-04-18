#!/usr/bin/env bash
#
# Clean up user-actionable PATH duplicates reported by `just doctor`.
#
# Actions:
#   A. Remove stale /etc/paths.d entries (MacGPG2, go, Wireshark)
#      - MacGPG2: replaced by brew gnupg
#      - /usr/local/go/bin: replaced by mise-managed go
#      - Wireshark.app bundle: already symlinked into /opt/homebrew/bin by brew cask
#   B. Remove pnpm globals that duplicate brew formulas
#
# Idempotent: skips actions that have already been applied.
#
# Usage:
#   scripts/cleanup_path_duplicates.sh [--dry-run] [--skip-paths-d] [--skip-pnpm]

set -euo pipefail

DRY_RUN=0
SKIP_PATHS_D=0
SKIP_PNPM=0

# --- argument parsing (early) -------------------------------------------------
while (($#)); do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --skip-paths-d) SKIP_PATHS_D=1 ;;
        --skip-pnpm) SKIP_PNPM=1 ;;
        -h | --help)
            sed -n '3,17p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 2
            ;;
    esac
    shift
done

run() {
    if ((DRY_RUN)); then
        printf '[dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

run_sudo() {
    if ((DRY_RUN)); then
        printf '[dry-run] sudo %s\n' "$*"
    else
        sudo "$@"
    fi
}

log_section() { printf '\n=== %s ===\n' "$1"; }
log_ok() { printf '  OK   %s\n' "$1"; }
log_skip() { printf '  SKIP %s\n' "$1"; }

# --- A: /etc/paths.d cleanup -------------------------------------------------
declare -a PATHS_D_TARGETS=(
    /etc/paths.d/MacGPG2
    /etc/paths.d/go
    /etc/paths.d/Wireshark
)

if ((SKIP_PATHS_D)); then
    log_section "A. /etc/paths.d cleanup (skipped)"
else
    log_section "A. /etc/paths.d cleanup"
    for f in "${PATHS_D_TARGETS[@]}"; do
        if [[ -e "$f" ]]; then
            run_sudo rm "$f"
            log_ok "removed $f"
        else
            log_skip "$f (already absent)"
        fi
    done
fi

# --- B: pnpm globals deduplication -------------------------------------------
# These pnpm-installed packages provide CLIs that also exist in brew.
# Keep brew, drop pnpm. Listed as package names (not bin names) because
# `pnpm rm -g` operates on package identifiers.
declare -a PNPM_DUPES=(
    "@githubnext/github-copilot-cli" # bin: github-copilot-cli
    "@nestjs/cli"                    # bin: nest
    "@playwright/cli"                # bin: playwright
    "@thunderclient/cli"             # bins: tc, tc2
    "@vivliostyle/cli"               # bin: vivliostyle
    azurite                          # bins: azurite, azurite-*
    firebase-tools                   # bin: firebase
    fx
    http-server
    json-schema-to-typescript # bin: json2ts
    json-server
    lint-staged
    playwright
    pyright
    tldr
    typeorm
    typescript # bin: tsc
    wrangler   # bins: wrangler, wrangler2
    wscat
)

if ((SKIP_PNPM)); then
    log_section "B. pnpm globals dedup (skipped)"
elif ! command -v pnpm > /dev/null 2>&1; then
    log_section "B. pnpm globals dedup"
    log_skip "pnpm not found in PATH"
else
    log_section "B. pnpm globals dedup"
    # Snapshot installed globals so we can do idempotence by package name.
    # Run from $HOME to avoid projects that pin packageManager to npm/yarn
    # (pnpm refuses to execute in such a working directory).
    installed=$(env -C "$HOME" pnpm ls -g --depth 0 --parseable 2> /dev/null || true)
    to_remove=()
    for pkg in "${PNPM_DUPES[@]}"; do
        # `pnpm ls --parseable` prints paths like .../node_modules/<pkg>;
        # match by trailing "/<pkg>" to support scoped names like @scope/name.
        if grep -qE "/${pkg}\$" <<< "$installed"; then
            to_remove+=("$pkg")
        else
            log_skip "$pkg (not installed)"
        fi
    done
    if ((${#to_remove[@]})); then
        run env -C "$HOME" pnpm rm -g "${to_remove[@]}"
        for pkg in "${to_remove[@]}"; do log_ok "removed pnpm global: $pkg"; done
    else
        log_ok "nothing to remove"
    fi
fi

# --- next actions guidance ---------------------------------------------------
log_section "Next actions"
cat << 'EOF'
  1. Restart your terminal (or run `exec zsh -l`) so /etc/paths.d changes apply.
  2. Verify results:
       just doctor
  3. Remaining duplicates (reported as [user] in validate-path-duplicates)
     are out of scope for this script — see ROOT_AGENTS.md or docs for
     further cleanup (e.g. stale python.org/intel brew under /usr/local/bin).
EOF
