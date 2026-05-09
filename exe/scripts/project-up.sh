#!/usr/bin/env bash
# project-up.sh — workspace VM 上で project lifecycle 「up」 phase を実行する。
#
# Usage:
#   project-up.sh <id> [--org=<org>] [--repo=<repo>]
#
# Example:
#   project-up.sh foo
#   project-up.sh foo --org=acme --repo=widget
#
# What this does (refs/docs/issues/0020-multi 軸 2 受入基準):
#   1. validate <id> against runops-gateway domain spec (= [a-zA-Z0-9_-]+, max 64).
#   2. mkdir ~/projects/<id>/ + ~/projects/<id>/.phonewave/{outbox,archive}
#      (idempotent: 既存なら skip、 perms 0777 = fetch-projects-env.sh と同方針).
#   3. (optional) git clone github.com/<org>/<repo> ~/projects/<id>/ (= --org / --repo
#      指定時のみ、 既に clone 済なら skip)。
#   4. fetch-projects-env.sh を再実行 (= gateway registry から project list 取得、
#      dmail-receiver/emitter systemd drop-in env を更新 + daemon-reload + try-restart)。
#      これにより新 project が dmail 配送対象に追加される。
#   5. (0009 完成時) phonewave@<id>.service systemctl enable。 現状 0009 は defer 状態
#      なので暫定的に単一 phonewave + PHONEWAVE_OUTBOX_DIRS_BY_PROJECT で互換動作。
#
# Idempotency: 同じ <id> で複数回実行しても破壊的副作用なし。
# Fail mode: 各 step で error は明示的 fail-loud + stderr (silent escalation 防止)。
#
# 関連:
#   - dotfiles ADR 0011 (multi-project systemd env delivery)
#   - dotfiles ADR 0012 (RUNOPS_ACTOR_TYPE env injection)
#   - refs issue 0020-multi (project lifecycle completion) 軸 2

set -euo pipefail

err() { printf '\033[31m[project-up]\033[0m %s\n' "$*" >&2; exit 1; }
log() { printf '\033[36m[project-up]\033[0m %s\n' "$*" >&2; }

# ---- arg parsing ------------------------------------------------------

if [[ $# -lt 1 ]]; then
  err "usage: project-up.sh <id> [--org=<org>] [--repo=<repo>]"
fi

PROJECT_ID="$1"
shift
ORG=""
REPO=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --org=*) ORG="${1#--org=}" ;;
    --repo=*) REPO="${1#--repo=}" ;;
    *) err "unexpected arg: $1" ;;
  esac
  shift
done

# project_id spec — mirror runops-gateway internal/core/domain/project.go and
# fetch-projects-env.sh PROJECT_ID_RE.
PROJECT_ID_RE='^[a-zA-Z0-9_-]+$'
PROJECT_ID_MAX_LEN=64

if (( ${#PROJECT_ID} > PROJECT_ID_MAX_LEN )); then
  err "project id exceeds ${PROJECT_ID_MAX_LEN} chars (got ${#PROJECT_ID})"
fi
if ! [[ "$PROJECT_ID" =~ ${PROJECT_ID_RE} ]]; then
  err "project id failed regex (must match ${PROJECT_ID_RE})"
fi

# org / repo 指定時の format check (= 緩い validation: ascii / hyphen / dot のみ)。
if [[ -n "$ORG" ]] && ! [[ "$ORG" =~ ^[a-zA-Z0-9_.-]+$ ]]; then
  err "--org failed regex"
fi
if [[ -n "$REPO" ]] && ! [[ "$REPO" =~ ^[a-zA-Z0-9_.-]+$ ]]; then
  err "--repo failed regex"
fi
# org / repo は両方 set または両方 unset。
if [[ -n "$ORG" && -z "$REPO" ]] || [[ -z "$ORG" && -n "$REPO" ]]; then
  err "--org and --repo must be specified together"
fi

# ---- step 1: project directory + .phonewave 作成 ----------------------

WORKSPACE_HOME="${WORKSPACE_HOME:-${HOME}}"
PROJECT_DIR="${WORKSPACE_HOME}/projects/${PROJECT_ID}"

log "step 1: create ${PROJECT_DIR}"
mkdir -p "${PROJECT_DIR}/.phonewave/outbox" "${PROJECT_DIR}/.phonewave/archive"
chmod 0777 "${PROJECT_DIR}/.phonewave/outbox" "${PROJECT_DIR}/.phonewave/archive"

# ---- step 2: git clone (optional) -------------------------------------

if [[ -n "$ORG" && -n "$REPO" ]]; then
  CLONE_URL="https://github.com/${ORG}/${REPO}.git"
  if [[ -d "${PROJECT_DIR}/.git" ]]; then
    log "step 2: git repo already exists at ${PROJECT_DIR}, skip clone"
  else
    log "step 2: git clone ${CLONE_URL} -> ${PROJECT_DIR}"
    # clone を project ディレクトリ内に展開。 既に .phonewave/ がある場合は preserve。
    if ! git clone "${CLONE_URL}" "${PROJECT_DIR}.tmp" 2>&1 | sed 's/^/  git: /' >&2; then
      err "git clone failed; ${CLONE_URL} unreachable or auth failure"
    fi
    # tmp 内容を project_dir に move (= .phonewave 保護)。
    rsync -a "${PROJECT_DIR}.tmp/" "${PROJECT_DIR}/" 2>/dev/null || \
      cp -R "${PROJECT_DIR}.tmp/." "${PROJECT_DIR}/"
    rm -rf "${PROJECT_DIR}.tmp"
  fi
else
  log "step 2: --org/--repo unset, skip git clone"
fi

# ---- step 3: fetch-projects-env.sh 再実行 (= dmail 系 env reload) ------

FETCH_SCRIPT="${FETCH_PROJECTS_ENV:-/usr/local/bin/fetch-projects-env.sh}"
if [[ ! -x "${FETCH_SCRIPT}" ]]; then
  log "step 3: ${FETCH_SCRIPT} not executable, skip env reload (= legacy single-mode fallback で動作維持)"
else
  log "step 3: fetch-projects-env.sh で dmail systemd drop-in env reload"
  if ! "${FETCH_SCRIPT}" 2>&1 | sed 's/^/  fetch-projects-env: /' >&2; then
    err "fetch-projects-env.sh failed; check gateway URL / admin token / connectivity"
  fi
fi

# ---- step 4: phonewave per-project systemd (0009 完成時に有効化) ------

# 0009 (phonewave per-project systemd) が defer 状態 = phonewave@.service が
# 存在しないため現状 no-op。 暫定的に単一 phonewave + PHONEWAVE_OUTBOX_DIRS_BY_PROJECT
# で動作 (Phase α で確認済)。 0009 着地後にこの block を有効化。
#
# if systemctl list-unit-files phonewave@.service >/dev/null 2>&1; then
#   log "step 4: enable phonewave@${PROJECT_ID}.service"
#   sudo systemctl enable --now "phonewave@${PROJECT_ID}.service"
# fi
log "step 4: phonewave per-project systemd は 0009 defer 状態、 暫定単一 daemon で互換動作"

log "project-up complete: ${PROJECT_ID}"
log "  dir: ${PROJECT_DIR}"
log "  outbox: ${PROJECT_DIR}/.phonewave/outbox"
log "  archive: ${PROJECT_DIR}/.phonewave/archive"
