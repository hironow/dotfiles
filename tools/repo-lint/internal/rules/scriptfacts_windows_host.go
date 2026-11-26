package rules

import (
	"fmt"
	"regexp"
	"strings"
)

// The Windows runner host scripts and the tests that read them.
const (
	runnerModeWin     = "scripts/runner_mode_win.ps1"
	runnerWatchdogWin = "scripts/runner_watchdog_win.ps1"
	runnerSvcWin      = "scripts/install_runner_svc_win.ps1"
	restartSvcWin     = "scripts/restart_runner_svc_win.ps1"
	machinePathPs1    = "scripts/restore_machine_path.ps1"
)

// windowsHostFacts: the Windows runner mode switch, watchdog, service
// installer, Machine PATH repair and WSL fsck advisor keep what the tests
// that read them held. Findings name the removed test.
func windowsHostFacts() Rule {
	return factRule(
		"windows-host-facts",
		"the Windows runner host scripts keep their guards: no killed jobs, UAC conventions, no hard-coded host, REG_EXPAND_SZ PATH writes, an advisory fsck",
		[]string{runnerModeWin, runnerWatchdogWin, runnerSvcWin, restartSvcWin, machinePathPs1, fsckSh, gcStatusScript, doctorScript},
		windowsHostFactList,
	)
}

