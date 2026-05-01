#!/usr/bin/env bash
# bootstrap.sh — one-time provisioning that must happen BEFORE `tofu init`.
#
# What it does (idempotent — safe to re-run):
#   1. Verify gcloud auth + active project.
#   2. Enable required Google APIs.
#   3. Create the GCS bucket holding tofu state (versioned, uniform IAM).
#   4. Create the local tofu encryption passphrase if missing.
#   5. Print the next-step command.
#
# Required env: none.
# Required tools: gcloud, openssl.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-gen-ai-hironow}"
REGION="${REGION:-asia-northeast1}"
STATE_BUCKET="${PROJECT_ID}-tofu-state"
PASSPHRASE_FILE="${HOME}/.config/tofu/exe.passphrase"

REQUIRED_APIS=(
  compute.googleapis.com
  iam.googleapis.com
  iamcredentials.googleapis.com
  secretmanager.googleapis.com
  storage.googleapis.com
)

log() { printf '\033[36m[bootstrap]\033[0m %s\n' "$*"; }
err() { printf '\033[31m[bootstrap]\033[0m %s\n' "$*" >&2; exit 1; }

require() {
  command -v "$1" >/dev/null 2>&1 || err "missing required tool: $1"
}

require gcloud
require openssl

log "active project: ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}" >/dev/null

active_account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' || true)"
if [[ -z "${active_account}" ]]; then
  err "no active gcloud account; run 'gcloud auth login' and 'gcloud auth application-default login'"
fi
log "active account: ${active_account}"

log "enabling required APIs (idempotent)..."
gcloud services enable "${REQUIRED_APIS[@]}" --project="${PROJECT_ID}"

if gcloud storage buckets describe "gs://${STATE_BUCKET}" >/dev/null 2>&1; then
  log "state bucket already exists: gs://${STATE_BUCKET}"
else
  log "creating state bucket: gs://${STATE_BUCKET}"
  gcloud storage buckets create "gs://${STATE_BUCKET}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --uniform-bucket-level-access \
    --public-access-prevention
  gcloud storage buckets update "gs://${STATE_BUCKET}" --versioning
fi

if [[ ! -f "${PASSPHRASE_FILE}" ]]; then
  log "generating tofu state encryption passphrase: ${PASSPHRASE_FILE}"
  mkdir -p "$(dirname "${PASSPHRASE_FILE}")"
  openssl rand -base64 48 > "${PASSPHRASE_FILE}"
  chmod 0600 "${PASSPHRASE_FILE}"
else
  log "tofu encryption passphrase already exists: ${PASSPHRASE_FILE}"
fi

printf '\n\033[32m[bootstrap] done.\033[0m\n\n'
cat <<EOF
Next steps:
  cp tofu/exe/terraform.tfvars.example tofu/exe/terraform.tfvars
  \$EDITOR tofu/exe/terraform.tfvars            # cf_account_id, tailnet
  just exe-init
  just exe-plan                                 # needs CLOUDFLARE_API_TOKEN + TAILSCALE_API_KEY
EOF
