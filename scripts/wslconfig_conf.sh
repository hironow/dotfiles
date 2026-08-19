#!/usr/bin/env bash

# ==============================================================================
# Advise on the Windows-side %USERPROFILE%\.wslconfig (config/wsl/wslconfig)
# ------------------------------------------------------------------------------
# Windows counterpart of the `wsl-conf` recipe (which covers the distro-side
# /etc/wsl.conf). Advisory only: reloading .wslconfig needs `wsl --shutdown`,
# which takes the self-hosted runner distro offline (ADR 0035), so this
# previews the template, diffs the recommended keys against the live file,
# and prints the apply steps — it never writes the file or restarts WSL.
# ==============================================================================

set -euo pipefail

case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) ;;
  *)
    echo "ℹ️  Not a native Windows host ($(uname -s)); .wslconfig lives on the Windows side — nothing to do."
    exit 0
    ;;
esac

tmpl="config/wsl/wslconfig"
# Git Bash exposes the Windows home as $USERPROFILE (a Windows path); go
# through cygpath so the shell can read it.
conf="$(cygpath -u "${USERPROFILE}")/.wslconfig"

echo "🪟 Recommended Windows-side WSL settings (${tmpl}):"
sed 's/^/    /' "${tmpl}"
echo

missing=0
if [ -f "${conf}" ] && grep -qE '^[[:space:]]*autoMemoryReclaim[[:space:]]*=[[:space:]]*gradual' "${conf}"; then
  echo "✅ autoMemoryReclaim=gradual present in ${conf}"
else
  echo "⚠️  ${conf} missing 'autoMemoryReclaim=gradual' ([experimental])"
  missing=1
fi

if [ "${missing}" -eq 0 ]; then
  echo "✅ ${conf} already carries the recommended keys."
  exit 0
fi

echo
echo "Apply by merging the missing keys into the live file:"
echo "  notepad ${USERPROFILE}\\.wslconfig"
echo "Then reload from Windows PowerShell (a full WSL restart — the runner"
echo "distro goes offline for the duration, pick an idle moment):"
echo "  wsl --shutdown"
