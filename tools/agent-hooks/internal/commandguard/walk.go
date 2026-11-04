package commandguard

import (
	"regexp"
	"slices"
	"strings"
	"unicode/utf8"

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
	ymlCreatingCommands = words("touch", "tee", "cp", "mv")
	protectedRefs       = words("main", "master")
	forcePushFlags      = words("-f", "--force", "--force-if-includes")
	// fixed-command-split: a newline and every control operator end a command.
	commandSeparators = words(";", "&&", "||", "|", "&", "(", ")", ";;", "\n", "|&", ";&", ";;&")
	// fixed-command-start: bash starts a command after these words.
	commandStarts = words("!", "{", "if", "then", "elif", "else", "do", "while", "until", "coproc", "exec")
	// fixed-command-start: a compound command, before which coproc takes a NAME.
	compoundStarts = words("{", "(", "if", "while", "until", "for", "case", "select", "[[")
	// fixed-shell-string: the shells whose -c string the guard reads.
	shells = words("sh", "bash", "zsh", "dash", "ksh")
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
	redirectWrites  bool // fixed-command-split: the pending redirection writes its target
	functionName    bool // fixed-command-start: the next word names a function
	inRTK           bool
	rtkRan          bool     // past an rtk verb that runs a command, still in rtk's options
	shellString     bool     // a -c or --shell flag says an operand is a shell string
	skipValue       bool     // the next token is --shell's value, a shell's name
	depth           int      // fixed-shell-string: the depth of the text walked
	caseStates      []string // fixed-command-start: each open case, and where it stands
	name            string
	args            []string
}

// walk returns the guard's verdict on the tokens of one text, read at depth.
func walk(tokens []token, depth int) ir.Outcome {
	w := commandWalk{atStart: true, depth: depth}
	for _, t := range dropCoprocNames(tokens) {
		if outcome := w.step(t); outcome.Action == ir.Block {
			return outcome
		}
	}
	return w.finalize(w.name, w.args)
}

// dropCoprocNames drops the NAME of `coproc NAME` before a compound command
// (fixed-command-start: bash runs the compound, and NAME only names it).
func dropCoprocNames(tokens []token) []token {
	kept := make([]token, 0, len(tokens))
	for k, t := range tokens {
		if k > 0 && tokens[k-1].text == "coproc" && !tokens[k-1].quoted && k+1 < len(tokens) &&
			compoundStarts[tokens[k+1].text] && !tokens[k+1].quoted {
			continue
		}
		kept = append(kept, t)
	}
	return kept
}

func (w *commandWalk) step(t token) ir.Outcome {
	// a redirection's operand comes first (<<<esac in a body is no esac)
	operand := w.pendingRedirect && !t.op
	if len(w.caseStates) > 0 && !operand && w.followCase(t) {
		return ir.Outcome{}
	}
	if t.op {
		// fixed-command-split: every redirection takes the next word as its
		// operand, and the .yml rule reads the operands of those that write.
		if redirections[t.text] {
			w.pendingRedirect, w.redirectWrites = true, strings.Contains(t.text, ">")
		}
		if !commandSeparators[t.text] {
			return ir.Outcome{}
		}
		outcome := w.finalize(w.name, w.args)
		*w = commandWalk{
			atStart:         true,
			pendingRedirect: w.pendingRedirect,
			redirectWrites:  w.redirectWrites,
			functionName:    w.functionName,
			depth:           w.depth,
			caseStates:      w.caseStates,
		}
		return outcome
	}
	if w.pendingRedirect {
		w.pendingRedirect = false
		if w.redirectWrites && isYMLName(t.text) {
			return blockYML("'> " + t.text + "' ")
		}
		return ir.Outcome{}
	}
	if w.atStart {
		return w.commandStart(t)
	}
	w.args = append(w.args, t.text)
	return ir.Outcome{}
}

