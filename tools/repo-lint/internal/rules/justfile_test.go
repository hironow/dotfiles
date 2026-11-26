package rules

import (
	"strings"
	"testing"
)

const spokeJustBlocks = "ROOT_AGENTS_docs_agents_project-structure.md"

// edit replaces the first old in the text input at path; a fixture that no
// longer holds old fails the test instead of passing unchanged.
func edit(path, old, new string) func(Inputs) {
	return func(in Inputs) {
		text, _ := in[path].(string)
		if !strings.Contains(text, old) {
			panic("fixture of " + path + " lacks " + old)
		}
		in[path] = strings.Replace(text, old, new, 1)
	}
}

// editSpoke is edit for one file of the spoke glob.
func editSpoke(old, new string) func(Inputs) {
	return func(in Inputs) {
		spokes := in[spokeGlob].(map[string]any)
		text := spokes[spokeJustBlocks].(string)
		if !strings.Contains(text, old) {
			panic("spoke fixture lacks " + old)
		}
		spokes[spokeJustBlocks] = strings.Replace(text, old, new, 1)
	}
}

const gateJustfile = `ci: check check-forbidden-tokens-branch
    @echo ok

check:
    @just check-except-go
    just go-lint
    just go-test

check-except-go:
    @echo 'Python (ruff check, no --fix)...'
    @just rttm-check
    just js-lint
    just js-typecheck
    just pi-jev-test
    git -C site --work-tree=.. ls-files -z x | xargs -0 -r mise x -- vp -C site fmt --check
    @mise exec -- go run tools/text-hygiene/main.go

lint:
    @just rttm-lint rttm-typecheck
    just js-lint
    just js-typecheck
    just pi-jev-test

fmt:
    @just rttm-fmt

harden-env:
    bash scripts/harden_env.sh

rttm-fmt:
    @{{ UV_RUN }} --only-group lint ruff format .

rttm-lint:
    @{{ UV_RUN }} --only-group lint ruff check .

rttm-typecheck:
    @{{ UV_RUN }} --group lint ty check

rttm-check: rttm-lint rttm-typecheck
    @cd tools/rttm && {{ UV_RUN }} --group lint python -m pytest -q tests

runner-watchdog-install: run-hidden-build
    powershell.exe -File scripts/runner_watchdog_win.ps1 -Install

runner-mode-interactive: run-hidden-build
    powershell.exe -File scripts/runner_mode_win.ps1 -Mode interactive

runner-gc-install: run-hidden-build
    bash scripts/install_runner_gc.sh

go-lint:
    golangci-lint run ./...

go-fmt:
    golangci-lint fmt ./...
`

