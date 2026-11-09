#!/usr/bin/env bash
# Thin glue for these two ephemeral CI jobs, not a host installer.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted || "$(uname -s)" != Linux || "$(id -u)" -eq 0 ]]; then
  echo 'ci-bootstrap requires an ephemeral non-root GitHub Actions Linux runner' >&2
  exit 1
fi
: "${RUNNER_TEMP:?}" "${GITHUB_ENV:?}" "${GITHUB_PATH:?}"
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bash "$repo/install.sh" --podman-only
# Service/runtime dependencies only, from this Ubuntu release's native packages.
sudo -n apt-get update -y
sudo -n apt-get install -y --no-install-recommends uidmap slirp4netns fuse-overlayfs curl ca-certificates
# Ubuntu 26.04's AppArmor profile for pasta refuses podman's SIGTERM, so
# rootless Podman cannot tear down its network namespace. The guard probes
# that, and adds the one rule GitHub's image fix adds only when the probe
# fails with exactly that denial (see the script).
bash "$repo/.devcontainer/allow-podman-stop-pasta.sh" /etc/apparmor.d/usr.bin.pasta

bootstrap="$RUNNER_TEMP/dotfiles-podman-bootstrap"
mkdir -p "$bootstrap/bin"
# Both the bootstrap pin and mise declarations have existing canonical sources.
python3 - "$repo" "$bootstrap" <<'PY'
import pathlib
import re
import sys
import tomllib
repo, target = map(pathlib.Path, sys.argv[1:])
source = tomllib.loads((repo / 'config/mise/image-tools.toml').read_text(encoding='utf-8'))
(target / 'mise-version').write_text(source['bootstrap']['mise'], encoding='utf-8')
feature = (repo / '.devcontainer/features/dotfiles-tools/install.sh').read_text(encoding='utf-8')
body = feature.split("cat > /etc/mise/config.toml <<'EOF'\n", 1)[1].split('\nEOF\n', 1)[0]
canonical = tomllib.loads(body)
required = {'bun', 'node', 'uv', 'just', 'npm:@devcontainers/cli', 'pypi:podman-compose'}
missing = required - canonical['tools'].keys()
if missing:
    raise SystemExit(f'canonical generated mise tools missing: {sorted(missing)}')
# Keep source declarations byte-for-byte, including tool-scoped resolver options.
lines = []
for line in body.split('[tools]\n', 1)[1].splitlines():
    match = re.match(r'("[^"]+"|[^ =]+)\s*=', line)
    if match and match[1].strip('"') in required:
        lines.append(line)
config = body.split('[tools]\n', 1)[0] + '[tools]\n' + '\n'.join(lines) + '\n'
assert set(tomllib.loads(config)['tools']) == required
(target / 'config.toml').write_text(config, encoding='utf-8')
PY
version="$(< "$bootstrap/mise-version")"
case "$(uname -m)" in
  x86_64) arch=linux-x64-musl ;;
  aarch64|arm64) arch=linux-arm64-musl ;;
  *) echo 'unsupported mise bootstrap architecture' >&2; exit 1 ;;
esac
artifact="mise-v${version}-${arch}.tar.gz"
release="https://github.com/jdx/mise/releases/download/v${version}"
api="https://api.github.com/repos/jdx/mise/releases"
# github.com's /releases/download/ returned 504 for 1.5 h on 2026-11-09 while
# the API asset path stayed up. Each fetch retries before it falls back.
fetch() {
  curl --proto '=https' --tlsv1.2 -fsSL --retry 3 --retry-all-errors --max-time 120 "$@"
}
# The token goes only to the API, and through stdin, not the command line.
fetch_github_api() {
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    printf 'Authorization: Bearer %s\n' "$GITHUB_TOKEN" | fetch -H @- "$@"
  else
    fetch "$@"
  fi
}
# SHASUMS256.txt as the release's API asset, found by name in the release JSON.
fetch_mise_checksums_from_api() {
  local id
  fetch_github_api -H 'Accept: application/vnd.github+json' -o "$bootstrap/mise-release.json" "$api/tags/v${version}" || return 1
  id="$(python3 -I -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); m=[a["id"] for a in r["assets"] if a["name"]=="SHASUMS256.txt"]; assert len(m)==1 and type(m[0]) is int; print(m[0])' "$bootstrap/mise-release.json")" || return 1
  fetch_github_api -H 'Accept: application/octet-stream' -o "$bootstrap/SHASUMS256.txt" "$api/assets/$id"
}
# The pinned artifact from mise's own host, as its official installer does;
# GitHub's release download if that fails. The host is only a route: the
# bytes must match GitHub's SHASUMS256.txt, which never comes from
# mise.jdx.dev (mise's docs: "Checksums never come from mise.jdx.dev").
if ! fetch -o "$bootstrap/$artifact" "https://mise.jdx.dev/v${version}/${artifact}"; then
  echo "ci-bootstrap: mise.jdx.dev failed; downloading $artifact from GitHub" >&2
  fetch -o "$bootstrap/$artifact" "$release/$artifact"
