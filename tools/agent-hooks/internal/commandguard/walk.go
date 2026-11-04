package commandguard

import (
	"regexp"
	"slices"
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// The guard's word lists, as in the Python guard.
var (
	pipCommands         = words("pip", "pip3", "poetry", "pipenv")
	nodeCommands        = words("npm", "yarn", "pnpm")
	corepackPMs         = words("pnpm", "yarn", "npm")
	corepackValueFlags  = words("--cwd") // corepack flags that take the next token
	wrappers            = words("env", "sudo", "time", "nohup", "command", "xargs")
	rtkRunSubcommands   = words("bypass", "proxy", "run", "err", "test", "summary", "smart")
	rtkShellStringFlags = words("-c", "--command")
	commandSeparators   = words(";", "&&", "||", "|", "&", "(", ")", ";;")
	ymlCreatingCommands = words("touch", "tee", "cp", "mv")
	protectedRefs       = words("main", "master")
	forcePushFlags      = words("-f", "--force", "--force-if-includes")
)

const (
	// rtk is the mandatory output proxy (ADR 0047); what it runs is a command too.
	rtkLauncher = "rtk"
	// rtkShellNameFlag takes the shell's name; the shell string is an operand.
	rtkShellNameFlag = "--shell"
)

// assignment is a NAME=VALUE prefix (Python's ASSIGNMENT_RE).
var assignment = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*=`)

func words(list ...string) map[string]bool {
	set := make(map[string]bool, len(list))
	for _, w := range list {
		set[w] = true
	}
	return set
}

// commandWalk is Python's _CommandWalker: a walk over the tokens with a minimal
// shell grammar. A separator ends a command. At a command's start the walk
// skips NAME=VALUE prefixes, wrappers, and rtk with its own words, and
// re-analyzes the one shell string `rtk run -c "..."` runs. A redirection
// operator makes the next token its target.
type commandWalk struct {
	atStart         bool
	pendingRedirect bool
	inRTK           bool
	rtkRan          bool // past an rtk verb that runs a command, still in rtk's options
	shellString     bool // a -c or --shell flag says an operand is a shell string
	skipValue       bool // the next token is --shell's value, a shell's name
	name            string
	args            []string
}

// walk returns the guard's verdict on the tokens of one text.
func walk(tokens []string) ir.Outcome {
	w := commandWalk{atStart: true}
	for _, token := range tokens {
		if outcome := w.step(token); outcome.Action == ir.Block {
			return outcome
		}
	}
	return finalize(w.name, w.args)
}

func (w *commandWalk) step(token string) ir.Outcome {
	if isOperator(token) {
		if strings.Contains(token, ">") {
			w.pendingRedirect = true
		}
		if !commandSeparators[token] {
			return ir.Outcome{}
		}
		outcome := finalize(w.name, w.args)
		*w = commandWalk{atStart: true, pendingRedirect: w.pendingRedirect}
		return outcome
	}
	if w.pendingRedirect {
		w.pendingRedirect = false
		if isYMLName(token) {
			return blockYML("'> " + token + "' ")
		}
		return ir.Outcome{}
	}
	if w.atStart {
		return w.commandStart(token)
	}
	w.args = append(w.args, token)
	return ir.Outcome{}
}

// commandStart handles a token where a command name may still come.
func (w *commandWalk) commandStart(token string) ir.Outcome {
	if assignment.MatchString(token) {
		return ir.Outcome{}
	}
	base := basename(token)
	if wrappers[base] {
		return ir.Outcome{}
	}
	if base == rtkLauncher {
		w.inRTK, w.rtkRan, w.shellString, w.skipValue = true, false, false, false
		return ir.Outcome{}
	}
	if w.inRTK {
		if consumed, outcome := w.rtkWord(token, base); consumed {
			return outcome
		}
	}
	w.name, w.atStart = base, false
	return ir.Outcome{}
}

// rtkWord handles a token after rtk, before the command it runs. It reports
// whether rtk consumed the token; if not, the token is the command.
func (w *commandWalk) rtkWord(token, base string) (bool, ir.Outcome) {
	switch {
	case w.skipValue:
		w.skipValue = false
	case w.rtkRan && (rtkShellStringFlags[token] || token == rtkShellNameFlag):
		w.shellString = true
		w.skipValue = token == rtkShellNameFlag
	case strings.HasPrefix(token, "-"):
		// rtk's own options, such as --ultra-compact
	case w.rtkRan && w.shellString:
		w.atStart, w.inRTK = false, false
		return true, analyze(token, 1) // rtk runs this one string through a shell
	case rtkRunSubcommands[base]:
		w.rtkRan = true // transparent: the real command is next
	default:
		w.inRTK = false
		return false, ir.Outcome{}
	}
	return true, ir.Outcome{}
}

// finalize is Python's _finalize: the verdict on one complete command.
func finalize(name string, args []string) ir.Outcome {
	switch {
	case pipCommands[name]:
		return block(RulePythonPackages, msgPythonPackages)
	case nodeCommands[name]:
		return block(RuleNodePackages, msgNodePackages)
	case name == "corepack" && corepackRunsPackageManager(args):
		return block(RuleNodePackages, msgNodePackages)
	case name == "make":
		return block(RuleMake, msgMake)
	case name == "git" && slices.Contains(args, "push") && forcePushesProtectedRef(args):
		return block(RuleForcePush, msgForcePush)
	case ymlCreatingCommands[name]:
		return ymlCreation(name, args)
	default:
		return ir.Outcome{}
	}
}

// corepackRunsPackageManager reports whether the first operand after
// corepack's own flags names a package manager (`corepack pnpm@9 i`) rather
// than a subcommand (`corepack enable`).
func corepackRunsPackageManager(args []string) bool {
	skipNext := false
	for _, arg := range args {
		if skipNext {
			skipNext = false
			continue
		}
		if strings.HasPrefix(arg, "-") {
			skipNext = corepackValueFlags[arg]
			continue
		}
		pm, _, _ := strings.Cut(arg, "@")
		return arg != "" && corepackPMs[pm]
	}
	return false
}

// forcePushesProtectedRef reports whether a push rewrites main or master: any
// force flag with a refspec whose destination is protected, or the flagless
// `+<refspec>` form.
func forcePushesProtectedRef(args []string) bool {
	hasForceFlag := slices.ContainsFunc(args, isForcePushFlag)
	for _, arg := range args {
		if strings.HasPrefix(arg, "-") {
			continue
		}
		forcedRefspec := strings.HasPrefix(arg, "+")
		dest := strings.TrimLeft(arg, "+")
		dest = dest[strings.LastIndex(dest, ":")+1:] // src:dst -> dst
		dest = basename(dest)                        // refs/heads/main -> main
		if protectedRefs[dest] && (hasForceFlag || forcedRefspec) {
			return true
		}
	}
	return false
}

func isForcePushFlag(arg string) bool {
	return forcePushFlags[arg] || arg == "--force-with-lease" || strings.HasPrefix(arg, "--force-with-lease=")
}

// ymlCreation blocks touch or tee of a .yml name, and cp or mv to one.
func ymlCreation(name string, args []string) ir.Outcome {
	var positional []string
	for _, arg := range args {
		if !strings.HasPrefix(arg, "-") {
			positional = append(positional, arg)
		}
	}
	if name == "touch" || name == "tee" {
		for _, arg := range positional {
			if isYMLName(arg) {
				return blockYML("'" + name + " " + arg + "' ")
			}
		}
		return ir.Outcome{}
	}
	if len(positional) > 0 {
		if dest := positional[len(positional)-1]; isYMLName(dest) {
			return blockYML("'" + name + " ... " + dest + "' ")
		}
	}
	return ir.Outcome{}
}

// isOperator reports whether a token is made only of `();<>|&`.
func isOperator(token string) bool {
	return token != "" && strings.Trim(token, "();<>|&") == ""
}

func basename(token string) string {
	return token[strings.LastIndex(token, "/")+1:]
}

func isYMLName(token string) bool {
	base := basename(token)
	return strings.HasSuffix(base, ".yml") || base == "docker-compose.yaml"
}
