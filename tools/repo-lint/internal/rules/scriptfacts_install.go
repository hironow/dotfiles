package rules

// installSh is the Unix installer.
const installSh = "install.sh"

// installFacts: install.sh keeps the steps the tests that read it held.
func installFacts() Rule {
	return factRule(
		"install-facts",
		"install.sh runs every step its tests name",
		[]string{installSh},
		[]scriptFact{
			// tests/unit/test_install_zsh_steps.py
			fact("test_install_sh_runs_the_zsh_step", matches(installSh, `(?m)^step_zsh$`)),
		},
	)
}
