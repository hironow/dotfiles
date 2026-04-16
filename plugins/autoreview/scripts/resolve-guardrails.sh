#!/usr/bin/env bash
# resolve-guardrails.sh - Resolve the guardrails/semgrep rules path
#
# Searches for guardrails/semgrep/.semgrep/ from the git repository root.
# Falls back to a path relative to CLAUDE_PLUGIN_ROOT if not in a git repo.
#
# Output: Prints the absolute path to the .semgrep/ rules directory.
# Exit 1 if rules directory cannot be found.

set -euo pipefail

# Try git toplevel first
if REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
  RULES_DIR="${REPO_ROOT}/guardrails/semgrep/.semgrep"
  if [[ -d "$RULES_DIR" ]]; then
    echo "$RULES_DIR"
    exit 0
  fi
fi

# Fallback: walk up from CLAUDE_PLUGIN_ROOT
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  CANDIDATE=$(cd "$CLAUDE_PLUGIN_ROOT" && cd ../.. && pwd)/guardrails/semgrep/.semgrep
  if [[ -d "$CANDIDATE" ]]; then
    echo "$CANDIDATE"
    exit 0
  fi
fi

echo "ERROR: Cannot find guardrails/semgrep/.semgrep/ rules directory" >&2
exit 1
