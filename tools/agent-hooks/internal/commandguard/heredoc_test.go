package commandguard

import (
	"fmt"
	"slices"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
)

func TestSplitHeredocsAgreesWithPythonOnTheCorpus(t *testing.T) {
	for _, entry := range guardcorpus.Entries(t) {
		t.Run(fmt.Sprintf("line-%d", entry.Line), func(t *testing.T) {
			// given an input of the corpus, when its heredocs are split off
			cleaned, codeBodies := splitHeredocs(entry.Input)
			// then the text that stays and the bodies fed to an interpreter are Python's
			if cleaned != entry.Cleaned || !slices.Equal(codeBodies, entry.CodeBodies) {
				t.Fatalf("splitHeredocs(%q) = %q, %q; Python gave %q, %q",
					entry.Input, cleaned, codeBodies, entry.Cleaned, entry.CodeBodies)
			}
		})
	}
}
