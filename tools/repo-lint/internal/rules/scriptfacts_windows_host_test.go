package rules

import (
	"strings"
	"testing"
)

const modeWinFixture = `param([ValidateSet('interactive', 'service')] $Mode, $RunnerRoot = $(if ($env:RUNNER_WIN_ROOT) { $env:RUNNER_WIN_ROOT } else { Join-Path $env:USERPROFILE 'actions-runner' }))
if (Get-Process Runner.Worker -ErrorAction SilentlyContinue) { throw 'a job is running; -Force to override' }
try { $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @('-Mode', $Mode, '-RunnerRoot', $RunnerRoot); exit $p.ExitCode } catch { exit 1 }
Start-Transcript -Path x
$action = New-ScheduledTaskAction -Execute (Join-Path $RunnerRoot 'run.cmd')
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero)
sc.exe config $svc start= disabled
if ($listener.SessionId -eq 0) { throw 'session 0' }
Unregister-ScheduledTask -TaskName x -Confirm:$false
sc.exe config $svc start= delayed-auto
takeown /F $dir /R /D Y
$internal = '_actions', '_temp', '_tool', '_update', '_PipelineMapping'
& (Join-Path $PSScriptRoot 'runner_watchdog_win.ps1') -Install
Unregister-ScheduledTask -TaskName 'dotfiles-runner-watchdog' -Confirm:$false
Remove-Item (Join-Path $startup 'actions-runner.lnk') # the legacy Startup shortcut
wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true
`

// watchdogFixture uses BACKTICK for PowerShell's line continuation, which a
// Go raw string cannot hold.
var watchdogFixture = strings.ReplaceAll(`# -Install registers the repeating task
$watchTask = 'dotfiles-runner-watchdog'
$interactiveTask = 'dotfiles-runner-interactive'
if (-not (Get-Process Runner.Listener -ErrorAction SilentlyContinue)) {
    Start-ScheduledTask -TaskName $interactiveTask
    Add-Content (Join-Path $env:LOCALAPPDATA 'runner-watchdog-win.log') "$(Get-Date) restarted"
}
if ($Install) {
    Install-RunHidden
    Copy-Item $PSCommandPath $installed
    Unregister-ScheduledTask -TaskName $watchTask -Confirm:$false -ErrorAction SilentlyContinue
    if (Get-ScheduledTask -TaskName $watchTask -ErrorAction SilentlyContinue) {
        Write-Output 'the task cannot be replaced unelevated; keeping it as-is'
    } else {
        $action = New-ScheduledTaskAction -Execute $runHidden BACKTICK
            -Argument ('"{0}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{1}" -RunnerRoot "{2}"' -f $powershell, $installed, $RunnerRoot)
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskName $watchTask -Action $action -Settings $settings
    }
}
`, "BACKTICK", "\x60")

const svcWinFixture = `$RunnerRoot = if ($env:RUNNER_WIN_ROOT) { $env:RUNNER_WIN_ROOT } else { Join-Path $env:USERPROFILE 'actions-runner' }
$config = Join-Path $RunnerRoot '.runner'
if (-not (Test-Path $config)) { throw 'the runner is not configured on this box' }
$name = $json.agentName
try { $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @('-RunnerRoot', $RunnerRoot); exit $p.ExitCode } catch { exit 1 }
Start-Transcript -Path x
sc.exe create $svc obj= LocalSystem start= delayed-auto
if ($LASTEXITCODE) { throw 'sc.exe create failed' }
& sc.exe @('failure', $svc, 'reset=', '0', 'actions=', 'restart/60000')
sc.exe failureflag $svc 1
& sc.exe @('config', $svc)
$svc = $svc -replace '/', '-'
Write-Output '_work owned by the user: run takeown or git safe.directory'
Write-Output 'Machine PATH: scoop, bun and mise shims; repair with restore_machine_path.ps1; SYSTEM sees no per-user state'
`

const restartWinFixture = `if (Get-Process Runner.Worker -ErrorAction SilentlyContinue) { throw 'a job is running' }
try { $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @('-RunnerRoot', $RunnerRoot); exit $p.ExitCode } catch { exit 1 }
Start-Transcript -Path x
`

