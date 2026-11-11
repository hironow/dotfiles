package bump

import (
	"errors"
	"slices"
	"strings"
	"testing"
)

const claudeJSON = `{
  "marketplaces": {
    "openai-codex": "openai/codex-plugin-cc#v1.0.6",
    "claude-plugins-official": "anthropics/claude-plugins-official",
    "googlechrome": "GoogleChrome/modern-web-guidance#v1.0.0",
    "egm": "google/elephant-goldfish-model#v0.1.0",
    "hironow-plugins": "./.claude-plugin/marketplace.json"
  },
  "plugins": [
    "codex@openai-codex",
    "context7@claude-plugins-official",
    "egm@egm",
    "modern-web-guidance@googlechrome"
  ]
}
`

const piJSON = `[
  "npm:pi-goal-x",
  "npm:@ollama/pi-web-search@0.4.0",
  "git:github.com/google/elephant-goldfish-model@v0.1.0",
  "npm:pi-blackhole"
]
`

const skillJSON = `{
  "version": 1,
  "skills": [
    {
      "installed_dir": "security-audit",
      "upstream_name": "security-audit",
      "lock_key": "security-audit",
      "source": "cloudflare/security-audit-skill",
      "skill_path": "skills/security-audit/SKILL.md",
      "skill_folder_hash": "ccbc33ed119b28c3ef7b44a7e2081ab191ad63af",
      "resolved_by": "installed"
    }
  ]
}
`

const installerPy = `EGM_PACKAGE = "git:github.com/google/elephant-goldfish-model"
EGM_SOURCE = "git:github.com/google/elephant-goldfish-model@v0.1.0"
EGM_COMMIT = "b3a35956759bf7f024af2ff061b2e0b44b438e4c"
`

const justfileText = `egm-install-native:
    codex plugin marketplace add google/elephant-goldfish-model --ref v0.1.0 --json
`

func files() map[string]string {
	return map[string]string{
		ClaudePlugins: claudeJSON,
		PiPackages:    piJSON,
		SkillLock:     skillJSON,
		PiInstaller:   installerPy,
		Justfile:      justfileText,
	}
}

func parsed(t *testing.T) Declarations {
	t.Helper()
	d, err := Parse(files())
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	return d
}

func TestParseFindsEveryDeclaredItemButUnpinnedMarketplaces(t *testing.T) {
	d := parsed(t)
	var got []string
	for _, it := range d.Items {
		got = append(got, string(it.Kind)+":"+it.Name+"="+it.Current)
	}
	want := []string{
		"egm:egm=v0.1.0",
		"marketplace:googlechrome=v1.0.0",
		"marketplace:openai-codex=v1.0.6",
		"pi:@ollama/pi-web-search=0.4.0",
		"pi:pi-blackhole=",
		"pi:pi-goal-x=",
		"skill:security-audit=ccbc33ed119b28c3ef7b44a7e2081ab191ad63af",
	}
	if !slices.Equal(got, want) {
		t.Fatalf("items\n got %q\nwant %q", got, want)
	}
	egm, _ := Resolve(d, "egm")
	if egm.Commit != "b3a35956759bf7f024af2ff061b2e0b44b438e4c" || !slices.Equal(egm.Plugins, []string{"egm"}) {
		t.Fatalf("egm item: %+v", egm)
	}
	codex, _ := Resolve(d, "openai-codex")
	if codex.Repo != "openai/codex-plugin-cc" || !slices.Equal(codex.Plugins, []string{"codex"}) {
		t.Fatalf("codex item: %+v", codex)
	}
}

func TestResolveAcceptsTheNpmPrefixAndRefusesUnknownNames(t *testing.T) {
	d := parsed(t)
	for _, name := range []string{"pi-goal-x", "npm:pi-goal-x", "npm:@ollama/pi-web-search"} {
		if _, err := Resolve(d, name); err != nil {
			t.Errorf("Resolve(%q): %v", name, err)
		}
	}
	for _, name := range []string{"claude-plugins-official", "hironow-plugins", "nope"} {
		if _, err := Resolve(d, name); !errors.Is(err, ErrUndeclared) {
			t.Errorf("Resolve(%q) = %v, want ErrUndeclared", name, err)
		}
	}
}

