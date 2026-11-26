package rules

import (
	"fmt"
	"regexp"
	"strings"
)

// The runner GC scripts (ADR-0035, ADR-0067) and the tests that read them.
const (
	gcSh           = "scripts/runner_gc.sh"
	gcWin          = "scripts/runner_gc_win.ps1"
	gcInstallSh    = "scripts/install_runner_gc.sh"
	gcInstallWin   = "scripts/install_runner_gc_win.ps1"
	diskGcSh       = "scripts/disk_gc.sh"
	compactSh      = "scripts/wsl_compact.sh"
	vhdxLib        = "scripts/wsl_vhdx_lib.sh"
	fsckSh         = "scripts/wsl_fsck.sh"
	githubStatusSh = "scripts/gc_github_status.sh"
	gcModel        = "scripts/spec/podman_image_gc.qnt"
)

// runnerGcFacts: the runner GC, disk GC, compaction and status scripts keep
// what the tests that read them held. Findings name the removed test of
// tests/unit/test_runner_gc.py and its neighbours.
func runnerGcFacts() Rule {
	return factRule(
		"runner-gc-facts",
		"the runner GC scripts keep their guards: job detection, no unfiltered prune, advisory compaction, the hook's shape, the workspace sweep's proofs",
		[]string{gcSh, gcWin, gcInstallSh, gcInstallWin, diskGcSh, compactSh, vhdxLib, fsckSh, gcStatusScript, githubStatusSh, gcModel},
		runnerGcFactList,
	)
}

