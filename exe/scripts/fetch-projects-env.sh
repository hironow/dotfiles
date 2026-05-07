#!/usr/bin/env bash
# fetch-projects-env.sh — workspace-VM hook that switches the dmail
# daemons into multi-mode by querying the runops-gateway HTTP admin
# endpoint and writing per-project drop-in env files.
#
# Idempotent: safe to run on every workspace boot (and on every
# systemd reload). Fail-soft: never blocks startup — when the gateway
# is unreachable, the registry is empty, or any project_id fails the
# defensive regex check, the script falls back to single-mode by
# emitting empty drop-ins so the daemon's main unit `Environment=
# PHONEWAVE_OUTBOX_DIR` stays effective. The dmail-receiver and
# dmail-emitter daemons (runops-gateway #0006 / #0007) consume the
# resulting drop-ins via systemd's standard `<unit>.service.d/*.conf`
# auto-merge mechanism.
#
# Required env (when multi-mode is desired):
#   RUNOPS_GATEWAY_URL    — base URL of the gateway HTTP admin endpoint.
#   RUNOPS_ADMIN_TOKEN    — Bearer token configured by gateway #0012.
#
# Optional env (overridable in tests):
#   WORKSPACE_HOME        — defaults to /home/coder.
#   DROP_IN_RECEIVER_DIR  — drop-in dir for dmail-receiver.
#   DROP_IN_EMITTER_DIR   — drop-in dir for dmail-emitter.
#   FETCH_PROJECTS_NO_RELOAD — set to 1 to skip systemctl daemon-reload
#                              + restart (used by smoke tests).
#
# Defensive validation: every project_id returned by the gateway is
# matched against ^[a-zA-Z0-9_-]+$ and a 64-char limit, the same regex
# the gateway's domain.ValidateProjectID enforces. This is a second
# line of defence so a misbehaving gateway, a man-in-the-middle, or a
# tampered response cannot inject hostile values into systemd
# Environment= lines or path-traversal sequences into mkdir.

set -uo pipefail

GATEWAY_URL="${RUNOPS_GATEWAY_URL:-}"
ADMIN_TOKEN="${RUNOPS_ADMIN_TOKEN:-}"
WORKSPACE_HOME="${WORKSPACE_HOME:-/home/coder}"
PROJECTS_ROOT="${WORKSPACE_HOME}/projects"
DROP_IN_RECEIVER_DIR="${DROP_IN_RECEIVER_DIR:-/etc/systemd/system/dmail-receiver.service.d}"
DROP_IN_EMITTER_DIR="${DROP_IN_EMITTER_DIR:-/etc/systemd/system/dmail-emitter.service.d}"
DROP_IN_RECEIVER="${DROP_IN_RECEIVER_DIR}/env.conf"
DROP_IN_EMITTER="${DROP_IN_EMITTER_DIR}/env.conf"

# project_id spec — mirror runops-gateway internal/core/domain/project.go.
PROJECT_ID_RE='^[a-zA-Z0-9_-]+$'
PROJECT_ID_MAX_LEN=64

mkdir -p "${PROJECTS_ROOT}" "${DROP_IN_RECEIVER_DIR}" "${DROP_IN_EMITTER_DIR}"

emit_fallback_drop_ins() {
    # Single-mode fallback: drop-ins carry only [Service] so systemd
    # merges no Environment= overlays, leaving the main unit's
    # PHONEWAVE_OUTBOX_DIR / PHONEWAVE_ARCHIVE_DIRS effective. Daemons
    # then run with SingleOutboxRouter / SingleArchiveRouter
    # (gateway #0006 / #0007), preserving pre-multiplex behaviour.
    cat > "${DROP_IN_RECEIVER}" <<'EOF'
[Service]
# Multi-mode disabled (fallback). systemd merges nothing dynamic; the
# main unit's PHONEWAVE_OUTBOX_DIR remains effective.
EOF
    cat > "${DROP_IN_EMITTER}" <<'EOF'
[Service]
# Multi-mode disabled (fallback). systemd merges nothing dynamic.
EOF
}

