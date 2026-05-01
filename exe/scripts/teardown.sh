#!/usr/bin/env bash
# teardown.sh — staged destroy for the exe.hironow.dev stack.
#
# Three stages, selected via the first argument:
#   vm     (default) — destroy only the VM. Cheapest "go to sleep" path.
#                      Tunnel + DNS + Access + Tailscale keys survive.
#   stack            — destroy every tofu-managed resource (full apply
#                      again to bring it back). State + passphrase remain.
#   nuke             — stack + delete the GCS state bucket and the
#                      passphrase file. Last resort; bootstrap.sh will
#                      recreate them.
#
# Idempotent: re-running on an already-empty stack is a no-op with a
# clear message.
#
# Required env: same preconditions as `just exe-plan`.

set -euo pipefail

STAGE="${1:-vm}"
STACK_DIR="${STACK_DIR:-tofu/exe}"
PASSPHRASE_FILE="${HOME}/.config/tofu/exe.passphrase"

green() { printf '\033[32m✓\033[0m %s\n' "$*"; }
red()   { printf '\033[31m✗\033[0m %s\n' "$*" >&2; }
log()   { printf '\033[36m[teardown:%s]\033[0m %s\n' "${STAGE}" "$*"; }

require() {
  command -v "$1" >/dev/null 2>&1 || { red "missing required tool: $1"; exit 1; }
}

require tofu

[[ -f "${PASSPHRASE_FILE}" ]] || { red "missing ${PASSPHRASE_FILE}"; exit 1; }
# State encryption is currently disabled; see tofu/exe/main.tf.

case "${STAGE}" in
  vm)
    log "destroying only the workspace VM (-target=google_compute_instance.exe_coder)"
    cd "${STACK_DIR}"
    tofu destroy -auto-approve \
      -target=google_compute_instance.exe_coder
    cd - >/dev/null
    green "VM destroyed. Tunnel, DNS, Access, and Tailscale keys retained."
    ;;

  stack)
    log "destroying the entire stack"
    cd "${STACK_DIR}"
    tofu destroy
    cd - >/dev/null
    green "Stack destroyed. State bucket and passphrase still on disk."
    ;;

  nuke)
    log "WARNING: this will delete the GCS state bucket and the passphrase file."
    read -r -p "Type 'NUKE' to confirm: " confirm
    [[ "${confirm}" == "NUKE" ]] || { red "aborted"; exit 1; }

    require gcloud

    cd "${STACK_DIR}"
    tofu destroy
    cd - >/dev/null

    project="$(gcloud config get-value project 2>/dev/null)"
    bucket="${project}-tofu-state"
    if gcloud storage buckets describe "gs://${bucket}" >/dev/null 2>&1; then
      log "deleting state bucket gs://${bucket}"
      gcloud storage rm -r "gs://${bucket}"
    fi
    if [[ -f "${PASSPHRASE_FILE}" ]]; then
      log "removing ${PASSPHRASE_FILE}"
      rm -f "${PASSPHRASE_FILE}"
    fi
    green "Nuked. Run 'just exe-bootstrap' to start over."
    ;;

  *)
    red "unknown stage: ${STAGE}"
    cat <<EOF >&2
Usage: $0 [vm|stack|nuke]
  vm     destroy VM only (default)
  stack  destroy every tofu-managed resource
  nuke   stack + delete state bucket + passphrase
EOF
    exit 2
    ;;
esac