func TestResolveStopsWhenANameMeansTwoThings(t *testing.T) {
	f := files()
	f[PiPackages] = `["npm:security-audit"]`
	d, err := Parse(f)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := Resolve(d, "security-audit"); err == nil || !strings.Contains(err.Error(), "ambiguous") {
		t.Fatalf("Resolve = %v, want an ambiguity error", err)
	}
}

func TestTargetKeepsThePinStateUnlessLatestIsAsked(t *testing.T) {
	d := parsed(t)
	pinned, _ := Resolve(d, "@ollama/pi-web-search")
	unpinned, _ := Resolve(d, "pi-goal-x")
	cases := []struct {
		it      Item
		arg     string
		latest  string
		want    string
		unpin   bool
		explain string
	}{
		{pinned, "", "0.5.0", "0.5.0", false, "pinned, no version: move the pin to the newest"},
		{unpinned, "", "2.0.0", "", false, "unpinned, no version: stay unpinned"},
		{pinned, "latest", "0.5.0", "", true, "latest drops the pin"},
		{unpinned, "1.2.3", "2.0.0", "1.2.3", false, "an explicit version pins"},
	}
	for _, c := range cases {
		got := TargetFor(c.it, c.arg, c.latest)
		if got.Version != c.want || got.Unpin != c.unpin {
			t.Errorf("%s: got %+v", c.explain, got)
		}
	}
}

func editsFor(t *testing.T, name string, target Target) []Edit {
	t.Helper()
	it, err := Resolve(parsed(t), name)
	if err != nil {
		t.Fatal(err)
	}
	edits, err := Edits(it, target)
	if err != nil {
		t.Fatalf("Edits(%s): %v", name, err)
	}
	return edits
}

func TestMarketplaceEditRewritesOnlyItsTag(t *testing.T) {
	got := editsFor(t, "openai-codex", Target{Version: "v1.0.5"})
	want := []Edit{{ClaudePlugins, `"openai/codex-plugin-cc#v1.0.6"`, `"openai/codex-plugin-cc#v1.0.5"`}}
	if !slices.Equal(got, want) {
		t.Fatalf("got %q", got)
	}
}

func TestEGMEditsEveryPinTogether(t *testing.T) {
	sha := strings.Repeat("a", 40)
	edits := editsFor(t, "egm", Target{Version: "v0.1.2", Commit: sha})
	out, err := Apply(files(), edits)
	if err != nil {
		t.Fatal(err)
	}
	for path, want := range map[string]string{
		ClaudePlugins: `"google/elephant-goldfish-model#v0.1.2"`,
		PiPackages:    `"git:github.com/google/elephant-goldfish-model@v0.1.2"`,
		PiInstaller:   `EGM_COMMIT = "` + sha + `"`,
		Justfile:      "google/elephant-goldfish-model --ref v0.1.2 ",
	} {
		if !strings.Contains(out[path], want) || strings.Contains(out[path], "v0.1.0") {
			t.Errorf("%s:\n%s", path, out[path])
		}
	}
	if !strings.Contains(out[PiInstaller], `EGM_SOURCE = "git:github.com/google/elephant-goldfish-model@v0.1.2"`) {
		t.Errorf("EGM_SOURCE not moved:\n%s", out[PiInstaller])
	}
}

func TestPiEditsPinMoveAndDropTheVersion(t *testing.T) {
	cases := []struct {
		name   string
		target Target
		want   []Edit
	}{
		{"pi-goal-x", Target{Version: "1.2.3"}, []Edit{{PiPackages, `"npm:pi-goal-x"`, `"npm:pi-goal-x@1.2.3"`}}},
		{"@ollama/pi-web-search", Target{Version: "0.5.0"}, []Edit{{PiPackages, `"npm:@ollama/pi-web-search@0.4.0"`, `"npm:@ollama/pi-web-search@0.5.0"`}}},
		{"@ollama/pi-web-search", Target{Unpin: true}, []Edit{{PiPackages, `"npm:@ollama/pi-web-search@0.4.0"`, `"npm:@ollama/pi-web-search"`}}},
		{"pi-goal-x", Target{}, nil}, // unpinned to the newest: nothing to write
	}
	for _, c := range cases {
		if got := editsFor(t, c.name, c.target); !slices.Equal(got, c.want) {
			t.Errorf("%s %+v: got %q", c.name, c.target, got)
		}
	}
}