reload_units() {
    if [[ "${FETCH_PROJECTS_NO_RELOAD:-0}" == "1" ]]; then
        echo "fetch-projects-env: FETCH_PROJECTS_NO_RELOAD=1 — skipping systemctl reload" >&2
        return 0
    fi
    systemctl daemon-reload || true
    systemctl try-restart dmail-receiver.service dmail-emitter.service || true
}

if [[ -z "${GATEWAY_URL}" || -z "${ADMIN_TOKEN}" ]]; then
    echo "fetch-projects-env: gateway URL / admin token unset — using single-mode fallback" >&2
    emit_fallback_drop_ins
    reload_units
    exit 0
fi

response=$(curl --silent --max-time 15 \
    --header "Authorization: Bearer ${ADMIN_TOKEN}" \
    "${GATEWAY_URL}/admin/projects?status=active" 2>/dev/null) || {
    echo "fetch-projects-env: gateway request failed — using single-mode fallback" >&2
    emit_fallback_drop_ins
    reload_units
    exit 0
}

if ! command -v jq >/dev/null 2>&1; then
    echo "fetch-projects-env: jq is required for response parsing — using single-mode fallback" >&2
    emit_fallback_drop_ins
    reload_units
    exit 0
fi

project_ids=$(jq -r '.projects[]?.id' <<<"${response}" 2>/dev/null) || {
    echo "fetch-projects-env: response parse failed — using single-mode fallback" >&2
    emit_fallback_drop_ins
    reload_units
    exit 0
}

if [[ -z "${project_ids}" ]]; then
    echo "fetch-projects-env: registry returned zero projects — using single-mode fallback" >&2
    emit_fallback_drop_ins
    reload_units
    exit 0
fi

valid_ids=()
while IFS= read -r pid; do
    [[ -z "${pid}" ]] && continue
    if (( ${#pid} > PROJECT_ID_MAX_LEN )); then
        printf 'fetch-projects-env: project id (length=%d) exceeds %d chars — skipping\n' \
            "${#pid}" "${PROJECT_ID_MAX_LEN}" >&2
        continue
    fi
    if ! [[ "${pid}" =~ ${PROJECT_ID_RE} ]]; then
        printf 'fetch-projects-env: project id failed regex (length=%d) — skipping\n' "${#pid}" >&2
        continue
    fi
    valid_ids+=("${pid}")
done <<<"${project_ids}"

if (( ${#valid_ids[@]} == 0 )); then
    echo "fetch-projects-env: zero valid project ids after defensive validation — using single-mode fallback" >&2
    emit_fallback_drop_ins
    reload_units
    exit 0
fi

outbox_pairs=""
archive_pairs=""
for pid in "${valid_ids[@]}"; do
    project_dir="${PROJECTS_ROOT}/${pid}"
    mkdir -p "${project_dir}/.phonewave/outbox" "${project_dir}/.phonewave/archive"
    chmod 0777 "${project_dir}/.phonewave/outbox" "${project_dir}/.phonewave/archive"
    outbox_pairs+="${pid}:${project_dir}/.phonewave/outbox,"
    archive_pairs+="${pid}:${project_dir}/.phonewave/archive,"
done
outbox_pairs="${outbox_pairs%,}"
archive_pairs="${archive_pairs%,}"

cat > "${DROP_IN_RECEIVER}" <<EOF
[Service]
# Multi-mode (workspace boot hook fetched ${#valid_ids[@]} active project(s)).
Environment=PHONEWAVE_OUTBOX_DIRS_BY_PROJECT=${outbox_pairs}
Environment=PHONEWAVE_PEER_RECEIVER_MODE=multi
EOF
cat > "${DROP_IN_EMITTER}" <<EOF
[Service]
# Multi-mode (workspace boot hook fetched ${#valid_ids[@]} active project(s)).
Environment=PHONEWAVE_ARCHIVE_DIRS_BY_PROJECT=${archive_pairs}
Environment=PHONEWAVE_PEER_RECEIVER_MODE=multi
EOF

echo "fetch-projects-env: configured ${#valid_ids[@]} project(s) (multi-mode)" >&2
reload_units
