package launch

import (
	"bytes"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/goccy/go-json/jsontext"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/bashsubst"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/commandguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/formatter"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/rtkpolicy"
)

// The old rtk scripts' timeouts, for rtk and for `mise which rtk`, and
// rtk.ts's for `rtk rewrite` (REWRITE_TIMEOUT_MS).
const (
	rtkTimeout   = 10 * time.Second
	miseTimeout  = 10 * time.Second
	piRTKTimeout = 2 * time.Second
)

// rtkHook is rtk's hook: on Claude and Codex, a delegate to rtk's own adapter
// for the harness (`rtk hook claude`, `rtk hook codex`), as the old scripts
// were. It fails open: any doubt prints nothing, and the typed command runs.
func rtkHook(call ir.Call, machine Machine) ir.Outcome {
	switch call.Harness {
	case "claude":
		return claudeRTK(call, machine)
	case "codex":
		return codexRTK(call, machine)
	case "pi":
		return piRTK(call, machine)
	default:
		return ir.Outcome{}
	}
}

// piRTK is the vendored config/pi/extensions/rtk.ts, run per call: on a
// shell tool (Pi's bash), it asks `rtk rewrite` about the command and
// answers the rewrite rtk gives (rtkpolicy.PiRewrite), or the pass. Unlike
// rtk.ts it does not probe `rtk --version` once per session
// (rtk-version-probe): the binary runs once per call, and an rtk without
// `rewrite` fails the rewrite as well. rtk found through a relative PATH
// entry is not run (path-relative).
func piRTK(call ir.Call, machine Machine) ir.Outcome {
	if call.Kind != ir.KindShell {
		return ir.Outcome{}
	}
	disabled, _ := machine.LookupEnv("RTK_DISABLED") // "" when not set
	command, ok := rtkpolicy.PiCommand(call.Fields[ir.FieldCommand], disabled)
	if !ok {
		return ir.Outcome{}
	}
	program, found := machine.LookPath("rtk")
	if !found || program.Relative {
		return ir.Outcome{}
	}
	// rtk.ts runs "rtk" by name (Node's spawn), so argv[0] is "rtk".
	result, err := machine.Run(process.Command{
		Path: program.Path, Args: []string{"rtk", "rewrite", command}, Timeout: piRTKTimeout,
	})
	rewritten, ok := rtkpolicy.PiRewrite(command, rtkpolicy.PiRun{
		Ended: err == nil, Signaled: result.Signaled, Exit: result.Exit, Stdout: result.Stdout,
	})
	if !ok {
		return ir.Outcome{}
	}
	return ir.Outcome{Action: ir.Rewrite, Set: ir.Assignment{Field: ir.FieldCommand, Value: rewritten}}
}

// claudeRTK is ROOT_AGENTS_hooks_rtk-hook-claude.py: rtk from PATH, else
// through mise; rtk's answer edited by rtkpolicy.Claude.
func claudeRTK(call ir.Call, machine Machine) ir.Outcome {
	if !isJSONObject(call.Native) {
		return ir.Outcome{} // the script read only an object
	}
	path, miseLauncher := "", ""
	if program, found := machine.LookPath("rtk"); found {
		if program.Relative {
			return ir.Outcome{}
		}
		path = program.Path
	} else {
		mise, found := machine.LookPath("mise")
		if !found || mise.Relative {
			return ir.Outcome{}
		}
		// The script runs "mise" by name, which finds this same program.
		result, err := machine.Run(process.Command{Path: mise.Path, Args: []string{"mise", "which", "rtk"}, Timeout: miseTimeout})
		if err != nil || result.Exit != 0 || !utf8.Valid(result.Stdout) {
			return ir.Outcome{}
		}
		candidate := commandguard.StripPython(string(result.Stdout))
		// A name with no separator would be searched for, and PATH has no rtk.
		if candidate == "" || !hasSeparator(machine, candidate) || !machine.IsExecutable(candidate) {
			return ir.Outcome{}
		}
		// The script names Path(found).as_posix(), and Path follows the OS.
		path, miseLauncher = candidate, rtkpolicy.AsPosix(candidate)
		if machine.IsWindows() {
			miseLauncher = rtkpolicy.AsPosixWindows(candidate)
		}
	}
	answer, ok := runRTK(machine, path, "claude", call.Native)
	if !ok {
		return ir.Outcome{}
	}
	cwdValue, present := call.Fields[ir.FieldCwd]
	edited, ok := rtkpolicy.Claude(answer, rtkpolicy.VetoCwd(cwdValue, present, machine.Getwd()), miseLauncher)
	if !ok {
		return ir.Outcome{}
	}
	return ir.Outcome{Action: ir.Forward, Native: string(edited)}
}

