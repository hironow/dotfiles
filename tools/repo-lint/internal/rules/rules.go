// Package rules holds the repository's file policies that a Semgrep rule
// cannot hold: a value read from a file's structure, or values compared
// across files (ADR-0093). Each rule is pure: it takes the decoded inputs and
// returns findings, and does no I/O.
package rules

import (
	"fmt"
	"slices"
)

// Format says how the shell decodes an input before a rule reads it.
type Format string

// The formats. Text is the file as a string with LF line ends; the others are
// the value the file's JSON form decodes to (map[string]any, []any, string,
// float64, bool, nil).
const (
	Text Format = "text"
	JSON Format = "json"
	TOML Format = "toml"
	YAML Format = "yaml"
	// JSONC is JSON with comments and trailing commas (devcontainer.json).
	JSONC Format = "jsonc"
)

// Input is one file a rule reads, relative to the repository root. With Glob
// set, Path is a git pathspec glob (`**` spans directories), and the input is
// a map from each tracked file it matches to that file's decoded value.
type Input struct {
	Path   string
	Format Format
	Glob   bool
}

// Inputs maps each input path to its decoded value.
type Inputs map[string]any

// Finding is one broken policy.
type Finding struct {
	Path    string
	Rule    string
	Message string
}

func (f Finding) String() string {
	return fmt.Sprintf("%s: %s: %s", f.Path, f.Rule, f.Message)
}

// Rule is one policy.
type Rule struct {
	ID     string
	Why    string
	Inputs []Input
	Check  func(Inputs) []Finding
}

// All returns every rule, in a fixed order.
func All() []Rule {
	return []Rule{
		miseAgentTools(),
		miseAWSCLI(),
		miseMQ(),
		miseHostSettings(),
		miseAgeExemptPins(),
		miseImageBakesGoLint(),
		misePlaywrightCLIVersion(),
		caIncidentFloors(),
		emulatorGroups(),
		emulatorNoExporters(),
		emulatorEnvPorts(),
		emulatorMCPInspector(),
		emulatorGoBuilders(),
		emulatorHealthDockerfile(),
		emulatorHealthServices(),
		telemetryStack(),
		telemetryDependabot(),
		rootLintCoversTelemetry(),
		dependabotPythonHeld(),
		dependabotUVSyncedTools(),
		claudeLintRunsOfficialValidate(),
		claudeTelemetryOff(),
		claudeMdExcludes(),
		settingsLeavePluginKeys(),
		skillOverrides(),
		claudePluginsPinned(),
		marketplaceMatchesManifests(),
		namedSkillsDeclared(),
		egmPinnedBundle(),
		piEgmReviewerReadOnly(),
	}
}

// Paths returns every input path of the rules, each once, sorted.
func Paths(rules []Rule) []Input {
	seen := map[string]Input{}
	for _, r := range rules {
		for _, in := range r.Inputs {
			seen[in.Path] = in
		}
	}
	out := make([]Input, 0, len(seen))
	for _, in := range seen {
		out = append(out, in)
	}
	slices.SortFunc(out, func(a, b Input) int {
		switch {
		case a.Path < b.Path:
			return -1
		case a.Path > b.Path:
			return 1
		}
		return 0
	})
	return out
}

// report collects one rule's findings for one path.
type report struct {
	rule string
	path string
	out  []Finding
}

func (r *report) add(format string, args ...any) {
	r.addAt(r.path, format, args...)
}

// addAt adds a finding for another path than the report's.
func (r *report) addAt(path, format string, args ...any) {
	r.out = append(r.out, Finding{Path: path, Rule: r.rule, Message: fmt.Sprintf(format, args...)})
}

// at walks nested tables by key.
func at(v any, keys ...string) (any, bool) {
	for _, k := range keys {
		t, ok := v.(map[string]any)
		if !ok {
			return nil, false
		}
		v, ok = t[k]
		if !ok {
			return nil, false
		}
	}
	return v, true
}

func str(v any, keys ...string) (string, bool) {
	got, ok := at(v, keys...)
	if !ok {
		return "", false
	}
	s, ok := got.(string)
	return s, ok
}

func table(v any, keys ...string) (map[string]any, bool) {
	got, ok := at(v, keys...)
	if !ok {
		return nil, false
	}
	t, ok := got.(map[string]any)
	return t, ok
}

// strs is a list of strings at the keys, or nil when there is none.
func strs(v any, keys ...string) []string {
	got, _ := at(v, keys...)
	items, ok := got.([]any)
	if !ok {
		return nil
	}
	out := make([]string, 0, len(items))
	for _, item := range items {
		s, ok := item.(string)
		if !ok {
			return nil
		}
		out = append(out, s)
	}
	return out
}

// tables is the tables in the list at the keys; an item that is not a table is
// left out.
func tables(v any, keys ...string) []map[string]any {
	got, _ := at(v, keys...)
	items, _ := got.([]any)
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		if t, ok := item.(map[string]any); ok {
			out = append(out, t)
		}
	}
	return out
}

// version is a tool entry's version: the string itself, or a table's
// `version` ("" when there is none).
func version(spec any) string {
	if s, ok := spec.(string); ok {
		return s
	}
	v, _ := str(spec, "version")
	return v
}

// sameSet reports whether a and b hold the same strings, ignoring order.
func sameSet(a, b []string) bool {
	x := slices.Clone(a)
	y := slices.Clone(b)
	slices.Sort(x)
	slices.Sort(y)
	return slices.Equal(x, y)
}
