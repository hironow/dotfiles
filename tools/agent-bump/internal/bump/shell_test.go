package bump_test

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-bump/fake/machine"
	"github.com/hironow/dotfiles/tools/agent-bump/fake/registry"
	"github.com/hironow/dotfiles/tools/agent-bump/fake/releases"
	"github.com/hironow/dotfiles/tools/agent-bump/fake/repo"
	"github.com/hironow/dotfiles/tools/agent-bump/internal/bump"
)

const (
	egmOld = "b3a35956759bf7f024af2ff061b2e0b44b438e4c"
	egmNew = "1111111111111111111111111111111111111111"
)

var required = []string{"LICENSE", "skills/egm_review/SKILL.md"}

func marketplaceJSON(plugin, version string) string {
	return `{"plugins": [{"name": "` + plugin + `", "version": "` + version + `"}]}`
}

// EGM's marketplace names the plugin with a relative source and no version;
// the version lives in the plugin's own plugin.json (checked on v0.1.0/v0.1.1).
const egmMarketplace = `{"plugins": [{"name": "egm", "source": "./"}]}`

func egmPluginJSON(version string) string { return `{"name": "egm", "version": "` + version + `"}` }

type world struct {
	app      bump.App
	repo     *repo.Fake
	machine  *machine.Fake
	releases *releases.Fake
}

func newWorld() world {
	r := &repo.Fake{Files: map[string]string{
		bump.ClaudePlugins: `{
  "marketplaces": {
    "openai-codex": "openai/codex-plugin-cc#v1.0.6",
    "egm": "google/elephant-goldfish-model#v0.1.0"
  },
  "plugins": ["codex@openai-codex", "egm@egm"]
}
`,
		bump.PiPackages: `["npm:pi-goal-x", "npm:@ollama/pi-web-search@0.4.0", "git:github.com/google/elephant-goldfish-model@v0.1.0"]
`,
		bump.SkillLock: `{"version": 1, "skills": [{"installed_dir": "security-audit", "source": "cloudflare/security-audit-skill", "skill_path": "skills/security-audit/SKILL.md", "skill_folder_hash": "ccbc33ed119b28c3ef7b44a7e2081ab191ad63af"}]}
`,
		bump.PiInstaller: `EGM_SOURCE = "git:github.com/google/elephant-goldfish-model@v0.1.0"
EGM_COMMIT = "` + egmOld + `"
`,
	}}
	rel := &releases.Fake{Repos: map[string]releases.Repo{
		"openai/codex-plugin-cc": {Latest: "v1.0.6", Tags: map[string]releases.Tag{
			"v1.0.5": {Commit: "c105", Files: map[string]string{".claude-plugin/marketplace.json": marketplaceJSON("codex", "1.0.5")}},
			"v1.0.6": {Commit: "c106", Files: map[string]string{".claude-plugin/marketplace.json": marketplaceJSON("codex", "1.0.6")}},
		}},
		"google/elephant-goldfish-model": {Latest: "v0.1.1", Tags: map[string]releases.Tag{
			"v0.1.1": {Commit: strings.Repeat("2", 40), Files: map[string]string{
				".claude-plugin/marketplace.json": egmMarketplace,
				".claude-plugin/plugin.json":      egmPluginJSON("0.1.1"),
				"LICENSE":                         "",
				"skills/egm-review/SKILL.md":      "",
			}},
			"v0.1.2": {Commit: egmNew, Files: map[string]string{
				".claude-plugin/marketplace.json": egmMarketplace,
				".claude-plugin/plugin.json":      egmPluginJSON("0.1.2"),
				"LICENSE":                         "",
				"skills/egm_review/SKILL.md":      "",
			}},
		}},
		"cloudflare/security-audit-skill": {Tags: map[string]releases.Tag{
			"HEAD": {Dirs: map[string]string{"skills/security-audit": "ccbc33ed119b28c3ef7b44a7e2081ab191ad63af"}},
		}},
	}}
	reg := &registry.Fake{Packages: map[string]registry.Package{
		"pi-goal-x":             {Latest: "2.0.0", Versions: []string{"1.0.0", "2.0.0"}},
		"@ollama/pi-web-search": {Latest: "0.5.0", Versions: []string{"0.4.0", "0.5.0"}},
	}}
	m := &machine.Fake{
		Installed: map[string]string{"openai-codex": "v1.0.6", "egm": "v0.1.0", "pi-goal-x": "", "@ollama/pi-web-search": "0.4.0"},
		Required:  required,
	}
	return world{
		app:      bump.App{Releases: rel, Registry: reg, Repo: r, Machine: m},
		repo:     r,
		machine:  m,
		releases: rel,
	}
}

