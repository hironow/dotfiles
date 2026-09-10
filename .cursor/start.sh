#!/usr/bin/env bash
# Cursor Cloud Agent per-boot startup for hironow/dotfiles.
#
# Brings up the Docker daemon (fuse-overlayfs) so the Docker-backed gates work:
# `just test` (devcontainer sandbox), `just test-install`, and the emulator /
# telemetry compose stacks. Idempotent and best-effort: the primary dev loop
# (`just ci` / `just fmt` / `just lint`) needs no Docker, so a Docker hiccup
# must not block the environment from starting.
set -uo pipefail

if sudo docker info >/dev/null 2>&1; then
  echo "[start] docker already running"
else
  echo "[start] starting dockerd (fuse-overlayfs)"
  sudo bash -c 'nohup dockerd >/var/log/dockerd.log 2>&1 &'
  for _ in $(seq 1 30); do
    if sudo docker info >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi

# Let the non-root agent user reach the daemon socket without sudo.
sudo chmod 666 /var/run/docker.sock 2>/dev/null || true

if sudo docker info >/dev/null 2>&1; then
  echo "[start] docker ready"
else
  echo "[start] WARN: docker did not start; 'just ci' still works, but 'just test'/emulators will not" >&2
  tail -n 20 /var/log/dockerd.log 2>/dev/null || true
fi

exit 0
