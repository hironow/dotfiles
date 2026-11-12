package main

import (
	"context"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-bump/fake/registry"
	"github.com/hironow/dotfiles/tools/agent-bump/fake/releases"
	"github.com/hironow/dotfiles/tools/agent-bump/fake/repo"
	"github.com/hironow/dotfiles/tools/agent-bump/internal/bump"
)

// These suites hold the fakes to what the real services do. The fake leg runs
// in every `just check`; the real leg needs the network and a GitHub token,
// so `go test -short` skips it.

const codexRepo = "openai/codex-plugin-cc"

var sha = regexp.MustCompile(`^[0-9a-f]{40}$`)

func releasesContract(t *testing.T, r bump.Releases) {
	t.Helper()
	ctx := context.Background()
	latest, err := r.Latest(ctx, codexRepo)
	if err != nil || !strings.HasPrefix(latest, "v") {
		t.Fatalf("Latest = %q, %v", latest, err)
	}
	commit, err := r.Commit(ctx, codexRepo, "v1.0.5")
	if err != nil || !sha.MatchString(commit) {
		t.Fatalf("Commit = %q, %v", commit, err)
	}
	if _, err := r.Commit(ctx, codexRepo, "v0.0.0-missing"); err == nil {
		t.Fatal("a missing tag must fail")
	}
	manifest, err := r.File(ctx, codexRepo, "v1.0.5", ".claude-plugin/marketplace.json")
	if err != nil || !strings.Contains(string(manifest), `"1.0.5"`) {
		t.Fatalf("File = %q, %v", manifest, err)
	}
	tree, err := r.Tree(ctx, codexRepo, "v1.0.5")
	if err != nil {
		t.Fatal(err)
	}
	if !slices.ContainsFunc(tree, func(e bump.TreeEntry) bool { return e.Path == ".claude-plugin" && e.Dir && sha.MatchString(e.SHA) }) ||
		!slices.ContainsFunc(tree, func(e bump.TreeEntry) bool { return e.Path == ".claude-plugin/marketplace.json" && !e.Dir }) {
		t.Fatalf("Tree lacks the marketplace dir or file: %v", tree)
	}
}

func registryContract(t *testing.T, r bump.Registry) {
	t.Helper()
	ctx := context.Background()
	for _, pkg := range []string{"pi-goal-x", "@ollama/pi-web-search"} {
		latest, all, err := r.Versions(ctx, pkg)
		if err != nil || latest == "" || !slices.Contains(all, latest) {
			t.Fatalf("Versions(%s) = %q, %d versions, %v", pkg, latest, len(all), err)
		}
	}
	if _, _, err := r.Versions(ctx, "no-such-package-agent-bump-contract"); err == nil {
		t.Fatal("a missing package must fail")
	}
}

func TestFakeReleasesContract(t *testing.T) {
	tag := func(version string) releases.Tag {
		return releases.Tag{
			Commit: strings.Repeat(version[len(version)-1:], 40),
			Files:  map[string]string{".claude-plugin/marketplace.json": `{"plugins":[{"name":"codex","version":"` + version[1:] + `"}]}`},
			Dirs:   map[string]string{".claude-plugin": strings.Repeat("d", 40)},
		}
	}
	releasesContract(t, &releases.Fake{Repos: map[string]releases.Repo{
		codexRepo: {Latest: "v1.0.6", Tags: map[string]releases.Tag{"v1.0.5": tag("v1.0.5"), "v1.0.6": tag("v1.0.6")}},
	}})
}

func TestRealReleasesContract(t *testing.T) {
	if testing.Short() {
		t.Skip("needs the network")
	}
	gh, err := newGitHub(context.Background())
	if err != nil {
		t.Skip(err)
	}
	releasesContract(t, gh)
}

func TestFakeRegistryContract(t *testing.T) {
	registryContract(t, &registry.Fake{Packages: map[string]registry.Package{
		"pi-goal-x":             {Latest: "2.0.0", Versions: []string{"1.0.0", "2.0.0"}},
		"@ollama/pi-web-search": {Latest: "0.5.0", Versions: []string{"0.5.0"}},
	}})
}

func TestRealRegistryContract(t *testing.T) {
	if testing.Short() {
		t.Skip("needs the network")
	}
	registryContract(t, newNpmRegistry())
}

// repoContract holds the fake checkout to what the real one does: the fake
// once let a write to a missing file through and never marked a written file
// as changed, so the shell tests passed while the live bump stopped.
func repoContract(t *testing.T, r bump.Repo) {
	t.Helper()
	if _, err := r.Read("no/such/file.json"); err == nil {
		t.Fatal("Read of a missing file must fail")
	}
	if err := r.Write("no/such/file.json", "{}"); err == nil {
		t.Fatal("Write must not create a file the declarations do not have")
	}
	if err := r.Write(bump.PiPackages, "[\"npm:x\"]\n"); err != nil {
		t.Fatal(err)
	}
	if got, err := r.Read(bump.PiPackages); err != nil || got != "[\"npm:x\"]\n" {
		t.Fatalf("Read after Write = %q, %v", got, err)
	}
}

func TestFakeRepoContract(t *testing.T) {
	repoContract(t, &repo.Fake{Files: map[string]string{bump.PiPackages: "[]\n"}})
}

func TestRealRepoContract(t *testing.T) {
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "dump", "harness"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, filepath.FromSlash(bump.PiPackages)), []byte("[]\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	repoContract(t, checkout{root: root})
}
