package rules

import (
	"strings"
	"testing"
)

// gcInstallWinFixture uses BACKTICK for PowerShell's line continuation, which
// a Go raw string cannot hold.
var gcInstallWinFixture = strings.ReplaceAll(`$autoPayload = Join-Path $here 'wsl_autostart.ps1'
$runHidden = Install-RunHidden -Source x
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
Write-Host "scheduled task: $TaskName exists but cannot be replaced unelevated; keeping it as-is"
$action = New-ScheduledTaskAction BACKTICK
    -Execute $runHidden BACKTICK
    -Argument ('"{0}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{1}" -Retention {2}' -f $powershell, $payload, $Retention)
$autoAction = New-ScheduledTaskAction BACKTICK
    -Execute $runHidden BACKTICK
    -Argument ('"{0}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{1}" -Distro {2}' -f $powershell, $autoPayload, $Distro)
$autoTrigger = New-ScheduledTaskTrigger -AtLogOn -User $me
$autoSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName 'dotfiles-wsl-autostart' -Action $autoAction -Settings $autoSettings
Start-ScheduledTask -TaskName $AutostartTaskName
Write-Host "the proof is 'just status' after the next reboot"
`, "BACKTICK", "\x60")

const gcInstallShFixture = `powershell.exe -NoProfile -File "$ps1" -Distro "$_distro"
`

const autostartFixture = `$ErrorActionPreference = 'Continue'
$env:WSL_UTF8 = '1'
$raw = & $WslExe --list --quiet --running 2>$null
if ($running -contains $Distro) { Write-Log 'already running' }
& $WslExe -d $Distro -e sh -c "pgrep -f 'dotfiles-wsl-keepaliv[e]' >/dev/null"
$state = & $WslExe -d $Distro -u root -e systemctl is-system-running
$units = & $WslExe -d $Distro -u root -e systemctl list-units --type=service 'actions.runner.*'
& $WslExe -d $Distro -e sh -c ': dotfiles-wsl-keepalive; while :; do sleep 3600; done'
`

const autostartStatusFixture = `if wsl.exe --list --quiet --running | grep -qxF "$DISTRO"; then up=1; fi
_lis="$(pgrep -cx Runner.Listener || true)"
_windows_status() {
  elseif (\$i.LastTaskResult -eq 267009) { 'OK|last run: running now (result 267009 = still executing)' }
  if (\$trig -contains 'MSFT_TaskLogonTrigger') { 'OK|autostart task: logon trigger' }
  if (\$ai.LastTaskResult -eq 2147946720 -and \$a.State -eq 'Running') {
    'OK|autostart last run: duplicate start refused (0x800710E0)'
  }
  foreach (\$n in @('$TASK', '$AUTOTASK', 'dotfiles-runner-watchdog')) {
    if (\$x.Actions[0].Execute -notlike '*\\run-hidden.exe') { 'WARN|' + \$n }
  }
}
`

const autostartWatchdogFixture = `Start-ScheduledTask -TaskName $runnerTask
`

func wslAutostartBase() Inputs {
	return Inputs{
		gcInstallWin:      gcInstallWinFixture,
		gcInstallSh:       gcInstallShFixture,
		autostartPs1:      autostartFixture,
		gcStatusScript:    autostartStatusFixture,
		runnerWatchdogWin: autostartWatchdogFixture,
	}
}

