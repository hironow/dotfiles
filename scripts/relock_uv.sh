#!/usr/bin/env bash
# ADR 0028: regenerate the uv locks that currently resolve from raw pypi.org so
# they route through the flatt mirror, WITHOUT pulling in nino's machine-local
# hardening config.
#
# uv reads the user hardening config from $XDG_CONFIG_HOME/uv/uv.toml on
# mac/linux (`scripts/harden_env.sh` writes a flatt default index + a personal
# `exclude-newer = "7 days"` there). Pointing XDG_CONFIG_HOME at an empty temp
# dir makes each lock reflect ONLY its project pyproject.toml:
#   - flatt comes from the project's own [[tool.uv.index]] (ADR 0028), not the
#     personal global default;
#   - exclude-newer stays whatever the project declares -- emulator keeps its
#     repo-authoritative `exclude-newer = "7 days"` (P7D preserved), tools/rttm
#     declares none and stays span-less. The personal exclude-newer does NOT
#     leak into a project that does not ask for it.
#
# telemetry/examples is intentionally NOT relocked here: its committed lock is
# already on flatt with no raw pypi.org, so a temp-XDG relock would only strip
# its (personal-derived) P7D for no benefit. It is covered by the guard only.
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECTS=(
    emulator
    tools/rttm
)

tmpcfg="$(mktemp -d)"
trap 'rm -rf "$tmpcfg"' EXIT

for p in "${PROJECTS[@]}"; do
    echo "relock-uv: $p"
    ( cd "$p" && XDG_CONFIG_HOME="$tmpcfg" uv lock )
done

echo "relock-uv: done. Verify with: just check-uv-flatt-index"
