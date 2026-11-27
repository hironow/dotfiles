package rules

import (
	"strings"
	"testing"
)

const featureCurl = `curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 -o "$t" https://example.com/`

var featureFixture = `set -euo pipefail
echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries
apt-get install -y podman uidmap
podman --version # Podman >=5 is required
` + strings.Repeat(featureCurl+"a\n", 9) + `verify_artifact_with_signed_checksums() {
  tmp="$(mktemp -d)"
  gpg --batch --import "$1"
  awk '{print $1}' "$3" | grep -F x | sha256sum -c
}
retry_git() {
  for i in 1 2 3; do git "$@" && return; done
}
retry_git clone https://example.com/a.git
install -d -m 0755 /opt/mise
cat > /etc/profile.d/dotfiles-mise.sh <<'PROFILE'
export MISE_DATA_DIR=/opt/mise
export PATH="/opt/mise/shims:$PATH"
PROFILE
MISE_BASE="https://github.com/jdx/mise/releases/download/v${MISE_VERSION}"
MISE_HOST="https://mise.jdx.dev/v${MISE_VERSION}"
fetch_first "${MISE_TMP}/${MISE_FILE}" "${MISE_HOST}/${MISE_FILE}" "${MISE_BASE}/${MISE_FILE}"
fetch_first "${MISE_TMP}/SHASUMS256.asc" "${MISE_BASE}/SHASUMS256.asc" "${MISE_HOST}/SHASUMS256.asc"
verify_artifact_with_signed_checksums https://mise.jdx.dev/gpg-key.pub \
  24853EC9F655CE80B48E6C3A8B81C9D17413A06D \
  "${MISE_TMP}/SHASUMS256.asc" "${MISE_TMP}/${MISE_FILE}"
install -m 0755 "${MISE_TMP}/mise/bin/mise" /usr/local/bin/mise
QUINT_EVALUATOR_REV="0123456789abcdef0123456789abcdef01234567"
QUINT_EVALUATOR_VERSION="v0.5.0"
cargo build --release --locked
cp target/release/quint_evaluator "${QUINT_HOME}/rust-evaluator-${QUINT_EVALUATOR_VERSION}/quint_evaluator"
`

func TestDevcontainerFeatureFacts(t *testing.T) {
	f := featureInstall
	base := func() Inputs { return Inputs{f: featureFixture, postCreate: "mise install\n"} }
	runCases(t, devcontainerFeatureFacts(), base, []ruleCase{
		{"a download is gone", edit(f, featureCurl+"a\n", ""), "test_the_scan_finds_every_download"},
		{"a curl gives up on a reset", edit(f, featureCurl+"a\n", strings.Replace(featureCurl, " --retry-all-errors", "", 1)+"a\n"), "test_every_curl_retries_and_still_fails_on_http_errors"},
		{"a git clone does not retry", edit(f, "retry_git clone https://example.com/a.git", "git clone https://example.com/a.git"), "test_git_fetches_retry"},
		{"apt does not retry", edit(f, "echo 'Acquire::Retries \"5\";' > /etc/apt/apt.conf.d/80-retries\n", ""), "test_apt_retries_too"},
		{"mise comes from apt", edit(f, "apt-get install -y podman uidmap\n", "apt-get install -y podman uidmap\napt-get install -y mise\n"), "test_the_feature_installs_mise_without_its_apt_repository"},
		{"another key is trusted", edit(f, "  24853EC9F655CE80B48E6C3A8B81C9D17413A06D \\\n", "  0000000000000000000000000000000000000000 \\\n"), "test_the_feature_verifies_the_tarball_with_the_pinned_key"},
		{"one host only", edit(f, "MISE_HOST=\"https://mise.jdx.dev/v${MISE_VERSION}\"\n", ""), "test_each_download_has_a_second_host"},
		{"the check needs a new tool", edit(f, "awk '{print $1}' \"$3\" | ", "jq -r . \"$3\" | "), "test_the_check_needs_no_more_than_the_tools_the_image_has"},
		{"/opt/mise is not made", edit(f, "install -d -m 0755 /opt/mise\n", ""), "test_feature_install_creates_opt_mise"},
		{"the old data dir is used", edit(f, "install -d -m 0755 /opt/mise\n", "install -d -m 0755 /opt/mise\nmise install --data-dir /root/.local/share/mise\n"), "test_feature_install_does_not_use_home_share_mise"},
		{"profile.d sets no data dir", edit(f, "export MISE_DATA_DIR=/opt/mise\n", ""), "test_feature_install_writes_profile_d_with_data_dir"},
		{"post-create forces online", edit(postCreate, "mise install\n", "MISE_OFFLINE=0 mise install\n"), "test_post_create_does_not_force_mise_offline_zero"},
		{"no uidmap", edit(f, "podman uidmap", "podman"), "test_feature_installs_native_podman_without_changing_generated_versions"},
		{"quint's evaluator from a branch", edit(f, `QUINT_EVALUATOR_REV="0123456789abcdef0123456789abcdef01234567"`, `QUINT_EVALUATOR_REV="main"`), "test_quints_evaluator_is_built_from_a_pinned_commit"},
	})
}

