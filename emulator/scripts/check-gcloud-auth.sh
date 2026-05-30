#!/usr/bin/env bash
set -euo pipefail

# Check whether `gcloud auth login` and `gcloud auth application-default login`
# need to be re-run. Idempotent: performs checks only, no changes.
#
# Usage:
#   bash scripts/check-gcloud-auth.sh [--json] [--verbose] [--details] [--strict]
#
# Exit codes:
#   0  = both user login and ADC are OK
#   10 = user login needs (re)login
#   11 = ADC needs (re)login
#   12 = both user login and ADC need (re)login
#   127= gcloud not found
#   2  = invalid argument

JSON=false
VERBOSE=false
DETAILS=false
STRICT=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON=true; shift ;;
    --verbose|-v) VERBOSE=true; shift ;;
    --details) DETAILS=true; shift ;;
    --strict|--fail-on-warn) STRICT=true; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

log() { if [[ "$VERBOSE" == true ]]; then echo "$*"; fi; }

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud not found. Install Google Cloud CLI: https://cloud.google.com/sdk/docs/install" >&2
  exit 127
fi

# Collect details
GCLOUD_VERSION=$(gcloud --version 2>/dev/null | head -n1 | sed -E 's/^Google Cloud SDK[[:space:]]+//' || true)
if [[ -z "${GCLOUD_VERSION}" ]]; then
  GCLOUD_VERSION="unknown"
fi
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || true)

# Helpful config values
CORE_PROJECT=$(gcloud config get-value project 2>/dev/null || true)
BILLING_QUOTA_PROJECT=$(gcloud config get-value billing/quota_project 2>/dev/null || true)
CONFIG_ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)
IMPERSONATE_SA=$(gcloud config get-value auth/impersonate_service_account 2>/dev/null || true)

# Check user login by attempting to get an access token for the active account (if any).
USER_LOGIN_OK=false
if [[ -n "${ACTIVE_ACCOUNT}" ]]; then
  if gcloud auth print-access-token --account "${ACTIVE_ACCOUNT}" --quiet >/dev/null 2>&1; then
    USER_LOGIN_OK=true
  fi
fi

# If no active account, definitely not OK.
if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
  USER_LOGIN_OK=false
fi

# Check ADC by trying to print an application default access token.
ADC_OK=false
if gcloud auth application-default print-access-token --quiet >/dev/null 2>&1; then
  ADC_OK=true
fi

# Determine ADC source and path
ADC_SOURCE="none"
ADC_PATH=""

# Prefer env var if set
if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
  ADC_SOURCE="env"
  ADC_PATH="${GOOGLE_APPLICATION_CREDENTIALS}"
else
  # Resolve gcloud config dir and default ADC file path
  CONFIG_DIR=$(gcloud info --format='value(config.paths.global_config_dir)' 2>/dev/null || true)
  if [[ -n "${CONFIG_DIR}" ]]; then
    CANDIDATE="${CONFIG_DIR%/}/application_default_credentials.json"
    if [[ -f "${CANDIDATE}" ]]; then
      ADC_SOURCE="default"
      ADC_PATH="${CANDIDATE}"
    fi
  fi
fi

# Try to parse ADC metadata if a JSON file is available
ADC_TYPE=""
ADC_CLIENT_EMAIL=""
ADC_PROJECT_ID=""
ADC_QUOTA_PROJECT_ID=""
ADC_AUDIENCE=""
ADC_IMPERSONATION_URL=""
ADC_PARSE_OK=false
ADC_HAS_REFRESH_TOKEN=false
ADC_HAS_PRIVATE_KEY=false
ADC_FILE_MODE=""

_have_python=false
PYBIN=""
if command -v python3 >/dev/null 2>&1; then _have_python=true; PYBIN="python3"; fi
if [[ "$_have_python" == false ]] && command -v python >/dev/null 2>&1; then _have_python=true; PYBIN="python"; fi

