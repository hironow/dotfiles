package rules

import "testing"

const gcShFixture = `#!/usr/bin/env bash
for _w in $(pgrep -x Runner.Worker 2>/dev/null); do :; done
# pgrep -f would match this script itself
if [ "$FORCE" != "1" ] && _foreign_worker; then exit 0; fi
case "$(uname -s)" in
  MINGW*)
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d x -- bash /x
    if [ -x /usr/local/bin/runner-gc.sh ]; then :; fi
    powershell.exe -NoProfile -NonInteractive \
      -ExecutionPolicy Bypass -File "$d/runner_gc_win.ps1"
    ;;
esac
RETENTION="${RUNNER_GC_RETENTION:-2h}"
[[ "$id" =~ ^(sha256:)?([a-f0-9]{64})$ ]]
jq 'select(.Id == $id)'
reference="$(_normalize_image_id "$reference")"
if [ "$created" -ge "$PODMAN_CUTOFF" ]; then podman rmi --no-prune "$id"; fi
find _diag -mtime +7 -delete
keep="${RUNNER_GC_TOOLCACHE_KEEP:-3}" # newest patch per series
ls _tool | sort -V
if _foreign_worker; then
  exit 0
fi
if fstrim / >/dev/null 2>&1; then :; fi
echo "workspaces: aged on .runner-gc-last-used"
if [ -z "${RUNNER_GC_ROOT:-}" ] || [ "${RUNNER_GC_ALLOW_BUSY:-0}" != "1" ]; then :; fi
[ -f "${_rdir}/.runner" ] || exit 0
echo "$RUNNER_WORKSPACE $GITHUB_WORKSPACE"
_runner_managed="_actions _tool _temp _diag _update"
[ -L "${_rdir}/bin" ]; [ -L "${_rdir}/externals" ]; readlink -f x; find x -mmin +1440
`

const gcWinFixture = `function Invoke-PodmanGuarded { Write-Output 'timed out' }
$protect = '_actions', '_tool', '_temp', '_update', '_PipelineMapping'
foreach ($candidate in @($env:RUNNER_WORKSPACE, $env:GITHUB_WORKSPACE)) {}
$items = @(Get-ChildItem x)
$items.Count
$link.LinkType
$retention = if ($x) { $x } else { '2h' }
$imageIdPattern = '\A(?:sha256:)?([a-f0-9]{64})\z'
if ($container.Id -cne $containerId) { continue }
$references += ConvertTo-PodmanImageId $container.Image
if ($created -ge $Cutoff) { Invoke-PodmanGuarded @('rmi', '--no-prune', $imageId) }
$bun = Join-Path $HOME '.bun\bin'; $glob = '*.stale-*'; $floor = (Get-Date).AddHours(-24)
function Get-PodmanJson {
    $cmdlet = Microsoft.PowerShell.Core\Get-Command -Name ConvertFrom-Json -CommandType Cmdlet -ErrorAction Stop
    $convert = @{ InputObject = $text }
    if ($cmdlet.Parameters.ContainsKey('DateKind')) { $convert.DateKind = 'String' }
    $parsed = Microsoft.PowerShell.Utility\ConvertFrom-Json @convert
    return $parsed
}
`

const installShFixture = `_dest="/usr/local/bin/runner-gc.sh"
grep -v "^${_hook_key}=" .env > tmp
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d x -- bash /x
powershell.exe -File install_runner_gc_win.ps1
`

const installWinFixture = `$enc = New-Object System.Text.UTF8Encoding($false)
$lines = $lines | Where-Object { $_ -notmatch "^$hookKey=" }
Unregister-ScheduledTask -TaskName x -Confirm:$false
$hookCmd = $payload -replace '\\', '/'
$principal = 'S4U'
try { Register-ScheduledTask x } catch { Write-Output 'fires only while signed in' }
Start-Process powershell.exe -Verb RunAs -ArgumentList @('-Retention', $Retention, '-Distro', $Distro)
Start-Transcript -Path x
`

