package load

import (
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/goccy/go-json"
	"github.com/hironow/dotfiles/tools/repo-lint/internal/rules"
)

// TestMain lets this test binary stand in for yq: with REPO_LINT_FAKE_YQ set
// it prints its arguments as a JSON document, so the test sees exactly how
// Files calls yq and decodes what yq prints.
func TestMain(m *testing.M) {
	if os.Getenv("REPO_LINT_FAKE_YQ") != "" {
		out, _ := json.Marshal(map[string]any{"args": os.Args[1:]})
		fmt.Println(string(out))
		os.Exit(0)
	}
	os.Exit(m.Run())
}

func write(t *testing.T, root, name, body string) {
	t.Helper()
	path := filepath.Join(root, filepath.FromSlash(name))
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
}

func TestFilesReadsTextAndJSON(t *testing.T) {
	root := t.TempDir()
	write(t, root, "a/notes.txt", "line\n")
	write(t, root, "a/data.json", `{"floors": {"go": [{"branch": "1.27"}]}, "n": 1}`)
	files := Files{Root: root}
	got, err := files.Load(rules.Input{Path: "a/notes.txt", Format: rules.Text})
	if err != nil || got != "line\n" {
		t.Fatalf("text = %#v, %v", got, err)
	}
	got, err = files.Load(rules.Input{Path: "a/data.json", Format: rules.JSON})
	want := map[string]any{"floors": map[string]any{"go": []any{map[string]any{"branch": "1.27"}}}, "n": float64(1)}
	if err != nil || !reflect.DeepEqual(got, want) {
		t.Fatalf("json = %#v, %v", got, err)
	}
}

func TestFilesAsksYQForTOMLAndYAMLAsJSON(t *testing.T) {
	root := t.TempDir()
	write(t, root, "config/x.toml", "a = 1\n")
	self, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("REPO_LINT_FAKE_YQ", "1")
	files := Files{Root: root, YQ: self}
	for _, format := range []rules.Format{rules.TOML, rules.YAML} {
		got, err := files.Load(rules.Input{Path: "config/x.toml", Format: format})
		if err != nil {
			t.Fatal(err)
		}
		args, _ := got.(map[string]any)["args"].([]any)
		want := []any{"-p", string(format), "-o", "json", ".", filepath.Join(root, "config", "x.toml")}
		if !reflect.DeepEqual(args, want) {
			t.Errorf("%s: yq args = %v, want %v", format, args, want)
		}
	}
}

func TestFilesReportsWhatItCannotRead(t *testing.T) {
	root := t.TempDir()
	write(t, root, "bad.json", "{")
	files := Files{Root: root, YQ: filepath.Join(root, "no-such-yq")}
	for _, in := range []rules.Input{
		{Path: "missing.txt", Format: rules.Text},
		{Path: "bad.json", Format: rules.JSON},
		{Path: "bad.json", Format: rules.TOML},
		{Path: "bad.json", Format: "ini"},
	} {
		if _, err := files.Load(in); err == nil || !strings.Contains(err.Error(), in.Path) {
			t.Errorf("%s as %s: error %v does not name the file", in.Path, in.Format, err)
		}
	}
}