if [[ -n "${ADC_PATH}" && -f "${ADC_PATH}" ]]; then
  # Capture file mode (best-effort across platforms)
  if command -v stat >/dev/null 2>&1; then
    # macOS: -f %A, Linux: -c %a; try both
    ADC_FILE_MODE=$(stat -f %A "${ADC_PATH}" 2>/dev/null || stat -c %a "${ADC_PATH}" 2>/dev/null || echo "")
  fi
fi

if [[ -n "${ADC_PATH}" && -f "${ADC_PATH}" && "$_have_python" == true ]]; then
  # shellcheck disable=SC2016
  ADC_JSON=$(ADC_PATH="${ADC_PATH}" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os, sys
path = os.environ.get('ADC_PATH')
try:
    with open(path, 'r') as f:
        d = json.load(f)
    parse_ok = True
except Exception:
    d = {}
    parse_ok = False
out = {
    'type': d.get('type',''),
    'client_email': d.get('client_email',''),
    'project_id': d.get('project_id','') or d.get('universe_project',''),
    'quota_project_id': d.get('quota_project_id',''),
    'audience': d.get('audience',''),
    'impersonation_url': d.get('service_account_impersonation_url',''),
    'parse_ok': parse_ok,
    'has_refresh_token': bool(d.get('refresh_token')),
    'has_private_key': bool(d.get('private_key'))
}
print(json.dumps(out))
PY
)
  if [[ -n "${ADC_JSON}" ]]; then
    # Extract fields without jq using Python again for reliability
    # shellcheck disable=SC2016
    ADC_TYPE=$(ADC_JSON="$ADC_JSON" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os
d = json.loads(os.environ.get('ADC_JSON','{}'))
print(d.get('type',''))
PY
    )
    ADC_CLIENT_EMAIL=$(ADC_JSON="$ADC_JSON" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os
d = json.loads(os.environ.get('ADC_JSON','{}'))
print(d.get('client_email',''))
PY
    )
    ADC_PROJECT_ID=$(ADC_JSON="$ADC_JSON" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os
d = json.loads(os.environ.get('ADC_JSON','{}'))
print(d.get('project_id',''))
PY
    )
    ADC_QUOTA_PROJECT_ID=$(ADC_JSON="$ADC_JSON" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os
d = json.loads(os.environ.get('ADC_JSON','{}'))
print(d.get('quota_project_id',''))
PY
    )
    ADC_AUDIENCE=$(ADC_JSON="$ADC_JSON" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os
d = json.loads(os.environ.get('ADC_JSON','{}'))
print(d.get('audience',''))
PY
    )
    ADC_IMPERSONATION_URL=$(ADC_JSON="$ADC_JSON" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os
d = json.loads(os.environ.get('ADC_JSON','{}'))
print(d.get('impersonation_url',''))
PY
    )
    ADC_PARSE_OK=$(ADC_JSON="$ADC_JSON" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os
d = json.loads(os.environ.get('ADC_JSON','{}'))
print('true' if d.get('parse_ok') else 'false')
PY
    )
    ADC_HAS_REFRESH_TOKEN=$(ADC_JSON="$ADC_JSON" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os
d = json.loads(os.environ.get('ADC_JSON','{}'))
print('true' if d.get('has_refresh_token') else 'false')
PY
    )
    ADC_HAS_PRIVATE_KEY=$(ADC_JSON="$ADC_JSON" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os
d = json.loads(os.environ.get('ADC_JSON','{}'))
print('true' if d.get('has_private_key') else 'false')
PY
    )
  fi
fi

log "gcloud version: ${GCLOUD_VERSION}"
log "active account: ${ACTIVE_ACCOUNT:-<none>}"

# Build warnings/suggestions based on heuristics
WARNINGS=()
SUGGESTIONS=()
NOTICES=()

# User login problems
if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
  WARNINGS+=("No active gcloud account is set")
  SUGGESTIONS+=("Run: gcloud auth login")
elif [[ "${USER_LOGIN_OK}" != true ]]; then
  WARNINGS+=("Active gcloud account token invalid/expired: ${ACTIVE_ACCOUNT}")
  SUGGESTIONS+=("Run: gcloud auth login")
fi

