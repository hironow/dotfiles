#!/usr/bin/env bash
set -euo pipefail

# Run E2E tests (sequential due to Docker client state management).
# Usage: bash scripts/run-tests-e2e.sh

command -v uv >/dev/null 2>&1 || { echo "uv not found. Install: https://github.com/astral-sh/uv" >&2; exit 127; }

echo "Running E2E tests"
uv run pytest tests/e2e -v -m e2e -ra
echo "Done."