var windowsHostFactList = []scriptFact{
	// tests/unit/test_runner_mode_win.py
	fact("test_mode_switch_exists_and_is_generic",
		has(runnerModeWin, "'interactive'", "'service'", "RUNNER_WIN_ROOT", "USERPROFILE"),
		lacksFold(runnerModeWin, "absin")),
	fact("test_mode_switch_shares_the_elevation_conventions",
		has(runnerModeWin, "-Verb RunAs", "-Wait", "ExitCode", "'-RunnerRoot'", "'-Mode'", "Start-Transcript"),
		matches(runnerModeWin, `(?i)catch`)),
	fact("test_mode_switch_refuses_to_kill_a_running_job", has(runnerModeWin, "Runner.Worker")),
	fact("test_interactive_mode_shape",
		has(runnerModeWin, "run.cmd", "AtLogOn", "Interactive", "SessionId"),
		matches(runnerModeWin, `ExecutionTimeLimit.*Zero|-ExecutionTimeLimit 0`),
		anyOf(hasFold(runnerModeWin, "'disabled'"), has(runnerModeWin, "start= disabled"))),
	fact("test_service_mode_is_the_inverse", has(runnerModeWin, "Unregister-ScheduledTask", "delayed-auto")),
	fact("test_status_recognises_deliberate_interactive_mode", has(gcStatusScript, "dotfiles-runner-interactive")),
	fact("test_interactive_mode_reowns_foreign_work_checkouts",
		has(runnerModeWin, "takeown", "_PipelineMapping"),
		takeownWithoutA),
	fact("test_watchdog_exists_and_is_generic",
		lacksFold(runnerWatchdogWin, "absin"),
		has(runnerWatchdogWin, "dotfiles-runner-watchdog", "dotfiles-runner-interactive", "Runner.Listener",
			"Start-ScheduledTask", "-Install", "Unregister-ScheduledTask", "IgnoreNew"),
		lacks(runnerWatchdogWin, "Stop-Process", "taskkill")),
	fact("test_watchdog_writes_a_log_line_on_every_restart",
		has(runnerWatchdogWin, "runner-watchdog-win.log"),
		matches(runnerWatchdogWin, `Get-Date`)),
	fact("test_watchdog_task_runs_a_copy_outside_the_working_tree",
		has(runnerWatchdogWin, "LOCALAPPDATA", "Copy-Item"),
		matches(runnerWatchdogWin, `-File "\{1\}"[^\n]*-f \$powershell, \$installed`),
		lacks(runnerWatchdogWin, "-f $PSCommandPath")),
	fact("test_watchdog_task_starts_through_run_hidden",
		matches(runnerWatchdogWin, "-Execute \\$runHidden \x60\\s+-Argument \\('\\\"\\{0\\}\\\" -NoProfile -NonInteractive "+
			"-ExecutionPolicy Bypass -File \\\"\\{1\\}\\\" -RunnerRoot \\\"\\{2\\}\\\"' -f "+
			"\\$powershell, \\$installed, \\$RunnerRoot\\)"),
		lacks(runnerWatchdogWin, "-Execute (Get-Command powershell.exe).Source"),
		watchdogCopiesBeforeRemoving),
	fact("test_mode_switch_wires_the_watchdog_and_removes_the_legacy_lnk",
		has(runnerModeWin, "runner_watchdog_win.ps1", "-Install", "dotfiles-runner-watchdog", ".lnk", "Startup",
			"Microsoft-Windows-TaskScheduler/Operational", "/e:true")),
	fact("test_watchdog_install_keeps_a_task_it_cannot_replace", watchdogKeepsTask),
	// tests/unit/test_restore_machine_path.py
	fact("test_writes_expandstring_never_setenvironmentvariable",
		has(machinePathPs1, "ExpandString"),
		codeLacks(machinePathPs1, "SetEnvironmentVariable")),
	fact("test_merges_instead_of_clobbering", matches(machinePathPs1, `(?i)-notin|NotContains|missing`)),
	fact("test_detects_optional_dirs_instead_of_hardcoding_users",
		has(machinePathPs1, "Test-Path", "USERPROFILE"),
		noMatch(machinePathPs1, `C:\\Users\\[A-Za-z]`)),
	fact("test_optional_container_path_uses_native_podman_not_docker_desktop",
		codeOrder(machinePathPs1, `"$env:ProgramFiles\Podman"`, `$env:ProgramFiles\RedHat\Podman`),
		codeLacks(machinePathPs1, `Docker\Docker\resources\bin`)),
	fact("test_missing_comparison_expands_env_vars", codeHas(machinePathPs1, "ExpandEnvironmentVariables")),
	fact("test_dedupes_existing_entries_by_expanded_value", matches(machinePathPs1, `(?i)dedup`)),
	fact("test_requires_apply_switch_and_self_elevates",
		anyOf(has(machinePathPs1, "-Apply"), has(machinePathPs1, "$Apply")),
		has(machinePathPs1, "RunAs")),
	fact("test_git_bin_is_prepended_ahead_of_system32",
		matches(machinePathPs1, `Git\\bin`, `usr\\+bin`),
		hasFold(machinePathPs1, "prepend")),
	fact("test_nothing_to_do_honours_ordering", nothingToDoGate),
	fact("test_git_bin_detection_handles_a_scoop_install",
		matches(machinePathPs1, `scoop\\apps\\git\\current\\bin`),
		order(machinePathPs1, `Git\bin`, `scoop\apps\git\current\bin`)),
	fact("test_doctor_bash_shadow_resolves_git_bin_via_cygpath", has(doctorScript, "win_git_root", "realpath -m")),
	fact("test_doctor_detects_the_bash_shadow", has(doctorScript, "win-bash-shadow"), countAtLeast(doctorScript, "restore_machine_path.ps1", 3)),
	// tests/unit/test_runner_svc_win.py
	fact("test_installer_is_generic_not_this_host",
		has(runnerSvcWin, "RUNNER_WIN_ROOT", "USERPROFILE", "agentName"),
		matches(runnerSvcWin, `\.runner`),
		lacksFold(runnerSvcWin, "absin")),
	fact("test_installer_refuses_an_unconfigured_runner",
		matches(runnerSvcWin, `Join-Path .*'\.runner'`),
		has(runnerSvcWin, "Test-Path", "not configured")),
	fact("test_installer_self_elevates_and_propagates_the_exit_code",
		has(runnerSvcWin, "-Verb RunAs", "-Wait", "ExitCode", "-RunnerRoot", "Start-Transcript"),
		matches(runnerSvcWin, `(?i)catch`),
		has(restartSvcWin, "-Verb RunAs", "-Wait", "ExitCode", "-RunnerRoot", "Start-Transcript"),
		matches(restartSvcWin, `(?i)catch`)),
	fact("test_sc_exit_codes_are_checked", has(runnerSvcWin, "LASTEXITCODE")),
	fact("test_restart_refuses_to_kill_a_running_job", has(restartSvcWin, "Runner.Worker")),
	fact("test_installer_service_shape",
		has(runnerSvcWin, "LocalSystem", "delayed-auto", "restart/60000", "'failure'", "failureflag", "'config'"),
		matches(runnerSvcWin, `replace\('/'|-replace\s*'/'`)),
	fact("test_installer_warns_about_localsystem_work_ownership",
		has(runnerSvcWin, "_work"),
		anyOf(has(runnerSvcWin, "safe.directory"), has(runnerSvcWin, "takeown"))),
	fact("test_installer_verifies_the_machine_path_onion",
		has(runnerSvcWin, "scoop", "bun", "mise", "restore_machine_path.ps1", "SYSTEM")),
	fact("test_status_surfaces_a_stopped_or_disabled_service",
		has(gcStatusScript, "Get-Service", "Runner.Listener", "Disabled", "runner-svc-install")),
	// tests/unit/test_wsl_fsck.py
	fact("test_fsck_stays_advisory",
		has(fsckSh, "--shutdown"),
		noMatch(fsckSh, `(?m)^\s*[^#]*wsl\.exe --shutdown`),
		fsckRunsNoE2fsck),
	fact("test_fsck_uses_the_shared_vhdx_resolver",
		has(fsckSh, "wsl_vhdx_path", "wsl_vhdx_lib.sh"),
		lacks(fsckSh, "head -1")),
	fact("test_detection_is_mount_state_not_dmesg", has(fsckSh, "findmnt"), matches(fsckSh, `overlay`)),
	fact("test_wsl_invocations_disable_msys_conversion_and_pin_the_distro", fsckWslCallsGuarded),
	fact("test_wsl_list_output_is_denulled", fsckListDenulled),
	fact("test_helper_selection_excludes_docker_and_wsl1",
		has(fsckSh, "docker-desktop"),
		matches(fsckSh, `-l\s+-v|--list\s+--verbose`)),
	fact("test_runbook_covers_the_dangerous_steps",
		order(fsckSh, "-e true", "--vhd --bare"),
		has(fsckSh, "--bare", "lsblk", "e2fsck -fn", "e2fsck -fy", "--unmount", "--export"),
		anyOf(has(fsckSh, "/proc/mounts"), has(fsckSh, "findmnt"))),
	fact("test_doctor_advises_wsl_fsck_without_booting_wsl", has(doctorScript, "wsl-fsck", "--running")),
	fact("test_ro_detection_ignores_errors_remount_ro",
		noMatch(fsckSh, `ext4\*ro`, `ext4.*\*ro,?\*`),
		noMatch(doctorScript, `ext4\*ro`, `ext4.*\*ro,?\*`)),
}

