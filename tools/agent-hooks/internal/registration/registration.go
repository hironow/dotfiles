// Package registration renders hook fragments from the embedded definitions.
// Render is pure; Main adds flag parsing and writes the fragment and losses.
// Neither runs a hook, accesses a home, nor logs a hook invocation.
package registration

import (
	"bytes"
	"fmt"
	"maps"
	"slices"
	"strings"
	"text/template"

	"github.com/goccy/go-json/jsontext"
	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
)

// Hook is the manifest metadata a registration needs.
type Hook struct {
	ID      string `json:"id"`
	Event   string `json:"event"`
	Failure string `json:"failure"`
}

// Loss is one support cell that is not supported on the requested OS.
type Loss struct {
	Level   string `json:"level"`
	Harness string `json:"harness"`
	OS      string `json:"os"`
	Hook    string `json:"hook,omitempty"`
	Tool    string `json:"tool"`
	Reason  string `json:"reason"`
}

type renderError struct {
	code   int
	reason string
}

func (e *renderError) Error() string { return e.reason }

type nativeBlock struct {
	Matcher string           `json:"matcher"`
	Hooks   []jsontext.Value `json:"hooks"`
}

// Render returns compact JSON followed by a newline, and an ordered loss
// report. A refusal returns no fragment. The binary path is never accessed.
func Render(def definition.Definition, hooks []Hook, os, shell, binary string) ([]byte, []Loss, error) {
	launcher, err := selectLauncher(def, os, shell)
	if err != nil {
		return nil, nil, err
	}
	if err := checkPath(binary, os, launcher.Shell); err != nil {
		return nil, nil, &renderError{2, err.Error()}
	}
	fragment, err := renderFragment(def, hooks, launcher, binary)
	if err != nil {
		return nil, nil, err
	}
	return fragment, supportLosses(def, os), nil
}

// selectLauncher picks the OS's launcher from the definition's data: the only
// one when there is one, else the one --shell names. An exec launcher runs the
// binary with no shell, so it takes no --shell.
func selectLauncher(def definition.Definition, os, shell string) (definition.Launcher, error) {
	if def.Registration == nil {
		return definition.Launcher{}, &renderError{64, fmt.Sprintf("harness %q has no registration", def.Name)}
	}
	var launchers []definition.Launcher
	var shells []string
	for _, launcher := range def.Registration.Launchers {
		if slices.Contains(launcher.OS, os) {
			launchers = append(launchers, launcher)
			shells = append(shells, launcher.Shell)
		}
	}
	switch {
	case len(launchers) == 0:
		return definition.Launcher{}, &renderError{64, fmt.Sprintf("OS %q has no launcher for %s", os, def.Name)}
	case len(launchers) == 1 && launchers[0].Shell == "exec" && shell != "":
		return definition.Launcher{}, &renderError{2, fmt.Sprintf("%s runs its hooks on %s with no shell, so it takes no --shell", def.Name, os)}
	case shell == "" && len(launchers) == 1:
		return launchers[0], nil
	case shell == "":
		return definition.Launcher{}, &renderError{2, fmt.Sprintf("%s on %s needs --shell, one of %s", def.Name, os, strings.Join(shells, ", "))}
	}
	for _, launcher := range launchers {
		if launcher.Shell == shell && shell != "exec" {
			return launcher, nil
		}
	}
	return definition.Launcher{}, &renderError{2, fmt.Sprintf("%s on %s has no shell %q, only %s", def.Name, os, shell, strings.Join(shells, ", "))}
}

var quoting = template.FuncMap{
	"sh":         func(s string) string { return "'" + strings.ReplaceAll(s, "'", "'\\''") + "'" },
	"powershell": func(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" },
	"cmd":        func(s string) string { return `"` + s + `"` },
}

func supportLosses(def definition.Definition, os string) []Loss {
	var losses []Loss
	for _, hook := range slices.Sorted(maps.Keys(def.Support)) {
		for _, tool := range slices.Sorted(maps.Keys(def.Support[hook])) {
			cell := def.SupportOn(hook, tool, os)
			if cell.Level != definition.LevelSupported {
				losses = append(losses, Loss{Level: cell.Level, Harness: def.Name, OS: os, Hook: hook, Tool: tool, Reason: cell.Reason})
			}
		}
	}
	for _, tool := range slices.Sorted(slices.Values(def.Pending)) {
		losses = append(losses, Loss{Level: "pending", Harness: def.Name, OS: os, Tool: tool, Reason: "no captured payload; no hook is registered"})
	}
	return losses
}

func renderFragment(def definition.Definition, hooks []Hook, launcher definition.Launcher, binary string) ([]byte, error) {
	specs := map[string]Hook{}
	for _, hook := range hooks {
		specs[hook.ID] = hook
	}
	var events []string
	blocks := map[string][]nativeBlock{}
	for _, block := range def.Registration.Blocks {
		native := def.Registration.Events[block.Event]
		if _, seen := blocks[native]; !seen {
			events = append(events, native)
		}
		rendered := nativeBlock{Matcher: block.Matcher, Hooks: []jsontext.Value{}}
		for _, id := range block.Hooks {
			spec, ok := specs[id]
			if !ok || (spec.Failure != "closed" && spec.Failure != "open") || spec.Event != block.Event {
				return nil, fmt.Errorf("hook %q has no matching manifest entry", id)
			}
			values := definition.RegistrationValues{Binary: binary, Harness: def.Name, Event: block.Event, Hook: id}
			entry, err := launcher.Render(spec.Failure == "closed", values, quoting)
			if err != nil {
				return nil, err
			}
			rendered.Hooks = append(rendered.Hooks, jsontext.Value(entry))
		}
		blocks[native] = append(blocks[native], rendered)
	}
	var out bytes.Buffer
	out.WriteString(`{"hooks":{`)
	for i, event := range events {
		if i > 0 {
			out.WriteByte(',')
		}
		key, err := json.Marshal(event)
		if err != nil {
			return nil, err
		}
		value, err := json.Marshal(blocks[event])
		if err != nil {
			return nil, err
		}
		out.Write(key)
		out.WriteByte(':')
		out.Write(value)
	}
	out.WriteString("}}\n")
	return out.Bytes(), nil
}
