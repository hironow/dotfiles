#!/usr/bin/env bash
set -euo pipefail

# Run E2E tests (sequential due to Podman client state management).
# Usage: bash scripts/run-tests-e2e.sh

command -v uv >/dev/null 2>&1 || { echo "uv not found. Install: https://github.com/astral-sh/uv" >&2; exit 127; }

echo "Running E2E tests"
: "${DOTFILES_PODMAN_RUN_MANIFEST:?Prepare an isolated Podman run first}"
export DOTFILES_E2E_REQUIRED=1
uv run --frozen pytest tests/e2e -v -m e2e -ra
echo "Done."
