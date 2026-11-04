// Package fileguard is the files guard. It blocks writing a file whose name
// breaks a naming rule of these dotfiles: the .yml extension (this project
// uses .yaml) and the Docker Compose v1 names (use compose.yaml). AGENTS.md,
// CLAUDE.md, and anything under a docs/agents/ directory may name them as
// examples.
//
// It is a port of the shell guard ROOT_AGENTS_hooks_block-prohibited-files.sh,
// decision for decision, quirks included, except for the guard's bugs, which
// it fixes (fixes_test.go). It is tested against that guard, and against the
// guard with those bugs fixed, on the corpus in internal/guardcorpus.
package fileguard

import (
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// The rules a block names, for the log.
const (
	RuleComposeV1    = "file.compose-v1"
	RuleYMLExtension = "file.yml"
	// RuleUnresolved blocks a path the shell could not resolve as the
	// harness resolves it (ir.Call.PathUnresolved): the guard cannot judge a
	// file it cannot name.
	RuleUnresolved = "file.unresolved"
)

// CheckCall is the guard's verdict on a call: Check on its paths (Paths),
// unless its file path could not be resolved as the harness resolves it.
func CheckCall(call ir.Call) ir.Outcome {
	if call.PathUnresolved {
		return block(RuleUnresolved, "agent-hook cannot tell which file Pi writes for the path '"+
			call.Fields[ir.FieldFilePath].Text+"' (a file: URL in an unusual form, or ~ with no home directory). "+
			"Name the file by a plain path.")
	}
	return Check(Paths(call))
}

// Check returns the guard's verdict on the paths of one tool call. Like the
// shell guard, it reads each path line by line, skips empty lines, and drops
// NUL bytes (bash drops them from a command substitution).
//
// fixed-dash-line: the shell guard took each line's base name with
// basename(1), which fails on a line that starts with "-" (or, on GNU, prints
// a message for a prefix of --help or --version); the guard then exited 1,
// which no harness blocks on, and checked no later line. Here the base name
// is taken without basename(1), so every line is checked.
//
// Each path's first line is where the path starts (fixed-docs-agents-relative,
// in exempt); Paths gives a file_path, each file of a patch, and a
// notebook_path as paths of their own.
func Check(paths []string) ir.Outcome {
	for _, path := range paths {
		start := true
		for line := range strings.SplitSeq(strings.ReplaceAll(path, "\x00", ""), "\n") {
			pathStart := start
			start = false
			if line == "" || exempt(line, pathStart) {
				continue
			}
			if outcome := checkName(baseName(line)); outcome.Action == ir.Block {
				return outcome
			}
		}
	}
	return ir.Outcome{}
}

// exempt is the shell guard's `case` pattern
// `*/AGENTS.md|AGENTS.md|*/CLAUDE.md|CLAUDE.md|*/docs/agents/*`: the policy
// files may name prohibited patterns as examples.
//
// fixed-docs-agents-relative: `*/docs/agents/*` needs a "/" before docs, so
// the shell guard blocked a relative path under docs/agents/ (Codex's patch
// names its files relative to the session), though it exempts a bare
// AGENTS.md. Here that path is exempt too, but only on a line where a path
// starts (pathStart): a later line is part of the path above it, so /w/x, a
// newline, and docs/agents/y.yml names a file under no docs/agents/
// directory, and stays blocked as the shell guard blocked it.
func exempt(path string, pathStart bool) bool {
	for _, name := range []string{"AGENTS.md", "CLAUDE.md"} {
		if path == name || strings.HasSuffix(path, "/"+name) {
			return true
		}
	}
	return strings.Contains(path, "/docs/agents/") || (pathStart && strings.HasPrefix(path, "docs/agents/"))
}

// checkName applies the two naming rules to a file's base name.
func checkName(base string) ir.Outcome {
	switch {
	case base == "docker-compose.yaml" || base == "docker-compose.yml":
		return block(RuleComposeV1,
			"'"+base+"' is the deprecated Compose v1 name. Use 'compose.yaml' (Compose Spec v2+).")
	case strings.HasSuffix(base, ".yml"):
		return block(RuleYMLExtension,
			"'"+base+"' uses '.yml'. This project uses '.yaml' exclusively. Rename to '"+
				strings.TrimSuffix(base, ".yml")+".yaml'.")
	default:
		return ir.Outcome{}
	}
}

// baseName is POSIX basename(1) for a path that is not empty: trailing
// slashes go, then everything up to the last slash; a path of slashes is "/".
func baseName(path string) string {
	trimmed := strings.TrimRight(path, "/")
	if trimmed == "" {
		return "/"
	}
	return trimmed[strings.LastIndex(trimmed, "/")+1:]
}

func block(rule, reason string) ir.Outcome {
	return ir.Outcome{Action: ir.Block, Rule: rule, Reason: reason}
}
