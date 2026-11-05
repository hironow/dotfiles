package registration

import (
	"errors"
	"flag"
	"fmt"
	"io"

	json "github.com/goccy/go-json/v2"

	agenthooks "github.com/hironow/dotfiles/tools/agent-hooks"
	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
)

const usage = "usage: agent-hook render --harness claude|codex --os darwin|linux|windows [--shell sh|powershell|cmd] --binary PATH"

// Main is agent-hook render, with args after the command name. The binary and
// the corpus writer call this same entry point, with no machine dependency.
func Main(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("render", flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.Usage = func() { _, _ = fmt.Fprintln(stderr, usage) }
	harness := flags.String("harness", "", "harness")
	os := flags.String("os", "", "target OS")
	shell := flags.String("shell", "", "command shell")
	binary := flags.String("binary", "", "absolute binary path")
	if err := flags.Parse(args); err != nil {
		return 64
	}
	if flags.NArg() != 0 || *harness == "" || *os == "" || *binary == "" {
		flags.Usage()
		return 64
	}
	shellGiven := false
	flags.Visit(func(f *flag.Flag) { shellGiven = shellGiven || f.Name == "shell" })
	if shellGiven && *shell == "" {
		_, _ = fmt.Fprintln(stderr, "agent-hook render: --shell must name a supported shell")
		return 2
	}
	def, err := definition.Load(harnesses.FS, *harness)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook render: %v\n", err)
		return 64
	}
	var manifest struct {
		Hooks []Hook `json:"hooks"`
	}
	if err := json.Unmarshal(agenthooks.Manifest, &manifest); err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook render: %v\n", err)
		return 2
	}
	fragment, losses, err := Render(def, manifest.Hooks, *os, *shell, *binary)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook render: %v\n", err)
		var refusal *renderError
		if errors.As(err, &refusal) {
			return refusal.code
		}
		return 2
	}
	var report []byte
	for _, loss := range losses {
		line, err := json.Marshal(loss)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "agent-hook render: %v\n", err)
			return 2
		}
		report = append(report, line...)
		report = append(report, '\n')
	}
	_, _ = stderr.Write(report)
	_, _ = stdout.Write(fragment)
	return 0
}