# Config account vs active account mismatch
if [[ -n "${CONFIG_ACCOUNT}" && -n "${ACTIVE_ACCOUNT}" && "${CONFIG_ACCOUNT}" != "${ACTIVE_ACCOUNT}" ]]; then
  WARNINGS+=("gcloud config account (${CONFIG_ACCOUNT}) differs from active account (${ACTIVE_ACCOUNT})")
  SUGGESTIONS+=("Run: gcloud config set account ${ACTIVE_ACCOUNT}")
fi

# ADC problems
if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" && ! -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]]; then
  WARNINGS+=("GOOGLE_APPLICATION_CREDENTIALS points to a missing file: ${GOOGLE_APPLICATION_CREDENTIALS}")
  SUGGESTIONS+=("Fix path or unset GOOGLE_APPLICATION_CREDENTIALS")
fi

if [[ "${ADC_OK}" != true ]]; then
  WARNINGS+=("Application Default Credentials (ADC) not usable")
  if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
    SUGGESTIONS+=("Verify credentials file and permissions at ${GOOGLE_APPLICATION_CREDENTIALS}")
  else
    SUGGESTIONS+=("Run: gcloud auth application-default login")
  fi
fi

# ADC file validations
if [[ -n "${ADC_PATH}" && ! -r "${ADC_PATH}" ]]; then
  WARNINGS+=("ADC file is not readable: ${ADC_PATH}")
fi
if [[ -n "${ADC_PATH}" && -f "${ADC_PATH}" && -n "${ADC_FILE_MODE}" ]]; then
  # If world-readable or world-writable, surface as a notice for security hygiene
  case "${ADC_FILE_MODE}" in
    *7|*6|*5|*4)
      NOTICES+=("ADC file permissions are broad (${ADC_FILE_MODE}); consider restricting to owner-only")
      ;;
  esac
fi
if [[ -n "${ADC_PATH}" && -f "${ADC_PATH}" && "${ADC_PARSE_OK}" != true ]]; then
  WARNINGS+=("ADC file is not valid JSON or could not be parsed: ${ADC_PATH}")
fi
if [[ "${ADC_TYPE}" == "authorized_user" && "${ADC_HAS_REFRESH_TOKEN}" != true ]]; then
  WARNINGS+=("Authorized user ADC missing refresh_token (re-auth likely required)")
  SUGGESTIONS+=("Run: gcloud auth application-default login")
fi
if [[ "${ADC_TYPE}" == "service_account" && "${ADC_HAS_PRIVATE_KEY}" != true ]]; then
  WARNINGS+=("Service account ADC missing private_key (invalid credentials file)")
fi
if [[ "${ADC_TYPE}" == "external_account" && -z "${ADC_AUDIENCE}" ]]; then
  WARNINGS+=("External account ADC missing audience")
fi
if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" && "${ADC_TYPE}" == "authorized_user" ]]; then
  NOTICES+=("GOOGLE_APPLICATION_CREDENTIALS points to authorized_user; typically service_account is preferred for automation")
fi

# Authorized user ADC without quota project can cause 403 on some APIs
if [[ "${ADC_TYPE}" == "authorized_user" && -z "${ADC_QUOTA_PROJECT_ID}" && -z "${BILLING_QUOTA_PROJECT}" ]]; then
  WARNINGS+=("ADC type is authorized_user with no quota project configured")
  if [[ -n "${CORE_PROJECT}" ]]; then
    SUGGESTIONS+=("Run: gcloud auth application-default set-quota-project ${CORE_PROJECT}")
  else
    SUGGESTIONS+=("Set quota project: gcloud auth application-default set-quota-project <PROJECT>")
  fi
fi

# Missing core project can be confusing for CLI operations
if [[ -z "${CORE_PROJECT}" ]]; then
  WARNINGS+=("gcloud core/project is not set")
  SUGGESTIONS+=("Run: gcloud config set project <PROJECT>")
fi

# Informational notice if quota project differs from core project (not necessarily wrong)
if [[ -n "${ADC_QUOTA_PROJECT_ID}" && -n "${CORE_PROJECT}" && "${ADC_QUOTA_PROJECT_ID}" != "${CORE_PROJECT}" ]]; then
  NOTICES+=("ADC quota project (${ADC_QUOTA_PROJECT_ID}) differs from core/project (${CORE_PROJECT})")