func TestJustfileGateLegs(t *testing.T) {
	base := func() Inputs { return Inputs{justfilePath: gateJustfile} }
	j := justfilePath
	runCases(t, justfileGateLegs(), base, []ruleCase{
		{"ci stops rescanning the branch", edit(j, "ci: check check-forbidden-tokens-branch", "ci: check other"), "check-forbidden-tokens-branch"},
		{"ci stops starting with check", edit(j, "ci: check check-forbidden-tokens-branch", "ci: check-forbidden-tokens-branch"), "ci: check "},
		{"an installer stops building run-hidden", edit(j, "runner-gc-install: run-hidden-build", "runner-gc-install:"), "run-hidden-build"},
		{"rttm-check stops type checking", edit(j, "rttm-check: rttm-lint rttm-typecheck", "rttm-check: rttm-lint"), "rttm-typecheck"},
		{"check skips the non-Go legs", edit(j, "    @just check-except-go\n", ""), "@just check-except-go"},
		{"check skips the Go lint", edit(j, "    just go-lint\n    just go-test", "    just go-test"), "go-lint"},
		{"a header comment is not a leg", edit(j, "lint:\n    @just rttm-lint rttm-typecheck\n    just js-lint\n    just js-typecheck\n", "lint: # just js-typecheck\n    @just rttm-lint rttm-typecheck\n    just js-lint\n"), "just js-typecheck"},
		{"a gate takes a dependency", edit(j, "check:\n", "check: lint\n"), "line of its own name"},
		{"a comment that fixes is not a leg", edit(j, "    @just rttm-check\n", "    @just rttm-check # then ruff --fix\n"), "--fix"},
		{"lint skips the type check", edit(j, "lint:\n    @just rttm-lint rttm-typecheck\n    just js-lint\n    just js-typecheck\n", "lint:\n    @just rttm-lint rttm-typecheck\n    just js-lint\n"), "just js-typecheck"},
		{"check-except-go skips the Pi tests", edit(j, "    just pi-jev-test\n    git", "    git"), "just pi-jev-test"},
		{"check-except-go stops checking the JS format", edit(j, "vp -C site fmt --check", "vp -C site fmt"), "vp -C site fmt --check"},
		{"check-except-go drops the hygiene gate", edit(j, "    @mise exec -- go run tools/text-hygiene/main.go\n", ""), "tools/text-hygiene"},
		{"check-except-go fixes files", edit(j, "    @just rttm-check\n", "    @just rttm-check\n    ruff check --fix .\n"), "--fix"},
		{"check-except-go skips RTTM", edit(j, "    @just rttm-check\n", ""), "just rttm-check"},
		{"lint skips RTTM", edit(j, "    @just rttm-lint rttm-typecheck\n", ""), "just rttm-lint"},
		{"fmt skips RTTM", edit(j, "    @just rttm-fmt\n", "    @echo fmt\n"), "just rttm-fmt"},
		{"RTTM types are checked without the project", edit(j, "--group lint ty check", "--only-group lint ty check"), "--only-group lint ty"},
		{"RTTM tests leave the lint group", edit(j, "--group lint python -m pytest", "python -m pytest"), "--group lint python -m pytest"},
		{"RTTM types mention the project-less mode", edit(j, "    @{{ UV_RUN }} --group lint ty check\n", "    # never --only-group lint ty\n    @{{ UV_RUN }} --group lint ty check\n"), "--only-group lint ty"},
		{"harden-env runs something else", edit(j, "bash scripts/harden_env.sh", "bash scripts/other.sh"), "scripts/harden_env.sh"},
		{"harden-env is gone", edit(j, "harden-env:\n", "harden-it:\n"), "harden-env"},
		{"go-fmt stops using golangci-lint", edit(j, "golangci-lint fmt ./...", "go fmt ./..."), "golangci-lint fmt"},
		{"go-lint stops using golangci-lint", edit(j, "golangci-lint run ./...", "go vet ./..."), "golangci-lint run"},
		{"vp lints", edit(j, "    @just rttm-fmt\n", "    @just rttm-fmt\n    mise x -- vp -C site lint\n"), "vp -C site lint"},
		{"vp checks", edit(j, "    @just rttm-fmt\n", "    @just rttm-fmt\n    mise x -- vp -C site check\n"), "vp -C site check"},
		{"an RTTM recipe is gone", edit(j, "rttm-fmt:\n    @{{ UV_RUN }} --only-group lint ruff format .\n", ""), "rttm-fmt"},
	})
	// What the replaced tests accepted stays accepted.
	for name, change := range map[string]func(Inputs){
		"check runs golangci-lint directly": edit(j, "    just go-lint\n", "    golangci-lint run ./...\n"),
		"harden-env delegates to a recipe":  edit(j, "harden-env:\n    bash scripts/harden_env.sh", "harden-env: harden-inner\n\nharden-inner:\n    bash scripts/harden_env.sh"),
		"an echo of --fix is not a fix":     edit(j, "    @just rttm-check\n", "    @just rttm-check\n    echo 'run ruff --fix yourself'\n"),
		"rttm-check names its type check":   edit(j, "rttm-check: rttm-lint rttm-typecheck", "rttm-check: rttm-lint\n    @just rttm-typecheck"),
	} {
		in := base()
		change(in)
		if got := findingsOf(t, justfileGateLegs(), in); len(got) != 0 {
			t.Errorf("%s: %v", name, got)
		}
	}
}

