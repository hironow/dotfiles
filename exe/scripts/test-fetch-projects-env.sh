#!/usr/bin/env bash
# test-fetch-projects-env.sh — smoke tests for fetch-projects-env.sh.
#
# bash assertions only (no bats / shunit2 dependency). Each scenario
# runs the script in an isolated tempdir + mock gateway response,
# asserts the resulting drop-in content, and prints the case status.
#
# Pre-requisite: jq must be on PATH (the production script also
# falls back to single-mode if jq is missing, but the smoke matrix
# below covers the happy path that needs jq).

set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUT="${THIS_DIR}/fetch-projects-env.sh"
[[ -x "${SUT}" ]] || chmod +x "${SUT}"

failures=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$*"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$*" >&2; failures=$((failures + 1)); }

setup_case() {
    case_dir=$(mktemp -d)
    receiver_dir="${case_dir}/etc/systemd/system/dmail-receiver.service.d"
    emitter_dir="${case_dir}/etc/systemd/system/dmail-emitter.service.d"
    home_dir="${case_dir}/home"
    mkdir -p "${receiver_dir}" "${emitter_dir}" "${home_dir}"
    receiver_drop="${receiver_dir}/env.conf"
    emitter_drop="${emitter_dir}/env.conf"
}

# Spin up a tiny HTTP server backed by python so the script can curl
# a controlled response. Returns the URL on stdout.
spawn_mock_gateway() {
    local body_file="$1" status_code="${2:-200}"
    python3 - "${body_file}" "${status_code}" <<'PYEOF' &
import http.server, sys, threading
body_path = sys.argv[1]
status = int(sys.argv[2])
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        with open(body_path, "rb") as f:
            data = f.read()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *a, **kw):
        return
srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
print(f"http://127.0.0.1:{srv.server_address[1]}", flush=True)
srv.serve_forever()
PYEOF
    SERVER_PID=$!
    # Read URL from python stdout via /proc fd is awkward; instead use
    # the simpler approach: spawn synchronously and grab the URL.
}

# We use a helper that spawns + waits in a single call so the
# concurrency dance is contained.
run_with_mock_gateway() {
    local body_file="$1"
    local status_code="$2"
    shift 2

    # Start a background python server and capture its first stdout
    # line (the URL).
    local fifo=$(mktemp -u)
    mkfifo "${fifo}"
    python3 - "${body_file}" "${status_code}" >"${fifo}" 2>/dev/null &
    local pid=$!
    local server_url
    server_url=$(head -n 1 "${fifo}")
    rm -f "${fifo}"

    # Run the SUT against the mock URL.
    "$@" "${server_url}"
    local rc=$?
    kill "${pid}" 2>/dev/null || true
    wait "${pid}" 2>/dev/null || true
    return ${rc}
}

# Inline python — simpler than the helper above and avoids a fifo.
mock_gateway_run() {
    local body_file="$1"
    local status_code="$2"
    local extra_env="$3"
    setup_case
    local script
    script=$(cat <<PYEOF
import http.server, sys, threading, os
body = open("${body_file}", "rb").read()
status = ${status_code}
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a, **kw):
        return
srv = http.server.HTTPServer(("127.0.0.1", 0), H)
print(srv.server_address[1])
sys.stdout.flush()
srv.serve_forever()
PYEOF
)
    local port_log="${case_dir}/port.txt"
    python3 -c "${script}" >"${port_log}" 2>/dev/null &
    local pid=$!
    # wait briefly for server to print port
    local tries=0
    local port=""
    while [[ -z "${port}" && ${tries} -lt 20 ]]; do
        sleep 0.05
        if [[ -s "${port_log}" ]]; then
            port=$(head -n 1 "${port_log}")
        fi
        tries=$((tries + 1))
    done
    if [[ -z "${port}" ]]; then
        kill "${pid}" 2>/dev/null || true
        return 1
    fi

    env \
        RUNOPS_GATEWAY_URL="http://127.0.0.1:${port}" \
        RUNOPS_ADMIN_TOKEN="test-token" \
        WORKSPACE_HOME="${home_dir}" \
        DROP_IN_RECEIVER_DIR="${receiver_dir}" \
        DROP_IN_EMITTER_DIR="${emitter_dir}" \
        FETCH_PROJECTS_NO_RELOAD=1 \
        ${extra_env} \
        bash "${SUT}"
    local rc=$?
    kill "${pid}" 2>/dev/null || true
    wait "${pid}" 2>/dev/null || true
    return ${rc}
}

