package rules

import "testing"

const installFixture = `#!/usr/bin/env bash
set -eu
case "$(uname -s)" in
  Darwin) DOTFILES_OS=mac ;;
  Linux) DOTFILES_OS=linux ;;
  MINGW*|MSYS*|CYGWIN*) DOTFILES_OS=windows ;;
  *) echo "unsupported OS" >&2; exit 1 ;;
esac
_skip_windows() {
  echo "skip $1: $2"
}
step_homebrew() {
  [ -n "${INSTALL_SKIP_HOMEBREW:-}" ] && return
  _skip_windows "step_homebrew" "no Homebrew on Windows"
}
step_symlink_dotfiles() {
  _skip_windows "step_symlink_dotfiles" "deploy copies instead"
}
step_sheldon() {
  _skip_windows "step_sheldon" "no zsh on Windows"
}
step_brew_bundle() {
  _skip_windows "step_brew_bundle" "no Homebrew on Windows"
}
step_gcloud_components() {
  [ -n "${INSTALL_SKIP_GCLOUD:-}" ] && return
  _skip_windows "step_gcloud_components" "scoop provides it"
}
step_corepack() {
  case "$DOTFILES_OS" in
    windows) _skip_windows "step_corepack" "no pnpm on native Windows" ;;
    *) corepack enable ;;
  esac
}
step_update_all() {
  _skip_windows "step_update_all" "winget updates it"
}
step_mise_bootstrap() {
  curl -sSfL -o "$t/m.tgz" "https://github.com/jdx/mise/releases/download/v1/m.tgz"
  (cd "$t" && sha256sum -c SHASUMS256.txt)
}
step_mise_install() {
  if [ -n "${INSTALL_SKIP_ADD_UPDATE:-}" ]; then return; fi
  mise install
}
step_homebrew
step_mise_bootstrap
step_mise_install
step_symlink_dotfiles
step_sheldon
step_zsh
step_wsl_clipboard
step_brew_bundle
step_gcloud_components
step_corepack
step_update_all
`

func TestInstallFacts(t *testing.T) {
	i := installSh
	runCases(t, installFacts(), func() Inputs { return Inputs{i: installFixture} }, []ruleCase{
		{"the zsh step is skipped", edit(i, "\nstep_zsh\n", "\n# step_zsh\n"), "test_install_sh_runs_the_zsh_step"},
		{"no DOTFILES_OS", func(in Inputs) {
			for range 3 {
				edit(i, "DOTFILES_OS=", "OS_KIND=")(in)
			}
		}, "test_install_sh_identifies_dotfiles_os"},
		{"no Darwin arm", edit(i, "  Darwin) DOTFILES_OS=mac ;;\n", ""), "test_install_sh_dispatches_mac_linux_windows"},
		{"a Linux arm glued to a word", edit(i, "  Linux) DOTFILES_OS=linux ;;", "  GNULinux) DOTFILES_OS=linux ;;"), "test_install_sh_dispatches_mac_linux_windows"},
		{"an unknown OS goes on", edit(i, `  *) echo "unsupported OS" >&2; exit 1 ;;`, `  *) echo "unsupported OS" >&2 ;;`), "test_install_sh_fails_closed_on_unknown_os"},
		{"a step is not defined", edit(i, "step_sheldon() {\n  _skip_windows \"step_sheldon\" \"no zsh on Windows\"\n}\n", ""), "test_install_sh_defines_required_step_function"},
		{"a step is never called", edit(i, "\nstep_update_all\n", "\n"), "test_step_functions_are_called"},
		{"an override is gone", edit(i, `[ -n "${INSTALL_SKIP_GCLOUD:-}" ] && return`, `true`), "test_install_sh_honours_legacy_skip_env_vars"},
		{"pnpm globals come back", edit(i, "\nstep_update_all\n", "\nstep_update_all\nstep_pnpm_globals\n"), "test_install_sh_enables_corepack_not_pnpm_globals"},
		{"a Windows stub is back", edit(i, "\nstep_update_all\n", "\nstep_update_all\n_todo_windows step_x\n"), "test_install_sh_no_todo_windows_stub_remains"},
		{"corepack runs on Windows", edit(i, `windows) _skip_windows "step_corepack" "no pnpm on native Windows" ;;`, `windows) corepack enable ;;`), "test_install_sh_windows_step_corepack_is_skipped"},
		{"a skip without a reason", edit(i, `_skip_windows "step_update_all" "winget updates it"`, `_skip_windows "step_update_all" "  "`), "test_install_sh_skip_windows_calls_have_reason"},
		{"mise bootstrap is never called", edit(i, "\nstep_mise_bootstrap\n", "\n"), "test_defines_and_calls_mise_bootstrap"},
		{"mise install is not defined", edit(i, "step_mise_install() {", "install_mise() {"), "test_defines_and_calls_mise_install"},
		{"mise is piped to a shell", edit(i, "  (cd \"$t\" && sha256sum -c SHASUMS256.txt)\n", "  curl -sSfL https://mise.run | sh\n"), "test_mise_bootstrap_downloads_verified_binary"},
		{"mise install cannot be skipped", edit(i, `  if [ -n "${INSTALL_SKIP_ADD_UPDATE:-}" ]; then return; fi`+"\n", ""), "test_mise_install_is_skippable"},
		{"the clipboard step is skipped", edit(i, "\nstep_wsl_clipboard\n", "\n"), "test_step_is_in_normal_install_flow"},
	})
}

func TestPyCompileReadsLikePython(t *testing.T) {
	for _, c := range []struct {
		pattern, text string
		found         bool
	}{
		{`_skip_windows\s+"x"`, "_skip_windows\u00a0\"x\"", true},       // NBSP is \s in Python
		{`DOTFILES_OS\s*=`, "DOTFILES_OS\u3000=", true},                 // so is the ideographic space
		{`\bMISE_OFFLINE=0\b`, "# \u00e9MISE_OFFLINE=0", false},         // \u00e9 is a word character
		{`\bMISE_OFFLINE=0\b`, "# MISE_OFFLINE=0 x", true},              // a space is not
		{`Acquire::Retries "\d+"`, "Acquire::Retries \"\u0663\"", true}, // Arabic-Indic three is \d
		{`\*\)[\s\S]*?exit\s+[1-9]`, "*)\n  exit 1", true},
	} {
		if got := pyCompile(c.pattern).Search(c.text); got != c.found {
			t.Errorf("pyCompile(%q).Search(%q) = %v, want %v", c.pattern, c.text, got, c.found)
		}
	}
}