const (
	unixInterpreter    = "[unix]\nset script-interpreter := [\"bash\"]\n"
	windowsInterpreter = "[windows]\nset script-interpreter := [\"sh\", \"-c\", 'PATH=\"/usr/bin:$PATH\"; exec /usr/bin/bash \"$0\" \"$@\"']\n"
	windowsShell       = "[windows]\nset shell := [\"sh\", \"-eu\", \"-o\", \"pipefail\", \"-c\", 'PATH=\"/usr/bin:$PATH\"; exec /usr/bin/sh -eu -o pipefail -c \"$0\"']\n"
	safeJustfile       = windowsShell + "\n" + unixInterpreter + "\n" + windowsInterpreter + `
doctor:
    @bash scripts/doctor.sh

deploy:
    @bash scripts/deploy.sh

clean:
    @bash scripts/clean.sh

prune-rogue-npm-globals:
    @bash scripts/rogue_npm_globals.sh prune

[script]
go-lint:
    set -euo pipefail
    echo "#!not a shebang, a string"
`
	safeTemplate = unixInterpreter + "\n" + windowsInterpreter + `
[script]
check:
    set -euo pipefail
    uv run ruff check --no-fix .
`
)

func TestJustfileShellSafety(t *testing.T) {
	base := func() Inputs {
		return Inputs{justfilePath: safeJustfile, templateJustfile: safeTemplate}
	}
	// doctor's test found it with parameters too
	withParams := base()
	edit(justfilePath, "doctor:\n", "doctor verbose='':\n")(withParams)
	if got := findingsOf(t, justfileShellSafety(), withParams); len(got) != 0 {
		t.Errorf("doctor may take parameters: %v", got)
	}
	j, tpl := justfilePath, templateJustfile
	runCases(t, justfileShellSafety(), base, []ruleCase{
		{"doctor becomes a shebang recipe", edit(j, "doctor:\n    @bash scripts/doctor.sh", "doctor:\n    #!/usr/bin/env bash\n    bash scripts/doctor.sh"), "doctor"},
		{"deploy runs something else", edit(j, "@bash scripts/deploy.sh", "@bash scripts/install.sh"), "bash scripts/deploy.sh"},
		{"clean runs something else", edit(j, "@bash scripts/clean.sh", "@sh scripts/clean.sh"), "bash scripts/clean.sh"},
		{"the prune recipe is gone", edit(j, "prune-rogue-npm-globals:\n    @bash scripts/rogue_npm_globals.sh prune\n", ""), "prune-rogue-npm-globals"},
		{"the prune recipe stops pruning", edit(j, "rogue_npm_globals.sh prune", "rogue_npm_globals.sh list"), "bash scripts/rogue_npm_globals.sh prune"},
		{"a recipe runs through a shebang", edit(j, "go-lint:\n    set -euo pipefail", "go-lint:\n    #!/usr/bin/env bash"), "go-lint"},
		{"a template recipe runs through a shebang", edit(tpl, "check:\n    set -euo pipefail", "check:\n    #!/usr/bin/env bash"), "check"},
		{"the template's unix interpreter differs", edit(tpl, "set script-interpreter := [\"bash\"]", "set script-interpreter := [\"bash\", \"-eu\"]"), "[unix]"},
		{"the template's windows interpreter differs", edit(tpl, "exec /usr/bin/bash", "exec bash"), "[windows]"},
		{"the justfile sets no windows interpreter", edit(j, windowsInterpreter, ""), "[windows]"},
		{"the windows shell starts with bash", edit(j, "set shell := [\"sh\",", "set shell := [\"bash\","), "[windows] shell"},
		{"the windows shell hands the recipe elsewhere", edit(j, "\"pipefail\", \"-c\", 'PATH", "\"pipefail\", \"-x\", 'PATH"), "[windows] shell"},
		{"the windows shell loses nounset", edit(j, "exec /usr/bin/sh -eu -o pipefail", "exec /usr/bin/sh -e -o pipefail"), "-eu"},
		{"the windows shell loses pipefail", edit(j, "exec /usr/bin/sh -eu -o pipefail -c", "exec /usr/bin/sh -eu -c"), "pipefail"},
		{"the windows shell keeps System32 first", edit(j, "'PATH=\"/usr/bin:$PATH\"; exec /usr/bin/sh", "'exec /usr/bin/sh"), "/usr/bin first"},
		{"the windows interpreter runs another bash", edit(j, "exec /usr/bin/bash", "exec bash"), "script-interpreter"},
		{"deploy takes a parameter", edit(j, "deploy:\n", "deploy target='':\n"), "deploy"},
		{"the windows interpreter starts with bash", edit(j, "set script-interpreter := [\"sh\", \"-c\"", "set script-interpreter := [\"bash\", \"-c\""), "[windows] script-interpreter"},
	})
}

