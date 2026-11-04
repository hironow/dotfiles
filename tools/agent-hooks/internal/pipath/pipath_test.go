package pipath_test

import (
	"bytes"
	"fmt"
	"os"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pipath"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pipath/pioracle"
)

func TestResolveMatchesPiCorpus(t *testing.T) {
	entries, err := pioracle.Parse(readCorpus(t))
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) == 0 {
		t.Fatal("the corpus needs cases")
	}
	for i, entry := range entries {
		t.Run(fmt.Sprintf("%03d", i), func(t *testing.T) {
			resolved, ok := pipath.Resolve(entry.Path, entry.Cwd, pipath.Home{Dir: entry.Home, Known: true})
			if !ok {
				if !strings.HasPrefix(strings.TrimPrefix(entry.Path, "@"), "file://") {
					t.Fatalf("unresolved non-URL case: %+v", entry)
				}
				return
			}
			if entry.Error != "" || entry.Resolved == nil {
				t.Fatalf("resolved %q but Pi threw: %+v", resolved, entry)
			}
			if resolved != *entry.Resolved {
				t.Fatalf("case %+v: resolved %q, Pi resolved %q", entry.Case, resolved, *entry.Resolved)
			}
		})
	}
}

func TestCorpusIsFresh(t *testing.T) {
	node, module, err := pioracle.Find()
	if err != nil {
		t.Skip(err)
	}
	cases := pioracle.Cases()
	answers, err := pioracle.Run(node, module, cases)
	if err != nil {
		t.Fatal(err)
	}
	fresh, err := pioracle.Render(cases, answers)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(fresh, readCorpus(t)) {
		t.Fatal("Pi's answers changed; run just pi-paths-corpus")
	}
}

func readCorpus(t *testing.T) []byte {
	t.Helper()
	corpus, err := os.ReadFile("corpus.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	return corpus
}

func TestResolveWithUnknownHome(t *testing.T) {
	for _, path := range []string{"~", "~/x", "@~", "@~/x"} {
		t.Run(path, func(t *testing.T) {
			if resolved, ok := pipath.Resolve(path, "/w", pipath.Home{}); ok {
				t.Fatalf("resolved unknown home to %q", resolved)
			}
		})
	}
	for path, want := range map[string]string{
		"x": "/w/x", "/x": "/x", "~user": "/w/~user", "file:///x": "/x",
	} {
		t.Run(path, func(t *testing.T) {
			resolved, ok := pipath.Resolve(path, "/w", pipath.Home{})
			if !ok || resolved != want {
				t.Fatalf("resolved %q, %t; want %q", resolved, ok, want)
			}
		})
	}
}

func TestResolveRejectsRelativeCwd(t *testing.T) {
	for _, cwd := range []string{"", ".", "w", "../w"} {
		for _, path := range []string{"x", "/x", "file:///x", "~"} {
			t.Run(cwd+"/"+path, func(t *testing.T) {
				if resolved, ok := pipath.Resolve(path, cwd, pipath.Home{Dir: "/home/user", Known: true}); ok {
					t.Fatalf("resolved against relative cwd %q: %q", cwd, resolved)
				}
			})
		}
	}
}

func TestResolvePlainFileURLs(t *testing.T) {
	for path, want := range map[string]string{
		"file:///": "/", "file:///a/b": "/a/b", "file://localhost/x": "/x",
		"@file:///x": "/x", "file:///a%20b": "/a b", "file:///a/": "/a",
		"file:///%7E": "/~", "file:///a/%2e%2e/x": "/x", "file:///a/../x": "/x",
		"file:///%E6%97%A5": "/日", "file:///%5C": "/\\", "file:///%3F%23": "/?#",
		"file:///a/%252e%252e/x": "/a/%2e%2e/x", "file:///AZaz09._~-": "/AZaz09._~-",
	} {
		t.Run(path, func(t *testing.T) {
			resolved, ok := pipath.Resolve(path, "/w", pipath.Home{Known: true})
			if !ok || resolved != want {
				t.Fatalf("resolved %q, %t; want %q", resolved, ok, want)
			}
		})
	}
}

func TestResolveRejectsOtherFileURLs(t *testing.T) {
	for _, path := range []string{
		"file://", "file://localhost", "file://other/x", "file://LOCALHOST/x",
		"file:///x?q", "file:///x#f", "file:///a\\b", "file:///a b", "file:///日",
		"file:///%", "file:///%G0", "file:///%FF", "file:///%00", "file:///%2F", "file:///%2f",
		"file:///%C0%AF", "file:///%ED%A0%80", "file:///%F4%90%80%80", "file:///x:y",
		// an empty segment: the URL parser keeps it, so a later .. removes it
		// instead of the segment before it
		"file:////x", "file:///w/docker-compose.yaml//..", "file:///w/docs/extra//../agents/docker-compose.yaml",
		"@file:///w/compose.yml//%2e%2e", "file:///a//../x", "file:///a/b//../../x", "file:///a/.//../x",
		"file:///a//%2e%2e/x", "file:///a//",
	} {
		t.Run(path, func(t *testing.T) {
			if resolved, ok := pipath.Resolve(path, "/w", pipath.Home{Known: true}); ok {
				t.Fatalf("resolved URL outside the plain form: %q", resolved)
			}
		})
	}
}

func TestCorpusIsASCII(t *testing.T) {
	// Some tools split lines on U+2028 or U+0085; the corpus holds none.
	for i, b := range readCorpus(t) {
		if b > 0x7f {
			t.Fatalf("byte %d is not ASCII; run just pi-paths-corpus", i)
		}
	}
}
