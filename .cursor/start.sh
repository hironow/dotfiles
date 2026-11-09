#!/usr/bin/env bash
# Explicit Cursor per-boot entrypoint, never a shell-startup hook.
# Start only this user's native Linux Podman API socket; no VM lifecycle.
set -euo pipefail
export PODMAN_COMPOSE_PROVIDER=podman-compose
if [ "$(id -u)" -eq 0 ]; then
  echo '[start] rootless Podman requires a non-root Cursor user' >&2
  exit 1
fi
if [ -z "${CONTAINER_HOST:-}" ]; then
  : "${XDG_RUNTIME_DIR:?Cursor must supply the user-owned XDG_RUNTIME_DIR}"
  socket="$(podman info --format '{{.Host.RemoteSocket.Path}}')"
  socket="${socket#unix://}"
  case "$socket" in
    "${XDG_RUNTIME_DIR}/podman/podman.sock") ;;
    *) echo "[start] refusing unexpected user socket: $socket" >&2; exit 1 ;;
  esac
  if ! systemctl --user start podman.socket; then
    # Container-based Cursor environments need no systemd or root daemon.
    # The selected native socket remains private to this user (umask 077).
    if [ ! -S "$socket" ]; then
      mkdir -p "${XDG_RUNTIME_DIR}/podman"
      (umask 077; nohup podman system service --time=0 "unix://$socket" \
        > "${XDG_RUNTIME_DIR}/podman/service.log" 2>&1 < /dev/null &)
    fi
  fi
  export CONTAINER_HOST="unix://$socket"
fi
# Client and selected server are separate requirements. No Docker fallback.
for _ in $(seq 1 30); do
  if versions="$(podman version --format '{{.Client.Version}} {{.Server.Version}}' 2>/dev/null)"; then
    read -r client server <<< "$versions"
    if [[ "$client" =~ ^([0-9]+)\. && "${BASH_REMATCH[1]}" -ge 5 ]] &&
       [[ "$server" =~ ^([0-9]+)\. && "${BASH_REMATCH[1]}" -ge 5 ]]; then
      echo '[start] rootless Podman client and selected server >=5 ready'
      exit 0
    fi
    echo "[start] Podman >=5 client AND server required: $versions" >&2
    exit 1
  fi
  sleep 1
done
echo '[start] selected Podman socket unavailable; container gates cannot run' >&2
exit 1
