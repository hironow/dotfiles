package bashsubst_test

import (
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/bashsubst"
)

func TestOutputIsWhatACommandSubstitutionCaptures(t *testing.T) {
	cases := []struct{ printed, want string }{
		{"a.yml", "a.yml"},
		{"a.yml\n\n\n", "a.yml"},
		{"a\x00.yml", "a.yml"},
		{"a.yml\n\x00\n", "a.yml"},
		{"\n\x00\n", ""},
		{"a\n\nb\n", "a\n\nb"},
		{"a\r\n", "a\r"},
		{"\na", "\na"},
	}
	for _, c := range cases {
		if got := bashsubst.Output(c.printed); got != c.want {
			t.Errorf("Output(%q) = %q, want %q", c.printed, got, c.want)
		}
	}
}
