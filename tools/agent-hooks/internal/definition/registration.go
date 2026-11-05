package definition

import (
	"errors"
	"fmt"
	"slices"
	"text/template"

	"github.com/goccy/go-json/jsontext"
	json "github.com/goccy/go-json/v2"

	agenthooks "github.com/hironow/dotfiles/tools/agent-hooks"
)

// Registration lists blocks in their native order and the launchers for them.
type Registration struct {
	Events    map[string]string   `json:"events"`
	Blocks    []RegistrationBlock `json:"blocks"`
	Launchers []Launcher          `json:"launchers"`
}

// RegistrationBlock is one native event and matcher, with ordered hook ids.
type RegistrationBlock struct {
	Event   string   `json:"event"`
	Matcher string   `json:"matcher"`
	Hooks   []string `json:"hooks"`
}

// Launcher holds command templates for one shell on its OSes.
type Launcher struct {
	OS     []string       `json:"os"`
	Shell  string         `json:"shell"`
	Closed jsontext.Value `json:"closed"`
	Open   jsontext.Value `json:"open"`
}

// RegistrationValues are the only values a registration template reads.
type RegistrationValues struct {
	Binary, Harness, Event, Hook string
}

// Render expands a launcher's chosen entry, preserving its JSON member order.
// The caller supplies quoting functions after checking the path for its form.
func (l Launcher) Render(closed bool, values RegistrationValues, funcs template.FuncMap) ([]byte, error) {
	entry := l.Open
	if closed {
		entry = l.Closed
	}
	parsed, err := parseAnswerWithFuncs(answerFile{StdoutJSON: entry}, funcs)
	if err != nil {
		return nil, err
	}
	rendered, err := parsed.renderJSON(values)
	return []byte(rendered), err
}

var registrationOSes = []string{"darwin", "linux", "windows"}

func checkRegistration(file harnessFile) error {
	if file.Registration != nil {
		if err := checkBlocks(file); err != nil {
			return fmt.Errorf("registration: %w", err)
		}
		if err := checkLaunchers(file.Registration.Launchers); err != nil {
			return fmt.Errorf("registration: %w", err)
		}
	}
	return checkOSSupport(file)
}

func checkBlocks(file harnessFile) error {
	var manifest struct {
		Hooks []struct {
			ID    string `json:"id"`
			Event string `json:"event"`
		} `json:"hooks"`
	}
	if err := json.Unmarshal(agenthooks.Manifest, &manifest); err != nil {
		return err
	}
	known := map[string]string{}
	for _, hook := range manifest.Hooks {
		known[hook.ID] = hook.Event
	}
	seen := map[string]bool{}
	for _, block := range file.Registration.Blocks {
		if native, ok := file.Registration.Events[block.Event]; !ok || native == "" {
			return fmt.Errorf("block event %q has no registration event", block.Event)
		}
		if _, ok := file.Events[block.Event]; !ok {
			return fmt.Errorf("block event %q has no definition", block.Event)
		}
		if block.Matcher == "" {
			return errors.New("block has an empty matcher")
		}
		for _, hook := range block.Hooks {
			event, ok := known[hook]
			if !ok || seen[hook] {
				return fmt.Errorf("hook %q is unknown or repeated", hook)
			}
			if event != block.Event {
				return fmt.Errorf("hook %q runs on %s, not %s", hook, event, block.Event)
			}
			registered := false
			for _, support := range file.Support[hook] {
				registered = registered || support.Level == LevelSupported || support.Level == LevelDegraded
			}
			if !registered {
				return fmt.Errorf("hook %q is not registered for any tool", hook)
			}
			seen[hook] = true
		}
	}
	for _, hook := range manifest.Hooks {
		if !seen[hook.ID] {
			return fmt.Errorf("hook %q has no block", hook.ID)
		}
	}
	return nil
}

func checkLaunchers(launchers []Launcher) error {
	seen := map[[2]string]bool{}
	covered := map[string]bool{}
	for _, launcher := range launchers {
		if len(launcher.OS) == 0 || !slices.Contains([]string{"exec", "sh", "powershell", "cmd"}, launcher.Shell) {
			return errors.New("launcher needs OSes and a known shell")
		}
		for _, os := range launcher.OS {
			pair := [2]string{os, launcher.Shell}
			if !slices.Contains(registrationOSes, os) || seen[pair] {
				return fmt.Errorf("launcher pair %q is unknown or repeated", pair)
			}
			seen[pair], covered[os] = true, true
		}
		if err := checkLauncherEntries(launcher); err != nil {
			return err
		}
	}
	for _, os := range registrationOSes {
		if !covered[os] {
			return fmt.Errorf("no launcher for %s", os)
		}
	}
	return nil
}

func checkLauncherEntries(launcher Launcher) error {
	// Quoting changes string contents only. At load we check the template's
	// structure and values; registration supplies the real quoting at render.
	identity := func(s string) string { return s }
	funcs := template.FuncMap{"sh": identity, "powershell": identity, "cmd": identity}
	values := RegistrationValues{Binary: "/sample/dotfiles/agent-hooks/current/h/agent-hook", Harness: "h", Event: "pre", Hook: "command-guard"}
	for _, closed := range []bool{true, false} {
		rendered, err := launcher.Render(closed, values, funcs)
		if err != nil {
			return fmt.Errorf("launcher template: %w", err)
		}
		var entry map[string]jsontext.Value
		if len(rendered) == 0 || rendered[0] != '{' {
			return errors.New("launcher entry must be an object")
		}
		if err := json.Unmarshal(rendered, &entry); err != nil {
			return err
		}
		var kind, command string
		if json.Unmarshal(entry["type"], &kind) != nil || kind != "command" ||
			json.Unmarshal(entry["command"], &command) != nil || entry["command"].Kind() != '"' {
			return errors.New("launcher needs type command and a string command")
		}
		if launcher.Shell == "exec" && !stringArray(entry["args"]) {
			return errors.New("exec launcher needs args as a list of strings")
		}
	}
	return nil
}

func stringArray(value jsontext.Value) bool {
	var elements []jsontext.Value
	if value.Kind() != '[' || json.Unmarshal(value, &elements) != nil {
		return false
	}
	for _, element := range elements {
		if element.Kind() != '"' {
			return false
		}
	}
	return true
}

func checkOSSupport(file harnessFile) error {
	for hook, tools := range file.Support {
		for tool, support := range tools {
			for os, override := range support.OS {
				if override.Level != LevelDegraded || override.Reason == "" {
					return fmt.Errorf("OS support for %s on %s/%s must be degraded with a reason", hook, tool, os)
				}
				found := false
				if file.Registration != nil {
					for _, launcher := range file.Registration.Launchers {
						found = found || slices.Contains(launcher.OS, os)
					}
				}
				if !found {
					return fmt.Errorf("OS support for %s on %s/%s has no launcher", hook, tool, os)
				}
			}
		}
	}
	return nil
}