// lacksFold: `s not in text.lower()`.
func lacksFold(path, s string) factCheck {
	return func(files map[string]string) []string {
		if strings.Contains(strings.ToLower(files[path]), s) {
			return []string{fmt.Sprintf("%s must not hold %q in any case", path, s)}
		}
		return nil
	}
}

// hasFold: `s in text.lower()`.
func hasFold(path, s string) factCheck {
	return func(files map[string]string) []string {
		if !strings.Contains(strings.ToLower(files[path]), s) {
			return []string{fmt.Sprintf("%s must hold %q in any case", path, s)}
		}
		return nil
	}
}

// codeHas and codeLacks search the lines that are not comments.
func codeHas(path, s string) factCheck {
	return func(files map[string]string) []string {
		if !strings.Contains(strings.Join(codeLinesOf(files[path]), "\n"), s) {
			return []string{fmt.Sprintf("%s must hold %q outside a comment", path, s)}
		}
		return nil
	}
}

func codeLacks(path, s string) factCheck {
	return func(files map[string]string) []string {
		if strings.Contains(strings.Join(codeLinesOf(files[path]), "\n"), s) {
			return []string{fmt.Sprintf("%s must not hold %q outside a comment", path, s)}
		}
		return nil
	}
}

// order: both strings are present and the first comes first
// (`text.index(a) < text.index(b)`, which fails when either is missing).
func order(path, first, second string) factCheck {
	return func(files map[string]string) []string {
		return orderIn(path, files[path], first, second)
	}
}

func codeOrder(path, first, second string) factCheck {
	return func(files map[string]string) []string {
		return orderIn(path, strings.Join(codeLinesOf(files[path]), "\n"), first, second)
	}
}

func orderIn(path, text, first, second string) []string {
	a, b := strings.Index(text, first), strings.Index(text, second)
	if a < 0 || b < 0 || a >= b {
		return []string{fmt.Sprintf("%s must hold %q before %q", path, first, second)}
	}
	return nil
}

// countAtLeast: `text.count(s) >= n`.
func countAtLeast(path, s string, n int) factCheck {
	return func(files map[string]string) []string {
		if got := strings.Count(files[path], s); got < n {
			return []string{fmt.Sprintf("%s must name %q at least %d times, not %d", path, s, n, got)}
		}
		return nil
	}
}

// takeownWithoutA: takeown without /A gives the checkout to the runner user;
// /A gives it to Administrators, the state being repaired.
func takeownWithoutA(files map[string]string) []string {
	_, after, ok := strings.Cut(files[runnerModeWin], "takeown")
	if !ok {
		return nil // has() above reports the missing takeown
	}
	line, _, _ := strings.Cut(after, "\n")
	if strings.Contains(line, "/A") {
		return []string{"takeown must not use /A: " + strings.TrimSpace(line)}
	}
	return nil
}

