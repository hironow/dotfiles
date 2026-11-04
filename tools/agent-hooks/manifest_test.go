package agenthooks_test

import (
	"io/fs"
	"maps"
	"slices"
	"testing"

	json "github.com/goccy/go-json/v2"

	agenthooks "github.com/hironow/dotfiles/tools/agent-hooks"
	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
)

func TestEveryHarnessStatesItsSupportForEachHookOfTheManifest(t *testing.T) {
	var manifest struct {
		Hooks []struct {
			ID string `json:"id"`
		} `json:"hooks"`
	}
	if err := json.Unmarshal(agenthooks.Manifest, &manifest); err != nil {
		t.Fatal(err)
	}
	var want []string
	for _, hook := range manifest.Hooks {
		want = append(want, hook.ID)
	}
	slices.Sort(want)
	entries, err := fs.ReadDir(harnesses.FS, ".")
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		def, err := definition.Load(harnesses.FS, entry.Name())
		if err != nil {
			t.Fatal(err)
		}
		if got := slices.Sorted(maps.Keys(def.Support)); !slices.Equal(got, want) {
			t.Errorf("%s: support states hooks %v, want the manifest's %v", entry.Name(), got, want)
		}
	}
}
