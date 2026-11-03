// Package commandguard is the command guard. It blocks a shell command that
// breaks a rule of these dotfiles: pip, poetry, or pipenv instead of uv; npm,
// yarn, or pnpm instead of bun; make instead of just; a force push to main or
// master; a new .yml file; deleting /; or a gcloud change to infrastructure
// that OpenTofu manages.
//
// It is a port of the Python guard ROOT_AGENTS_hooks_block-prohibited-commands.py,
// decision for decision, quirks included, and is tested against that guard on
// the corpus in internal/guardcorpus. docs/agents/enforcement.md describes what
// it catches and the long tail it accepts.
package commandguard

import (
	"regexp"
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pyshlex"
)

// The rules a block names, for the log.
const (
	RulePythonPackages = "command.pip"
	RuleNodePackages   = "command.node"
	RuleMake           = "command.make"
	RuleForcePush      = "command.force-push"
	RuleYMLFile        = "command.yml"
	RuleRootDeletion   = "command.rm-root"
	RuleGcloudIAM      = "command.gcloud-iam"
	RuleGcloudInfra    = "command.gcloud-infra"
)

// The reasons, word for word the Python guard's.
const (
	msgPythonPackages = "Python package management is 'uv' only (uv add / uv sync / uv run). " +
		"Do not use pip/poetry/pipenv."
	msgNodePackages = "Node package management is 'bun' only. " +
		"Do not use npm/yarn/pnpm (including 'corepack pnpm')."
	msgMake = "Task automation is 'just' only. Add a recipe to the root justfile " +
		"instead of using make."
	msgYML = "creates a '.yml' file via Bash. This project uses '.yaml' exclusively " +
		"(and 'compose.yaml', not docker-compose.*) \u2014 write the .yaml name instead."
	msgForcePush = "Refusing force-push to a protected branch (main/master). Open a PR; " +
		"never rewrite shared history on the default branch."
	msgRootDeletion = "Refusing 'rm -rf /' (or equivalent root deletion)."
	msgGcloudIAM    = "IAM changes go through OpenTofu (iam_*.tf) + PR, not gcloud. See " +
		"docs/agents/iac-drift-policy.md."
	msgGcloudInfra = "This gcloud command mutates IaC-managed infra and will drift from " +
		"tofu. Open an IaC PR. (Read-only debug is fine; emergency rollback " +
		"must be followed by an IaC PR same session.)"
)

// maxDepth is how deep heredoc bodies fed to an interpreter are read.
const maxDepth = 2

// textRule blocks a text that matches its pattern.
type textRule struct {
	pattern *regexp.Regexp
	rule    string
	reason  string
}

// rawGuards read the text with its heredoc bodies dropped but quoting kept,
// since over-blocking is the safe side for these (Python's RAW_GUARDS).
var rawGuards = []textRule{
	{
		regexp.MustCompile(`rm` + pythonSpace + `+(?:-[a-zA-Z]*[rR][a-zA-Z]*` + pythonSpace +
			`+)?(?:-[a-zA-Z]*f[a-zA-Z]*` + pythonSpace + `+)?/(?:$|` + pythonSpace + `)`),
		RuleRootDeletion, msgRootDeletion,
	},
	{
		regexp.MustCompile(`gcloud` + pythonSpace + `.*(?:add-iam-policy-binding|set-iam-policy)`),
		RuleGcloudIAM, msgGcloudIAM,
	},
	{
		regexp.MustCompile(`gcloud` + pythonSpace + `+(?:compute|run|sql|secrets)` + pythonSpace +
			`.*(?:set-machine-type|resize|update|deploy|versions` + pythonSpace + `+add)`),
		RuleGcloudInfra, msgGcloudInfra,
	},
}

// legacyNames are what the guard looks for when the tokenizer fails (Python's
// _legacy_scan, `(^|[^\w./-])(names)(\s|$)`): a name not inside quotes on its
// line, with no word character, `.`, `/`, or `-` before it, and a Python space
// or the end after it.
var legacyNames = []struct {
	names  []string
	rule   string
	reason string
}{
	{[]string{"pip", "pip3", "poetry", "pipenv"}, RulePythonPackages, msgPythonPackages},
	{[]string{"npm", "yarn", "pnpm"}, RuleNodePackages, msgNodePackages},
	{[]string{"make"}, RuleMake, msgMake},
}

var (
	doubleQuoted = regexp.MustCompile(`"[^"]*"`)
	singleQuoted = regexp.MustCompile(`'[^']*'`)
)

// Check returns the guard's verdict on one shell command.
func Check(command string) ir.Outcome {
	return analyze(command, 0)
}

// analyze is Python's analyze: heredocs off, then the raw guards, then the
// token walk (or the legacy scan), then each interpreter heredoc as code.
func analyze(text string, depth int) ir.Outcome {
	if depth > maxDepth {
		return ir.Outcome{}
	}
	cleaned, codeBodies := splitHeredocs(text)
	if outcome := firstMatch(rawGuards, cleaned); outcome.Action == ir.Block {
		return outcome
	}
	var outcome ir.Outcome
	if tokens, err := pyshlex.Split(cleaned); err != nil {
		outcome = legacyScan(cleaned)
	} else {
		outcome = walk(tokens)
	}
	if outcome.Action == ir.Block {
		return outcome
	}
	for _, body := range codeBodies {
		if outcome := analyze(body, depth+1); outcome.Action == ir.Block {
			return outcome
		}
	}
	return ir.Outcome{}
}

// legacyScan removes what is quoted on each line, then looks for the names.
func legacyScan(text string) ir.Outcome {
	lines := strings.Split(text, "\n")
	for i, line := range lines {
		lines[i] = singleQuoted.ReplaceAllString(doubleQuoted.ReplaceAllString(line, ""), "")
	}
	scan := []rune(strings.Join(lines, "\n"))
	notInName := func(r rune) bool { return !isPythonWord(r) && !strings.ContainsRune("./-", r) }
	for _, l := range legacyNames {
		if containsName(scan, l.names, notInName, isPythonSpace) {
			return block(l.rule, l.reason)
		}
	}
	return ir.Outcome{}
}

func firstMatch(rules []textRule, text string) ir.Outcome {
	for _, r := range rules {
		if r.pattern.MatchString(text) {
			return block(r.rule, r.reason)
		}
	}
	return ir.Outcome{}
}

func block(rule, reason string) ir.Outcome {
	return ir.Outcome{Action: ir.Block, Rule: rule, Reason: reason}
}

// blockYML blocks a .yml file; what names the file comes first in the reason.
func blockYML(what string) ir.Outcome {
	return block(RuleYMLFile, what+msgYML)
}