fi
if [[ -n "${IMPERSONATE_SA}" ]]; then
  NOTICES+=("gcloud is configured to impersonate service account: ${IMPERSONATE_SA} (CLI may differ from library ADC)")
fi

# High-privilege role detection (best effort): Owner/IAM Admin/Billing Admin
HIGH_PRIV_PATTERNS=(
  'roles/owner'
  'roles/resourcemanager.projectIamAdmin'
  'roles/iam.securityAdmin'
  'roles/iam.roleAdmin'
  'roles/billing.admin'
)
PRIV_LINES_STR=""  # newline-separated entries: project<TAB>role
PRIV_COUNT=0
PRINCIPAL=""
if [[ "${ADC_TYPE}" == "service_account" && -n "${ADC_CLIENT_EMAIL}" ]]; then
  PRINCIPAL="serviceAccount:${ADC_CLIENT_EMAIL}"
elif [[ -n "${CONFIG_ACCOUNT}" ]]; then
  PRINCIPAL="user:${CONFIG_ACCOUNT}"
elif [[ -n "${ACTIVE_ACCOUNT}" ]]; then
  PRINCIPAL="user:${ACTIVE_ACCOUNT}"
fi
if [[ -n "${PRINCIPAL}" ]]; then
  PROJECTS_TO_CHECK=()
  if [[ -n "${CORE_PROJECT}" ]]; then PROJECTS_TO_CHECK+=("${CORE_PROJECT}"); fi
  if [[ -n "${ADC_QUOTA_PROJECT_ID}" && "${ADC_QUOTA_PROJECT_ID}" != "${CORE_PROJECT}" ]]; then PROJECTS_TO_CHECK+=("${ADC_QUOTA_PROJECT_ID}"); fi
  for proj in "${PROJECTS_TO_CHECK[@]:-}"; do
    _roles_out=$(gcloud projects get-iam-policy "$proj" --flatten=bindings --filter="bindings.members=${PRINCIPAL}" --format="value(bindings.role)" 2>/dev/null || true)
    while IFS= read -r r; do
      [[ -z "$r" ]] && continue
      for pat in "${HIGH_PRIV_PATTERNS[@]}"; do
        if [[ "$r" == "$pat" ]]; then
          key="$proj"$'\t'"$r"
          if ! printf '%s\n' "$PRIV_LINES_STR" | grep -Fqx "$key"; then
            PRIV_LINES_STR+="$key"$'\n'
            PRIV_COUNT=$((PRIV_COUNT+1))
          fi
        fi
      done
    done <<< "$_roles_out"
  done
fi

if [[ "$JSON" == true ]]; then
  # Emit JSON object for machine consumption.
  if [[ "$_have_python" == true && -n "${PYBIN}" ]]; then
    GCLOUD_VERSION="$GCLOUD_VERSION" \
    ACTIVE_ACCOUNT="$ACTIVE_ACCOUNT" \
    USER_LOGIN_OK="$USER_LOGIN_OK" \
    ADC_OK="$ADC_OK" \
    ADC_SOURCE="$ADC_SOURCE" \
    ADC_PATH="$ADC_PATH" \
    ADC_TYPE="$ADC_TYPE" \
    ADC_CLIENT_EMAIL="$ADC_CLIENT_EMAIL" \
    ADC_PROJECT_ID="$ADC_PROJECT_ID" \
    ADC_QUOTA_PROJECT_ID="$ADC_QUOTA_PROJECT_ID" \
    ADC_AUDIENCE="$ADC_AUDIENCE" \
    # Pass warnings/suggestions/notices via temporary files to avoid env size issues
    WFILE=$(mktemp 2>/dev/null || echo /tmp/gcloud_warn.$$)
    SFILE=$(mktemp 2>/dev/null || echo /tmp/gcloud_sugg.$$)
    NFILE=$(mktemp 2>/dev/null || echo /tmp/gcloud_note.$$)
    PFILE=$(mktemp 2>/dev/null || echo /tmp/gcloud_priv.$$)
    printf '%s\n' "${WARNINGS[@]:-}" >"$WFILE"
    printf '%s\n' "${SUGGESTIONS[@]:-}" >"$SFILE"
    printf '%s\n' "${NOTICES[@]:-}" >"$NFILE"
    printf '%s' "${PRIV_LINES_STR}" >"$PFILE"
    WFILE="$WFILE" SFILE="$SFILE" NFILE="$NFILE" PFILE="$PFILE" "${PYBIN}" - <<'PY' 2>/dev/null || true
