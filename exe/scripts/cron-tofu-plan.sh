#!/usr/bin/env bash
# cron-tofu-plan.sh — runs INSIDE an ephemeral Coder workspace
# spawned by the Coder VM's nightly systemd timer (ADR 0008 step 4).
#
# Responsibility chain:
#   1. coder-cron-tofu-plan.timer fires on the Coder VM
#   2. coder-cron-tofu-plan.service ExecStart calls
#      coder-cron-spawn-job, which:
#       - generates a unique workspace name
#       - calls coder-cron-run create <name> --template
#         exe-dotfiles-job --parameter "job_command=<this script>"
#       - polls until the agent's startup_script (which IS this
#         script) finishes, then deletes the workspace
#   3. The workspace's agent runs THIS script. The script:
#       - clones the dotfiles repo (workspace VMs do not bake it)
#       - fetches the TF_ENCRYPTION passphrase from Secret Manager
#       - runs `tofu init && tofu plan -refresh=false -out=plan.bin`
#       - ships plan.bin (binary) + plan.txt (human-readable) to
#         gs://<project>-tofu-state/jobs/<date>/
#       - prints a final summary to stdout (captured into journald
#         on the Coder VM via cdr logs)
#
# Failure mode: each step is best-effort wrapped — diagnostic output
# is shipped to GCS even when tofu plan fails (which is informative
# for the operator on first runs while CF/TS API token grants are
# still pending). The script ALWAYS exits 0 unless prerequisites are
# missing; per-step failures are captured in the artifact.

set -uo pipefail

PROJECT="${EXE_PROJECT_ID:-gen-ai-hironow}"
PASSPHRASE_SECRET="${EXE_TOFU_PASSPHRASE_SECRET:-exe-tofu-encryption-passphrase}"
STATE_BUCKET="${EXE_STATE_BUCKET:-${PROJECT}-tofu-state}"
DOTFILES_REPO="${EXE_DOTFILES_REPO:-https://github.com/hironow/dotfiles.git}"
DOTFILES_REF="${EXE_DOTFILES_REF:-main}"
WORKDIR="${EXE_WORKDIR:-/root/cron-tofu-plan}"

# UTC date stamps for artifact naming.
DATE_STAMP="$(date -u +%Y-%m-%d)"
TIME_STAMP="$(date -u +%H%M%SZ)"
ARTIFACT_PREFIX="gs://${STATE_BUCKET}/jobs/${DATE_STAMP}/tofu-plan-${TIME_STAMP}"

log() { printf '[cron-tofu-plan] %s\n' "$*"; }
err() { printf '[cron-tofu-plan] ERROR: %s\n' "$*" >&2; }

log "starting; artifact prefix=${ARTIFACT_PREFIX}"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    err "missing required tool: $1"
    exit 70
  }
}
require git
require gcloud
require tofu

# 1. Clone or refresh the dotfiles repo.
mkdir -p "$(dirname "$WORKDIR")"
if [ -d "${WORKDIR}/.git" ]; then
  log "refreshing existing clone at ${WORKDIR}"
  git -C "$WORKDIR" fetch --depth 1 origin "$DOTFILES_REF" || \
    err "git fetch failed; continuing with existing checkout"
  git -C "$WORKDIR" checkout -q "origin/${DOTFILES_REF}" || true
else
  log "cloning ${DOTFILES_REPO}@${DOTFILES_REF} to ${WORKDIR}"
  if ! git clone --depth 1 --branch "$DOTFILES_REF" "$DOTFILES_REPO" "$WORKDIR"; then
    err "git clone failed"
    exit 71
  fi
fi

# 2. Fetch TF_ENCRYPTION passphrase from Secret Manager.
log "fetching TF_ENCRYPTION passphrase from secret '${PASSPHRASE_SECRET}'"
if ! PASSPHRASE="$(gcloud --quiet --project="$PROJECT" \
      secrets versions access latest \
      --secret="$PASSPHRASE_SECRET" 2>/dev/null)"; then
  err "failed to fetch passphrase from Secret Manager."
  err "Operator action: see exe/docs/runbook.md section 'TF_ENCRYPTION passphrase for cron'."
  exit 72
fi

# Build the HCL TF_ENCRYPTION payload (mirrors justfile:_exe-encryption).
TF_ENCRYPTION="$(cat <<HCL
key_provider "pbkdf2" "default" {
  passphrase = "${PASSPHRASE}"
}
method "aes_gcm" "default" {
  keys = key_provider.pbkdf2.default
}
state {
  method   = method.aes_gcm.default
  enforced = true
}
plan {
  method   = method.aes_gcm.default
  enforced = true
}
HCL
)"
export TF_ENCRYPTION
unset PASSPHRASE

# 3. tofu init + plan. The whole block is captured to a log file
#    that ships to GCS regardless of exit code.
RUN_DIR="$(mktemp -d)"
PLAN_BIN="${RUN_DIR}/plan.bin"
PLAN_TXT="${RUN_DIR}/plan.txt"
RUN_LOG="${RUN_DIR}/run.log"

cd "${WORKDIR}/tofu/exe" || { err "cd ${WORKDIR}/tofu/exe failed"; exit 73; }

log "running tofu init"
{
  echo "=== tofu init ==="
  tofu init -input=false -upgrade=false 2>&1
  init_rc=$?
  echo "tofu init rc=${init_rc}"

  echo "=== tofu plan -refresh=false ==="
  # -refresh=false avoids reaching the CF / Tailscale APIs (whose
  # tokens are not yet provisioned to this workspace SA). Once
  # those grants land, drop -refresh=false for a true plan.
  tofu plan -input=false -refresh=false -out="${PLAN_BIN}" 2>&1
  plan_rc=$?
  echo "tofu plan rc=${plan_rc}"

  if [ "${plan_rc}" -eq 0 ] && [ -f "${PLAN_BIN}" ]; then
    echo "=== tofu show ==="
    tofu show "${PLAN_BIN}" > "${PLAN_TXT}" 2>&1
    echo "(human-readable plan written to ${PLAN_TXT})"
  fi
} > "${RUN_LOG}" 2>&1
final_rc=$?

log "tofu run finished (final rc=${final_rc}); shipping artifacts"

# 4. Ship artifacts to GCS. Each upload is independent so a partial
#    set still surfaces useful debugging.
gcloud --quiet storage cp "${RUN_LOG}" "${ARTIFACT_PREFIX}.log" || \
  err "failed to upload run.log"
if [ -f "${PLAN_BIN}" ]; then
  gcloud --quiet storage cp "${PLAN_BIN}" "${ARTIFACT_PREFIX}.bin" || \
    err "failed to upload plan.bin"
fi
if [ -f "${PLAN_TXT}" ]; then
  gcloud --quiet storage cp "${PLAN_TXT}" "${ARTIFACT_PREFIX}.txt" || \
    err "failed to upload plan.txt"
fi

log "done; artifacts at ${ARTIFACT_PREFIX}.{log,bin,txt}"
log "inspect: gcloud storage ls ${ARTIFACT_PREFIX}.*"
exit 0