func TestBumpingAMarketplaceDownAndBackChangesTheDeclarationAndTheMachine(t *testing.T) {
	w := newWorld()
	original := w.repo.Files[bump.ClaudePlugins]
	if _, err := w.app.Bump(context.Background(), "openai-codex", "v1.0.5"); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(w.repo.Files[bump.ClaudePlugins], `"openai/codex-plugin-cc#v1.0.5"`) {
		t.Fatalf("declaration:\n%s", w.repo.Files[bump.ClaudePlugins])
	}
	if w.machine.Installed["openai-codex"] != "v1.0.5" {
		t.Fatalf("installed %q", w.machine.Installed["openai-codex"])
	}
	if _, err := w.app.Bump(context.Background(), "openai-codex", ""); err != nil {
		t.Fatal(err)
	}
	if w.repo.Files[bump.ClaudePlugins] != original || w.machine.Installed["openai-codex"] != "v1.0.6" {
		t.Fatalf("not back at v1.0.6:\n%s", w.repo.Files[bump.ClaudePlugins])
	}
}

func TestAnUncommittedPinFileStopsTheBumpBeforeAnyChange(t *testing.T) {
	w := newWorld()
	w.repo.DirtyPaths = []string{bump.ClaudePlugins}
	before := w.repo.Files[bump.ClaudePlugins]
	if _, err := w.app.Bump(context.Background(), "openai-codex", "v1.0.5"); err == nil {
		t.Fatal("want a refusal")
	}
	if w.repo.Files[bump.ClaudePlugins] != before || w.machine.Installed["openai-codex"] != "v1.0.6" {
		t.Fatal("a refused bump changed something")
	}
}

func TestARedBaselineStopsTheBumpBeforeAnyChange(t *testing.T) {
	w := newWorld()
	w.machine.RedBaseline = map[string]bool{"openai-codex": true}
	before := w.repo.Files[bump.ClaudePlugins]
	if _, err := w.app.Bump(context.Background(), "openai-codex", "v1.0.5"); err == nil {
		t.Fatal("want a refusal")
	}
	if w.repo.Files[bump.ClaudePlugins] != before {
		t.Fatal("a refused bump wrote the declaration")
	}
}

func TestAFailedInstallRestoresTheDeclarationAndReinstallsIt(t *testing.T) {
	w := newWorld()
	w.machine.FailInstall = map[string]string{"openai-codex": "v1.0.5"}
	before := w.repo.Files[bump.ClaudePlugins]
	_, err := w.app.Bump(context.Background(), "openai-codex", "v1.0.5")
	if err == nil || !strings.Contains(err.Error(), "restored") {
		t.Fatalf("got %v", err)
	}
	if w.repo.Files[bump.ClaudePlugins] != before || w.machine.Installed["openai-codex"] != "v1.0.6" {
		t.Fatal("not restored")
	}
}

