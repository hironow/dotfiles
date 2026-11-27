package rules

import "testing"

const doctorFixture2 = `_brew_docker='docker docker-buildx docker-compose docker-credential-helper docker-desktop orbstack'
if has podman-compose; then log_ok 'podman-compose'; else log_err 'podman-compose' 'install it'; fi
if podman --version >/dev/null; then podman info --format '{{.Host.Os}}'; else log_err 'podman' 'install podman'; fi
# zsh is the supported interactive shell on Linux
log_warn 'zsh' 'run: sudo apt-get install -y zsh, then chsh -s "$(command -v zsh)"'
rogue_out=$(bash scripts/rogue_npm_globals.sh detect 2>/dev/null)
rc=$?
if [ "$rc" -ne 0 ]; then
  log_warn 'npm-rogue' 'scan failed'
elif [ -n "$rogue_out" ]; then
  log_warn 'npm-rogue' 'run: just prune-rogue-npm-globals'
fi
retired_out=$(bash scripts/retired_python_tools.sh detect 2>/dev/null)
[ -n "$retired_out" ] && log_warn 'python-retired' 'run: just prune-retired-python-tools'
if ps_profile_starship_before_mise "$p"; then :; fi
if ps_profile_mise_stale "$p"; then :; fi
if ps_profile_mise_unclosed "$p"; then :; fi
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    usr_bin="$(cygpath -w /usr/bin)"
    git_cmd="$(cygpath -w /cmd)"
    [ -x "$SYSTEMROOT/System32/WindowsPowerShell/v1.0/powershell.exe" ] && ps="$SYSTEMROOT/System32/WindowsPowerShell/v1.0/powershell.exe"
    persisted=$("$ps" -Command "[Environment]::GetEnvironmentVariable('Path','User')")
    log_warn 'win-cygpath' "run: [Environment]::SetEnvironmentVariable('Path', ...)"
    log_warn 'win-git-cmd' 'run: just harden-env'
    log_warn 'win-machine-path' 'in an ELEVATED shell: [Microsoft.Win32.Registry]::SetValue(k, v, d, ExpandString)'
    for marker in 'starship init' 'mise activate' 'mise node corepack'; do :; done
    cmp -s config/mise/config.toml "$HOME/.config/mise/config.toml" || log_warn 'win-deploy' 'run: just deploy'
    [ -f "$(cygpath -u "$APPDATA")/uv/uv.toml" ] || log_warn 'win-uv' 'run: just harden-env'
    has jq && has shellcheck || log_warn 'win-clis' 'run: scoop install jq shellcheck'
    winget_links="${HOME}/AppData/Local/Microsoft/WinGet/Links"
    for cli in codex claude copilot pi; do log_warn 'winget-shadow' "run: winget uninstall $cli"; done
    ;;
esac
`

func doctorBase() Inputs { return Inputs{doctorScript: doctorFixture2} }