echo "Test 1: missing gateway URL → single-mode fallback"
setup_case
env -u RUNOPS_GATEWAY_URL -u RUNOPS_ADMIN_TOKEN \
    WORKSPACE_HOME="${home_dir}" \
    DROP_IN_RECEIVER_DIR="${receiver_dir}" \
    DROP_IN_EMITTER_DIR="${emitter_dir}" \
    FETCH_PROJECTS_NO_RELOAD=1 \
    bash "${SUT}" >/dev/null 2>&1
if grep -q "Multi-mode disabled" "${receiver_drop}" && grep -q "Multi-mode disabled" "${emitter_drop}"; then
    pass "missing env yields single-mode fallback drop-ins"
else
    fail "missing env should produce single-mode fallback drop-ins"
fi

echo "Test 2: happy path with two valid project ids"
setup_case
body_file="${case_dir}/body.json"
cat > "${body_file}" <<'EOF'
{"projects":[
    {"id":"foo","github_org":"hironow","github_repo":"demo","status":"active"},
    {"id":"bar","github_org":"hironow","github_repo":"another","status":"active"}
]}
EOF
mock_gateway_run "${body_file}" 200 "" >/dev/null 2>&1
if grep -q "PHONEWAVE_OUTBOX_DIRS_BY_PROJECT=foo:" "${receiver_drop}" \
    && grep -q ",bar:" "${receiver_drop}" \
    && grep -q "PHONEWAVE_PEER_RECEIVER_MODE=multi" "${receiver_drop}"; then
    pass "happy path emits multi-mode receiver drop-in"
else
    fail "happy path receiver drop-in missing expected env vars"
fi
if grep -q "PHONEWAVE_ARCHIVE_DIRS_BY_PROJECT=foo:" "${emitter_drop}" \
    && grep -q "PHONEWAVE_PEER_RECEIVER_MODE=multi" "${emitter_drop}"; then
    pass "happy path emits multi-mode emitter drop-in"
else
    fail "happy path emitter drop-in missing expected env vars"
fi
for pid in foo bar; do
    if [[ -d "${home_dir}/projects/${pid}/.phonewave/outbox" ]] \
        && [[ -d "${home_dir}/projects/${pid}/.phonewave/archive" ]]; then
        pass "happy path created project dirs for ${pid}"
    else
        fail "happy path missing project dirs for ${pid}"
    fi
done

echo "Test 3: invalid project ids skipped via defensive regex"
setup_case
body_file="${case_dir}/body.json"
cat > "${body_file}" <<'EOF'
{"projects":[
    {"id":"foo","status":"active"},
    {"id":"../etc","status":"active"},
    {"id":"with spaces","status":"active"},
    {"id":"foo,bar","status":"active"},
    {"id":"valid_id-2","status":"active"}
]}
EOF
mock_gateway_run "${body_file}" 200 "" >/dev/null 2>&1
if grep -q "foo:" "${receiver_drop}" \
    && grep -q "valid_id-2:" "${receiver_drop}" \
    && ! grep -q "etc:" "${receiver_drop}" \
    && ! grep -q "with spaces" "${receiver_drop}" \
    && ! grep -q "foo,bar" "${receiver_drop}"; then
    pass "regex-invalid ids skipped, valid ids retained"
else
    fail "drop-in should retain only regex-valid project ids"
    cat "${receiver_drop}" >&2
fi

echo "Test 4: zero projects in registry → single-mode fallback"
setup_case
body_file="${case_dir}/body.json"
echo '{"projects":[]}' > "${body_file}"
mock_gateway_run "${body_file}" 200 "" >/dev/null 2>&1
if grep -q "Multi-mode disabled" "${receiver_drop}"; then
    pass "empty registry yields single-mode fallback"
else
    fail "empty registry should yield single-mode fallback"
fi

echo "Test 5: gateway HTTP 500 → single-mode fallback (curl --max-time exit nonzero)"
setup_case
body_file="${case_dir}/body.json"
echo '{"error":"internal"}' > "${body_file}"
# curl --silent treats HTTP 500 as success unless --fail is used; the
# script does not use --fail so the JSON is parsed — but jq will emit
# an empty list and the script falls back. This case mostly exercises
# that "no projects extracted" path, which Test 4 also covers; we
# include it here to make the matrix explicit.
mock_gateway_run "${body_file}" 500 "" >/dev/null 2>&1
if grep -q "Multi-mode disabled" "${receiver_drop}"; then
    pass "HTTP 500 with non-projects body yields fallback"
else
    fail "HTTP 500 should yield single-mode fallback"
fi

if (( failures > 0 )); then
    printf '\n\033[31m%d test(s) failed\033[0m\n' "${failures}" >&2
    exit 1
fi
printf '\n\033[32mAll fetch-projects-env smoke tests passed\033[0m\n'