func TestWslAutostartFacts(t *testing.T) {
	g, a, s := gcInstallWin, autostartPs1, gcStatusScript
	runCases(t, wslAutostartFacts(), wslAutostartBase, []ruleCase{
		{"the task fires at boot", edit(g, "-AtLogOn -User $me", "-AtStartup"), "test_installer_registers_logon_autostart_task"},
		{"the distro is left to the environment", edit(g, "-f $powershell, $autoPayload, $Distro)", "-f $powershell, $autoPayload, $env:RUNNER_GC_WSL_DISTRO)"), "test_installer_bakes_distro_into_the_task_command_line"},
		{"the GC task starts powershell.exe itself", edit(g, "$action = New-ScheduledTaskAction \x60\n    -Execute $runHidden", "$action = New-ScheduledTaskAction \x60\n    -Execute (Get-Command powershell.exe).Source"), "test_installer_starts_both_tasks_through_run_hidden"},
		{"the task is removed before the copy", edit(g, "$runHidden = Install-RunHidden -Source x\nUnregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop\n", "Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop\n$runHidden = Install-RunHidden -Source x\n"), "test_installer_copies_the_launcher_before_it_removes_any_task"},
		{"the installer stops the keepalive", edit(g, "Start-ScheduledTask -TaskName $AutostartTaskName", "Stop-ScheduledTask -TaskName $AutostartTaskName\nStart-ScheduledTask -TaskName $AutostartTaskName"), "test_installers_never_stop_a_running_task"},
		{"the watchdog stops the runner task", edit(runnerWatchdogWin, "Start-ScheduledTask -TaskName $runnerTask", "Stop-ScheduledTask -TaskName $runnerTask\nStart-ScheduledTask -TaskName $runnerTask"), "test_installers_never_stop_a_running_task"},
		{"status skips the autostart task's launcher", edit(s, "'$AUTOTASK', ", ""), "test_status_warns_about_a_task_that_starts_a_console_program_directly"},
		{"the smoke fire is called proof", edit(g, "after the next reboot", "now"), "test_installer_does_not_claim_the_smoke_fire_proves_recovery"},
		{"an S4U task stops the install", edit(g, "keeping it as-is", "giving up"), "test_installer_survives_an_unreplaceable_s4u_task"},
		{"the dispatcher drops the distro", edit(gcInstallSh, `-Distro "$_distro"`, `-Distro Ubuntu`), "test_bash_dispatcher_passes_the_resolved_distro"},
		{"wsl.exe's exit throws", edit(a, "$ErrorActionPreference = 'Continue'", "$ErrorActionPreference = 'Stop'"), "test_payload_is_fail_open_on_wsl_list_errors"},
		{"a sibling distro matches", edit(a, "-contains $Distro", "-match $Distro"), "test_payload_matches_the_distro_exactly"},
		{"the probe matches itself", edit(a, "keepaliv[e]", "keepalive"), "test_payload_ends_as_a_blocking_keepalive_client"},
		{"the keepalive task times out", edit(g, "-ExecutionTimeLimit (New-TimeSpan -Seconds 0)", "-ExecutionTimeLimit (New-TimeSpan -Hours 72)"), "test_installer_gives_the_keepalive_task_no_time_limit"},
		{"a runner unit is not counted", edit(a, "list-units --type=service", "is-active"), "test_payload_enforces_the_systemd_contract"},
		{"status judges the principal", edit(s, "MSFT_TaskLogonTrigger", "MSFT_TaskBootTrigger"), "test_status_checks_the_autostart_task_by_trigger_shape"},
		{"a running keepalive reads FAIL", edit(s, "  elseif (\\$i.LastTaskResult -eq 267009) { 'OK|last run: running now (result 267009 = still executing)' }\n", ""), "test_status_does_not_flag_a_running_keepalive_as_failure"},
		{"a running GC task reads FAIL", edit(s, "running now (result 267009", "running now (code 267009"), "test_status_does_not_flag_a_running_gc_task_as_failure"},
		{"the running state is read after a leg", func(in Inputs) {
			edit(s, "if wsl.exe --list --quiet --running | grep -qxF \"$DISTRO\"; then up=1; fi\n", "")(in)
			edit(s, "_windows_status() {\n", "_windows_status() {\n  if wsl.exe --list --quiet --running | grep -qxF \"$DISTRO\"; then up=1; fi\n")(in)
		}, "test_status_captures_distro_running_state_once_up_front"},
		{"no listener kills set -e", edit(s, "pgrep -cx Runner.Listener || true", "pgrep -cx Runner.Listener"), "test_status_counts_runner_listeners_without_killing_set_e"},
		{"a refused start is OK on a stopped task", edit(s, " -and \\$a.State -eq 'Running'", ""), "test_status_exempts_a_refused_duplicate_start_while_the_keepalive_lives"},
	})
}

func TestRefusedStartWindowIsPythonsSlice(t *testing.T) {
	// The phrase sits within 900 characters of the start: Python's negative
	// slice start is near the end, so the window is empty and the test failed.
	early := "2147946720 Running\nautostart last run\n" + strings.Repeat("x", 2000)
	if got := refusedStartExempted(map[string]string{gcStatusScript: early}); len(got) == 0 {
		t.Fatal("a phrase within 900 characters of the start must fail, as the Python slice did")
	}
	// Characters, not bytes: 899 three-byte characters keep the code inside.
	far := strings.Repeat("—", 1000) + "2147946720 Running" + strings.Repeat("—", 880) + "autostart last run"
	if got := refusedStartExempted(map[string]string{gcStatusScript: far}); len(got) != 0 {
		t.Fatalf("the window counts characters: %v", got)
	}
}