const diskShFixture = `export PATH="$HOME/.local/share/mise/shims:$PATH"
if [ "$_win" -eq 1 ]; then
  _add "$HOME/AppData/Local/x"
else
  _add "$HOME/.cache/uv"
fi
if [ "${DISK_GC_HUGGINGFACE:-0}" = 1 ]; then _add "$HOME/.cache/huggingface"; fi
go clean -modcache
[ "${DISK_GC_NO_WSL:-0}" = 1 ] || MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d "$_distro" -e bash -lc "DISK_GC_HUGGINGFACE=${DISK_GC_HUGGINGFACE:-0} DISK_GC_ALLOW_BUSY=${DISK_GC_ALLOW_BUSY:-0} bash /x"
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' tasklist \
  /FI "IMAGENAME eq Runner.Worker.exe"
`

const statusShFixture = `[ -n "$hook" ] || { echo "hook: not set in $env"; continue; }
grep -lF "${_h} is not a valid path to a script" x
Select-String -SimpleMatch -Pattern ($h + ' is not a valid path to a script')
bash "$dir/gc_github_status.sh"
echo "just runner-svc-restart -Force"
printf 'systemctl restart actions.runner.%s.%s.service'
`

func gcBase() Inputs {
	return Inputs{
		gcSh:           gcShFixture,
		gcWin:          gcWinFixture,
		gcInstallSh:    installShFixture,
		gcInstallWin:   installWinFixture,
		diskGcSh:       diskShFixture,
		compactSh:      "# never runs wsl --shutdown itself\necho 'run: wsl --shutdown'\ndu -B1 \"$vhdx\"\nvhdx=\"$(wsl_vhdx_path \"$distro\")\"\n",
		vhdxLib:        "reg.exe query 'HKCU\\...\\Lxss' /s | grep DistributionName\n",
		fsckSh:         "wsl_vhdx_locate_hint \"$distro\"\n",
		gcStatusScript: statusShFixture,
		githubStatusSh: "gh api \"orgs/$o/actions/runners\" --paginate --jq '.runners[]'\ngh api \"repos/$r/actions/runners\" --paginate --jq '.runners[]'\necho 'wait 5 min for the self-heal'\n",
		gcModel:        "val RETENTION_SECONDS = 7200\nageSeconds > RETENTION_SECONDS\nval ParentProtection = parentExists\nval ReferenceProtection = referenced implies imageExists\nval ConfigurationProtection = not(configurationOk) implies not(removed)\n",
	}
}