var runnerGcFactList = []scriptFact{
	fact("test_job_detection_uses_exact_name_match",
		matches(gcSh, `pgrep\s+-x\s+Runner\.Worker`),
		noLine(gcSh, `^\s*[^#]*pgrep\s+(-\w*f\w*\s+)`)),
	fact("test_dispatchers_disable_msys_path_conversion", dispatchersDisableMsys),
	fact("test_image_identity_is_strict_and_separate_from_container_identity",
		has(gcSh, "^(sha256:)?([a-f0-9]{64})$", "select(.Id == $id", `reference="$(_normalize_image_id "$reference")"`),
		has(gcWin, `\A(?:sha256:)?([a-f0-9]{64})\z`, "$container.Id -cne $containerId", "$references += ConvertTo-PodmanImageId $container.Image")),
	fact("test_gc_never_reclaims_unfiltered_persistent_cache", noUnfilteredPrune(gcSh), noUnfilteredPrune(gcWin)),
	fact("test_installer_upserts_hook_without_duplicating",
		matches(gcInstallSh, `grep -v "\^\$\{_hook_key\}="`),
		noLine(gcInstallSh, `^\s*[^#]*\bsed\s+-i\b`)),
	fact("test_compaction_stays_advisory",
		has(compactSh, "--shutdown"),
		noMatch(compactSh, `(?m)^\s*[^#]*wsl\.exe --shutdown`, `(?m)^\s*[^#]*--allow-unsafe`, `(?m)^\s*[^#]*--set-sparse\s+(true|1)\b`)),
	fact("test_windows_gc_podman_calls_carry_a_watchdog",
		has(gcWin, "Invoke-PodmanGuarded", "timed out"),
		noLine(gcWin, `^\s*[^#]*&\s+podman\b`)),
	fact("test_windows_installer_upserts_hook_without_bom",
		has(gcInstallWin, "UTF8Encoding($false)", `-notmatch "^$hookKey="`, "Unregister-ScheduledTask")),
	fact("test_windows_entrypoint_drives_both_runners",
		has(gcSh, "wsl.exe", "runner_gc_win.ps1"),
		has(gcInstallSh, "wsl.exe", "install_runner_gc_win.ps1"),
		lacks(gcSh, "exec wsl.exe"),
		lacks(gcInstallSh, "exec wsl.exe")),
	fact("test_diag_logs_are_rotated_on_the_linux_leg",
		has(gcSh, "_diag"),
		matches(gcSh, `-mtime\s+\+`)),
	fact("test_toolcache_keeps_the_newest_patch_of_each_series",
		has(gcSh, "RUNNER_GC_TOOLCACHE_KEEP"),
		matches(gcSh, `(?i)series`)),
	fact("test_toolcache_reaping_is_semver_ordered_and_atomic",
		has(gcSh, "_tool"),
		matches(gcSh, `\bsort\s+-V\b`),
		noLine(gcSh, `^\s*[^#]*\bsort\s+-r?\s*$`, `^\s*[^#]*\bsort\s+-r\b`)),
	fact("test_toolcache_reaping_never_races_a_running_job",
		matches(gcSh, `if \[ "\$FORCE" != "1" \] && _foreign_worker`, `(?m)^if _foreign_worker; then$`)),
	fact("test_workspace_sweep_protects_the_live_checkout",
		has(gcWin, "RUNNER_WORKSPACE", "GITHUB_WORKSPACE")),
	fact("test_workspace_sweep_uses_an_explicit_runner_dir_allowlist",
		has(gcWin, "_actions", "_tool", "_temp", "_update", "_PipelineMapping")),
	fact("test_counted_collections_are_wrapped_for_powershell_51", countedCollectionsWrapped),
	fact("test_stale_version_pruning_requires_a_resolvable_symlink",
		anyOf(has(gcWin, "LinkType"), has(gcWin, "ResolvedTarget"))),
	fact("test_the_tests_start_the_windows_gc_as_runner_gc_sh_does", windowsGcStart),
	fact("test_gc_discards_freed_blocks_back_to_the_host",
		matches(gcSh, `(?m)^\s*[^#]*\bfstrim\b`, `if\s+fstrim\b|fstrim[^\n]*\|\|`)),
	fact("test_windows_dispatch_falls_back_to_the_checkout",
		matches(gcSh, `if \[ -x /usr/local/bin/runner-gc\.sh \]`)),
	fact("test_disk_gc_reaches_the_wsl_runner_user",
		has(diskGcSh, "wsl.exe", "DISK_GC_NO_WSL"),
		noMatch(diskGcSh, `wsl\.exe[^\n]*-u root`)),
	fact("test_disk_gc_uses_go_clean_for_the_module_cache", has(diskGcSh, "go clean -modcache")),
	fact("test_disk_gc_finds_mise_managed_tools", has(diskGcSh, "mise/shims")),
	fact("test_disk_gc_keeps_huggingface_opt_in", has(diskGcSh, "DISK_GC_HUGGINGFACE"), huggingfaceNotUnconditional),
	fact("test_disk_gc_huggingface_optin_reaches_both_legs", huggingfaceOnBothLegs),
	fact("test_compaction_measures_allocated_not_logical_size", has(compactSh, "du -B1")),
	fact("test_compaction_resolves_vhdx_for_the_target_distro",
		lacks(compactSh, "head -1"),
		lacks(vhdxLib, "head -1"),
		has(vhdxLib, "Lxss", "DistributionName"),
		has(compactSh, "wsl_vhdx_path")),
	fact("test_hook_payload_carries_a_script_extension",
		matches(gcInstallSh, `_dest="/usr/local/bin/runner-gc\.sh"`)),
	fact("test_windows_hook_is_a_path_not_a_command_line",
		matches(gcInstallWin, `(?m)^\s*\$hookCmd\s*=\s*\$payload\s*(-replace\s+'\\\\',\s*'/')?\s*$`)),
	fact("test_status_never_claims_proof_for_a_hook_that_is_not_set", unsetHookStops),
	fact("test_windows_installer_survives_without_elevation",
		has(gcInstallWin, "S4U"),
		matches(gcInstallWin, `catch\s*\{`)),
	fact("test_no_ambiguous_and_or_chains", noAndOrChains),
	fact("test_wsl_leg_sweeps_workspaces_too", has(gcSh, "workspaces:", ".runner-gc-last-used")),
	fact("test_workspace_sweep_is_exercisable_on_a_busy_runner",
		has(gcSh, "RUNNER_GC_ALLOW_BUSY"),
		matches(gcSh, `\[ -z "\$\{RUNNER_GC_ROOT:-\}" \] \|\|`)),
	fact("test_workspace_sweep_demands_proof_it_is_a_runner",
		matches(gcSh, `\[ -f "\$\{_rdir\}/\.runner" \]`),
		has(gcSh, "RUNNER_WORKSPACE", "GITHUB_WORKSPACE")),
	fact("test_workspace_sweep_excludes_runner_dirs_by_name", runnerManagedList),
	fact("test_superseded_runner_versions_need_a_live_symlink",
		matches(gcSh, `-L "\$\{_rdir\}/bin"`, `-L "\$\{_rdir\}/externals"`),
		has(gcSh, "readlink -f", "-mmin +1440")),
	fact("test_gc_installer_offers_uac_elevation_for_s4u",
		has(gcInstallWin, "-Verb RunAs", "'-Retention'", "'-Distro'", "Start-Transcript", "only while signed in")),
	fact("test_windows_hook_path_is_dotenv_parseable",
		matches(gcInstallWin, `-replace\s+'\\\\'\s*,\s*'/'`)),
	fact("test_win_gc_sweeps_bun_stale_renames_with_a_day_floor",
		matches(gcWin, `\.bun\\bin|\.bun.bin`),
		has(gcWin, "stale-"),
		matches(gcWin, `AddHours\(-24\)|AddDays\(-1\)`)),
	fact("test_model_and_real_retention_and_guards_lockstep",
		has(gcSh, `RETENTION="${RUNNER_GC_RETENTION:-2h}"`, `"$created" -ge "$PODMAN_CUTOFF"`, "podman rmi --no-prune"),
		has(gcWin, "else { '2h' }", "$created -ge $Cutoff", "@('rmi', '--no-prune', $imageId)"),
		has(gcModel, "RETENTION_SECONDS = 7200", "ageSeconds > RETENTION_SECONDS",
			"ParentProtection = parentExists", "ReferenceProtection = referenced implies imageExists",
			"ConfigurationProtection = not(configurationOk) implies not(removed)")),
	fact("test_get_podman_json_asks_the_real_cmdlet_for_date_kind", podmanJSONDateKind),
	fact("test_rejection_scan_is_anchored_to_the_hook_path", rejectionAnchored),
	fact("test_rejection_scan_matches_literally", rejectionLiteral),
	fact("test_tasklist_runs_without_msys_path_conversion", tasklistGuarded),
	fact("test_wsl_leg_receives_the_allow_busy_knob", wslDispatchHolds("DISK_GC_ALLOW_BUSY=")),
	fact("test_fsck_shares_the_locate_hint",
		lacks(fsckSh, "--get-location"),
		has(fsckSh, "wsl_vhdx_locate_hint")),
	fact("test_status_feeds_the_github_section", has(gcStatusScript, "gc_github_status.sh")),
	fact("test_github_section_builds_slashless_endpoints_for_both_scopes",
		has(githubStatusSh, "orgs/", "repos/", "--paginate", "--jq"),
		lacks(githubStatusSh, `gh api "/`, "gh api '/")),
	fact("test_zombie_runbook_survives_its_own_advice",
		has(githubStatusSh, "5 min"),
		has(gcStatusScript, "runner-svc-restart", "-Force", "systemctl restart", "actions.runner.%s.%s.service")),
}

