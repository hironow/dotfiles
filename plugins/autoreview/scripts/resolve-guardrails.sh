#!/usr/bin/env bash
# resolve-guardrails.sh - Resolve the guardrails Semgrep rules path
#
# The rules live in hironow/dotfiles at .semgrep/rules/guardrails/, one
# directory per category plus tests/ for the fixtures. Looks there in the
# current git repository first, then in the repository that holds this plugin
# (two levels above CLAUDE_PLUGIN_ROOT).
#
# Output: Prints the absolute path to the rules directory.
# Exit 1 if the rules directory cannot be found.

set -euo pipefail

RULES_SUBDIR=".semgrep/rules/guardrails"

# Try git toplevel first
if REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
  RULES_DIR="${REPO_ROOT}/${RULES_SUBDIR}"
  if [[ -d "$RULES_DIR" ]]; then
    echo "$RULES_DIR"
    exit 0
  fi
fi

# Fallback: the repository that holds this plugin
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  CANDIDATE=$(cd "$CLAUDE_PLUGIN_ROOT" && cd ../.. && pwd)/${RULES_SUBDIR}
  if [[ -d "$CANDIDATE" ]]; then
    echo "$CANDIDATE"
    exit 0
  fi
fi

echo "ERROR: Cannot find the ${RULES_SUBDIR}/ rules directory" >&2
exit 1
