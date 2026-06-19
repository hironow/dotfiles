#!/usr/bin/env bash
# ADR 0028 enforcement: assert every uv project declares the Flatt Security PyPI
# mirror (malware-scanned) as its default index, and that no committed lock falls
# back to raw pypi.org.
#
# The invariant is the ABSENCE of raw pypi.org (not the universal presence of
# flatt) -- which would also allow an explicit non-flatt index (e.g. a CUDA
# wheel index) if one were ever added. dotfiles has none today.
#
# Pure grep, no network. Fails loud + non-zero per the "no silent skip/fail"
# policy. Run from anywhere (resolves the repo root from this script's path).
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECTS=(
    emulator
    tools/rttm
    telemetry/examples
)

fail=0

for p in "${PROJECTS[@]}"; do
    py="$p/pyproject.toml"
    lock="$p/uv.lock"

    if [ ! -f "$py" ]; then
        echo "check-uv-flatt-index: ERROR -- missing $py" >&2
        fail=1
        continue
    fi

    # (a) pyproject must declare the flatt index.
    if ! grep -q 'pypi.flatt.tech' "$py"; then
        echo "check-uv-flatt-index: ERROR -- $py does not declare the flatt index (ADR 0028)." >&2
        echo "  Fix: add [[tool.uv.index]] name=\"flatt\" url=\"https://pypi.flatt.tech/simple/\" default=true" >&2
        fail=1
    fi

    # (b) lock must NOT reference raw pypi.org.
    if [ -f "$lock" ] && grep -q 'registry = "https://pypi.org/simple"' "$lock"; then
        n=$(grep -c 'registry = "https://pypi.org/simple"' "$lock")
        echo "check-uv-flatt-index: ERROR -- $lock has $n raw pypi.org registry line(s) (ADR 0028)." >&2
        echo "  Fix: just relock-uv" >&2
        fail=1
    fi
done

if [ "$fail" -ne 0 ]; then
    echo "check-uv-flatt-index: FAILED -- see above. Ref: docs/adr/0028-flatt-pypi-mirror-default-index.md" >&2
    exit 1
fi

echo "check-uv-flatt-index: OK -- all ${#PROJECTS[@]} uv projects declare the flatt"
echo "  default index, and no committed lock references raw pypi.org."
