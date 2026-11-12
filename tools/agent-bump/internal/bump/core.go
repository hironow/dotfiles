// Package bump moves the version of an agent plugin, EGM, Pi package, or
// skill that dotfiles already declares (ADR 0074). The core in this file is
// pure: it reads declaration text and upstream facts and returns edits.
package bump

import (
	"errors"
	"fmt"
	"path"
	"regexp"
	"slices"
	"strings"

	json "github.com/goccy/go-json/v2"
)

// Kind is what a declared name refers to.
type Kind string

const (
	Marketplace Kind = "marketplace" // a Claude plugin marketplace pinned to a tag
	EGM         Kind = "egm"         // the EGM bundle, pinned in four places
	PiPackage   Kind = "pi"          // an npm package Pi installs
	Skill       Kind = "skill"       // a skill in the bunx skills store
)

// The files that hold the declarations, relative to the repo root.
const (
	ClaudePlugins = "dump/harness/claude-plugins.json"
	PiPackages    = "dump/harness/pi-packages.json"
	SkillLock     = "dump/harness/skill-lock.json"
	PiInstaller   = "scripts/install_pi_extensions.py"
)

// The files Parse reads.
var DeclarationFiles = []string{ClaudePlugins, PiPackages, SkillLock, PiInstaller}

const (
	egmMarketplace = "egm"
	egmRepo        = "google/elephant-goldfish-model"
	egmPiPackage   = "git:github.com/" + egmRepo
)

var (
	ErrUndeclared   = errors.New("not declared; add a new one by hand (ADR 0074 D3)")
	ErrSkillVersion = errors.New("a skill can only move to its upstream HEAD: the skills CLI takes no version")
	egmCommitLine   = regexp.MustCompile(`EGM_COMMIT = "([0-9a-f]{40})"`)
)

// Item is one declared thing whose version can move.
type Item struct {
	Kind    Kind
	Name    string   // marketplace key, npm package name, or skill dir
	Repo    string   // GitHub owner/repo (marketplace, EGM, skill source)
	Current string   // tag, pinned npm version ("" when unpinned), or skill hash
	Source  string   // Pi: the declared source; skill: its SKILL.md path
	Plugins []string // marketplace and EGM: the declared plugins it provides
	Commit  string   // EGM: the pinned commit
}

// Declarations are every item, sorted by kind and name.
type Declarations struct{ Items []Item }

// Target is where a bump moves an item.
type Target struct {
	Version string // tag or npm version; "" for "the newest, unpinned"
	Commit  string // EGM: the commit the tag points at
	Unpin   bool   // Pi: drop the pin
}

// Upstream holds what the shell learned about the target before any write.
type Upstream struct {
	TagExists      bool
	PluginVersions map[string]string // plugin -> version in the tag's marketplace.json
	RequiredPaths  []string          // EGM: files the Pi installer requires
	TreePaths      []string          // EGM: files in the tag's tree
	NpmVersions    []string          // Pi: published versions
}

// Edit replaces Old, which must occur exactly once, with New in Path.
type Edit struct{ Path, Old, New string }

type claudeDecl struct {
	Marketplaces map[string]string `json:"marketplaces"`
	Plugins      []string          `json:"plugins"`
}

type skillDecl struct {
	Skills []struct {
		InstalledDir string `json:"installed_dir"`
		Source       string `json:"source"`
		SkillPath    string `json:"skill_path"`
		Hash         string `json:"skill_folder_hash"`
	} `json:"skills"`
}

// Parse reads the declaration files. Marketplaces without a tag
// (claude-plugins-official follows its branch, hironow-plugins is a repo
// path) have no version to move and are left out.
func Parse(files map[string]string) (Declarations, error) {
	var claude claudeDecl
	if err := json.Unmarshal([]byte(files[ClaudePlugins]), &claude); err != nil {
		return Declarations{}, fmt.Errorf("%s: %w", ClaudePlugins, err)
	}
	var pi []string
	if err := json.Unmarshal([]byte(files[PiPackages]), &pi); err != nil {
		return Declarations{}, fmt.Errorf("%s: %w", PiPackages, err)
	}
	var skills skillDecl
	if err := json.Unmarshal([]byte(files[SkillLock]), &skills); err != nil {
		return Declarations{}, fmt.Errorf("%s: %w", SkillLock, err)
	}
	var items []Item
	for name, source := range claude.Marketplaces {
		repo, tag, pinned := strings.Cut(source, "#")
		if !pinned {
			continue
		}
		it := Item{Kind: Marketplace, Name: name, Repo: repo, Current: tag, Plugins: pluginsOf(claude.Plugins, name)}
		if name == egmMarketplace {
			m := egmCommitLine.FindStringSubmatch(files[PiInstaller])
			if m == nil {
				return Declarations{}, fmt.Errorf("%s: no EGM_COMMIT line", PiInstaller)
			}
			it.Kind, it.Commit = EGM, m[1]
		}
		items = append(items, it)
	}
	for _, source := range pi {
		name, version, ok := NpmName(source)
		if !ok {
			continue // the EGM git package moves with the EGM item
		}
		items = append(items, Item{Kind: PiPackage, Name: name, Current: version, Source: source})
	}
	for _, s := range skills.Skills {
		items = append(items, Item{Kind: Skill, Name: s.InstalledDir, Repo: s.Source, Current: s.Hash, Source: s.SkillPath})
	}
	slices.SortFunc(items, func(a, b Item) int {
		return strings.Compare(string(a.Kind)+"\x00"+a.Name, string(b.Kind)+"\x00"+b.Name)
	})
	return Declarations{Items: items}, nil
}