const deprecatedSpoke = "Copy this:\n\n```just\nset shell := [\"bash\", \"-c\"]\n\nhello:\n    echo hi\n```\n\nNever write env_var( in prose? Prose is not a just block.\n"

func TestJustfileNoDeprecated(t *testing.T) {
	base := func() Inputs {
		return Inputs{
			justfilePath:     "set shell := [\"bash\", \"-c\"]\n\nhello:\n    echo {{ env('HOME') }}\n",
			templateJustfile: "check:\n    echo ok\n",
			spokeGlob:        map[string]any{spokeJustBlocks: deprecatedSpoke, "ROOT_AGENTS_docs_agents_naming.md": "No blocks.\n"},
		}
	}
	runCases(t, justfileNoDeprecated(), base, []ruleCase{
		{"set windows-shell", edit(justfilePath, "set shell", "set windows-shell"), "set windows-shell"},
		{"set windows-powershell", edit(justfilePath, "set shell := [\"bash\", \"-c\"]", "set windows-powershell := true"), "set windows-powershell"},
		{"env_var in the template", edit(templateJustfile, "echo ok", "echo {{ env_var('HOME') }}"), "env_var()"},
		{"env_var_or_default in a spoke's block", editSpoke("echo hi", "echo {{ env_var_or_default('X', 'y') }}"), "env_var_or_default()"},
	})
}

const docJustfile = `# Build the thing.
build:
    echo build

# A block of explanation
# that spans two lines.
[doc('Deploy it.')]
deploy:
    echo deploy

# a block
# of comments
[private]
helper:
    echo helper

# a block
# of comments
_hidden:
    echo hidden

X := "a"
`

func TestJustfileRecipeDoc(t *testing.T) {
	base := func() Inputs { return Inputs{justfilePath: docJustfile, templateJustfile: docJustfile} }
	runCases(t, justfileRecipeDoc(), base, []ruleCase{
		{"a recipe under a block without a doc", edit(justfilePath, "[doc('Deploy it.')]\n", ""), "deploy"},
		{"the template too", edit(templateJustfile, "[doc('Deploy it.')]\n", "[group('setup')]\n"), "deploy"},
		{"a recipe with parameters", edit(justfilePath, "# Build the thing.\nbuild:", "# Build\n# the thing.\nbuild target:"), "build"},
	})
}

const bunJustfile = `# npm, npx, pnpm and yarn are banned; a comment may name them.
prune-rogue-npm-globals:
    @echo 'on npm ETARGET run just harden-env'
    mise x npm:@informalsystems/quint@0.33.0 -- quint
    mise exec npm:@scope/tool@1.0.0 -- tool
    mise x 'npm:@scope/tool@1.0.0' -- tool

[doc('Remove npm globals the bun backend did not install.')]
check-npm-g:
    bun --version
`

func TestJustfileBunOnly(t *testing.T) {
	base := func() Inputs { return Inputs{justfilePath: bunJustfile} }
	var cases []ruleCase
	for _, command := range []string{
		"npm ls --global",
		"command -v npx >/dev/null 2>&1 || exit 127",
		"echo 'Hint: npm i -g @devcontainers/cli'",
		"mise x -- npm root -g",
		"git ls-files | xargs -0 -r npm view x",
		"sudo npm install x",
		"env A=1 npm root",
		"time npm root",
		"dir=`npm root -g`",
		"mise x npm:@scope/tool@1.0.0 -- npm root -g",
		"mise exec 'npm:@scope/tool@1.0.0' -- npm root -g",
		"mise x node@26 npm:@scope/tool@1.0.0 -- npx tool",
		"mise exec npm:@scope/tool@1.0.0 -- pnpm store path",
		"mise x npm:@scope/tool@1.0.0 -- yarn cache dir",
		"@-npm ci",
	} {
		cases = append(cases, ruleCase{command, edit(justfilePath, "    bun --version\n", "    bun --version\n    "+command+"\n"), command})
	}
	runCases(t, justfileBunOnly(), base, cases)
}

