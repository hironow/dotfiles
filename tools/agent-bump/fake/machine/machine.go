// Package machine is an in-memory stand-in for the agent homes on this machine.
package machine

import (
	"context"
	"fmt"

	"github.com/hironow/dotfiles/tools/agent-bump/internal/bump"
)

// Fake records which version of each item is installed. A version of ""
// means "the newest, unpinned" (a Pi package) or "upstream HEAD" (a skill).
type Fake struct {
	Installed   map[string]string
	RedBaseline map[string]bool   // item name -> its check is already failing
	FailInstall map[string]string // item name -> the version whose install fails
	Required    []string          // what the Pi installer requires of an EGM bundle
}

func (f *Fake) Baseline(_ context.Context, it bump.Item) error {
	if f.RedBaseline[it.Name] {
		return fmt.Errorf("%s: check is red", it.Name)
	}
	return nil
}

func (f *Fake) Install(_ context.Context, it bump.Item, t bump.Target) error {
	if v, ok := f.FailInstall[it.Name]; ok && v == t.Version {
		return fmt.Errorf("%s: install of %q failed", it.Name, t.Version)
	}
	f.Installed[it.Name] = t.Version
	return nil
}

func (f *Fake) Verify(_ context.Context, it bump.Item, t bump.Target) error {
	if got := f.Installed[it.Name]; got != t.Version {
		return fmt.Errorf("%s: installed %q, want %q", it.Name, got, t.Version)
	}
	return nil
}

func (f *Fake) EGMRequiredPaths(context.Context) ([]string, error) { return f.Required, nil }
