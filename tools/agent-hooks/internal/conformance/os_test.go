package conformance

import (
	"io/fs"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
)

// osGaps pins reported OS gaps only. The ordinary cell's scenarios already
// cover its behavior; PR 2e.4 owns scenarios for the Windows grammar gap.
var osGaps = map[[4]string]string{
	{"codex", "command-guard", "Bash", "windows"}: "Codex runs PowerShell on Windows; the guard reads its text with bash grammar (PR 2e.4)",
}

func TestEveryHarnessReportsExactlyItsOSGaps(t *testing.T) {
	entries, err := fs.ReadDir(harnesses.FS, ".")
	if err != nil {
		t.Fatal(err)
	}
	seen := map[[4]string]bool{}
	for _, entry := range entries {
		def, err := definition.Load(harnesses.FS, entry.Name())
		if err != nil {
			t.Fatal(err)
		}
		for hook, tools := range def.Support {
			for tool, support := range tools {
				for os := range support.OS {
					cell := [4]string{def.Name, hook, tool, os}
					if got := def.SupportOn(hook, tool, os); got.Level != definition.LevelDegraded || got.Reason != osGaps[cell] {
						t.Errorf("%v: %+v, want known OS gap %q", cell, got, osGaps[cell])
					}
					seen[cell] = true
				}
			}
		}
	}
	for cell := range osGaps {
		if !seen[cell] {
			t.Errorf("%v: OS gap is not reported", cell)
		}
	}
}