// watchdogCopiesBeforeRemoving: a failed copy of run-hidden must not leave
// the box without its watchdog.
func watchdogCopiesBeforeRemoving(files map[string]string) []string {
	text := files[runnerWatchdogWin]
	start := strings.Index(text, "if ($Install) {")
	if start < 0 {
		return []string{runnerWatchdogWin + " must have an if ($Install) { branch"}
	}
	install := text[start:]
	copyAt := strings.Index(install, "Install-RunHidden")
	removeAt := strings.Index(install, "Unregister-ScheduledTask -TaskName $watchTask")
	if copyAt == -1 || copyAt >= removeAt {
		return []string{"copy run-hidden before the watchdog task is removed"}
	}
	return nil
}

var watchdogPair = regexp.MustCompile(`(?s)Unregister-ScheduledTask -TaskName \$watchTask[^\r\n]*\s(.*?)Register-ScheduledTask -TaskName \$watchTask`)

// watchdogKeepsTask: a task the caller cannot delete is kept, not fought.
func watchdogKeepsTask(files map[string]string) []string {
	m := watchdogPair.FindStringSubmatch(files[runnerWatchdogWin])
	if m == nil {
		return []string{"expected the watchdog unregister/register pair"}
	}
	var out []string
	if !strings.Contains(m[1], "Get-ScheduledTask -TaskName $watchTask") {
		out = append(out, "probe whether the task still exists before registering it again")
	}
	if !regexp.MustCompile(`keeping it as-is|cannot be replaced unelevated`).MatchString(m[1]) {
		out = append(out, "an unremovable task is kept and the run says so")
	}
	return out
}

var nothingToDo = regexp.MustCompile(`if \(([^)]*)\) \{\s*\n\s*Write-Host 'Machine PATH already complete`)

// nothingToDoGate: "already complete" also requires the ordering.
func nothingToDoGate(files map[string]string) []string {
	m := nothingToDo.FindStringSubmatch(files[machinePathPs1])
	if m == nil {
		return []string{"the nothing-to-do gate should exist"}
	}
	gate := strings.ToLower(m[1])
	if !strings.Contains(gate, "order") && !strings.Contains(gate, "prepend") {
		return []string{"the nothing-to-do gate must include the ordering check"}
	}
	return nil
}

var e2fsckRun = regexp.MustCompile(`e2fsck -f`)

// fsckRunsNoE2fsck: the advisor prints the repair, never runs it.
func fsckRunsNoE2fsck(files map[string]string) []string {
	var out []string
	for line := range strings.SplitSeq(files[fsckSh], "\n") {
		if strings.Contains(line, "wsl.exe") && e2fsckRun.MatchString(line) {
			out = append(out, "wsl_fsck.sh must not run e2fsck itself: "+strings.TrimSpace(line))
		}
	}
	return out
}

var (
	fsckContinuation = regexp.MustCompile(`\\\n\s*`)
	wslCall          = regexp.MustCompile(`^\s*[^#]*\bwsl\.exe\b`)
	pinsDistro       = regexp.MustCompile(`-d\s`)
	wslList          = regexp.MustCompile(`wsl\.exe\s+(-l|--list)`)
	nulStrip         = regexp.MustCompile(`tr -d '\\+0`)
)

// fsckWslCallsGuarded: MSYS rewrites `/` arguments, and a bare wsl.exe boots
// the default distro, which may be the corrupted one.
func fsckWslCallsGuarded(files map[string]string) []string {
	var out []string
	for line := range strings.SplitSeq(fsckContinuation.ReplaceAllString(files[fsckSh], " "), "\n") {
		before, _, _ := strings.Cut(line, "wsl.exe")
		if !wslCall.MatchString(line) || strings.Contains(before, "--") {
			continue
		}
		if !strings.Contains(line, "MSYS_NO_PATHCONV") && !strings.Contains(line, "MSYS2_ARG_CONV_EXCL") {
			out = append(out, "wsl.exe call without path-conversion guard: "+strings.TrimSpace(line))
		}
		if !pinsDistro.MatchString(line) && !strings.Contains(line, "--list") && !strings.Contains(line, "-l") {
			out = append(out, "wsl.exe call must pin a distro with -d: "+strings.TrimSpace(line))
		}
	}
	return out
}

// fsckListDenulled: wsl.exe -l prints UTF-16LE; NULs are stripped.
func fsckListDenulled(files map[string]string) []string {
	var out []string
	for line := range strings.SplitSeq(files[fsckSh], "\n") {
		if wslList.MatchString(line) && !nulStrip.MatchString(strings.ReplaceAll(line, `"`, "'")) && !strings.Contains(line, `\0`) {
			out = append(out, "wsl.exe list output must strip NUL bytes: "+strings.TrimSpace(line))
		}
	}
	return out
}