func TestEGMMovesEveryPinOnlyWhenTheNewTreeHasTheRequiredFiles(t *testing.T) {
	w := newWorld()
	if _, err := w.app.Bump(context.Background(), "egm", ""); err == nil || !strings.Contains(err.Error(), "layout") {
		t.Fatalf("v0.1.1 renamed its skills; got %v", err)
	}
	if w.repo.Files[bump.PiInstaller] != `EGM_SOURCE = "git:github.com/google/elephant-goldfish-model@v0.1.0"
EGM_COMMIT = "`+egmOld+`"
` {
		t.Fatal("a refused EGM bump wrote a pin")
	}
	if _, err := w.app.Bump(context.Background(), "egm", "v0.1.2"); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{bump.ClaudePlugins, bump.PiPackages, bump.PiInstaller} {
		if strings.Contains(w.repo.Files[path], "v0.1.0") {
			t.Errorf("%s still pins v0.1.0:\n%s", path, w.repo.Files[path])
		}
	}
	if !strings.Contains(w.repo.Files[bump.PiInstaller], egmNew) || w.machine.Installed["egm"] != "v0.1.2" {
		t.Fatalf("EGM commit or install not moved:\n%s", w.repo.Files[bump.PiInstaller])
	}
}

func TestPiPackagesPinAndUnpin(t *testing.T) {
	w := newWorld()
	ctx := context.Background()
	if _, err := w.app.Bump(ctx, "pi-goal-x", "1.0.0"); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(w.repo.Files[bump.PiPackages], `"npm:pi-goal-x@1.0.0"`) || w.machine.Installed["pi-goal-x"] != "1.0.0" {
		t.Fatalf("pin: %s", w.repo.Files[bump.PiPackages])
	}
	if _, err := w.app.Bump(ctx, "pi-goal-x", "latest"); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(w.repo.Files[bump.PiPackages], `"npm:pi-goal-x",`) || w.machine.Installed["pi-goal-x"] != "" {
		t.Fatalf("unpin: %s", w.repo.Files[bump.PiPackages])
	}
	if _, err := w.app.Bump(ctx, "pi-goal-x", "9.9.9"); err == nil {
		t.Fatal("an unpublished version must fail")
	}
}

func TestASkillMovesOnlyToItsUpstreamHead(t *testing.T) {
	w := newWorld()
	w.machine.Installed["security-audit"] = "old"
	if _, err := w.app.Bump(context.Background(), "security-audit", "v1"); !errors.Is(err, bump.ErrSkillVersion) {
		t.Fatalf("got %v", err)
	}
	if _, err := w.app.Bump(context.Background(), "security-audit", ""); err != nil {
		t.Fatal(err)
	}
	if w.machine.Installed["security-audit"] != "" {
		t.Fatalf("installed %q, want upstream HEAD", w.machine.Installed["security-audit"])
	}
}

func TestAnUndeclaredNameIsRefused(t *testing.T) {
	w := newWorld()
	if _, err := w.app.Bump(context.Background(), "brand-new", ""); !errors.Is(err, bump.ErrUndeclared) {
		t.Fatalf("got %v", err)
	}
}

func TestTableShowsCurrentAndNewestForEveryItem(t *testing.T) {
	w := newWorld()
	rows, err := w.app.Table(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	got := map[string]bump.Row{}
	for _, r := range rows {
		got[r.Name] = r
	}
	for name, want := range map[string][2]string{
		"openai-codex":          {"v1.0.6", "v1.0.6"},
		"egm":                   {"v0.1.0", "v0.1.1"},
		"pi-goal-x":             {"unpinned", "2.0.0"},
		"@ollama/pi-web-search": {"0.4.0", "0.5.0"},
		"security-audit":        {"ccbc33ed119b", "ccbc33ed119b"},
	} {
		if r := got[name]; r.Current != want[0] || r.Latest != want[1] {
			t.Errorf("%s: got %+v, want current %q latest %q", name, r, want[0], want[1])
		}
	}
	if !got["egm"].Newer || got["openai-codex"].Newer || got["security-audit"].Newer {
		t.Errorf("newer flags: %+v", got)
	}
}
