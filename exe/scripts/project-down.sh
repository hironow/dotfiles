#!/usr/bin/env bash
# project-down.sh — workspace VM 上で project lifecycle 「down」 phase を実行する。
#
# Usage:
#   project-down.sh <id> [--hard]
#
# Example:
#   project-down.sh foo            # soft archive (= ~/projects/.archive/foo-<ts>/ に move)
#   project-down.sh foo --hard     # hard delete (= ディレクトリ rm -rf)
#
# What this does (refs/docs/issues/0020-multi 軸 2 受入基準):
#   1. validate <id> against runops-gateway domain spec.
#   2. (0009 完成時) phonewave@<id>.service systemctl disable。 現状 0009 defer
#      状態なので no-op。
#   3. fetch-projects-env.sh を再実行 (= gateway registry から project list を再取得、
#      <id> が registry から削除されていれば dmail systemd drop-in env から外れる)。
#   4. project ディレクトリを archive (default = soft、 `--hard` 指定で 削除):
#      - soft: ~/projects/<id>/ → ~/projects/.archive/<id>-<timestamp>/ に move
#              (再起動可能、 復旧は単純 mv)
#      - hard: rm -rf ~/projects/<id>/ (= 不可逆)
#
# Idempotency: 同じ <id> で複数回実行しても破壊的副作用なし (= ディレクトリ既不在なら skip)。
# Default は soft archive (= 復旧可能を優先)、 hard delete は明示的 opt-in のみ。
# Fail mode: 各 step で error は明示的 fail-loud + stderr。
#
# 関連:
#   - dotfiles ADR 0011 (multi-project systemd env delivery)
#   - refs issue 0020-multi (project lifecycle completion) 軸 2

set -euo pipefail

err() { printf '\033[31m[project-down]\033[0m %s\n' "$*" >&2; exit 1; }
log() { printf '\033[36m[project-down]\033[0m %s\n' "$*" >&2; }

# ---- arg parsing ------------------------------------------------------

if [[ $# -lt 1 ]]; then
  err "usage: project-down.sh <id> [--hard]"
fi

PROJECT_ID="$1"
shift
HARD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hard) HARD=1 ;;
    *) err "unexpected arg: $1" ;;
  esac
  shift
done

PROJECT_ID_RE='^[a-zA-Z0-9_-]+$'
PROJECT_ID_MAX_LEN=64

if (( ${#PROJECT_ID} > PROJECT_ID_MAX_LEN )); then
  err "project id exceeds ${PROJECT_ID_MAX_LEN} chars"
fi
if ! [[ "$PROJECT_ID" =~ ${PROJECT_ID_RE} ]]; then
  err "project id failed regex"
fi

WORKSPACE_HOME="${WORKSPACE_HOME:-${HOME}}"
PROJECT_DIR="${WORKSPACE_HOME}/projects/${PROJECT_ID}"
ARCHIVE_ROOT="${WORKSPACE_HOME}/projects/.archive"

# ---- step 1: phonewave per-project systemd disable (0009 完成時に有効化) -

# 0009 defer 状態 = phonewave@.service なし、 現状 no-op。
log "step 1: phonewave per-project systemd disable は 0009 defer 状態、 no-op"

# ---- step 2: fetch-projects-env.sh 再実行 -----------------------------

# Note: gateway registry 側で project が archived/deleted されていれば、
# fetch-projects-env.sh の curl 結果から外れて dmail env が再構成される。
# この script は workspace VM 側 cleanup で、 gateway registry update は
# cdr-project wrapper が呼出責任を持つ。

FETCH_SCRIPT="${FETCH_PROJECTS_ENV:-/usr/local/bin/fetch-projects-env.sh}"
if [[ ! -x "${FETCH_SCRIPT}" ]]; then
  log "step 2: ${FETCH_SCRIPT} not executable, skip env reload"
else
  log "step 2: fetch-projects-env.sh で dmail systemd drop-in env reload"
  if ! "${FETCH_SCRIPT}" 2>&1 | sed 's/^/  fetch-projects-env: /' >&2; then
    err "fetch-projects-env.sh failed"
  fi
fi

# ---- step 3: project ディレクトリ archive (or hard delete) -------------

if [[ ! -d "${PROJECT_DIR}" ]]; then
  log "step 3: ${PROJECT_DIR} 既不在 (idempotent: 既に down 済)、 skip"
elif [[ "${HARD}" == "1" ]]; then
  log "step 3: --hard 指定、 ${PROJECT_DIR} を rm -rf"
  if ! rm -rf "${PROJECT_DIR}"; then
    err "rm -rf failed; check perms / mounted"
  fi
else
  TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
  ARCHIVE_DIR="${ARCHIVE_ROOT}/${PROJECT_ID}-${TIMESTAMP}"
  mkdir -p "${ARCHIVE_ROOT}"
  log "step 3: soft archive: ${PROJECT_DIR} -> ${ARCHIVE_DIR}"
  if ! mv "${PROJECT_DIR}" "${ARCHIVE_DIR}"; then
    err "mv failed; check perms / cross-fs / mounted"
  fi
fi

log "project-down complete: ${PROJECT_ID} (mode: $([[ ${HARD} == 1 ]] && echo hard || echo soft))"