func pluginsOf(plugins []string, marketplace string) []string {
	var out []string
	for _, p := range plugins {
		if name, from, ok := strings.Cut(p, "@"); ok && from == marketplace {
			out = append(out, name)
		}
	}
	return out
}

// NpmName splits `npm:@scope/name@1.2.3` into its package name and pin.
func NpmName(source string) (name, version string, ok bool) {
	spec, isNpm := strings.CutPrefix(source, "npm:")
	if !isNpm {
		return "", "", false
	}
	scope := ""
	if rest, scoped := strings.CutPrefix(spec, "@"); scoped {
		scope, spec = "@", rest
	}
	name, version, _ = strings.Cut(spec, "@")
	return scope + name, version, true
}

// Resolve finds the one declared item a name refers to.
func Resolve(d Declarations, name string) (Item, error) {
	want := strings.TrimPrefix(name, "npm:")
	var found []Item
	for _, it := range d.Items {
		if it.Name == want {
			found = append(found, it)
		}
	}
	switch len(found) {
	case 0:
		return Item{}, fmt.Errorf("%s: %w", name, ErrUndeclared)
	case 1:
		return found[0], nil
	}
	kinds := make([]string, len(found))
	for i, it := range found {
		kinds[i] = string(it.Kind)
	}
	return Item{}, fmt.Errorf("%s is ambiguous: it names a %s", name, strings.Join(kinds, " and a "))
}

// TargetFor turns the user's version argument into a target. Without one, a
// pinned Pi package moves its pin to the newest version and an unpinned one
// stays unpinned; `latest` drops a Pi pin.
func TargetFor(it Item, arg, latest string) Target {
	switch {
	case it.Kind == PiPackage && arg == "latest":
		return Target{Unpin: true}
	case it.Kind == PiPackage && arg == "" && it.Current == "":
		return Target{}
	case arg == "":
		return Target{Version: latest}
	}
	return Target{Version: arg}
}

// Check refuses a target the upstream facts do not support, before any write.
func Check(it Item, t Target, up Upstream) error {
	switch it.Kind {
	case Marketplace, EGM:
		if !up.TagExists {
			return fmt.Errorf("%s: %s has no tag %s", it.Name, it.Repo, t.Version)
		}
		want := strings.TrimPrefix(t.Version, "v")
		for _, plugin := range it.Plugins {
			// claude_plugins.py compares the tag with the installed version,
			// so a mismatch would leave `--check` warning forever.
			if got := up.PluginVersions[plugin]; got != want {
				return fmt.Errorf("%s: plugin %s at %s declares version %q, not %q", it.Name, plugin, t.Version, got, want)
			}
		}
		if it.Kind == EGM {
			var missing []string
			for _, p := range up.RequiredPaths {
				if !slices.Contains(up.TreePaths, p) {
					missing = append(missing, p)
				}
			}
			if len(missing) > 0 {
				return fmt.Errorf("egm %s changed its layout (missing %s); agent-bump cannot move it: change the required files in scripts/install_pi_extensions.py and the four EGM pins together in one PR, then run the deploy installers (docs/runbook/egm.md)",
					t.Version, strings.Join(missing, ", "))
			}
		}
	case PiPackage:
		if t.Version != "" && !slices.Contains(up.NpmVersions, t.Version) {
			return fmt.Errorf("%s: npm has no version %s", it.Name, t.Version)
		}
	case Skill:
	}
	return nil
}

// Edits are the declaration changes that move it to t.
func Edits(it Item, t Target) ([]Edit, error) {
	switch it.Kind {
	case Marketplace:
		return []Edit{{ClaudePlugins, quote(it.Repo + "#" + it.Current), quote(it.Repo + "#" + t.Version)}}, nil
	case EGM:
		return []Edit{
			{ClaudePlugins, quote(egmRepo + "#" + it.Current), quote(egmRepo + "#" + t.Version)},
			{PiPackages, quote(egmPiPackage + "@" + it.Current), quote(egmPiPackage + "@" + t.Version)},
			{PiInstaller, "EGM_SOURCE = " + quote(egmPiPackage+"@"+it.Current), "EGM_SOURCE = " + quote(egmPiPackage+"@"+t.Version)},
			{PiInstaller, "EGM_COMMIT = " + quote(it.Commit), "EGM_COMMIT = " + quote(t.Commit)},
		}, nil
	case PiPackage:
		next := "npm:" + it.Name
		if t.Version != "" {
			next += "@" + t.Version
		}
		if t.Version == "" && !t.Unpin {
			next = it.Source // unpinned stays unpinned
		}
		if next == it.Source {
			return nil, nil
		}
		return []Edit{{PiPackages, quote(it.Source), quote(next)}}, nil
	case Skill:
		if t.Version != "" {
			return nil, ErrSkillVersion
		}
		return nil, nil // skills_lock.py writes the record's new hash
	}
	return nil, fmt.Errorf("unknown kind %q", it.Kind)
}

func quote(s string) string { return `"` + s + `"` }

// Apply returns the files with the edits made, leaving the input unchanged.
func Apply(files map[string]string, edits []Edit) (map[string]string, error) {
	out := make(map[string]string, len(files))
	for k, v := range files {
		out[k] = v
	}
	for _, e := range edits {
		if n := strings.Count(out[e.Path], e.Old); n != 1 {
			return nil, fmt.Errorf("%s: expected %q exactly once, found %d", e.Path, e.Old, n)
		}
		out[e.Path] = strings.Replace(out[e.Path], e.Old, e.New, 1)
	}
	return out, nil
}

// SkillDir is the directory a skill's SKILL.md lives in, in its repo.
func SkillDir(it Item) string { return path.Dir(it.Source) }
