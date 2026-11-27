package rules

import (
	"regexp"
	"strings"
	"unicode/utf8"
)

// autostartPs1 is the logon payload that boots the runner's WSL distro and
// stays attached as its keepalive client.
const autostartPs1 = "scripts/wsl_autostart.ps1"

// wslAutostartFacts: the WSL autostart task, its payload and the status lines
// that judge it keep what tests/unit/test_wsl_autostart.py's text checks held.
// Findings name the removed test.
func wslAutostartFacts() Rule {
	return factRule(
		"wsl-autostart-facts",
		"the WSL autostart task starts once per logon through run-hidden, never stops a running task, and its payload keeps the distro alive with one keepalive",
		[]string{gcInstallWin, gcInstallSh, autostartPs1, gcStatusScript, runnerWatchdogWin},
		wslAutostartFactList,
	)
}

// The two task actions; PowerShell's line continuation is a backtick, which a
// Go raw string cannot hold.
const (
	gcTaskAction = `\$action = New-ScheduledTaskAction ` + "\x60" + `\s+-Execute \$runHidden ` + "\x60" + `\s+` +
		`-Argument \('"\{0\}" -NoProfile -NonInteractive -ExecutionPolicy Bypass ` +
		`-File "\{1\}" -Retention \{2\}' -f \$powershell, \$payload, \$Retention\)`
	autostartTaskAction = `\$autoAction = New-ScheduledTaskAction ` + "\x60" + `\s+-Execute \$runHidden ` + "\x60" + `\s+` +
		`-Argument \('"\{0\}" -NoProfile -NonInteractive -ExecutionPolicy Bypass ` +
		`-File "\{1\}" -Distro \{2\}' -f \$powershell, \$autoPayload, \$Distro\)`
)

var wslAutostartFactList = []scriptFact{
	fact("test_installer_registers_logon_autostart_task",
		has(gcInstallWin, "dotfiles-wsl-autostart", "-AtLogOn", "IgnoreNew", "wsl_autostart.ps1")),
	fact("test_installer_bakes_distro_into_the_task_command_line",
		matches(gcInstallWin, `-Distro \{\d\}'[^\n]*\$Distro\)`)),
	fact("test_installer_starts_both_tasks_through_run_hidden",
		matches(gcInstallWin, gcTaskAction, autostartTaskAction),
		lacks(gcInstallWin, "-Execute (Get-Command powershell.exe).Source")),
	fact("test_installer_copies_the_launcher_before_it_removes_any_task",
		order(gcInstallWin, "Install-RunHidden", "Unregister-ScheduledTask")),
	fact("test_installers_never_stop_a_running_task",
		lacks(gcInstallWin, "Stop-ScheduledTask"),
		lacks(runnerWatchdogWin, "Stop-ScheduledTask")),
	fact("test_status_warns_about_a_task_that_starts_a_console_program_directly", statusChecksTaskLaunchers),
	fact("test_installer_does_not_claim_the_smoke_fire_proves_recovery", has(gcInstallWin, "after the next reboot")),
	fact("test_installer_survives_an_unreplaceable_s4u_task", has(gcInstallWin, "keeping it as-is")),
	fact("test_bash_dispatcher_passes_the_resolved_distro", has(gcInstallSh, `-Distro "$_distro"`)),
	fact("test_payload_is_fail_open_on_wsl_list_errors", has(autostartPs1, "$ErrorActionPreference = 'Continue'", "WSL_UTF8")),
	fact("test_payload_matches_the_distro_exactly", has(autostartPs1, "-contains $Distro", "--quiet")),
	fact("test_payload_ends_as_a_blocking_keepalive_client", has(autostartPs1, "dotfiles-wsl-keepalive", "keepaliv[e]")),
	fact("test_installer_gives_the_keepalive_task_no_time_limit",
		has(gcInstallWin, "-ExecutionTimeLimit (New-TimeSpan -Seconds 0)")),
	fact("test_payload_enforces_the_systemd_contract", has(autostartPs1, "is-system-running", "list-units")),
	fact("test_status_checks_the_autostart_task_by_trigger_shape", has(gcStatusScript, "MSFT_TaskLogonTrigger")),
	fact("test_status_does_not_flag_a_running_keepalive_as_failure", has(gcStatusScript, "267009")),
	fact("test_status_does_not_flag_a_running_gc_task_as_failure", has(gcStatusScript, "running now (result 267009")),
	fact("test_status_captures_distro_running_state_once_up_front",
		order(gcStatusScript, "--quiet --running", "_windows_status() {")),
	fact("test_status_counts_runner_listeners_without_killing_set_e",
		has(gcStatusScript, "pgrep -cx Runner.Listener || true")),
	fact("test_status_exempts_a_refused_duplicate_start_while_the_keepalive_lives", refusedStartExempted),
}

// statusTaskLoop is the status loop over dotfiles' tasks (no DOTALL: the list
// is on one line).
var statusTaskLoop = regexp.MustCompile(`foreach \(\\\$n in @\((.*?)\)\)`)

// statusChecksTaskLaunchers: status names every dotfiles task whose action
// still starts a console program directly.
func statusChecksTaskLaunchers(files map[string]string) []string {
	text := files[gcStatusScript]
	m := statusTaskLoop.FindStringSubmatch(text)
	if m == nil {
		return []string{gcStatusScript + " must loop over dotfiles' tasks: foreach (\\$n in @(...))"}
	}
	var out []string
	for _, name := range []string{"$TASK", "$AUTOTASK", "dotfiles-runner-watchdog"} {
		if !strings.Contains(m[1], name) {
			out = append(out, "the status task loop must check "+name)
		}
	}
	return append(out, has(gcStatusScript, "run-hidden.exe", "WARN|")(files)...)
}

// refusedStartExempted: a refused duplicate start (0x800710E0) reads OK only
// while the autostart task is Running. The window is the test's slice
// text[i-900 : i+200] in characters, with Python's reading of a negative
// start.
func refusedStartExempted(files map[string]string) []string {
	text := files[gcStatusScript]
	if !strings.Contains(text, "2147946720") && !strings.Contains(text, "0x800710E0") {
		return []string{gcStatusScript + " must recognise the refused-duplicate-start code (2147946720 or 0x800710E0)"}
	}
	at := strings.Index(text, "autostart last run")
	if at < 0 {
		return []string{gcStatusScript + ` must hold "autostart last run"`}
	}
	runes := []rune(text)
	i := utf8.RuneCountInString(text[:at])
	start, end := i-900, min(i+200, len(runes))
	if start < 0 {
		start = max(len(runes)+start, 0)
	}
	seg := ""
	if start < end {
		seg = string(runes[start:end])
	}
	if !strings.Contains(seg, "Running") || !strings.Contains(seg, "2147946720") && !strings.Contains(seg, "800710E0") {
		return []string{"the refused-start exemption must be conditioned on the task State being Running, next to \"autostart last run\""}
	}
	return nil
}
