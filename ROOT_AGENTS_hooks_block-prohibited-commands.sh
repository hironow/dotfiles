#!/usr/bin/env bash
# .claude/hooks/block-prohibited-commands.sh
# PreToolUse hook (matcher: Bash). Enforces the command-level non-negotiables in
# AGENTS.md and docs/agents/iac-drift-policy.md.
#
# Exit-code contract:
#   exit 0  -> allow
#   exit 2  -> BLOCK (stderr -> Claude). exit 1 would NOT block.
set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"
[ -z "$cmd" ] && exit 0

block() { echo "BLOCKED: $1" >&2; exit 2; }

# --- Package managers ---------------------------------------------------------
# Tooling-word guards scan with quoted substrings removed, so prose mentions
# (commit messages, echo strings) don't false-trigger. The flip side — a quoted
# invocation like `bash -c "npm i"` slips these guards — is accepted long tail:
# prose rules + review cover it. Destructive/IaC guards below keep scanning the
# full string (over-blocking is the safe side there).
scan="$(printf '%s' "$cmd" | sed -E -e 's/"[^"]*"//g' -e "s/'[^']*'//g")"

# Python: uv only.
if printf '%s' "$scan" | grep -Eq '(^|[^[:alnum:]_./-])(pip3?|poetry|pipenv)([[:space:]]|$)'; then
  block "Python package management is 'uv' only (uv add / uv sync / uv run). Do not use pip/poetry/pipenv."
fi

# Node: bun, unless pnpm-lock.yaml exists (then pnpm). Never npm/yarn.
if printf '%s' "$scan" | grep -Eq '(^|[^[:alnum:]_./-])(npm|yarn)([[:space:]]|$)'; then
  block "Node package management is 'bun' (or 'pnpm' iff pnpm-lock.yaml exists). Do not use npm/yarn."
fi

# pnpm: allowed only when a pnpm-lock.yaml governs EACH pnpm invocation's
# effective directory — the last `cd` target before it in its segment chain,
# its -C/--dir flag, or the session cwd — searched upward to the filesystem
# root. Parsing is best-effort; unresolvable targets (variables, subshells)
# fail safe (block), and the block message offers the `!` escape hatch.
find_pnpm_lock_upward() {
  local d
  d="$(cd "$1" 2>/dev/null && pwd)" || return 1
  while :; do
    [ -f "$d/pnpm-lock.yaml" ] && return 0
    [ "$d" = "/" ] && return 1
    d="$(dirname "$d")"
  done
}

if printf '%s' "$scan" | grep -Eq '(^|[^[:alnum:]_./-])pnpm([[:space:]]|$)'; then
  segs="$scan"
  segs="${segs//";"/$'\n'}"
  segs="${segs//"&&"/$'\n'}"
  segs="${segs//"||"/$'\n'}"
  eff_dir="$PWD"
  pnpm_ok=1
  while IFS= read -r seg; do
    seg="$(printf '%s' "$seg" | sed -E 's/^[[:space:](]+//')"
    case "$seg" in
      cd|cd\ *)
        tgt="${seg#cd}"
        tgt="${tgt# }"
        tgt="${tgt%%[[:space:]]*}"
        tgt="${tgt/#\~/$HOME}"
        case "$tgt" in
          "" | \$* | \`*) eff_dir="" ;; # empty/variable/substitution: unresolvable
          /*) eff_dir="$tgt" ;;
          *) if [ -n "$eff_dir" ]; then eff_dir="$eff_dir/$tgt"; else eff_dir=""; fi ;;
        esac
        ;;
    esac
    if printf '%s' "$seg" | grep -Eq '(^|[^[:alnum:]_./-])pnpm([[:space:]]|$)'; then
      if printf '%s' "$seg" | grep -Eq '[[:space:]](-C|--dir)[= ]'; then
        tdir="$(printf '%s' "$seg" | sed -nE 's/.*[[:space:]](-C|--dir)[= ]([^[:space:]]+).*/\2/p')"
        case "$tdir" in
          "" | \$* | \`*) check_dir="" ;;
          /*) check_dir="$tdir" ;;
          *) if [ -n "$eff_dir" ]; then check_dir="$eff_dir/$tdir"; else check_dir=""; fi ;;
        esac
      else
        check_dir="$eff_dir"
      fi
      if [ -z "$check_dir" ] || ! find_pnpm_lock_upward "$check_dir"; then
        pnpm_ok=0
      fi
    fi
  done <<<"$segs"
  if [ "$pnpm_ok" -ne 1 ]; then
    block "'pnpm' is allowed only when pnpm-lock.yaml governs each pnpm invocation's target directory (resolved cd/-C/--dir target or cwd, searched upward). Use 'bun' instead — or, for a legitimate cross-repo call this guard can't resolve, ask the user to run it with the '!' prefix."
  fi
fi

# Task runner: just only, no make.
if printf '%s' "$scan" | grep -Eq '(^|[^[:alnum:]_./-])make([[:space:]]|$)'; then
  block "Task automation is 'just' only. Add a recipe to the root justfile instead of using make."
fi

# --- Obviously destructive ----------------------------------------------------
if printf '%s' "$cmd" | grep -Eq 'rm[[:space:]]+(-[a-zA-Z]*[rR][a-zA-Z]*[[:space:]]+)?(-[a-zA-Z]*f[a-zA-Z]*[[:space:]]+)?/($|[[:space:]])'; then
  block "Refusing 'rm -rf /' (or equivalent root deletion)."
fi
if printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+push[[:space:]].*--force([[:space:]]|=).*(main|master)'; then
  block "Refusing force-push to main/master. Open a PR; never rewrite shared history on the default branch."
fi

# --- IaC drift (see docs/agents/iac-drift-policy.md) --------------------------
# These mutate state OpenTofu owns. Read-only verbs (describe/list/get/show) pass.
if printf '%s' "$cmd" | grep -Eq 'gcloud[[:space:]].*(add-iam-policy-binding|set-iam-policy)'; then
  block "IAM changes go through OpenTofu (iam_*.tf) + PR, not gcloud. See docs/agents/iac-drift-policy.md."
fi
if printf '%s' "$cmd" | grep -Eq 'gcloud[[:space:]]+(compute|run|sql|secrets)[[:space:]].*(set-machine-type|resize|update|deploy|versions[[:space:]]+add)'; then
  block "This gcloud command mutates IaC-managed infra and will drift from tofu. Open an IaC PR. (Read-only debug is fine; emergency rollback must be followed by an IaC PR same session.)"
fi
if printf '%s' "$cmd" | grep -Eq 'cdr[[:space:]]+workspaces[[:space:]]+(update|edit)'; then
  block "Patch the Coder template (coder_parameter), not the running workspace. See docs/agents/iac-drift-policy.md."
fi

exit 0