const machinePathFixture = `param([switch]$Apply)
# never SetEnvironmentVariable: it writes REG_SZ
$missing = $candidates | Where-Object { $_ -notin $current }
if (Test-Path (Join-Path $env:USERPROFILE 'scoop\shims')) {}
$optional = @("$env:ProgramFiles\Podman", "$env:ProgramFiles\RedHat\Podman")
$expanded = [Environment]::ExpandEnvironmentVariables($entry)
# dedupe the current entries by expanded value
$git = @("$env:ProgramFiles\Git\bin", "$env:USERPROFILE\scoop\apps\git\current\bin")
# prepend Git\bin ahead of System32, never Git\usr\bin (it shadows find and sort)
if (-not $missing -and $orderOk) {
    Write-Host 'Machine PATH already complete'
}
[Microsoft.Win32.Registry]::SetValue($key, 'Path', $new, [Microsoft.Win32.RegistryValueKind]::ExpandString)
Start-Process powershell.exe -Verb RunAs
`

const fsckFixture = `. "$dir/wsl_vhdx_lib.sh"
vhdx="$(wsl_vhdx_path "$distro")"
root="$(MSYS_NO_PATHCONV=1 wsl.exe -d "$distro" -e findmnt -no FSTYPE,OPTIONS /)"
case "$root" in overlay*) echo corrupted ;; esac
helpers="$(MSYS_NO_PATHCONV=1 wsl.exe -l -v | tr -d '\0' | grep -v docker-desktop)"
echo "after the repair: wsl --shutdown"
cat <<EOF
  wsl -d "$helper" -e true
  wsl --mount "$vhdx" --vhd --bare
  lsblk before and after the attach
  findmnt /dev/sdX must print nothing
  e2fsck -fn /dev/sdX, then e2fsck -fy /dev/sdX
  wsl --unmount "$vhdx"
  no helper: wsl --export "$distro" backup.tar
EOF
`

const doctorFixture = `win_git_root="$(dirname "$(cygpath -w /cmd)")"
realpath -m "$entry"
log_warn win-bash-shadow "run restore_machine_path.ps1"
log_warn win-machine-path "run restore_machine_path.ps1 -Apply; see restore_machine_path.ps1"
MSYS_NO_PATHCONV=1 wsl.exe -l --running
log_warn wsl-ro "run just wsl-fsck"
`

const statusWinFixture = `Get-Task 'dotfiles-runner-interactive'
$svc = Get-Service actions.runner.*
if ($svc.StartType -eq 'Disabled' -and -not (Get-Process Runner.Listener)) { 'FAIL run just runner-svc-install' }
`

func windowsHostBase() Inputs {
	return Inputs{
		runnerModeWin:     modeWinFixture,
		runnerWatchdogWin: watchdogFixture,
		runnerSvcWin:      svcWinFixture,
		restartSvcWin:     restartWinFixture,
		machinePathPs1:    machinePathFixture,
		fsckSh:            fsckFixture,
		gcStatusScript:    statusWinFixture,
		doctorScript:      doctorFixture,
	}
}