func TestDoctorFacts(t *testing.T) {
	d := doctorScript
	runCases(t, doctorFacts(), doctorBase, []ruleCase{
		{"Git usr/bin is hard-coded", edit(d, `usr_bin="$(cygpath -w /usr/bin)"`, `usr_bin='C:\Program Files\Git\usr\bin'`), "test_doctor_checks_persisted_path_reaches_cygpath"},
		{"the deploy hint is vague", edit(d, "'run: just deploy'", "'redeploy'"), "test_doctor_checks_deploy_managed_state"},
		{"uv's Windows config is unchecked", edit(d, "    [ -f \"$(cygpath -u \"$APPDATA\")/uv/uv.toml\" ] || log_warn 'win-uv' 'run: just harden-env'\n", ""), "test_doctor_checks_windows_uv_hardening"},
		{"the scoop line misses shellcheck", edit(d, "scoop install jq shellcheck", "scoop install jq"), "test_doctor_checks_scoop_unix_clis"},
		{"git's cmd dir is unchecked", edit(d, "win-git-cmd", "win-git"), "test_doctor_checks_persisted_path_reaches_git_cmd"},
		{"the Machine PATH fix writes REG_SZ", edit(d, "ExpandString", "String"), "test_doctor_checks_machine_path_sanity"},
		{"no absolute powershell.exe", edit(d, "    [ -x \"$SYSTEMROOT/System32/WindowsPowerShell/v1.0/powershell.exe\" ] && ps=\"$SYSTEMROOT/System32/WindowsPowerShell/v1.0/powershell.exe\"\n", ""), "test_doctor_powershell_fallback_when_system32_off_path"},
		{"WinGet's links are unchecked", edit(d, "/WinGet/Links", "/WinGet"), "test_doctor_checks_the_winget_links_dir"},
		{"pi is not checked", edit(d, "for cli in codex claude copilot pi", "for cli in codex claude copilot"), "test_doctor_covers_every_mise_managed_ai_cli"},
		{"the shadow has no fix", edit(d, "run: winget uninstall $cli", "remove $cli"), "test_doctor_reports_winget_shadow_with_a_fix"},
		{"the rogue check has no fix", edit(d, "'run: just prune-rogue-npm-globals'", "'prune them'"), "test_doctor_runs_rogue_detector"},
		{"the rogue check is Windows-only", func(in Inputs) {
			edit(d, "rogue_out=$(bash scripts/rogue_npm_globals.sh detect 2>/dev/null)\n", "")(in)
			edit(d, "  MINGW*|MSYS*|CYGWIN*)\n", "  MINGW*|MSYS*|CYGWIN*)\n    rogue_out=$(bash scripts/rogue_npm_globals.sh detect 2>/dev/null)\n")(in)
		}, "test_doctor_rogue_check_is_cross_platform"},
		{"a failed scan reads as clean", edit(d, "if [ \"$rc\" -ne 0 ]; then\n  log_warn 'npm-rogue' 'scan failed'\nelif", "if false; then\n  :\nelif"), "test_doctor_warns_not_ok_on_scan_error"},
		{"the order goes unreported", edit(d, "if ps_profile_starship_before_mise \"$p\"; then :; fi\n", ""), "test_doctor_reports_a_misordered_profile"},
		{"doctor upgrades the block", edit(d, "if ps_profile_mise_stale \"$p\"; then :; fi", "if ps_profile_mise_stale \"$p\"; then ps_profile_mise_upgrade \"$p\"; fi"), "test_doctor_reports_both_states_and_writes_nothing"},
		{"zsh's install line is gone", edit(d, "sudo apt-get install -y zsh", "apt install zsh"), "test_doctor_reports_zsh_on_linux"},
		{"a missing podman is only a warning", edit(d, "log_err 'podman' 'install podman'", "log_warn 'podman' 'install podman'"), "test_doctor_checks_required_podman_cli_and_selected_engine"},
		{"the retired tools have no fix", edit(d, "'run: just prune-retired-python-tools'", "'prune them'"), "test_doctor_runs_the_detector_cross_platform"},
	})
}

func TestInstallFacts(t *testing.T) {
	runCases(t, installFacts(), func() Inputs { return Inputs{installSh: "step_base\nstep_zsh\n"} }, []ruleCase{
		{"the zsh step is skipped", edit(installSh, "step_zsh\n", "# step_zsh\n"), "test_install_sh_runs_the_zsh_step"},
	})
}

const brewfileFixture = `tap "homebrew/bundle"
brew "podman"
cask "ghostty"
`

func TestBrewfileDockerFree(t *testing.T) {
	base := func() Inputs { return Inputs{doctorScript: doctorFixture2, macBrewfile: brewfileFixture} }
	runCases(t, brewfileDockerFree(), base, []ruleCase{
		{"doctor stops flagging orbstack", edit(doctorScript, " docker-desktop orbstack'", " docker-desktop'"), "test_doctor_and_the_brewfile_test_forbid_the_same_packages"},
		{"the Mac installs Docker Desktop", edit(macBrewfile, "cask \"ghostty\"\n", "cask \"ghostty\"\ncask \"docker-desktop\"\n"), "test_mac_package_manifest_provisions_podman_without_docker_providers"},
		{"the Mac has no podman", edit(macBrewfile, "brew \"podman\"\n", ""), "test_mac_package_manifest_provisions_podman_without_docker_providers"},
	})
}