func TestFeatureCurlScanReadsLikeTheTest(t *testing.T) {
	for _, c := range []struct {
		command string
		runs    bool
	}{
		{"curl -fsSL x", true},
		{"if curl -fsSL x; then :; fi", true},
		{"x && curl -f y", true},
		{"apt-get install -y curl jq", false},
		{"ifcurl -f x", false},
		{"éif curl -f x", false},
	} {
		if got := runsCurl(c.command); got != c.runs {
			t.Errorf("runsCurl(%q) = %v, want %v", c.command, got, c.runs)
		}
	}
	if hasFlagWithCount("curl --retry 3é", "--retry ") {
		t.Error("a count glued to a letter is not \\d+\\b")
	}
	if !curlHasFailFlag("curl -fsSL x") || curlHasFailFlag("curl -sSL x") || curlHasFailFlag("curl x-f") {
		t.Error("the -f flag is read as the test's regex reads it")
	}
}

const ciBootstrapFixture = `mode=podman
case "${1:-}" in
  --tools-only) mode=tools-only ;;
esac
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then exit 1; fi
if [[ "$mode" == podman ]]; then
  bash "$repo/install.sh" --podman-only
  sudo -n apt-get install -y uidmap
fi
required_tools='bun node uv just go vp markdownlint-cli2 aqua:golangci/golangci-lint'
python3 - <<'PY'
pin = source['bootstrap']['mise']
raise SystemExit("generated mise tools missing")
PY
export MISE_GLOBAL_CONFIG_FILE=x
mise install bun uv node just
second_tools=(npm:@devcontainers/cli pypi:podman-compose)
mise install "${second_tools[@]}"
if [[ "$mode" == podman ]]; then
  systemctl --user start podman.socket
  sock="$(python3 -c 'print(j["host"]["remoteSocket"]["path"])')"
  echo "PODMAN_COMPOSE_PROVIDER=podman-compose" >> "$GITHUB_ENV"
  echo "Docker remains on PATH"
fi
`

func TestCiBootstrapFacts(t *testing.T) {
	c := ciBootstrap
	runCases(t, ciBootstrapFacts(), func() Inputs { return Inputs{c: ciBootstrapFixture} }, []ruleCase{
		{"it runs anywhere", edit(c, `"${GITHUB_ACTIONS:-}" != true || `, ""), "test_bootstrap_is_ci_only_and_uses_canonical_pins_and_order"},
		{"the second tools come first", func(in Inputs) {
			edit(c, "mise install bun uv node just\n", "")(in)
			edit(c, "mise install \"${second_tools[@]}\"\n", "mise install \"${second_tools[@]}\"\nmise install bun uv node just\n")(in)
		}, "test_bootstrap_is_ci_only_and_uses_canonical_pins_and_order"},
		{"podman runs as root", edit(c, "  systemctl --user start podman.socket\n", "  systemctl --user start podman.socket\n  sudo podman info\n"), "test_bootstrap_is_ci_only_and_uses_canonical_pins_and_order"},
		{"a tool version is pinned here", edit(c, "pypi:podman-compose)", "pypi:podman-compose==1.5.0)"), "test_bootstrap_is_ci_only_and_uses_canonical_pins_and_order"},
		{"tools-only starts the socket", edit(c, "  systemctl --user start podman.socket\n", "systemctl --user start podman.socket\n"), "test_tools_only_mode_installs_the_check_tools_and_never_touches_podman"},
		{"no tools-only mode", edit(c, "  --tools-only) mode=tools-only ;;\n", ""), "test_tools_only_mode_installs_the_check_tools_and_never_touches_podman"},
	})
}

