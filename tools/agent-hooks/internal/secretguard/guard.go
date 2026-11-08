// Package secretguard is the secrets guard. It blocks writing content that
// looks like a live credential: provider API keys and tokens (OpenAI,
// Anthropic, GitHub, AWS, Slack, GitLab, Google) and private key headers.
// It is defense in depth, not a secret scanner.
//
// It is a port of the shell guard ROOT_AGENTS_hooks_block-secrets.sh, and is
// tested against that guard on the corpus in internal/guardcorpus.
package secretguard

import (
	"regexp"
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// RuleCredential is the rule a block names, for the log.
const RuleCredential = "secret.credential"

// Rules lists every rule a block of the guard names.
func Rules() []string {
	return []string{RuleCredential}
}

const reason = "content looks like a live secret (API key / token / private key). " +
	"Do not commit secrets; use a secret manager and reference via env var."

// credential is the shell guard's `grep -E` pattern, as it is. grep matches
// line by line; no class here matches a newline, so matching the whole text
// finds the same tokens.
var credential = regexp.MustCompile(`sk-(ant|proj|svcacct|admin)-[A-Za-z0-9_-]{20,}` +
	`|sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}` +
	`|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----` +
	`|xox[baprs]-[0-9][0-9A-Za-z-]{9,}|glpat-[0-9A-Za-z_-]{20,}|AIza[0-9A-Za-z_-]{35}`)

// Check returns the guard's verdict on the contents of one tool call. Like the
// shell guard, it drops NUL bytes first (bash drops them from a command
// substitution).
func Check(contents []string) ir.Outcome {
	for _, content := range contents {
		if credential.MatchString(strings.ReplaceAll(content, "\x00", "")) {
			return ir.Outcome{Action: ir.Block, Rule: RuleCredential, Reason: reason}
		}
	}
	return ir.Outcome{}
}