func TestRunnerGcFacts(t *testing.T) {
	g, w, is, iw, d := gcSh, gcWin, gcInstallSh, gcInstallWin, diskGcSh
	runCases(t, runnerGcFacts(), gcBase, []ruleCase{
		{"pgrep -x is gone", edit(g, "pgrep -x Runner.Worker", "pgrep Runner.Worker"), "test_job_detection_uses_exact_name_match"},
		{"pgrep -f runs", edit(g, "for _w", "pgrep -f Runner.Worker >/dev/null\nfor _w"), "test_job_detection_uses_exact_name_match"},
		{"wsl.exe without MSYS guards", edit(is, "MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe", "wsl.exe"), "test_dispatchers_disable_msys_path_conversion"},
		{"a container matched by image identity", edit(w, "if ($container.Id -cne $containerId) { continue }", "if ($false) { continue }"), "test_image_identity_is_strict_and_separate_from_container_identity"},
		{"an image prune", edit(g, "find _diag", "podman image prune -a\nfind _diag"), "test_gc_never_reclaims_unfiltered_persistent_cache"},
		{"a forced rmi", edit(w, "@('rmi', '--no-prune', $imageId)", "@('rmi', '--no-prune', $imageId); & podman rmi -f $imageId"), "test_gc_never_reclaims_unfiltered_persistent_cache"},
		{"a ps prune argument", edit(w, "$items.Count", "$items.Count; Invoke-PodmanGuarded @('image', 'prune')"), "test_gc_never_reclaims_unfiltered_persistent_cache"},
		{"the hook line is not stripped", edit(is, `grep -v "^${_hook_key}=" .env > tmp`, "cat .env > tmp"), "test_installer_upserts_hook_without_duplicating"},
		{"sed -i", edit(is, "_dest=", "sed -i 's/x/y/' .env\n_dest="), "test_installer_upserts_hook_without_duplicating"},
		{"compaction stops WSL", edit(compactSh, "du -B1", "wsl.exe --shutdown\ndu -B1"), "test_compaction_stays_advisory"},
		{"compaction forces sparse", edit(compactSh, "du -B1", "wsl --manage x --set-sparse true\ndu -B1"), "test_compaction_stays_advisory"},
		{"compaction allows unsafe", edit(compactSh, "du -B1", "wsl --manage x --allow-unsafe\ndu -B1"), "test_compaction_stays_advisory"},
		{"compaction stops documenting the shutdown", edit(compactSh, "# never runs wsl --shutdown itself\necho 'run: wsl --shutdown'\n", ""), "test_compaction_stays_advisory"},
		{"a bare podman call", edit(w, "$items.Count", "$items.Count\n& podman ps"), "test_windows_gc_podman_calls_carry_a_watchdog"},
		{"the watchdog is gone", edit(w, "function Invoke-PodmanGuarded { Write-Output 'timed out' }", "function Invoke-Podman { }"), "test_windows_gc_podman_calls_carry_a_watchdog"},
		{"the .env gets a BOM", edit(iw, "UTF8Encoding($false)", "UTF8Encoding($true)"), "test_windows_installer_upserts_hook_without_bom"},
		{"the Windows hook line is not stripped", edit(iw, `-notmatch "^$hookKey="`, `-notmatch "x"`), "test_windows_installer_upserts_hook_without_bom"},
		{"the old task stays", edit(iw, "Unregister-ScheduledTask -TaskName x -Confirm:$false\n", ""), "test_windows_installer_upserts_hook_without_bom"},
		{"the GC execs into WSL", edit(g, "MSYS2_ARG_CONV_EXCL='*' wsl.exe -d x", "MSYS2_ARG_CONV_EXCL='*' exec wsl.exe -d x"), "test_windows_entrypoint_drives_both_runners"},
		{"the installer skips the Windows leg", edit(is, "powershell.exe -File install_runner_gc_win.ps1\n", ""), "test_windows_entrypoint_drives_both_runners"},
		{"_diag is not rotated", edit(g, "find _diag -mtime +7 -delete\n", ""), "test_diag_logs_are_rotated_on_the_linux_leg"},
		{"the series count is fixed", edit(g, "${RUNNER_GC_TOOLCACHE_KEEP:-3}", "3"), "test_toolcache_keeps_the_newest_patch_of_each_series"},
		{"toolcache sorts lexically", edit(g, "ls _tool | sort -V", "ls _tool | sort -r"), "test_toolcache_reaping_is_semver_ordered_and_atomic"},
		{"FORCE reaches the toolcache", edit(g, "if _foreign_worker; then\n", "if [ \"$FORCE\" != \"1\" ] && _foreign_worker; then\n"), "test_toolcache_reaping_never_races_a_running_job"},
		{"the live checkout is not spared", edit(w, "$env:RUNNER_WORKSPACE, $env:GITHUB_WORKSPACE", "$env:RUNNER_WORKSPACE"), "test_workspace_sweep_protects_the_live_checkout"},
		{"the protect list loses _update", edit(w, " '_update',", ""), "test_workspace_sweep_uses_an_explicit_runner_dir_allowlist"},
		{"a counted collection is not wrapped", edit(w, "$items = @(Get-ChildItem x)", "$items = Get-ChildItem x"), "test_counted_collections_are_wrapped_for_powershell_51"},
		{"the symlink is not resolved", edit(w, "$link.LinkType", "$link.Name"), "test_stale_version_pruning_requires_a_resolvable_symlink"},
		{"the Windows leg starts differently", edit(g, "-ExecutionPolicy Bypass -File", "-File"), "test_the_tests_start_the_windows_gc_as_runner_gc_sh_does"},
		{"no fstrim", edit(g, "if fstrim / >/dev/null 2>&1; then :; fi\n", ""), "test_gc_discards_freed_blocks_back_to_the_host"},
		{"an unguarded fstrim", edit(g, "if fstrim / >/dev/null 2>&1; then :; fi", "fstrim /"), "test_gc_discards_freed_blocks_back_to_the_host"},
		{"the payload is assumed", edit(g, "if [ -x /usr/local/bin/runner-gc.sh ]; then :; fi\n", ""), "test_windows_dispatch_falls_back_to_the_checkout"},
		{"disk-gc runs WSL as root", edit(d, `wsl.exe -d "$_distro" -e bash`, `wsl.exe -u root -d "$_distro" -e bash`), "test_disk_gc_reaches_the_wsl_runner_user"},
		{"disk-gc cannot skip WSL", edit(d, `[ "${DISK_GC_NO_WSL:-0}" = 1 ] || `, ""), "test_disk_gc_reaches_the_wsl_runner_user"},
		{"disk-gc deletes the module cache", edit(d, "go clean -modcache", "rm -rf ~/go/pkg/mod"), "test_disk_gc_uses_go_clean_for_the_module_cache"},
		{"disk-gc misses the shims", edit(d, `export PATH="$HOME/.local/share/mise/shims:$PATH"`, ":"), "test_disk_gc_finds_mise_managed_tools"},
		{"huggingface collected by default", edit(d, "go clean", "_add \"$HOME/.cache/huggingface\"\ngo clean"), "test_disk_gc_keeps_huggingface_opt_in"},
		{"huggingface only on one leg", edit(d, "  _add \"$HOME/.cache/uv\"\n", "  _add \"$HOME/.cache/uv\"\n  [ \"${DISK_GC_HUGGINGFACE:-0}\" = 1 ] && :\n"), "test_disk_gc_huggingface_optin_reaches_both_legs"},
		{"the WSL leg misses the opt-in", edit(d, `-lc "DISK_GC_HUGGINGFACE=${DISK_GC_HUGGINGFACE:-0} `, `-lc "`), "test_disk_gc_huggingface_optin_reaches_both_legs"},
		{"compaction measures the logical size", edit(compactSh, `du -B1 "$vhdx"`, `stat -c %s "$vhdx"`), "test_compaction_measures_allocated_not_logical_size"},
		{"compaction takes the first vhdx", edit(compactSh, "du -B1", "find / -name ext4.vhdx | head -1\ndu -B1"), "test_compaction_resolves_vhdx_for_the_target_distro"},
		{"the resolver ignores the distro", edit(vhdxLib, "grep DistributionName", "grep BasePath"), "test_compaction_resolves_vhdx_for_the_target_distro"},
		{"the payload has no extension", edit(is, `_dest="/usr/local/bin/runner-gc.sh"`, `_dest="/usr/local/bin/runner-gc"`), "test_hook_payload_carries_a_script_extension"},
		{"the Windows hook is a command line", edit(iw, "$hookCmd = $payload -replace '\\\\', '/'", "$hookCmd = \"powershell.exe -File $payload\""), "test_windows_hook_is_a_path_not_a_command_line"},
		{"an unset hook falls through", edit(gcStatusScript, `echo "hook: not set in $env"; continue;`, `echo "hook: not set in $env";`), "test_status_never_claims_proof_for_a_hook_that_is_not_set"},
		{"no S4U fallback", edit(iw, "try { Register-ScheduledTask x } catch { Write-Output 'fires only while signed in' }", "Register-ScheduledTask x; 'fires only while signed in'"), "test_windows_installer_survives_without_elevation"},
		{"an and-or chain", edit(gcStatusScript, `bash "$dir/gc_github_status.sh"`, `[ -n "$x" ] && echo a || echo b`+"\n"+`bash "$dir/gc_github_status.sh"`), "test_no_ambiguous_and_or_chains"},
		{"workspaces are aged on mtime", edit(g, " on .runner-gc-last-used", ""), "test_wsl_leg_sweeps_workspaces_too"},
		{"a named root alone sweeps a busy runner", edit(g, `if [ -z "${RUNNER_GC_ROOT:-}" ] || [ "${RUNNER_GC_ALLOW_BUSY:-0}" != "1" ]; then :; fi`, `if [ -z "${RUNNER_GC_ROOT:-}" ]; then :; fi`), "test_workspace_sweep_is_exercisable_on_a_busy_runner"},
		{"any root is swept", edit(g, `[ -f "${_rdir}/.runner" ] || exit 0`, ":"), "test_workspace_sweep_demands_proof_it_is_a_runner"},
		{"a second marker names the missing dir", edit(g, `_runner_managed="_actions _tool _temp _diag _update"`, `_runner_managed="_actions _tool _temp _diag" # _runner_managed=_update`), "test_workspace_sweep_excludes_runner_dirs_by_name"},
		{"runner dirs by prefix", edit(g, `_runner_managed="_actions _tool _temp _diag _update"`, `_runner_managed="_actions _tool"`), "test_workspace_sweep_excludes_runner_dirs_by_name"},
		{"no 24h floor", edit(g, "-mmin +1440", "-mmin +120"), "test_superseded_runner_versions_need_a_live_symlink"},
		{"no UAC relaunch", edit(iw, "-Verb RunAs ", ""), "test_gc_installer_offers_uac_elevation_for_s4u"},
		{"the hook path keeps backslashes", edit(iw, "$hookCmd = $payload -replace '\\\\', '/'", "$hookCmd = $payload"), "test_windows_hook_path_is_dotenv_parseable"},
		{"bun litter has no floor", edit(w, "(Get-Date).AddHours(-24)", "(Get-Date)"), "test_win_gc_sweeps_bun_stale_renames_with_a_day_floor"},
		{"the model retention moves", edit(gcModel, "RETENTION_SECONDS = 7200", "RETENTION_SECONDS = 3600"), "test_model_and_real_retention_and_guards_lockstep"},
		{"the shell retention moves", edit(g, `RETENTION="${RUNNER_GC_RETENTION:-2h}"`, `RETENTION="${RUNNER_GC_RETENTION:-3h}"`), "test_model_and_real_retention_and_guards_lockstep"},
		{"DateKind is set unconditionally", edit(w, "$convert = @{ InputObject = $text }", "$convert = @{ InputObject = $text; DateKind = 'String' }"), "test_get_podman_json_asks_the_real_cmdlet_for_date_kind"},
		{"a second ConvertFrom-Json", edit(w, "$items.Count", "$items.Count; $x = $y | ConvertFrom-Json"), "test_get_podman_json_asks_the_real_cmdlet_for_date_kind"},
		{"a phrase search without the hook", edit(gcStatusScript, `grep -lF "${_h} is not a valid path to a script" x`, `grep -lF "is not a valid path to a script" x`), "test_rejection_scan_is_anchored_to_the_hook_path"},
		{"a regex phrase search", edit(gcStatusScript, `grep -lF "${_h} is`, `grep -l "${_h} is`), "test_rejection_scan_matches_literally"},
		{"tasklist without MSYS guards", edit(d, "MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' tasklist", "tasklist"), "test_tasklist_runs_without_msys_path_conversion"},
		{"the WSL leg misses the busy knob", edit(d, " DISK_GC_ALLOW_BUSY=${DISK_GC_ALLOW_BUSY:-0}", ""), "test_wsl_leg_receives_the_allow_busy_knob"},
		{"fsck uses --get-location", edit(fsckSh, "wsl_vhdx_locate_hint", "wsl.exe --get-location"), "test_fsck_shares_the_locate_hint"},
		{"status skips the GitHub section", edit(gcStatusScript, `bash "$dir/gc_github_status.sh"`, ":"), "test_status_feeds_the_github_section"},
		{"a leading-slash endpoint", edit(githubStatusSh, `gh api "orgs/`, `gh api "/orgs/`), "test_github_section_builds_slashless_endpoints_for_both_scopes"},
		{"no -Force hint", edit(gcStatusScript, "just runner-svc-restart -Force", "just runner-svc-restart"), "test_zombie_runbook_survives_its_own_advice"},
	})
}
