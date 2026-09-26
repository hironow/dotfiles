#!/usr/bin/env bash
#
# ==============================================================================
# exe_platform_bootstrap.sh -- the GCS bucket that holds tofu/exe-platform state
# ------------------------------------------------------------------------------
# One-time, out-of-band, idempotent. Run it once per project, BEFORE `tofu init`.
#
# WHY THIS ONE BUCKET IS A LEGITIMATE IaC EXCEPTION
#
# The standing rule is that nothing in the private project is mutated outside
# OpenTofu + PR + CD: a stray `gcloud ... update` creates drift that the next
# `tofu apply` silently reverts. This bucket is the single carve-out, and the
# reason is structural rather than a convenience:
#
#   the bucket IS the stack's state backend, and a stack cannot create its own
#   backend. `tofu init` has to reach and lock remote state before a resource
#   graph exists at all, so the bucket must already be there -- a chicken-and-egg
#   that no amount of ordering inside the stack can break.
#
# Consequences, deliberately:
#   * the bucket is NOT a resource in tofu/exe-platform -- no
#     `google_storage_bucket` for it, no `import` block. So there is nothing for
#     a later `tofu apply` to revert, and no drift to detect.
#   * EVERYTHING else in the project -- cluster, node pool, NAT, data buckets,
#     budgets, service accounts, APIs -- is created by tofu, and mutating any of
#     those by hand remains forbidden. This script touches one bucket and stops.
#   * because there is no `tofu plan` to review for it, `--dry-run` IS the
#     review: it prints every `gcloud` command plus the lifecycle document, and
#     executes none of them.
# ------------------------------------------------------------------------------
# Usage:
#   scripts/exe_platform_bootstrap.sh --project <id> [--bucket <name>] [--dry-run]
#   EXE_PLATFORM_PROJECT=<id> scripts/exe_platform_bootstrap.sh [--dry-run]
#   scripts/exe_platform_bootstrap.sh --print-lifecycle
#
# This repo is PUBLIC, so no identifier is baked in: the project id arrives as
# an argument or an environment variable, and nothing derived from it is ever
# written to a file inside the repo (the lifecycle document goes to a temp file
# under $TMPDIR and carries no identifier at all).
#
# Required tools: gcloud (not needed by --dry-run or --print-lifecycle).
# ==============================================================================

set -euo pipefail

# --- pinned end state ---------------------------------------------------------
readonly LOCATION='asia-northeast1'
readonly STORAGE_CLASS='STANDARD'
# The bound on a versioned state bucket. Without it every `tofu apply` adds a
# generation nothing ever removes; the repo's cost policy is that no storage
# sink accumulates silently.
readonly NONCURRENT_VERSIONS=10

DRY_RUN=0
PRINT_LIFECYCLE=0
PROJECT="${EXE_PLATFORM_PROJECT:-}"
BUCKET=''
FAILURES=0
LIFECYCLE_TMP=''

usage() {
  cat <<'EOF'
Usage:
  exe_platform_bootstrap.sh --project <gcp-project-id> [options]
  EXE_PLATFORM_PROJECT=<gcp-project-id> exe_platform_bootstrap.sh [options]

Options:
  --project <id>     GCP project that owns the state bucket. Required; may come
                     from $EXE_PLATFORM_PROJECT instead.
  --bucket <name>    Override the derived bucket name <project-id>-exe-tofu-state.
  --dry-run          Print every gcloud command (and the lifecycle document) and
                     run none of them. Needs no credentials.
  --print-lifecycle  Print the lifecycle document (JSON) and exit.
  -h, --help         This text.
EOF
}

# The lifecycle document handed to `gcloud storage buckets update
# --lifecycle-file=`. `isLive: false` scopes the rule to NONCURRENT generations,
# so the live object -- the current state file -- is never a candidate for
# deletion; `numNewerVersions` caps how many superseded generations survive.
# Single source of truth: `--print-lifecycle` and the applied temp file both
# come from here, so what a reviewer reads is what gets uploaded.
lifecycle_json() {
  cat <<EOF
{
  "rule": [
    {
      "action": { "type": "Delete" },
      "condition": { "numNewerVersions": ${NONCURRENT_VERSIONS}, "isLive": false }
    }
  ]
}
EOF
}

# --- arguments ----------------------------------------------------------------
while (($#)); do
  case "$1" in
    --project)
      if (($# < 2)); then
        printf '%s\n' '--project needs a value' >&2
        usage >&2
        exit 1
      fi
      PROJECT="$2"
      shift
      ;;
    --project=*) PROJECT="${1#*=}" ;;
    --bucket)
      if (($# < 2)); then
        printf '%s\n' '--bucket needs a value' >&2
        usage >&2
        exit 1
      fi
      BUCKET="$2"
      shift
      ;;
    --bucket=*) BUCKET="${1#*=}" ;;
    --dry-run) DRY_RUN=1 ;;
    --print-lifecycle) PRINT_LIFECYCLE=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if ((PRINT_LIFECYCLE)); then
  lifecycle_json
  exit 0
fi