func TestCursorFacts(t *testing.T) {
	base := func() Inputs {
		return Inputs{
			cursorInstall: "bash ./install.sh --podman-only\napt-get install -y fuse-overlayfs\n",
			cursorStart:   "systemctl --user start podman.socket\n",
		}
	}
	runCases(t, cursorFacts(), base, []ruleCase{
		{"the user joins the docker group", edit(cursorInstall, "apt-get install -y fuse-overlayfs\n", "apt-get install -y fuse-overlayfs\nsudo usermod -aG docker \"$USER\"\n"), "test_cursor_never_sets_up_docker_or_world_writable_sockets"},
		{"the socket opens to everyone", edit(cursorStart, "systemctl --user start podman.socket\n", "systemctl --user start podman.socket\nchmod 666 \"$socket\"\n"), "test_cursor_never_sets_up_docker_or_world_writable_sockets"},
		{"podman runs as root", edit(cursorStart, "systemctl --user start podman.socket\n", "sudo podman system service\n"), "test_cursor_never_sets_up_docker_or_world_writable_sockets"},
		{"a full install", edit(cursorInstall, "bash ./install.sh --podman-only\n", "bash ./install.sh\n"), "test_cursor_never_sets_up_docker_or_world_writable_sockets"},
	})
}

const hardenFixture = `_powershell() {
  powershell.exe "$@" || "$SYSTEMROOT/System32/WindowsPowerShell/v1.0/powershell.exe" "$@"
}
if [ -n "${APPDATA:-}" ] && [ -z "${HARDEN_ENV_SKIP_WIN_PATH:-}" ]; then
  _persisted="$(_powershell -Command "[Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')")"
  for _unix_dir in /usr/bin /cmd; do
    _win_dir="$(cygpath -w "$_unix_dir")"
    _powershell -Command "[Environment]::SetEnvironmentVariable('Path', 'x', 'User')"
  done
  _powershell -Command "[Environment]::SetEnvironmentVariable('RTK_TELEMETRY_DISABLED', '1', 'User'); [Environment]::SetEnvironmentVariable('HEADROOM_BEACON', 'off', 'User'); [Environment]::SetEnvironmentVariable('DO_NOT_TRACK', '1', 'User')"
fi
`

func TestHardenEnvFacts(t *testing.T) {
	h := hardenEnv
	runCases(t, hardenEnvFacts(), func() Inputs { return Inputs{h: hardenFixture} }, []ruleCase{
		{"the Machine scope is written", edit(h, "  done\n", "  done\n  _powershell -Command \"[Environment]::SetEnvironmentVariable('Path', 'y', 'Machine')\"\n"), "test_appends_missing_git_dirs_to_windows_user_path"},
		{"git's cmd dir is left out", edit(h, "for _unix_dir in /usr/bin /cmd", "for _unix_dir in /usr/bin"), "test_appends_missing_git_dirs_to_windows_user_path"},
		{"no absolute powershell.exe", edit(h, ` || "$SYSTEMROOT/System32/WindowsPowerShell/v1.0/powershell.exe" "$@"`, ""), "test_powershell_fallback_when_system32_off_path"},
		{"DO_NOT_TRACK stays unset", edit(h, "; [Environment]::SetEnvironmentVariable('DO_NOT_TRACK', '1', 'User')", ""), "test_harden_env_persists_the_telemetry_off_for_windows"},
	})
}
