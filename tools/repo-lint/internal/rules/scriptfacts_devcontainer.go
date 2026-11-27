package rules

import (
	"fmt"
	"regexp"
	"strings"
	"unicode/utf8"
)

// The dev container feature, its post-create step, the CI bootstrap, the
// Cursor setup and harden-env.
const (
	postCreate    = ".devcontainer/post-create.sh"
	ciBootstrap   = ".devcontainer/ci-bootstrap.sh"
	cursorInstall = ".cursor/install.sh"
	cursorStart   = ".cursor/start.sh"
	hardenEnv     = "scripts/harden_env.sh"
)

// The pinned mise key and the feature's check that uses it.
const (
	miseFingerprint = "24853EC9F655CE80B48E6C3A8B81C9D17413A06D"
	verifyFunction  = "verify_artifact_with_signed_checksums"
)

// devcontainerFeatureFacts: the feature's downloads retry, mise comes from
// the pinned tarball checked with the pinned key, and mise's data lives in
// /opt/mise.
func devcontainerFeatureFacts() Rule {
	return factRule(
		"devcontainer-feature-facts",
		"the dev container feature retries its downloads, installs mise from the pinned release checked with the pinned key, and keeps mise's data in /opt/mise",
		[]string{featureInstall, postCreate},
		[]scriptFact{
			// tests/unit/test_devcontainer_download_retries.py
			fact("test_the_scan_finds_every_download", featureScanFindsEveryDownload),
			fact("test_every_curl_retries_and_still_fails_on_http_errors", featureCurlsRetry),
			fact("test_git_fetches_retry", featureGitFetchesRetry),
			fact("test_apt_retries_too", pyMatches(featureInstall, `Acquire::Retries "\d+"`)),
			// tests/unit/test_devcontainer_mise_tarball.py
			fact("test_the_feature_installs_mise_without_its_apt_repository",
				lacks(featureInstall, "mise.jdx.dev/deb", "mise-archive-keyring"),
				aptInstallsNoMise),
			fact("test_the_feature_verifies_the_tarball_with_the_pinned_key",
				has(featureInstall,
					`MISE_BASE="https://github.com/jdx/mise/releases/download/v${MISE_VERSION}"`,
					`"${MISE_BASE}/SHASUMS256.asc"`,
					verifyFunction+" https://mise.jdx.dev/gpg-key.pub \\\n  "+miseFingerprint+" \\\n",
					`install -m 0755 "${MISE_TMP}/mise/bin/mise" /usr/local/bin/mise`)),
			fact("test_each_download_has_a_second_host",
				has(featureInstall,
					`MISE_HOST="https://mise.jdx.dev/v${MISE_VERSION}"`,
					`fetch_first "${MISE_TMP}/${MISE_FILE}" "${MISE_HOST}/${MISE_FILE}" "${MISE_BASE}/${MISE_FILE}"`+"\n",
					`fetch_first "${MISE_TMP}/SHASUMS256.asc" "${MISE_BASE}/SHASUMS256.asc" "${MISE_HOST}/SHASUMS256.asc"`+"\n")),
			fact("test_the_check_needs_no_more_than_the_tools_the_image_has", verifyNeedsOnlyImageTools),
			// tests/unit/test_mise_data_dir_relocation.py
			fact("test_feature_install_creates_opt_mise", pyMatches(featureInstall, `install\s+-d[^\n]*/opt/mise`)),
			fact("test_feature_install_does_not_use_home_share_mise", featureCodeKeepsOffHomeShare),
			fact("test_feature_install_writes_profile_d_with_data_dir", featureProfileExportsDataDir),
			fact("test_post_create_does_not_force_mise_offline_zero", pyNoMatch(postCreate, `\bMISE_OFFLINE=0\b`)),
			// tests/unit/test_sandbox_check_tools.py
			fact("test_quints_evaluator_is_built_from_a_pinned_commit", quintEvaluatorPinned),
			// tests/unit/test_podman_devcontainer_config.py
			fact("test_feature_installs_native_podman_without_changing_generated_versions",
				has(featureInstall, "podman uidmap", "podman --version", "Podman >=5")),
		},
	)
}

