package logline

import (
	"fmt"
	"io/fs"
	"strings"

	json "github.com/goccy/go-json/v2"

	agenthooks "github.com/hironow/dotfiles/tools/agent-hooks"
	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/commandguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/secretguard"
)

var (
	harnessTools = readHarnessTools()
	hooks        = readHooks()
	rules        = readRules()
	errorCodes   = wordSet(ErrInputUnreadable + " " + ErrShimBroken + " " + ErrHookFailed + " " + ErrHookTimeout + " " +
		ErrRewriteDropped + " " + ErrToolFailed + " " + ErrAnswerFailed + " " + ErrUsage)
	mismatches = wordSet(MismatchEnvelope + " " + MismatchInput + " " + MismatchMapping + " " + MismatchUnchecked)
)

func wordSet(words string) map[string]bool {
	set := make(map[string]bool)
	for word := range strings.FieldsSeq(words) {
		set[word] = true
	}
	return set
}

func fixed(value string, set map[string]bool) string {
	if set[value] {
		return value
	}
	return "other"
}

func optional(value string, set map[string]bool) string {
	if value == "" {
		return ""
	}
	return fixed(value, set)
}

func readHooks() map[string]bool {
	var manifest struct {
		Hooks []struct {
			ID string `json:"id"`
		} `json:"hooks"`
	}
	if err := json.Unmarshal(agenthooks.Manifest, &manifest); err != nil {
		panic(fmt.Errorf("decode embedded hook ids: %w", err))
	}
	set := make(map[string]bool, len(manifest.Hooks))
	for _, hook := range manifest.Hooks {
		set[hook.ID] = true
	}
	return set
}

func readRules() map[string]bool {
	set := wordSet(ir.RuleInputUnreadable + " " + ir.RuleShimBroken + " " + ir.RuleHookFailed + " " + ir.RuleHookTimeout)
	for _, list := range [][]string{commandguard.Rules(), fileguard.Rules(), secretguard.Rules()} {
		for _, rule := range list {
			set[rule] = true
		}
	}
	return set
}

// readHarnessTools reads only embedded definitions, never the filesystem.
func readHarnessTools() map[string]map[string]string {
	names, err := fs.Glob(harnesses.FS, "*/harness.json")
	if err != nil {
		panic(fmt.Errorf("list embedded harnesses: %w", err))
	}
	tools := make(map[string]map[string]string, len(names))
	for _, name := range names {
		encoded, err := harnesses.FS.ReadFile(name)
		if err != nil {
			panic(fmt.Errorf("read embedded harness: %w", err))
		}
		var definition struct {
			Tools map[string]string `json:"tools"`
		}
		if err := json.Unmarshal(encoded, &definition); err != nil {
			panic(fmt.Errorf("decode embedded harness tools: %w", err))
		}
		tools[name[:len(name)-len("/harness.json")]] = definition.Tools
	}
	return tools
}
