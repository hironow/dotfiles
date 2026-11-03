package applypatch_test

import (
	"slices"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/applypatch"
)

func patch(body string) string {
	return "*** Begin Patch\n" + body + "*** End Patch\n"
}

// The shell guards' readings of a patch, spelled out where they surprise.
func TestFilePathsReadsThePatchAsTheFilesGuardDoes(t *testing.T) {
	cases := []struct {
		name  string
		patch string
		paths []string
	}{
		{"added and updated files", patch("*** Add File: a.yaml\n+x\n*** Update File: b.go\n@@\n-x\n+y\n"), []string{"a.yaml", "b.go"}},
		{"a move keeps only its destination", patch("*** Update File: old.yml\n*** Move to: new.yaml\n"), []string{"new.yaml"}},
		{"the last move wins", patch("*** Update File: a\n*** Move to: b\n*** Move to: c.yml\n"), []string{"c.yml"}},
		{"a move with no update still names a file", patch("*** Move to: a.yml\n"), []string{"a.yml"}},
		{"a move to nothing drops the file", patch("*** Update File: a.yml\n*** Move to: \n"), nil},
		{"a deleted file is not written", patch("*** Delete File: a.yml\n"), nil},
		{"only exact headers count", patch("***  Add File: a.yml\n*** add file: b.yml\n"), nil},
		{"an added line is content, not a header", patch("*** Add File: a\n+*** Add File: b.yml\n"), []string{"a"}},
		{"text without Begin Patch is not a patch", "*** Add File: a.yml\n", nil},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := applypatch.FilePaths(c.patch); !slices.Equal(got, c.paths) {
				t.Fatalf("FilePaths(%q) = %q; want %q", c.patch, got, c.paths)
			}
		})
	}
}

func TestAddedLinesReadsThePatchAsTheSecretsGuardDoes(t *testing.T) {
	cases := []struct {
		name  string
		patch string
		added string
	}{
		{"added lines without their +", patch("*** Add File: a\n+x\n+y\n"), "x\ny"},
		{"removed and context lines are not new content", patch("*** Update File: a\n@@\n-old\n same\n+new\n"), "new"},
		{"a second + stays", patch("*** Add File: a\n++x\n"), "+x"},
		{"text without Begin Patch is not a patch", "+x\n", ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := applypatch.AddedLines(c.patch); got != c.added {
				t.Fatalf("AddedLines(%q) = %q; want %q", c.patch, got, c.added)
			}
		})
	}
}