// aptInstallsNoMise is not re.search(r"apt-get install[^\n]*\bmise\b"):
// no apt-get install line names mise as a word.
func aptInstallsNoMise(files map[string]string) []string {
	text := files[featureInstall]
	for from := 0; ; {
		i := strings.Index(text[from:], "apt-get install")
		if i < 0 {
			return nil
		}
		start := from + i + len("apt-get install")
		end := len(text)
		if j := strings.IndexByte(text[start:], '\n'); j >= 0 {
			end = start + j
		}
		for k := start; ; {
			m := strings.Index(text[k:end], "mise")
			if m < 0 {
				break
			}
			at := k + m
			if pyBoundaryAt(text, at) && pyBoundaryAt(text, at+len("mise")) {
				return []string{featureInstall + " installs mise with apt-get: " + text[from+i:end]}
			}
			k = at + 1
		}
		from += i + 1
	}
}

// featureCommands is the test's commands(): logical lines (backslash
// continuations joined), comment and blank lines dropped.
func featureCommands(text string) []string {
	var out []string
	pending := ""
	for _, raw := range pySplitlines(text) {
		line := pyStrip(raw)
		if pending == "" && (line == "" || strings.HasPrefix(line, "#")) {
			continue
		}
		if strings.HasSuffix(line, `\`) {
			pending += line[:len(line)-1] + " "
			continue
		}
		out = append(out, pending+line)
		pending = ""
	}
	return out
}

// curlKeywords may stand before a curl that starts a command.
var curlKeywords = []string{"if", "then", "do", "else", "elif", "while", "until"}

// runsCurl is the test's curls() filter: curl followed by whitespace, at the
// start, after one of `;&|(!`, or after a keyword that is a whole word.
func runsCurl(command string) bool {
	for from := 0; ; {
		i := strings.Index(command[from:], "curl")
		if i < 0 {
			return false
		}
		at := from + i
		from = at + 1
		after, _ := utf8.DecodeRuneInString(command[at+len("curl"):])
		if at+len("curl") >= len(command) || !pyIsSpace(after) {
			continue
		}
		q := at
		for q > 0 {
			r, size := utf8.DecodeLastRuneInString(command[:q])
			if !pyIsSpace(r) {
				break
			}
			q -= size
		}
		if q == 0 || strings.ContainsAny(command[q-1:q], ";&|(!") {
			return true
		}
		for _, k := range curlKeywords {
			if strings.HasSuffix(command[:q], k) && pyBoundaryAt(command, q-len(k)) && pyBoundaryAt(command, q) {
				return true
			}
		}
	}
}

func featureCurls(text string) []string {
	var out []string
	for _, c := range featureCommands(text) {
		if runsCurl(c) {
			out = append(out, c)
		}
	}
	return out
}

// featureScanFindsEveryDownload: at least nine code lines run `curl -`, and
// the command scan finds as many.
func featureScanFindsEveryDownload(files map[string]string) []string {
	text := files[featureInstall]
	lines := 0
	for line := range strings.SplitSeq(text, "\n") {
		if strings.HasPrefix(strings.TrimLeftFunc(line, pyIsSpace), "#") {
			continue
		}
		for from := 0; ; {
			i := strings.Index(line[from:], "curl -")
			if i < 0 {
				break
			}
			if pyBoundaryAt(line, from+i) {
				lines++
				break
			}
			from += i + 1
		}
	}
	var out []string
	if lines < 9 {
		out = append(out, fmt.Sprintf("the feature must download at least 9 times with curl -, found %d", lines))
	}
	if n := len(featureCurls(text)); n != lines {
		out = append(out, fmt.Sprintf("the command scan finds %d curl downloads, the lines hold %d", n, lines))
	}
	return out
}

// featureCurlsRetry: each curl fails on an HTTP error (-f in a flag
// cluster) and retries a bounded number of times, on every error, with a
// delay.
func featureCurlsRetry(files map[string]string) []string {
	var out []string
	for _, c := range featureCurls(files[featureInstall]) {
		if !curlHasFailFlag(c) {
			out = append(out, "no -f (fail on HTTP error): "+c)
		}
		if !hasFlagWithCount(c, "--retry ") {
			out = append(out, "no bounded --retry: "+c)
		}
		if !strings.Contains(c, "--retry-all-errors") {
			out = append(out, "a 5xx or reset is not retried: "+c)
		}
		if !hasFlagWithCount(c, "--retry-delay ") {
			out = append(out, "no --retry-delay: "+c)
		}
	}
	return out
}

// curlHasFailFlag is r"(?:^|\s)-\w*f\w*(?:\s|$)": a dash at the start or
// after whitespace, a run of word characters holding f, then whitespace or
// the end.
func curlHasFailFlag(c string) bool {
	for i := range len(c) {
		if c[i] != '-' {
			continue
		}
		if i > 0 {
			r, _ := utf8.DecodeLastRuneInString(c[:i])
			if !pyIsSpace(r) {
				continue
			}
		}
		j := i + 1
		for j < len(c) {
			r, size := utf8.DecodeRuneInString(c[j:])
			if !pyWordRune(r) {
				break
			}
			j += size
		}
		r, _ := utf8.DecodeRuneInString(c[j:])
		if strings.Contains(c[i+1:j], "f") && (j == len(c) || pyIsSpace(r)) {
			return true
		}
	}
	return false
}

// hasFlagWithCount is re.search(flag + r"\d+\b", c).
func hasFlagWithCount(c, flag string) bool {
	for from := 0; ; {
		i := strings.Index(c[from:], flag)
		if i < 0 {
			return false
		}
		if pyDigitsThenBoundary(c, from+i+len(flag)) {
			return true
		}
		from += i + 1
	}
}

// featureGitFetchesRetry: every command that fetches or clones with git goes
// through retry_git, and the scan finds at least one.
func featureGitFetchesRetry(files map[string]string) []string {
	var fetches []string
	for _, c := range featureCommands(files[featureInstall]) {
		rest, ok := strings.CutPrefix(c, "retry_git")
		if !ok {
			rest, ok = strings.CutPrefix(c, "git")
		}
		if !ok || rest == "" {
			continue
		}
		first, size := utf8.DecodeRuneInString(rest)
		if !pyIsSpace(first) {
			continue
		}
		if pyHasWord(rest[size:], "fetch") || pyHasWord(rest[size:], "clone") {
			fetches = append(fetches, c)
		}
	}
	if len(fetches) == 0 {
		return []string{"the scan found no git fetch"}
	}
	var out []string
	for _, c := range fetches {
		if !strings.HasPrefix(c, "retry_git ") {
			out = append(out, "a git fetch without retry_git: "+c)
		}
	}
	return out
}

var verifyFunctionBody = regexp.MustCompile(`(?ms)^` + verifyFunction + `\(\) \{\n.*?^\}\n`)

// verifyNeedsOnlyImageTools: the check uses gpg, sha256sum, mktemp, awk and
// grep, which the image has before mise.
func verifyNeedsOnlyImageTools(files map[string]string) []string {
	body := verifyFunctionBody.FindString(files[featureInstall])
	if body == "" {
		return []string{verifyFunction + " not found"}
	}
	return has(featureInstall, "gpg ", "sha256sum", "mktemp", "awk", "grep")(map[string]string{featureInstall: body})
}

var homeShareMise = []*regexp.Regexp{
	regexp.MustCompile(`/root/\.local/share/mise`),
	regexp.MustCompile(`\$HOME/\.local/share/mise`),
}

// featureCodeKeepsOffHomeShare: no code line names the old data dir.
func featureCodeKeepsOffHomeShare(files map[string]string) []string {
	code := strings.Join(pyCodeLines(files[featureInstall]), "\n")
	var out []string
	for _, re := range homeShareMise {
		if re.MatchString(code) {
			out = append(out, "the feature still references "+re.String())
		}
	}
	return out
}

var (
	featureProfileHeredoc = regexp.MustCompile(`(?s)cat > /etc/profile\.d/dotfiles-mise\.sh <<'PROFILE'(.*?)PROFILE`)
	exportDataDir         = pyCompile(`export\s+MISE_DATA_DIR=/opt/mise`)
)

// featureProfileExportsDataDir: the profile.d file exports the data dir and
// puts its shims on PATH.
func featureProfileExportsDataDir(files map[string]string) []string {
	m := featureProfileHeredoc.FindStringSubmatch(files[featureInstall])
	if m == nil {
		return []string{"could not locate the profile.d heredoc"}
	}
	var out []string
	if !exportDataDir.Search(m[1]) {
		out = append(out, "/etc/profile.d/dotfiles-mise.sh must export MISE_DATA_DIR=/opt/mise")
	}
	if !strings.Contains(m[1], "/opt/mise/shims") {
		out = append(out, "/etc/profile.d/dotfiles-mise.sh must add /opt/mise/shims to PATH")
	}
	return out
}

// ciBootstrapFacts: the CI bootstrap uses the canonical pins in order and
// keeps every Podman action inside the Podman mode.
func ciBootstrapFacts() Rule {
	return factRule(
		"ci-bootstrap-facts",
		"the CI bootstrap runs only on an ephemeral hosted runner, installs the pinned tools in order, and touches Podman only in its Podman mode",
		[]string{ciBootstrap},
		[]scriptFact{
			// tests/unit/test_podman_ci_workflows.py
			fact("test_bootstrap_is_ci_only_and_uses_canonical_pins_and_order",
				has(ciBootstrap,
					`"${GITHUB_ACTIONS:-}" != true`,
					`"${RUNNER_ENVIRONMENT:-}" != github-hosted`,
					`bash "$repo/install.sh" --podman-only`,
					"source['bootstrap']['mise']",
					"generated mise tools missing",
					"MISE_GLOBAL_CONFIG_FILE",
					"second_tools=(npm:@devcontainers/cli pypi:podman-compose)",
					"systemctl --user start podman.socket",
					`"host"]["remoteSocket"]["path"]`,
					"PODMAN_COMPOSE_PROVIDER=podman-compose",
					"Docker remains on PATH"),
				order(ciBootstrap, "mise install bun uv node just", `mise install "${second_tools[@]}"`),
				lacks(ciBootstrap, "sudo podman"),
				noMatch(ciBootstrap, `podman-compose[=@][0-9]|devcontainers/cli[=@][0-9]`)),
			fact("test_tools_only_mode_installs_the_check_tools_and_never_touches_podman",
				has(ciBootstrap,
					"--tools-only) mode=tools-only",
					"go vp markdownlint-cli2 aqua:golangci/golangci-lint",
					`if [[ "$mode" == podman ]]; then`),
				podmanActionsIndented),
		},
	)
}

// podmanActionsIndented: the first line holding each Podman action is
// indented inside the Podman-mode branch.
func podmanActionsIndented(files map[string]string) []string {
	lines := pySplitlines(files[ciBootstrap])
	var out []string
	for _, action := range []string{`install.sh" --podman-only`, "apt-get install", "systemctl --user"} {
		found := false
		for _, line := range lines {
			if strings.Contains(line, action) {
				found = true
				if !strings.HasPrefix(line, "  ") {
					out = append(out, fmt.Sprintf("%q must be indented inside the Podman mode: %s", action, line))
				}
				break
			}
		}
		if !found {
			out = append(out, fmt.Sprintf("no line runs %q", action))
		}
	}
	return out
}

// cursorFacts: the Cursor setup provisions rootless Podman, never Docker
// or a socket anyone can use.
func cursorFacts() Rule {
	return factRule(
		"cursor-facts",
		"the Cursor environment provisions rootless native Podman, never Docker, a docker group or a world-writable socket",
		[]string{cursorInstall, cursorStart},
		[]scriptFact{
			// tests/unit/test_podman_devcontainer_config.py
			fact("test_cursor_never_sets_up_docker_or_world_writable_sockets", cursorStaysRootless),
		},
	)
}

func cursorStaysRootless(files map[string]string) []string {
	install, start := files[cursorInstall], files[cursorStart]
	both := install + start // the test searched the two joined
	var out []string
	for _, forbidden := range []string{"docker.io", "dockerd", "daemon.json", "chmod 666", "usermod -aG docker"} {
		if strings.Contains(both, forbidden) {
			out = append(out, "the Cursor setup must not hold "+forbidden)
		}
	}
	out = append(out, has(cursorInstall, "--podman-only", "fuse-overlayfs")(files)...)
	out = append(out, has(cursorStart, "podman.socket")(files)...)
	return append(out, lacks(cursorStart, "sudo podman")(files)...)
}

// hardenTelemetryOff is test_agent_tool_telemetry.py's TELEMETRY_OFF.
var hardenTelemetryOff = [][2]string{{"RTK_TELEMETRY_DISABLED", "1"}, {"HEADROOM_BEACON", "off"}, {"DO_NOT_TRACK", "1"}}

// hardenEnvFacts: on native Windows harden-env repairs the persisted User
// PATH and turns the tools' telemetry off, and never writes the Machine
// scope.
func hardenEnvFacts() Rule {
	return factRule(
		"harden-env-facts",
		"harden-env repairs the Windows User PATH and turns telemetry off for the user, never writing the Machine scope",
		[]string{hardenEnv},
		[]scriptFact{
			// tests/unit/test_harden_env.py
			fact("test_appends_missing_git_dirs_to_windows_user_path",
				matches(hardenEnv, `for _unix_dir in /usr/bin /cmd`, `SetEnvironmentVariable[^\n]*'User'`, `APPDATA`),
				has(hardenEnv, `cygpath -w "$_unix_dir"`, "GetEnvironmentVariable", "HARDEN_ENV_SKIP_WIN_PATH"),
				hardenEnvLeavesMachineScope),
			fact("test_powershell_fallback_when_system32_off_path", has(hardenEnv, "WindowsPowerShell/v1.0/powershell.exe")),
			// tests/unit/test_agent_tool_telemetry.py
			fact("test_harden_env_persists_the_telemetry_off_for_windows", hardenEnvTurnsTelemetryOff),
		},
	)
}

// hardenEnvLeavesMachineScope: once the Machine PATH read is set aside, no
// command names the Machine scope.
func hardenEnvLeavesMachineScope(files map[string]string) []string {
	rest := strings.ReplaceAll(files[hardenEnv], "GetEnvironmentVariable('Path','Machine')", "")
	if strings.Contains(rest, `'Machine')"`) {
		return []string{"harden-env must never write the Machine scope"}
	}
	return nil
}

func hardenEnvTurnsTelemetryOff(files map[string]string) []string {
	var out []string
	for _, kv := range hardenTelemetryOff {
		re := regexp.MustCompile(`SetEnvironmentVariable\('` + kv[0] + `', '` + kv[1] + `', 'User'\)`)
		if !re.MatchString(files[hardenEnv]) {
			out = append(out, fmt.Sprintf("harden-env does not persist %s=%s for the Windows user", kv[0], kv[1]))
		}
	}
	return out
}

var (
	quintRev     = regexp.MustCompile(`\A[0-9a-f]{40}\z`)
	quintVersion = pyCompile(`\Av\d+\.\d+\.\d+\z`)
)

// featureAssignment is the test's assignment(): the first `NAME="..."` at
// a line start.
func featureAssignment(text, name string) (string, bool) {
	m := regexp.MustCompile(`(?m)^` + regexp.QuoteMeta(name) + `="([^"]*)"`).FindStringSubmatch(text)
	if m == nil {
		return "", false
	}
	return m[1], true
}

// quintEvaluatorPinned: quint's evaluator is built from a pinned commit of a
// released version, with its lockfile, into the path quint checks first.
func quintEvaluatorPinned(files map[string]string) []string {
	text := files[featureInstall]
	var out []string
	if rev, ok := featureAssignment(text, "QUINT_EVALUATOR_REV"); !ok || !quintRev.MatchString(rev) {
		out = append(out, "QUINT_EVALUATOR_REV must be a full commit hash")
	}
	if v, ok := featureAssignment(text, "QUINT_EVALUATOR_VERSION"); !ok || !quintVersion.Search(v) {
		out = append(out, "QUINT_EVALUATOR_VERSION must be a release tag vN.N.N")
	}
	return append(out, has(featureInstall,
		"cargo build --release --locked",
		`"${QUINT_HOME}/rust-evaluator-${QUINT_EVALUATOR_VERSION}/quint_evaluator"`)(files)...)
}
