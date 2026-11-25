package load

import (
	"fmt"
	"os"
	"os/exec"
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

func TestFilesReadsJSONWithComments(t *testing.T) {
	root := t.TempDir()
	write(t, root, ".devcontainer/devcontainer.json", "// the spec\n{\n  \"image\": \"x\", // inline\n}\n")
	got, err := Files{Root: root}.Load(rules.Input{Path: ".devcontainer/devcontainer.json", Format: rules.JSONC})
	if err != nil || !reflect.DeepEqual(got, map[string]any{"image": "x"}) {
		t.Fatalf("jsonc = %#v, %v", got, err)
	}
	write(t, root, "bad.json", "{ // no end\n")
	if _, err := (Files{Root: root}).Load(rules.Input{Path: "bad.json", Format: rules.JSONC}); err == nil || !strings.Contains(err.Error(), "bad.json") {
		t.Fatalf("error %v does not name the file", err)
	}
}

// A Windows checkout with core.autocrlf=true has CRLF line ends; a rule's
// line regexps see the same text as on Linux.
func TestFilesReadsCRLFTextAsLF(t *testing.T) {
	root := t.TempDir()
	write(t, root, "Dockerfile", "FROM a AS b\r\nRUN c\r\n")
	got, err := Files{Root: root}.Load(rules.Input{Path: "Dockerfile", Format: rules.Text})
	if err != nil || got != "FROM a AS b\nRUN c\n" {
		t.Fatalf("text = %#v, %v", got, err)
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

func TestFilesReadsEveryTrackedFileAGlobMatches(t *testing.T) {
	root := t.TempDir()
	for _, args := range [][]string{{"init", "-q"}, {"config", "user.email", "t@example.invalid"}, {"config", "user.name", "t"}} {
		if out, err := exec.Command("git", append([]string{"-C", root}, args...)...).CombinedOutput(); err != nil {
			t.Fatalf("git %v: %v %s", args, err, out)
		}
	}
	write(t, root, "a/Dockerfile", "FROM a\n")
	write(t, root, "b/c/Dockerfile.dev", "FROM c\n")
	write(t, root, "b/notes.txt", "no\n")
	write(t, root, "d/Dockerfile", "FROM untracked\n")
	if out, err := exec.Command("git", "-C", root, "add", "a", "b").CombinedOutput(); err != nil {
		t.Fatalf("git add: %v %s", err, out)
	}
	got, err := Files{Root: root, Git: "git"}.Load(rules.Input{Path: "**/Dockerfile*", Format: rules.Text, Glob: true})
	want := map[string]any{"a/Dockerfile": "FROM a\n", "b/c/Dockerfile.dev": "FROM c\n"}
	if err != nil || !reflect.DeepEqual(got, want) {
		t.Fatalf("glob = %#v, %v; want %#v (tracked files only)", got, err, want)
	}
}
