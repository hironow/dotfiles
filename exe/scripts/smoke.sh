#!/usr/bin/env bash
# smoke.sh — post-deploy smoke checks for the exe.hironow.dev stack.
#
# All checks are read-only and idempotent. Run after `just exe-apply`
# (or anytime) to verify the stack is healthy.
#
# Required tools: tofu, gcloud, dig, curl. tailscale optional (skipped
# if not installed).
# Required env: same preconditions as `just exe-plan`.

set -euo pipefail

STACK_DIR="${STACK_DIR:-tofu/exe}"
PASSPHRASE_FILE="${HOME}/.config/tofu/exe.passphrase"

green()  { printf '\033[32m✓\033[0m %s\n' "$*"; }
yellow() { printf '\033[33m~\033[0m %s\n' "$*"; }
red()    { printf '\033[31m✗\033[0m %s\n' "$*" >&2; }

require() {
  command -v "$1" >/dev/null 2>&1 || { red "missing required tool: $1"; exit 1; }
}

require tofu
require gcloud
require dig
require curl
require jq

[[ -f "${PASSPHRASE_FILE}" ]] || { red "missing ${PASSPHRASE_FILE}; run 'just exe-bootstrap' first"; exit 1; }
# State encryption is currently disabled (see tofu/exe/main.tf comment).
# When the encryption block is re-introduced, set TF_ENCRYPTION here.

# ----- pull values from tofu state -----------------------------------

cd "${STACK_DIR}"

OUT_JSON="$(tofu output -json)"
get() { jq -r ".$1.value // empty" <<<"${OUT_JSON}"; }

CODER_HOST="$(get coder_url | sed 's|https://||')"
TUNNEL_CNAME="$(get cloudflare_tunnel_cname)"
VM_NAME="$(get vm_name)"
VM_ZONE="$(get vm_zone)"
TS_SECRET_CODER="$(get tailscale_secret_coder)"
TS_SECRET_AGENT="$(get tailscale_secret_agent)"

[[ -n "${CODER_HOST}" ]] || { red "no outputs — has tofu apply succeeded yet?"; exit 1; }

cd - >/dev/null

# ----- DNS -----------------------------------------------------------

actual_cname="$(dig +short "${CODER_HOST}" CNAME @1.1.1.1 | head -n1 | sed 's/\.$//')"
if [[ "${actual_cname}" == "${TUNNEL_CNAME}" ]]; then
  green "DNS: ${CODER_HOST} CNAME -> ${TUNNEL_CNAME}"
else
  yellow "DNS: ${CODER_HOST} resolves to '${actual_cname}', expected '${TUNNEL_CNAME}' (proxied records may show edge IPs instead — see HTTPS check)"
fi

# Verify the orange-cloud is on (no origin IP leaks).
a_record="$(dig +short "${CODER_HOST}" A @1.1.1.1 | head -n1)"
if [[ -n "${a_record}" ]]; then
  if [[ "${a_record}" =~ ^104\.|^172\.|^173\.|^188\.|^190\.|^197\.|^198\. ]]; then
    green "DNS proxied: ${CODER_HOST} A -> ${a_record} (Cloudflare edge)"
  else
    red "DNS NOT proxied: ${CODER_HOST} A -> ${a_record} — origin IP may be leaking"
  fi
fi

# ----- Cloudflare Access ---------------------------------------------
#
# An anonymous GET should land on the OIDC interstitial (302 to
# cloudflareaccess.com), NOT on the Coder UI.

http_code="$(curl -fsS -o /dev/null -w '%{http_code}' -L --max-redirs 0 "https://${CODER_HOST}/" || true)"
final_url="$(curl -fsS -o /dev/null -w '%{url_effective}' -L "https://${CODER_HOST}/" || true)"

if [[ "${final_url}" == *cloudflareaccess.com* ]]; then
  green "Access: anonymous request gated by Cloudflare Access (final URL contains cloudflareaccess.com)"
elif [[ "${http_code}" == "302" ]] || [[ "${http_code}" == "301" ]]; then
  green "Access: anonymous request redirected (HTTP ${http_code})"
else
  red "Access: anonymous request reached origin (HTTP ${http_code}) — Access policy may be misconfigured"
fi

# ----- Tunnel health -------------------------------------------------

tunnel_state="$(gcloud --quiet --project="$(gcloud config get-value project 2>/dev/null)" \
  compute instances describe "${VM_NAME}" --zone="${VM_ZONE}" \
  --format='value(status)' 2>/dev/null || echo MISSING)"

case "${tunnel_state}" in
  RUNNING)    green "VM: ${VM_NAME} RUNNING in ${VM_ZONE}" ;;
  TERMINATED) yellow "VM: ${VM_NAME} TERMINATED (preempted; will auto-restart on next plan)" ;;
  MISSING)    red    "VM: ${VM_NAME} not found in ${VM_ZONE}" ;;
  *)          yellow "VM: ${VM_NAME} state=${tunnel_state}" ;;
esac

# ----- Secret Manager visibility -------------------------------------

for secret in "${TS_SECRET_CODER}" "${TS_SECRET_AGENT}"; do
  short="$(basename "${secret}")"
  if gcloud --quiet secrets describe "${short}" >/dev/null 2>&1; then
    versions="$(gcloud --quiet secrets versions list "${short}" --filter='state=ENABLED' --format='value(name)' | wc -l | tr -d ' ')"
    green "Secret: ${short} present, ${versions} enabled version(s)"
  else
    red "Secret: ${short} not found"
  fi
done

# ----- Coder server reachability (via Tailscale) ---------------------
#
# Coder listens on 127.0.0.1:7080 inside the VM. Reach it through
# Tailscale SSH so we don't have to go through Cloudflare Access.

if command -v tailscale >/dev/null 2>&1 && tailscale status --json >/dev/null 2>&1; then
  if coder_status="$(tailscale ssh "${VM_NAME}" -- \
        curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:7080/healthz 2>/dev/null)"; then
    if [[ "${coder_status}" == "200" ]]; then
      green "Coder: 127.0.0.1:7080/healthz returned 200"
    else
      yellow "Coder: 127.0.0.1:7080/healthz returned ${coder_status} (still booting?)"
    fi
  else
    yellow "Coder: tailscale ssh to ${VM_NAME} failed; skipping Coder healthz"
  fi
else
  yellow "Tailscale not available locally; skipping Coder healthz"
fi

# ----- Tailnet reachability (optional) -------------------------------

if command -v tailscale >/dev/null 2>&1; then
  if tailscale status --json >/dev/null 2>&1; then
    if tailscale status | grep -qE "\b${VM_NAME}\b"; then
      green "Tailscale: ${VM_NAME} visible on the tailnet from this device"
    else
      yellow "Tailscale: ${VM_NAME} not yet visible (may still be booting)"
    fi
  else
    yellow "Tailscale: this device is not connected to the tailnet"
  fi
else
  yellow "Tailscale CLI not installed locally; skipping tailnet check"
fi

green "smoke checks complete."