// dispatchersDisableMsys: Git Bash rewrites unix-looking argv before wsl.exe
// receives it, so every dispatcher that calls wsl.exe disables it.
func dispatchersDisableMsys(files map[string]string) []string {
	var out []string
	for _, path := range []string{gcSh, gcInstallSh, compactSh, diskGcSh} {
		text := files[path]
		if strings.Contains(text, "wsl.exe") && (!strings.Contains(text, "MSYS_NO_PATHCONV=1") || !strings.Contains(text, "MSYS2_ARG_CONV_EXCL")) {
			out = append(out, path+" calls wsl.exe without MSYS_NO_PATHCONV=1 and MSYS2_ARG_CONV_EXCL")
		}
	}
	return out
}

var (
	unfilteredPrune = regexp.MustCompile(`podman (?:image|system|builder|buildx) prune`)
	forcedRmi       = regexp.MustCompile(`podman rmi .*-(?:f|-force)`)
)

// noUnfilteredPrune: an aggressive prune also clears the unfiltered mount
// cache (ADR-0067); comments may name it.
func noUnfilteredPrune(path string) factCheck {
	return func(files map[string]string) []string {
		active := strings.Join(codeLinesOf(files[path]), "\n")
		var out []string
		if unfilteredPrune.MatchString(active) || strings.Contains(active, "'prune'") || forcedRmi.MatchString(active) {
			out = append(out, path+" prunes or force-removes images outside a comment")
		}
		return out
	}
}

var gciAssignment = regexp.MustCompile(`^\s*\$(\w+)\s*=\s*Get-ChildItem`)

// countedCollectionsWrapped: under powershell.exe 5.1 a single Get-ChildItem
// result has no .Count, so a counted collection is wrapped in @().
func countedCollectionsWrapped(files map[string]string) []string {
	text := files[gcWin]
	var out []string
	for line := range strings.SplitSeq(text, "\n") {
		m := gciAssignment.FindStringSubmatch(line)
		if m != nil && regexp.MustCompile(`\$`+regexp.QuoteMeta(m[1])+`\.Count`).MatchString(text) {
			out = append(out, fmt.Sprintf("%s counts an unwrapped collection: %s", gcWin, strings.TrimSpace(line)))
		}
	}
	return out
}