func TestASkillTakesNoVersion(t *testing.T) {
	it, _ := Resolve(parsed(t), "security-audit")
	if _, err := Edits(it, Target{Version: "abc"}); !errors.Is(err, ErrSkillVersion) {
		t.Fatalf("got %v, want ErrSkillVersion", err)
	}
	if edits, err := Edits(it, Target{}); err != nil || edits != nil {
		t.Fatalf("got %q, %v; the skills CLI writes the skill's record", edits, err)
	}
}

func TestApplyNeedsEachOldTextExactlyOnce(t *testing.T) {
	in := map[string]string{"f": "a b a"}
	if _, err := Apply(in, []Edit{{"f", "a", "x"}}); err == nil {
		t.Error("two matches must fail")
	}
	if _, err := Apply(in, []Edit{{"f", "zzz", "x"}}); err == nil {
		t.Error("no match must fail")
	}
	out, err := Apply(in, []Edit{{"f", "b", "x"}})
	if err != nil || out["f"] != "a x a" || in["f"] != "a b a" {
		t.Errorf("got %q, %v; input must stay unchanged", out, err)
	}
}

func TestCheckStopsOnAPluginVersionThatDoesNotMatchTheTag(t *testing.T) {
	it, _ := Resolve(parsed(t), "openai-codex")
	up := Upstream{TagExists: true, PluginVersions: map[string]string{"codex": "1.0.4"}}
	if err := Check(it, Target{Version: "v1.0.5"}, up); err == nil || !strings.Contains(err.Error(), "1.0.4") {
		t.Fatalf("got %v", err)
	}
	up.PluginVersions["codex"] = "1.0.5"
	if err := Check(it, Target{Version: "v1.0.5"}, up); err != nil {
		t.Fatalf("got %v", err)
	}
	if err := Check(it, Target{Version: "v9"}, Upstream{}); err == nil {
		t.Fatal("a missing tag must fail")
	}
}

func TestCheckStopsWhenANewEGMTagLacksARequiredFile(t *testing.T) {
	it, _ := Resolve(parsed(t), "egm")
	up := Upstream{
		TagExists:      true,
		PluginVersions: map[string]string{"egm": "0.1.1"},
		RequiredPaths:  []string{"LICENSE", "skills/egm_review/SKILL.md"},
		TreePaths:      []string{"LICENSE", "skills/egm-review/SKILL.md", "agents/new.md"},
	}
	err := Check(it, Target{Version: "v0.1.1"}, up)
	if err == nil || !strings.Contains(err.Error(), "skills/egm_review/SKILL.md") {
		t.Fatalf("got %v", err)
	}
	up.TreePaths = append(up.TreePaths, "skills/egm_review/SKILL.md")
	if err := Check(it, Target{Version: "v0.1.1"}, up); err != nil {
		t.Fatalf("extra files are fine: %v", err)
	}
}

func TestCheckStopsOnAnUnpublishedNpmVersion(t *testing.T) {
	it, _ := Resolve(parsed(t), "pi-goal-x")
	up := Upstream{NpmVersions: []string{"1.0.0", "1.1.0"}}
	if err := Check(it, Target{Version: "9.9.9"}, up); err == nil {
		t.Fatal("unpublished version must fail")
	}
	if err := Check(it, Target{Version: "1.1.0"}, up); err != nil {
		t.Fatal(err)
	}
	if err := Check(it, Target{}, up); err != nil {
		t.Fatal(err)
	}
}

func TestSkillDirIsTheParentOfTheSkillFile(t *testing.T) {
	it, _ := Resolve(parsed(t), "security-audit")
	if got := SkillDir(it); got != "skills/security-audit" {
		t.Fatalf("got %q", got)
	}
}