import json, os, sys
def to_bool(s):
    return True if str(s).lower() == 'true' else False
def read_lines(path):
    try:
        with open(path, 'r') as f:
            return [ln.rstrip('\n') for ln in f if ln.rstrip('\n')]
    except Exception:
        return []
def read_priv(path):
    items = []
    try:
        with open(path, 'r') as f:
            for ln in f:
                ln = ln.rstrip('\n')
                if not ln:
                    continue
                if '\t' in ln:
                    proj, role = ln.split('\t', 1)
                else:
                    proj, role = '', ln
                items.append({'project': proj, 'role': role})
    except Exception:
        pass
    return items
out = {
  'gcloudVersion': os.environ.get('GCLOUD_VERSION',''),
  'activeAccount': os.environ.get('ACTIVE_ACCOUNT',''),
  'userLoginOk': to_bool(os.environ.get('USER_LOGIN_OK','false')),
  'adcOk': to_bool(os.environ.get('ADC_OK','false')),
  'adcSource': os.environ.get('ADC_SOURCE',''),
  'adcPath': os.environ.get('ADC_PATH',''),
  'adcType': os.environ.get('ADC_TYPE',''),
  'adcClientEmail': os.environ.get('ADC_CLIENT_EMAIL',''),
  'adcProjectId': os.environ.get('ADC_PROJECT_ID',''),
  'adcQuotaProjectId': os.environ.get('ADC_QUOTA_PROJECT_ID',''),
  'adcAudience': os.environ.get('ADC_AUDIENCE',''),
  'adcParseOk': to_bool(os.environ.get('ADC_PARSE_OK','false')),
  'adcHasRefreshToken': to_bool(os.environ.get('ADC_HAS_REFRESH_TOKEN','false')),
  'adcHasPrivateKey': to_bool(os.environ.get('ADC_HAS_PRIVATE_KEY','false')),
  'adcFileMode': os.environ.get('ADC_FILE_MODE',''),
  'coreProject': os.environ.get('CORE_PROJECT',''),
  'billingQuotaProject': os.environ.get('BILLING_QUOTA_PROJECT',''),
  'configAccount': os.environ.get('CONFIG_ACCOUNT',''),
  'impersonateServiceAccount': os.environ.get('IMPERSONATE_SA',''),
  'warnings': read_lines(os.environ.get('WFILE','')),
  'suggestions': read_lines(os.environ.get('SFILE','')),
  'notices': read_lines(os.environ.get('NFILE','')),
  'highPrivilege': read_priv(os.environ.get('PFILE',''))
}
print(json.dumps(out))
PY
    rm -f "$WFILE" "$SFILE" "$NFILE" "$PFILE" 2>/dev/null || true
  else
    printf '{"gcloudVersion":"%s","activeAccount":"%s","userLoginOk":%s,"adcOk":%s,"adcSource":"%s","adcPath":"%s","adcType":"%s","adcClientEmail":"%s","adcProjectId":"%s","adcQuotaProjectId":"%s","adcAudience":"%s"}\n' \
      "${GCLOUD_VERSION}" "${ACTIVE_ACCOUNT}" \
      "${USER_LOGIN_OK}" "${ADC_OK}" \
      "${ADC_SOURCE}" "${ADC_PATH}" "${ADC_TYPE}" "${ADC_CLIENT_EMAIL}" "${ADC_PROJECT_ID}" "${ADC_QUOTA_PROJECT_ID}" "${ADC_AUDIENCE}"
  fi
