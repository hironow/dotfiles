#!/usr/bin/env bash
# initializeCommand runs on the launcher, before the engine resolves bind paths.
set -euo pipefail
fail() { echo "Podman launch refused: $*" >&2; exit 1; }
socket="${DOTFILES_PODMAN_ENGINE_SOCKET:-}"
case "$socket" in
  /run/*/podman/podman.sock|/run/podman/podman.sock) ;;
  *) fail 'DOTFILES_PODMAN_ENGINE_SOCKET must be the selected engine-side /run/.../podman/podman.sock path from podman info, not a host-forwarded socket.' ;;
esac
command -v podman >/dev/null || fail 'native Podman >=5 is required; install it separately.'
command -v jq >/dev/null || fail 'canonical jq is required; install it separately.'
client=$(podman --version) || fail 'native client version query failed.'
[[ "$client" =~ ^podman\ version\ ([0-9]+)\.[0-9]+\.[0-9]+([-.+][^[:space:]]+)?$ ]] || fail 'malformed native Podman client version.'
(( 10#${BASH_REMATCH[1]} >= 5 )) || fail 'native Podman client >=5 is required.'
info=$(podman info --format json) || fail 'selected engine info query failed; activate the selected engine separately.'
server=$(jq -er '.version.Version | select(type == "string")' <<<"$info") || fail 'selected engine version missing/malformed.'
[[ "$server" =~ ^([0-9]+)\.[0-9]+\.[0-9]+([-.+][^[:space:]]+)?$ ]] || fail 'malformed selected Podman server version.'
(( 10#${BASH_REMATCH[1]} >= 5 )) || fail 'selected Podman server >=5 is required.'
reported=$(jq -er '.host.remoteSocket.path | select(type == "string" and length > 0)' <<<"$info") || fail 'selected engine socket missing/malformed.'
reported="${reported#unix://}"
[[ "$reported" == "$socket" ]] || fail 'DOTFILES_PODMAN_ENGINE_SOCKET does not exactly match the selected engine socket.'
# Do not test -S here: on macOS/Windows this path exists in the selected VM,
# not the launcher filesystem. No connection switching or machine startup.