// commandStart handles a token where a command name may still come.
func (w *commandWalk) commandStart(t token) ir.Outcome {
	token := t.text
	if assignment.MatchString(token) {
		return ir.Outcome{}
	}
	// fixed-command-start: bash starts a command after its reserved words and
	// after exec; `function NAME` names one.
	if w.functionName {
		w.functionName = false
		return ir.Outcome{}
	}
	if t.text == "function" && !t.quoted {
		w.functionName = true
		return ir.Outcome{}
	}
	if t.text == "case" && !t.quoted {
		w.caseStates = append(w.caseStates, "subject")
		return ir.Outcome{}
	}
	// exec is a builtin, no reserved word: quoted, it is still exec
	if token == "exec" || (commandStarts[token] && !t.quoted) {
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

// followCase follows an open case through one token (fixed-command-start):
// its subject and its patterns are no commands; its bodies are. It reports
// whether it took the token.
func (w *commandWalk) followCase(t token) bool {
	last := len(w.caseStates) - 1
	top := w.caseStates[last]
	switch {
	case (top == "subject" || top == "in") && !t.op:
		if top == "subject" {
			w.caseStates[last] = "in"
		} else if t.text == "in" && !t.quoted {
			w.caseStates[last] = "pattern"
		}
		return true
	case top == "pattern" && !t.op:
		if t.text == "esac" && !t.quoted {
			w.caseStates = w.caseStates[:last]
		}
		return true
	case top == "pattern" && t.text == ")":
		w.caseStates[last] = "body"
		return true
	case top == "pattern" && (t.text == "(" || t.text == "|" || t.text == "\n"):
		return true
	case top == "body" && t.op && (t.text == ";;" || t.text == ";&" || t.text == ";;&"):
		w.caseStates[last] = "pattern" // and the separator ends the command, as always
	case top == "body" && !t.op && w.atStart && t.text == "esac" && !t.quoted:
		w.caseStates = w.caseStates[:last]
		return true
	}
	return false
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
func (w *commandWalk) finalize(name string, args []string) ir.Outcome {
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
	case shells[name]:
		// fixed-shell-string: a shell runs its -c string as commands.
		if command, ok := shellString(args); ok {
			return analyze(command, w.depth+1)
		}
		return ir.Outcome{}
	case name == "eval":
		// fixed-shell-string: eval runs its words, joined, as commands.
		words := args
		if len(words) > 0 && words[0] == "--" {
			words = words[1:]
		}
		if len(words) > 0 {
			return analyze(strings.Join(words, " "), w.depth+1)
		}
		return ir.Outcome{}
	default:
		return ir.Outcome{}
	}
}

// shellString is the operand a shell runs with -c: its first operand after
// the options, when they hold -c. In a cluster, a letter that takes a value
// (o, O) takes the rest of its word, or the next word when nothing follows it
// (zsh's -oNAME); --rcfile and --init-file take the next word; -- and - end
// the options.
func shellString(args []string) (string, bool) {
	hasC, i := false, 0
	for i < len(args) {
		arg := args[i]
		if arg == "--" || arg == "-" {
			i++
			break
		}
		if strings.HasPrefix(arg, "--") {
			i++
			if arg == "--rcfile" || arg == "--init-file" {
				i++
			}
			continue
		}
		if len(arg) > 1 && (arg[0] == '-' || arg[0] == '+') {
			i++
			for at, letter := range arg[1:] {
				if letter == 'o' || letter == 'O' {
					if 1+at+utf8.RuneLen(letter) == len(arg) {
						i++ // the value is the next word
					}
					break
				}
				hasC = hasC || (arg[0] == '-' && letter == 'c')
			}
			continue
		}
		break
	}
	if hasC && i < len(args) {
		return args[i], true
	}
	return "", false
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

func basename(token string) string {
	return token[strings.LastIndex(token, "/")+1:]
}

func isYMLName(token string) bool {
	base := basename(token)
	return strings.HasSuffix(base, ".yml") || base == "docker-compose.yaml"
}