fi
if ! fetch_mise_checksums_from_api; then
  echo 'ci-bootstrap: the GitHub API failed; downloading SHASUMS256.txt from the release' >&2
  fetch -o "$bootstrap/SHASUMS256.txt" "$release/SHASUMS256.txt"
fi
# Same SHA256 verification as install.sh bootstrap: one exact line, then check.
(cd "$bootstrap"; grep -E "[ *](\\./)?${artifact//./\\.}$" SHASUMS256.txt > selected.sha256; test "$(wc -l < selected.sha256)" -eq 1; sha256sum -c selected.sha256)
tar -xzf "$bootstrap/$artifact" -C "$bootstrap"
install -m 0755 "$bootstrap/mise/bin/mise" "$bootstrap/bin/mise"
export PATH="$bootstrap/bin:$PATH"
export MISE_GLOBAL_CONFIG_FILE="$bootstrap/config.toml"
export MISE_DATA_DIR="$bootstrap/data"
export MISE_TRUSTED_CONFIG_PATHS="$bootstrap/config.toml"
cd "$bootstrap"
# Put each tool's directories on PATH, for this script and (GITHUB_PATH) for
# the later steps: the ones mise itself uses (`mise bin-paths`). An
# executable is not always in <install>/bin; uv's archive keeps it in a
# nested directory. No directory, or one that does not exist, stops here.
publish_bin_paths() {
  local tool="$1" paths dir
  if ! paths="$(mise bin-paths "$tool")"; then
    echo "ci-bootstrap: mise bin-paths $tool failed" >&2
    exit 1
  fi
  if [[ -z "$paths" ]]; then
    echo "ci-bootstrap: mise bin-paths $tool printed nothing" >&2
    exit 1
  fi
  while IFS= read -r dir; do
    if [[ ! -d "$dir" ]]; then
      echo "ci-bootstrap: $tool's bin path $dir is not a directory" >&2
      exit 1
    fi
    export PATH="$dir:$PATH"
    printf '%s\n' "$dir" >> "$GITHUB_PATH"
  done <<< "$paths"
}
# uv's release assets from Astral's own mirror (docs.astral.sh/uv/reference/
# environment/, UV_ASTRAL_MIRROR_URL), byte-identical to GitHub's. Only the
# download moves: mise still takes the asset's sha256 from GitHub's release
# metadata and rejects other bytes, and checks GitHub's attestation. One
# tool, anchored, so nothing else is rerouted. A replacement has no
# fallback; not written to GITHUB_ENV, as later steps install nothing.
export MISE_URL_REPLACEMENTS='{"regex:^https://github\\.com/astral-sh/uv/releases/download/":"https://releases.astral.sh/github/uv/releases/download/"}'
mise install bun uv node just
for tool in bun uv node just; do
  publish_bin_paths "$tool"
done
# uv is now available to the pypi backend; bun/node precede npm tools.
mise install npm:@devcontainers/cli pypi:podman-compose
for tool in npm:@devcontainers/cli pypi:podman-compose; do
  publish_bin_paths "$tool"
done
printf '%s\n' "$bootstrap/bin" >> "$GITHUB_PATH"
{
  printf 'MISE_GLOBAL_CONFIG_FILE=%s\nMISE_DATA_DIR=%s\nMISE_TRUSTED_CONFIG_PATHS=%s\n' "$MISE_GLOBAL_CONFIG_FILE" "$MISE_DATA_DIR" "$MISE_TRUSTED_CONFIG_PATHS"
  echo 'PODMAN_COMPOSE_PROVIDER=podman-compose'
} >> "$GITHUB_ENV"
# Only this explicit ephemeral CI bootstrap starts the user's API service.
systemctl --user start podman.socket
socket="$(podman info --format json | python3 -c 'import json,sys; i=json.load(sys.stdin); assert i["host"]["security"]["rootless"] is True, "CI must use rootless Podman"; p=i["host"]["remoteSocket"]["path"]; print(p.removeprefix("unix://"))')"
DOTFILES_PODMAN_ENGINE_SOCKET="$socket" bash "$repo/.devcontainer/require-podman-socket.sh"
printf 'DOTFILES_PODMAN_ENGINE_SOCKET=%s\n' "$socket" >> "$GITHUB_ENV"
# Required engine/SDK jobs must work with NO Docker executable on PATH.
# Renaming is confined to the throwaway GitHub-hosted runner, never operator hosts.
if command -v docker >/dev/null 2>&1; then
  docker_binary="$(command -v docker)"
  sudo -n mv "$docker_binary" "${docker_binary}.disabled-for-podman-ci"
fi
if command -v docker >/dev/null 2>&1; then
  echo 'Docker remains on PATH; refusing to claim Podman-only acceptance' >&2
  exit 1
fi