// windowsGcStart: the Windows leg starts as powershell.exe 5.1 needs it.
func windowsGcStart(files map[string]string) []string {
	words := strings.Join(strings.Fields(strings.ReplaceAll(files[gcSh], "\\\n", " ")), " ")
	if want := "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File"; !strings.Contains(words, want) {
		return []string{gcSh + " must start the Windows leg with " + want}
	}
	return nil
}

var underscoreAdd = regexp.MustCompile(`^\s*_add\b`)

// huggingfaceNotUnconditional: models are opt-in; reporting them is fine,
// collecting them is gated.
func huggingfaceNotUnconditional(files map[string]string) []string {
	var out []string
	for line := range strings.SplitSeq(files[diskGcSh], "\n") {
		if strings.Contains(line, "huggingface") && underscoreAdd.MatchString(line) && !strings.Contains(line, "DISK_GC_HUGGINGFACE") {
			out = append(out, diskGcSh+" collects huggingface unconditionally: "+strings.TrimSpace(line))
		}
	}
	return out
}

var (
	perOSBlock   = regexp.MustCompile(`(?s)if \[ "\$_win" -eq 1 \]; then(.*?)\selse\s(.*?)\sfi\s`)
	optInAfter   = regexp.MustCompile(`DISK_GC_HUGGINGFACE.*_add "\$HOME/\.cache/huggingface"`)
	wslDispatch  = regexp.MustCompile(`wsl\.exe -d "\$_distro" -e bash -lc "([^"]*)"`)
	unsetHook    = "hook: not set in"
	rejection    = "is not a valid path to a script"
	hookVariable = regexp.MustCompile(`(?i)\$\{?_?h`)
	tasklistCall = regexp.MustCompile(`\btasklist\s+/`)
)

// huggingfaceOnBothLegs: the opt-in is evaluated on every leg, and the WSL
// dispatch carries it, since wsl.exe -e inherits no environment.
func huggingfaceOnBothLegs(files map[string]string) []string {
	text := files[diskGcSh]
	loc := perOSBlock.FindStringSubmatchIndex(text)
	if loc == nil {
		return []string{diskGcSh + " must keep the per-OS cache list if/else"}
	}
	var out []string
	if strings.Contains(text[loc[2]:loc[3]], "DISK_GC_HUGGINGFACE") || strings.Contains(text[loc[4]:loc[5]], "DISK_GC_HUGGINGFACE") {
		out = append(out, "the huggingface opt-in must not be confined to one OS branch")
	}
	if !optInAfter.MatchString(text[loc[1]:]) {
		out = append(out, "the huggingface opt-in must be evaluated after the per-OS block")
	}
	return append(out, wslDispatchHolds("DISK_GC_HUGGINGFACE")(files)...)
}

// wslDispatchHolds: the WSL leg's bash -lc command carries the knob inline.
func wslDispatchHolds(knob string) factCheck {
	return func(files map[string]string) []string {
		m := wslDispatch.FindStringSubmatch(files[diskGcSh])
		if m == nil || !strings.Contains(m[1], knob) {
			return []string{diskGcSh + "'s WSL dispatch must carry " + knob + " inside bash -lc"}
		}
		return nil
	}
}

// unsetHookStops: a branch that reports an unset hook does not fall through
// to the accept/reject verdict.
func unsetHookStops(files map[string]string) []string {
	var lines []string
	for line := range strings.SplitSeq(files[gcStatusScript], "\n") {
		if strings.Contains(line, unsetHook) {
			lines = append(lines, line)
		}
	}
	if len(lines) == 0 {
		return []string{"status must still report a hook that is not configured"}
	}
	var out []string
	for _, line := range lines {
		if !strings.Contains(line, "continue") {
			out = append(out, "an unset hook falls through to the verdict: "+strings.TrimSpace(line))
		}
	}
	return out
}

// noAndOrChains: `A && B || C` runs C when B fails.
func noAndOrChains(files map[string]string) []string {
	chain := regexp.MustCompile(`&&.*\|\|`)
	var out []string
	for _, path := range []string{gcSh, gcInstallSh, compactSh, diskGcSh, gcStatusScript} {
		for line := range strings.SplitSeq(files[path], "\n") {
			stripped := strings.TrimSpace(line)
			if !strings.HasPrefix(stripped, "#") && chain.MatchString(stripped) {
				out = append(out, fmt.Sprintf("%s: spell as if/else: %s", path, stripped))
			}
		}
	}
	return out
}