# Refuse rather than guess. Falling back to `gcloud config`'s active project
# would create -- or reconfigure -- a bucket in whatever project happened to be
# selected, which is the one unrecoverable mistake available here.
if [[ -z "${PROJECT}" ]]; then
  printf '%s\n' 'no project given: pass --project <id>, or set EXE_PLATFORM_PROJECT in the environment' >&2
  usage >&2
  exit 1
fi

BUCKET="${BUCKET:-${PROJECT}-exe-tofu-state}"

if ((DRY_RUN == 0)) && ! command -v gcloud >/dev/null 2>&1; then
  printf '%s\n' 'missing required tool: gcloud' >&2
  exit 1
fi

# Narration goes to fd 3 -- a duplicate of stdout -- so that a "would read" line
# emitted from inside a `$(...)` still reaches the reviewer instead of being
# captured into the variable the caller is reading.
exec 3>&1
say() { printf '%s\n' "$*" >&3; }
step() { printf '\n== %s ==\n' "$*" >&3; }
ok() { printf '  OK   %s\n' "$*" >&3; }
bad() {
  printf '  FAIL %s\n' "$*" >&3
  FAILURES=$((FAILURES + 1))
}

# The temp file lives under $TMPDIR, never inside the repo: it is derived from
# cloud config and this repo is public. Removed on every exit path.
cleanup() {
  if [[ -n "${LIFECYCLE_TMP}" ]]; then
    rm -f "${LIFECYCLE_TMP}"
  fi
}
trap cleanup EXIT

# Every mutating gcloud call goes through here. In --dry-run it is printed and
# NOT executed; that is the whole safety property of this script.
run_gcloud() {
  if ((DRY_RUN)); then
    printf '  + gcloud %s\n' "$*" >&3
    return 0
  fi
  gcloud "$@"
}

# Read one projected field off the live bucket, lower-cased (gcloud renders
# booleans as True/False and the location as ASIA-NORTHEAST1). Read-before-write:
# every converge step below asks first and only writes when the answer is wrong.
# In --dry-run the read is printed and answers empty, so each step falls through
# to its (also only printed) write and the full first-run command set is shown.
bucket_prop() {
  local projection="$1" raw
  if ((DRY_RUN)); then
    printf "  ? gcloud storage buckets describe gs://%s --project=%s --format='value(%s)'\n" \
      "${BUCKET}" "${PROJECT}" "${projection}" >&3
    return 0
  fi
  raw="$(gcloud storage buckets describe "gs://${BUCKET}" \
    --project="${PROJECT}" --format="value(${projection})" 2>/dev/null || true)"
  printf '%s' "${raw}" | tr '[:upper:]' '[:lower:]'
}

bucket_exists() {
  if ((DRY_RUN)); then
    printf '  ? gcloud storage buckets describe gs://%s --project=%s\n' \
      "${BUCKET}" "${PROJECT}" >&3
    say '  (dry-run: assuming absent, so the full create path is shown below)'
    return 1
  fi
  gcloud storage buckets describe "gs://${BUCKET}" \
    --project="${PROJECT}" --format='value(name)' >/dev/null 2>&1
}

assert_prop() {
  local label="$1" projection="$2" expected="$3" actual
  actual="$(bucket_prop "${projection}")"
  if [[ "${actual}" == "${expected}" ]]; then
    ok "${label}: ${actual}"
  else
    bad "${label}: expected '${expected}', got '${actual:-<unset>}'"
  fi
}

# --- banner -------------------------------------------------------------------
say "project      : ${PROJECT}"
say "state bucket : gs://${BUCKET}"
say ''
say 'desired end state:'
say "  location                    : ${LOCATION}"
say "  default storage class       : ${STORAGE_CLASS}"
say '  uniform bucket-level access : enabled'
say '  public access prevention    : enforced'
say '  object versioning           : enabled'
say "  noncurrent versions kept    : ${NONCURRENT_VERSIONS}"
say '  soft delete policy          : cleared (0s retention)'
if ((DRY_RUN)); then
  say ''
  say 'DRY RUN: no cloud state is touched.  + = would run,  ? = would read.'
fi

# --- 1. read before write -----------------------------------------------------
step 'read: does the bucket already exist?'
if bucket_exists; then
  say "  present: gs://${BUCKET} -- verifying its settings, not recreating it."
else
  # `--public-access-prevention` is the boolean flag; enabling it puts the
  # bucket's publicAccessPrevention into the `enforced` state (the default is
  # `inherited`, which is what we are guarding against).
  step 'create'
  run_gcloud storage buckets create "gs://${BUCKET}" \
    --project="${PROJECT}" \
    --location="${LOCATION}" \
    --default-storage-class="${STORAGE_CLASS}" \
    --uniform-bucket-level-access \
    --public-access-prevention
fi

# --- 2. converge each setting -------------------------------------------------
# A bucket that predates this script (or an older revision of it) can be missing
# any of these, so each is asked about and fixed independently rather than
# assumed from the create call above.
step 'converge: uniform bucket-level access'
if [[ "$(bucket_prop 'uniform_bucket_level_access')" == 'true' ]]; then
  ok 'already enabled'
