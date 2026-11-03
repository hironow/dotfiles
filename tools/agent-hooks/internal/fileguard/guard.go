// Package fileguard is the files guard. It blocks writing a file whose name
// breaks a naming rule of these dotfiles: the .yml extension (this project
// uses .yaml) and the Docker Compose v1 names (use compose.yaml). AGENTS.md,
// CLAUDE.md, and anything under a docs/agents/ directory may name them as
// examples.
//
// It is a port of the shell guard ROOT_AGENTS_hooks_block-prohibited-files.sh,
// decision for decision, quirks included, and is tested against that guard on
// the corpus in internal/guardcorpus.
package fileguard

import (
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// The rules a block names, for the log.
const (
	RuleComposeV1    = "file.compose-v1"
	RuleYMLExtension = "file.yml"
)

// Basename is the basename(1) the shell guard would run on this machine,
// which decides what it does with a path that starts with "-". Both fail on
// such a path (other than "-" itself), and the guard stops there, except that
// GNU's takes --help and --version, and their prefixes, as options that
// succeed: the guard then reads on.
type Basename int

const (
	// BSDBasename is BSD's basename, as on macOS.
	BSDBasename Basename = iota
	// GNUBasename is GNU's basename, as on Linux and in Git Bash.
	GNUBasename
)

// Check returns the guard's verdict on the paths of one tool call, as the
// shell guard decides with the given basename. Like the shell guard, it reads
// each path line by line, skips empty lines, and drops NUL bytes (bash drops
// them from a command substitution).
func Check(paths []string, basename Basename) ir.Outcome {
	for _, path := range paths {
		for line := range strings.SplitSeq(strings.ReplaceAll(path, "\x00", ""), "\n") {
			if line == "" {
				continue
			}
			if line != "-" && strings.HasPrefix(line, "-") {
				if basename == GNUBasename && isGNUInfoOption(line) {
					continue // basename prints its help or version, which names no file
				}
				// basename fails, and the shell guard exits 1 before reading
				// further: no harness blocks on that.
				return ir.Outcome{}
			}
			if exempt(line) {
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
func exempt(path string) bool {
	for _, name := range []string{"AGENTS.md", "CLAUDE.md"} {
		if path == name || strings.HasSuffix(path, "/"+name) {
			return true
		}
	}
	return strings.Contains(path, "/docs/agents/")
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

// isGNUInfoOption reports whether GNU basename takes the argument as --help
// or --version: either option, or a prefix of one ("--h", "--vers").
func isGNUInfoOption(arg string) bool {
	name, ok := strings.CutPrefix(arg, "--")
	return ok && name != "" && (isPrefixOf(name, "help") || isPrefixOf(name, "version"))
}

// isPrefixOf reports whether prefix starts word. getopt_long takes a prefix of
// a long option's name as that option.
func isPrefixOf(prefix, word string) bool {
	return strings.HasPrefix(word, prefix)
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