// runnerManagedList: the runner-owned directories are named, not matched by
// a leading underscore.
func runnerManagedList(files map[string]string) []string {
	_, after, ok := strings.Cut(files[gcSh], "_runner_managed=")
	if !ok {
		return []string{gcSh + " must list _runner_managed= explicitly"}
	}
	line, _, _ := strings.Cut(after, "\n")
	var out []string
	for _, owned := range []string{"_actions", "_tool", "_temp", "_diag", "_update"} {
		if !strings.Contains(line, owned) {
			out = append(out, owned+" must be in the runner-managed exclusion list")
		}
	}
	return out
}

var podmanJSONBody = regexp.MustCompile(`(?ms)^function Get-PodmanJson \{\n(.*?)^\}\n`)

// podmanJSONDateKind: pwsh 7.5+ reads JSON dates as strings only when asked,
// and 5.1 has no DateKind; the cmdlet is probed, never configured globally.
func podmanJSONDateKind(files map[string]string) []string {
	script := files[gcWin]
	m := podmanJSONBody.FindStringSubmatch(script)
	if m == nil {
		return []string{gcWin + " must define Get-PodmanJson"}
	}
	body := m[1]
	var out []string
	for _, want := range []string{
		"$cmdlet = Microsoft.PowerShell.Core\\Get-Command -Name ConvertFrom-Json -CommandType Cmdlet -ErrorAction Stop\n",
		"if ($cmdlet.Parameters.ContainsKey('DateKind')) { $convert.DateKind = 'String' }",
		"$parsed = Microsoft.PowerShell.Utility\\ConvertFrom-Json @convert",
		"    return $parsed\n",
	} {
		if !strings.Contains(body, want) {
			out = append(out, fmt.Sprintf("Get-PodmanJson must hold %q", strings.TrimSpace(want)))
		}
	}
	code := codeLinesOf(script)
	count := 0
	for _, line := range code {
		count += strings.Count(line, "DateKind")
	}
	if count != 2 {
		out = append(out, fmt.Sprintf("DateKind must appear only in the capability test, not %d times", count))
	}
	if strings.Contains(script, "PSDefaultParameterValues") {
		out = append(out, "DateKind must not be set through PSDefaultParameterValues")
	}
	calls := 0
	for _, line := range code {
		if strings.Contains(line, "ConvertFrom-Json") {
			calls++
			if !strings.Contains(body, strings.TrimSpace(line)) {
				out = append(out, "ConvertFrom-Json outside Get-PodmanJson: "+strings.TrimSpace(line))
			}
		}
	}
	if calls == 0 {
		out = append(out, "ConvertFrom-Json must be called through Get-PodmanJson")
	}
	return out
}

// rejectionAnchored: both legs search for "<hook> <phrase>", never the
// phrase alone, which a PR body quoting it would match.
func rejectionAnchored(files map[string]string) []string {
	var out []string
	for line := range strings.SplitSeq(files[gcStatusScript], "\n") {
		if strings.Contains(line, rejection) && !strings.HasPrefix(strings.TrimLeft(line, " \t"), "#") && !hookVariable.MatchString(line) {
			out = append(out, "a rejection search without the hook path: "+strings.TrimSpace(line))
		}
	}
	return out
}

// rejectionLiteral: a hook path is a filesystem path, not a regex.
func rejectionLiteral(files map[string]string) []string {
	used := 0
	var out []string
	for line := range strings.SplitSeq(files[gcStatusScript], "\n") {
		if !strings.Contains(line, rejection) {
			continue
		}
		used++
		if !strings.HasPrefix(strings.TrimLeft(line, " \t"), "#") && !strings.Contains(line, "grep -lF") && !strings.Contains(line, "-SimpleMatch") {
			out = append(out, "the hook path must be matched literally: "+strings.TrimSpace(line))
		}
	}
	if used == 0 {
		out = append(out, "status must still detect the runner's rejection message")
	}
	return out
}

// tasklistGuarded: Git Bash rewrites /FI into a path; every tasklist call
// disables the conversion.
func tasklistGuarded(files map[string]string) []string {
	var calls []string
	for line := range strings.SplitSeq(strings.ReplaceAll(files[diskGcSh], "\\\n", " "), "\n") {
		if tasklistCall.MatchString(line) && !strings.HasPrefix(strings.TrimLeft(line, " \t"), "#") {
			calls = append(calls, line)
		}
	}
	if len(calls) == 0 {
		return []string{diskGcSh + " must detect the Windows runner job with tasklist"}
	}
	var out []string
	for _, line := range calls {
		if !strings.Contains(line, "MSYS_NO_PATHCONV=1") || !strings.Contains(line, "MSYS2_ARG_CONV_EXCL") {
			out = append(out, "tasklist without MSYS guards: "+strings.TrimSpace(line))
		}
	}
	return out
}
