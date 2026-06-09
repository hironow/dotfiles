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
# Python: uv only.
if printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_./-])(pip3?|poetry|pipenv)([[:space:]]|$)'; then
  block "Python package management is 'uv' only (uv add / uv sync / uv run). Do not use pip/poetry/pipenv."
fi

# Node: bun, unless pnpm-lock.yaml exists (then pnpm). Never npm/yarn.
if printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_./-])(npm|yarn)([[:space:]]|$)'; then
  block "Node package management is 'bun' (or 'pnpm' iff pnpm-lock.yaml exists). Do not use npm/yarn."
fi
if printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_./-])pnpm([[:space:]]|$)'; then
  if [ ! -f pnpm-lock.yaml ]; then
    block "'pnpm' is allowed only when pnpm-lock.yaml exists in this project. Use 'bun' instead."
  fi
fi

# Task runner: just only, no make.
if printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_./-])make([[:space:]]|$)'; then
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