const jsListJustfile = `JS_FILES := "'*.ts' '*.js'"

fmt:
    git -C site --work-tree=.. ls-files -z {{ JS_FILES }} | xargs -0 -r mise x -- vp -C site fmt

check-except-go:
    git -C site --work-tree=.. ls-files -z {{ JS_FILES }} | xargs -0 -r mise x -- vp -C site fmt --check
`

func TestJustfileOneJSFileList(t *testing.T) {
	base := func() Inputs { return Inputs{justfilePath: jsListJustfile} }
	j := justfilePath
	runCases(t, justfileOneJSFileList(), base, []ruleCase{
		{"a gate spells its own list", edit(j, "ls-files -z {{ JS_FILES }} | xargs -0 -r mise x -- vp -C site fmt --check", "ls-files -z '*.ts' | xargs -0 -r mise x -- vp -C site fmt --check"), "{{ JS_FILES }}"},
		{"the check gate is gone", edit(j, "check-except-go:\n    git -C site --work-tree=.. ls-files -z {{ JS_FILES }} | xargs -0 -r mise x -- vp -C site fmt --check\n", ""), "fmt --check"},
		{"vp runs outside site", edit(j, "fmt:\n", "fmt:\n    mise x -- vp fmt .\n"), "vp fmt"},
		{"a vp line the list does not feed", edit(j, "fmt:\n", "fmt:\n    mise x -- vp -C site fmt src\n"), "vp -C site"},
	})
}

func TestJustfileNoClaudeCodeLint(t *testing.T) {
	base := func() Inputs { return Inputs{justfilePath: "lint-claude:\n    claude plugin validate --strict .\n"} }
	runCases(t, justfileNoClaudeCodeLint(), base, []ruleCase{
		{"the third-party linter returns", edit(justfilePath, "claude plugin validate --strict .", "bunx claude-code-lint ."), "claude-code-lint"},
	})
}

func TestJustfileUVRunModes(t *testing.T) {
	base := func() Inputs {
		return Inputs{justfilePath: "UV_RUN := \"mise exec -- uv run --frozen\"\nUV_RUN_SCRIPT := \"mise exec -- uv run\"\n"}
	}
	j := justfilePath
	runCases(t, justfileUVRunModes(), base, []ruleCase{
		{"the gates leave the lockfile", edit(j, "uv run --frozen", "uv run"), "--frozen"},
		{"scripts get --frozen", edit(j, "UV_RUN_SCRIPT := \"mise exec -- uv run\"", "UV_RUN_SCRIPT := \"mise exec -- uv run --frozen\""), "UV_RUN_SCRIPT"},
		{"scripts run another command", edit(j, "UV_RUN_SCRIPT := \"mise exec -- uv run\"", "UV_RUN_SCRIPT := \"uv run\""), "UV_RUN_SCRIPT"},
		{"no script runner", edit(j, "UV_RUN_SCRIPT := \"mise exec -- uv run\"\n", ""), "both"},
	})
}

func TestJustfileAWSCLI(t *testing.T) {
	base := func() Inputs {
		return Inputs{justfilePath: awsCLI + "\n\n" + awsListRec}
	}
	j := justfilePath
	runCases(t, justfileAWSCLI(), base, []ruleCase{
		{"Windows runs the mise build", edit(j, `{ "aws" }`, `{ CLI_TOOLS_MISE + " exec http:aws -- aws" }`), "AWS_CLI"},
		{"aws-list runs another aws", edit(j, "{{ AWS_CLI }} configure", "aws configure"), "aws-list"},
	})
}