// codexRTK is ROOT_AGENTS_hooks_rtk-hook-codex.py: rtk's real binary (mise's
// answer first), rtk's answer edited by rtkpolicy.Codex.
func codexRTK(call ir.Call, machine Machine) ir.Outcome {
	miseAnswer := ""
	if mise, found := machine.LookPath("mise"); found {
		if mise.Relative {
			return ir.Outcome{}
		}
		result, err := machine.Run(process.Command{Path: mise.Path, Args: []string{mise.Path, "which", "rtk"}, Timeout: miseTimeout})
		if err == nil && result.Exit == 0 && utf8.Valid(result.Stdout) {
			miseAnswer = commandguard.StripPython(string(result.Stdout))
		}
	}
	onPath, onPathFound := machine.LookPath("rtk")
	if !onPathFound {
		onPath = process.Program{}
	}
	launcher := rtkpolicy.CodexLauncher(miseAnswer, onPath.Path)
	if launcher == "" || (miseAnswer == "" && onPath.Relative) {
		return ir.Outcome{}
	}
	path := launcher
	if !hasSeparator(machine, launcher) {
		// Python's subprocess searches PATH for a name with no separator.
		program, found := machine.LookPath(launcher)
		if !found || program.Relative {
			return ir.Outcome{}
		}
		path = program.Path
	}
	answer, ok := runRTKAs(machine, path, launcher, "codex", call.Native)
	if !ok {
		return ir.Outcome{}
	}
	edited, ok := rtkpolicy.Codex(answer, launcher)
	if !ok {
		return ir.Outcome{}
	}
	return ir.Outcome{Action: ir.Forward, Native: string(edited)}
}

// runRTK runs `<path> hook <harness>` with the payload on stdin, the path
// also being the program's own name.
func runRTK(machine Machine, path, harness string, payload []byte) (jsontext.Value, bool) {
	return runRTKAs(machine, path, path, harness, payload)
}

// runRTKAs runs rtk's hook and returns its answer. A failure, a timeout, an
// exit other than 0, or empty output is no answer; rtkpolicy reads the answer
// strictly, as 2b reads input, so output that is not one JSON value is none
// either.
func runRTKAs(machine Machine, path, name, harness string, payload []byte) (jsontext.Value, bool) {
	result, err := machine.Run(process.Command{
		Path: path, Args: []string{name, "hook", harness}, Stdin: payload, Timeout: rtkTimeout,
	})
	if err != nil || result.Exit != 0 || !utf8.Valid(result.Stdout) || commandguard.StripPython(string(result.Stdout)) == "" {
		return nil, false
	}
	return jsontext.Value(result.Stdout), true
}

// hasSeparator reports whether a program names a path rather than a name to
// look up: it holds a slash, or on Windows a backslash too.
func hasSeparator(machine Machine, program string) bool {
	return strings.Contains(program, "/") || (machine.IsWindows() && strings.Contains(program, `\`))
}

// inShimCwd reports whether the binary runs in the call's cwd, both
// compared physically: the shim's contract, which the formatter relies on
// to run ruff and gofmt in the call's project. A shim that broke it would
// otherwise format against another project's settings.
func inShimCwd(call ir.Call, machine Machine) bool {
	cwd, ok := call.Fields[ir.FieldCwd]
	if !ok || !cwd.IsString {
		return false
	}
	real, err := machine.RealPath(cwd.Text)
	return err == nil && real == machine.Getwd()
}

// isJSONObject reports whether a JSON text's value is an object.
func isJSONObject(text []byte) bool {
	text = bytes.TrimLeft(text, " \t\r\n")
	return len(text) > 0 && text[0] == '{'
}

// formatterHook is ROOT_AGENTS_hooks_format-after-edit.sh: each named file
// that is a regular file is formatted by its suffix's formatter, when that is
// on PATH. A formatter found through a relative PATH entry is not run, and
// its file is left as it is. It always passes, reporting what ruff still
// finds.
//
// Claude and Codex run the hook in the session's directory, and the commands
// run there with the path as given, as the script's did. agy runs it where
// its hooks.json is, so the commands run in the file's project (locate),
// with the file's real path; a file it cannot place is left as it is.
//
// A shim runs the binary in the call's cwd: the commands run there, as on
// Claude, once the binary checks that it does run there (inShimCwd).
func formatterHook(call ir.Call, machine Machine) ir.Outcome {
	if call.Transport == ir.TransportShim && !inShimCwd(call, machine) {
		return ir.Outcome{}
	}
	var notice strings.Builder
	for _, path := range formatter.Paths(call) {
		target, dir := path, ""
		if call.HookCwd == ir.HookCwdRegistration {
			var placed bool
			if dir, target, placed = locate(call, path, machine); !placed {
				continue
			}
		}
		formatting, ok := formatter.For(target)
		if !ok || !machine.IsRegularFile(target) {
			continue
		}
		program, found := machine.LookPath(formatting.Program)
		if !found || program.Relative {
			continue
		}
		for i, args := range formatting.Commands {
			reported := i == formatting.Reported
			result, err := machine.Run(process.Command{Path: program.Path, Args: args, Combined: reported, Dir: dir})
			if reported && err == nil {
				notice.WriteString(formatter.Notice(path, bashsubst.Output(string(result.Stdout))))
			}
		}
	}
	return ir.Outcome{Notice: notice.String()}
}