else
  echo "gcloud: ${GCLOUD_VERSION}"
  if [[ "$USER_LOGIN_OK" == true ]]; then
    echo "User Login: OK (active: ${ACTIVE_ACCOUNT})"
  else
    if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
      echo "User Login: NEEDS LOGIN (no active account). Run: gcloud auth login" >&2
    else
      echo "User Login: NEEDS LOGIN (token invalid/expired). Run: gcloud auth login" >&2
    fi
  fi

  if [[ "$ADC_OK" == true ]]; then
    echo "ADC: OK (application-default credentials available)"
  else
    echo "ADC: NEEDS LOGIN. Run: gcloud auth application-default login" >&2
  fi

  if [[ "$DETAILS" == true ]]; then
    echo "--- ADC Details ---"
    if [[ -n "${ADC_SOURCE}" && "${ADC_SOURCE}" != "none" ]]; then
      if [[ "${ADC_SOURCE}" == "env" ]]; then
        echo "Source: ENV (GOOGLE_APPLICATION_CREDENTIALS)"
      else
        echo "Source: Default ADC file"
      fi
      echo "Path: ${ADC_PATH:-<unknown>}"
    else
      echo "Source: none (no ADC file detected)"
    fi
    if [[ -n "${ADC_TYPE}" ]]; then echo "Type: ${ADC_TYPE}"; fi
    if [[ -n "${ADC_CLIENT_EMAIL}" ]]; then echo "Service Account: ${ADC_CLIENT_EMAIL}"; fi
    if [[ -n "${ADC_PROJECT_ID}" ]]; then echo "Project ID: ${ADC_PROJECT_ID}"; fi
    if [[ -n "${ADC_QUOTA_PROJECT_ID}" ]]; then echo "Quota Project: ${ADC_QUOTA_PROJECT_ID}"; fi
    if [[ -n "${ADC_AUDIENCE}" ]]; then echo "Audience: ${ADC_AUDIENCE}"; fi
    if [[ -n "${ADC_IMPERSONATION_URL}" ]]; then echo "Impersonation URL: ${ADC_IMPERSONATION_URL}"; fi
    if [[ -n "${CORE_PROJECT}" ]]; then echo "Core Project: ${CORE_PROJECT}"; fi
    if [[ -n "${BILLING_QUOTA_PROJECT}" ]]; then echo "Billing Quota Project: ${BILLING_QUOTA_PROJECT}"; fi
    if [[ ${PRIV_COUNT} -gt 0 ]]; then
      echo "--- Privilege Check ---"
      echo "Principal: ${PRINCIPAL}"
      while IFS=$'\t' read -r proj role; do
        [[ -z "${proj}${role}" ]] && continue
        echo "High-privilege role: ${role} on project: ${proj}"
      done <<< "${PRIV_LINES_STR}"
      echo "CAUTION: High-privilege role(s) detected. Perform operations carefully."
    fi
    if (( ${#NOTICES[@]:-0} > 0 )); then
      echo "--- Notices ---"
      for n in "${NOTICES[@]}"; do echo "- ${n}"; done
    fi
    if (( ${#WARNINGS[@]:-0} > 0 )); then
      echo "--- Warnings ---" >&2
      for w in "${WARNINGS[@]}"; do echo "- ${w}" >&2; done
    fi
    if (( ${#SUGGESTIONS[@]:-0} > 0 )); then
      echo "--- Suggestions ---"
      for s in "${SUGGESTIONS[@]}"; do echo "- ${s}"; done
    fi
  fi
fi

# Decide exit code matrix
EXIT=0
if [[ "$USER_LOGIN_OK" == true && "$ADC_OK" == true ]]; then
  EXIT=0
elif [[ "$USER_LOGIN_OK" == false && "$ADC_OK" == true ]]; then
  EXIT=10
elif [[ "$USER_LOGIN_OK" == true && "$ADC_OK" == false ]]; then
  EXIT=11
else
  EXIT=12
fi

# If strict and there are warnings, prefer warning code 20 when base is 0
if [[ "$STRICT" == true && $EXIT -eq 0 && ${#WARNINGS[@]:-0} -gt 0 ]]; then
  EXIT=20
fi

exit $EXIT