else
  run_gcloud storage buckets update "gs://${BUCKET}" \
    --project="${PROJECT}" --uniform-bucket-level-access
fi

step 'converge: public access prevention (enforced)'
if [[ "$(bucket_prop 'public_access_prevention')" == 'enforced' ]]; then
  ok 'already enforced'
else
  run_gcloud storage buckets update "gs://${BUCKET}" \
    --project="${PROJECT}" --public-access-prevention
fi

step 'converge: object versioning'
if [[ "$(bucket_prop 'versioning_enabled')" == 'true' ]]; then
  ok 'already enabled'
else
  run_gcloud storage buckets update "gs://${BUCKET}" \
    --project="${PROJECT}" --versioning
fi

step "converge: lifecycle (keep at most ${NONCURRENT_VERSIONS} noncurrent versions)"
# All three fields are read up front rather than short-circuited inside one
# `&&` chain, so a --dry-run narrates every read it would perform.
lc_action="$(bucket_prop 'lifecycle_config.rule[0].action.type')"
lc_keep="$(bucket_prop 'lifecycle_config.rule[0].condition.numNewerVersions')"
lc_live="$(bucket_prop 'lifecycle_config.rule[0].condition.isLive')"
if [[ "${lc_action}" == 'delete' && "${lc_keep}" == "${NONCURRENT_VERSIONS}" \
  && "${lc_live}" == 'false' ]]; then
  ok 'already present'
else
  TMP_DIR="${TMPDIR:-/tmp}"
  LIFECYCLE_TMP="$(mktemp "${TMP_DIR%/}/exe-platform-lifecycle.XXXXXX")"
  lifecycle_json >"${LIFECYCLE_TMP}"
  if ((DRY_RUN)); then
    say '  would upload this document:'
    lifecycle_json >&3
  fi
  run_gcloud storage buckets update "gs://${BUCKET}" \
    --project="${PROJECT}" --lifecycle-file="${LIFECYCLE_TMP}"
fi

step 'converge: soft delete policy (disabled)'
# Soft delete retains deleted objects -- including the generations the lifecycle
# rule above prunes -- and bills for them. Clearing it is what makes the
# 10-version cap an actual ceiling rather than a rename.
#
# Three states are kept distinct on purpose: '0' is provably off, any other
# number is a billing window, and EMPTY means the field could not be read --
# which is NOT the same as off. A new GCS bucket is created with a 7-day soft
# delete policy by default, so an unproven read has to converge rather than
# assume, and `--clear-soft-delete-policy` is idempotent.
soft_retention="$(bucket_prop 'soft_delete_policy.retentionDurationSeconds')"
if [[ "${soft_retention}" == '0' ]]; then
  ok 'already disabled'
else
  run_gcloud storage buckets update "gs://${BUCKET}" \
    --project="${PROJECT}" --clear-soft-delete-policy
fi

# --- 3. verify ----------------------------------------------------------------
step 'verify'
if ((DRY_RUN)); then
  say '  skipped: nothing was changed (dry run).'
  say ''
  say "DRY RUN complete -- gs://${BUCKET} was not read or modified."
  exit 0
fi

assert_prop 'location                   ' 'location' "${LOCATION}"
assert_prop 'default storage class      ' 'default_storage_class' \
  "$(printf '%s' "${STORAGE_CLASS}" | tr '[:upper:]' '[:lower:]')"
assert_prop 'uniform bucket-level access' 'uniform_bucket_level_access' 'true'
assert_prop 'public access prevention   ' 'public_access_prevention' 'enforced'
assert_prop 'object versioning          ' 'versioning_enabled' 'true'
assert_prop 'lifecycle action           ' 'lifecycle_config.rule[0].action.type' 'delete'
assert_prop 'lifecycle numNewerVersions ' \
  'lifecycle_config.rule[0].condition.numNewerVersions' "${NONCURRENT_VERSIONS}"
assert_prop 'lifecycle isLive           ' \
  'lifecycle_config.rule[0].condition.isLive' 'false'

soft_retention="$(bucket_prop 'soft_delete_policy.retentionDurationSeconds')"
case "${soft_retention}" in
  0) ok 'soft delete policy         : disabled (0s retention)' ;;
  # An unreadable setting is an unverified one, never an assumed-off one.
  '') bad 'soft delete policy         : could not be read -- unverified' ;;
  *) bad "soft delete policy         : retention ${soft_retention}s, expected 0" ;;
esac

# --- 4. summary ---------------------------------------------------------------
step 'summary'
if ((FAILURES)); then
  say "  gs://${BUCKET}: ${FAILURES} setting(s) still wrong (listed above)."
  say '  Re-run to converge; if a FAIL persists, fix it before tofu init.'
  exit 1
fi
say "  gs://${BUCKET} ready: ${LOCATION}/${STORAGE_CLASS}, UBLA + PAP enforced,"
say "  versioned, at most ${NONCURRENT_VERSIONS} noncurrent versions, soft delete off."
say ''
say '  Next: cp tofu/exe-platform/terraform.tfvars.example tofu/exe-platform/terraform.tfvars'
say '        then: tofu -chdir=tofu/exe-platform init   (backend = the bucket above)'