func TestWindowsHostFacts(t *testing.T) {
	m, wd, sv, rs, mp, fk := runnerModeWin, runnerWatchdogWin, runnerSvcWin, restartSvcWin, machinePathPs1, fsckSh
	runCases(t, windowsHostFacts(), windowsHostBase, []ruleCase{
		{"the switch names a host", edit(m, "'actions-runner'", "'C:/Users/Absin/actions-runner'"), "test_mode_switch_exists_and_is_generic"},
		{"the switch forwards no mode", edit(m, "'-Mode', $Mode, ", ""), "test_mode_switch_shares_the_elevation_conventions"},
		{"the switch ignores a job", edit(m, "if (Get-Process Runner.Worker -ErrorAction SilentlyContinue) { throw 'a job is running; -Force to override' }\n", ""), "test_mode_switch_refuses_to_kill_a_running_job"},
		{"the task has a time limit", edit(m, "-ExecutionTimeLimit ([TimeSpan]::Zero)", "-ExecutionTimeLimit (New-TimeSpan -Days 3)"), "test_interactive_mode_shape"},
		{"the service stays delayed-auto", edit(m, "start= disabled", "start= demand"), "test_interactive_mode_shape"},
		{"service mode stays manual", edit(m, "start= delayed-auto", "start= demand"), "test_service_mode_is_the_inverse"},
		{"status calls interactive mode a warning", edit(gcStatusScript, "Get-Task 'dotfiles-runner-interactive'\n", ""), "test_status_recognises_deliberate_interactive_mode"},
		{"takeown gives Administrators", edit(m, "takeown /F $dir /R /D Y", "takeown /F $dir /A /R /D Y"), "test_interactive_mode_reowns_foreign_work_checkouts"},
		{"the watchdog kills", edit(wd, "    Start-ScheduledTask -TaskName $interactiveTask\n", "    Stop-Process -Name Runner.Worker\n    Start-ScheduledTask -TaskName $interactiveTask\n"), "test_watchdog_exists_and_is_generic"},
		{"the watchdog restarts silently", edit(wd, "'runner-watchdog-win.log'", "'x.log'"), "test_watchdog_writes_a_log_line_on_every_restart"},
		{"the task runs the working tree's copy", edit(wd, "-f $powershell, $installed, $RunnerRoot", "-f $powershell, $PSCommandPath, $RunnerRoot"), "test_watchdog_task_runs_a_copy_outside_the_working_tree"},
		{"the task starts powershell.exe itself", edit(wd, "-Execute $runHidden \x60", "-Execute (Get-Command powershell.exe).Source \x60"), "test_watchdog_task_starts_through_run_hidden"},
		{"the task is removed before the copy", edit(wd, "    Install-RunHidden\n    Copy-Item $PSCommandPath $installed\n    Unregister-ScheduledTask -TaskName $watchTask -Confirm:$false -ErrorAction SilentlyContinue\n", "    Unregister-ScheduledTask -TaskName $watchTask -Confirm:$false -ErrorAction SilentlyContinue\n    Install-RunHidden\n    Copy-Item $PSCommandPath $installed\n"), "test_watchdog_task_starts_through_run_hidden"},
		{"the switch keeps the legacy shortcut", edit(m, "Remove-Item (Join-Path $startup 'actions-runner.lnk') # the legacy Startup shortcut\n", ""), "test_mode_switch_wires_the_watchdog_and_removes_the_legacy_lnk"},
		{"the watchdog fights an existing task", edit(wd, "    if (Get-ScheduledTask -TaskName $watchTask -ErrorAction SilentlyContinue) {", "    if ($false) {"), "test_watchdog_install_keeps_a_task_it_cannot_replace"},
		{"the PATH is written as REG_SZ", edit(mp, "$expanded = ", "[Environment]::SetEnvironmentVariable('Path', $new, 'Machine')\n$expanded = "), "test_writes_expandstring_never_setenvironmentvariable"},
		{"the PATH is overwritten", func(in Inputs) {
			edit(mp, "$missing = $candidates | Where-Object { $_ -notin $current }", "$new = $candidates")(in)
			edit(mp, "if (-not $missing -and $orderOk) {", "if ($orderOk) {")(in)
		}, "test_merges_instead_of_clobbering"},
		{"a user path is hard-coded", edit(mp, "if (Test-Path", "$x = 'C:\\Users\\nino\\bin'\nif (Test-Path"), "test_detects_optional_dirs_instead_of_hardcoding_users"},
		{"Red Hat Podman wins", edit(mp, `@("$env:ProgramFiles\Podman", "$env:ProgramFiles\RedHat\Podman")`, `@("$env:ProgramFiles\RedHat\Podman", "$env:ProgramFiles\Podman")`), "test_optional_container_path_uses_native_podman_not_docker_desktop"},
		{"missing entries compare unexpanded", edit(mp, "$expanded = [Environment]::ExpandEnvironmentVariables($entry)", "$expanded = $entry"), "test_missing_comparison_expands_env_vars"},
		{"no dedupe", edit(mp, "# dedupe the current entries by expanded value\n", ""), "test_dedupes_existing_entries_by_expanded_value"},
		{"the write needs no -Apply", edit(mp, "param([switch]$Apply)", "param()"), "test_requires_apply_switch_and_self_elevates"},
		{"Git\\bin is appended", edit(mp, "# prepend Git\\bin ahead of System32", "# append Git\\bin after System32"), "test_git_bin_is_prepended_ahead_of_system32"},
		{"complete ignores the order", edit(mp, "if (-not $missing -and $orderOk) {", "if (-not $missing) {"), "test_nothing_to_do_honours_ordering"},
		{"no scoop Git", edit(mp, `, "$env:USERPROFILE\scoop\apps\git\current\bin"`, ""), "test_git_bin_detection_handles_a_scoop_install"},
		{"doctor compares unresolved paths", edit(doctorScript, "realpath -m \"$entry\"\n", ""), "test_doctor_bash_shadow_resolves_git_bin_via_cygpath"},
		{"doctor's bash shadow names no repair", edit(doctorScript, "log_warn win-bash-shadow \"run restore_machine_path.ps1\"", "log_warn win-bash-shadow \"fix the PATH\""), "test_doctor_detects_the_bash_shadow"},
		{"the installer names a host", edit(sv, "$name = $json.agentName", "$name = 'absin-runner'"), "test_installer_is_generic_not_this_host"},
		{"the installer creates a service for air", edit(sv, "if (-not (Test-Path $config)) { throw 'the runner is not configured on this box' }\n", ""), "test_installer_refuses_an_unconfigured_runner"},
		{"restart loses its transcript", edit(rs, "Start-Transcript -Path x\n", ""), "test_installer_self_elevates_and_propagates_the_exit_code"},
		{"sc.exe exit codes ignored", edit(sv, "if ($LASTEXITCODE) { throw 'sc.exe create failed' }\n", ""), "test_sc_exit_codes_are_checked"},
		{"restart kills a job", edit(rs, "if (Get-Process Runner.Worker -ErrorAction SilentlyContinue) { throw 'a job is running' }\n", ""), "test_restart_refuses_to_kill_a_running_job"},
		{"no failure flag", edit(sv, "sc.exe failureflag $svc 1\n", ""), "test_installer_service_shape"},
		{"no work ownership warning", edit(sv, "Write-Output '_work owned by the user: run takeown or git safe.directory'\n", ""), "test_installer_warns_about_localsystem_work_ownership"},
		{"no PATH onion check", edit(sv, "; SYSTEM sees no per-user state", ""), "test_installer_verifies_the_machine_path_onion"},
		{"status ignores a disabled service", edit(gcStatusScript, "'FAIL run just runner-svc-install'", "'WARN'"), "test_status_surfaces_a_stopped_or_disabled_service"},
		{"fsck repairs itself", edit(fk, "root=\"$(", "MSYS_NO_PATHCONV=1 wsl.exe -d \"$helper\" -e e2fsck -fy /dev/sdc\nroot=\"$("), "test_fsck_stays_advisory"},
		{"fsck walks for the vhdx", edit(fk, "vhdx=\"$(wsl_vhdx_path \"$distro\")\"", "vhdx=\"$(find /mnt/c -name ext4.vhdx | head -1)\""), "test_fsck_uses_the_shared_vhdx_resolver"},
		{"fsck reads dmesg", func(in Inputs) {
			edit(fk, "-e findmnt -no FSTYPE,OPTIONS /", "-e dmesg")(in)
			edit(fk, "findmnt /dev/sdX must print nothing", "grep /dev/sdX /proc/mounts must print nothing")(in)
		}, "test_detection_is_mount_state_not_dmesg"},
		{"a bare wsl.exe boots the default distro", edit(fk, "root=\"$(MSYS_NO_PATHCONV=1 wsl.exe -d \"$distro\" -e", "root=\"$(MSYS_NO_PATHCONV=1 wsl.exe -e"), "test_wsl_invocations_disable_msys_conversion_and_pin_the_distro"},
		{"the list keeps its NULs", edit(fk, " | tr -d '\\0'", ""), "test_wsl_list_output_is_denulled"},
		{"helpers include docker", edit(fk, " | grep -v docker-desktop", ""), "test_helper_selection_excludes_docker_and_wsl1"},
		{"the runbook skips the dry run", edit(fk, "e2fsck -fn /dev/sdX, then ", ""), "test_runbook_covers_the_dangerous_steps"},
		{"doctor boots WSL", edit(doctorScript, "wsl.exe -l --running", "wsl.exe -l -v"), "test_doctor_advises_wsl_fsck_without_booting_wsl"},
		{"a remount-ro root reads corrupted", edit(fk, "case \"$root\" in overlay*) echo corrupted ;; esac", "case \"$root\" in overlay*|ext4*ro*) echo corrupted ;; esac"), "test_ro_detection_ignores_errors_remount_ro"},
	})
}
