package bump

import (
	"context"
	"errors"
	"fmt"
	"path"
	"slices"
	"strings"

	json "github.com/goccy/go-json/v2"
)

// App reads through the ports, asks the core, and writes through the ports.
type App struct {
	Releases Releases
	Registry Registry
	Repo     Repo
	Machine  Machine
}

// Result says what a bump did.
type Result struct {
	Item     Item
	From, To string
	Changed  []string // declaration files rewritten
}

// Row is one line of the version table.
type Row struct {
	Kind            Kind
	Name            string
	Current, Latest string
	Newer           bool   // a newer version than the declared one exists
	Note            string // why Latest is missing
}

func (a App) load() (map[string]string, Declarations, error) {
	files := make(map[string]string, len(DeclarationFiles))
	for _, p := range DeclarationFiles {
		content, err := a.Repo.Read(p)
		if err != nil {
			return nil, Declarations{}, err
		}
		files[p] = content
	}
	d, err := Parse(files)
	return files, d, err
}

// Bump moves one declared item to version ("" means the newest).
func (a App) Bump(ctx context.Context, name, version string) (Result, error) {
	files, d, err := a.load()
	if err != nil {
		return Result{}, err
	}
	it, err := Resolve(d, name)
	if err != nil {
		return Result{}, err
	}
	if it.Kind == Skill {
		return a.bumpSkill(ctx, it, version)
	}
	t, up, err := a.target(ctx, it, version)
	if err != nil {
		return Result{}, err
	}
	if err := Check(it, t, up); err != nil {
		return Result{}, err
	}
	res := Result{Item: it, From: shown(it.Current), To: shown(t.Version)}
	if it.Kind != PiPackage && t.Version == it.Current {
		return res, nil // already there
	}
	edits, err := Edits(it, t)
	if err != nil {
		return Result{}, err
	}
	out, err := Apply(files, edits)
	if err != nil {
		return Result{}, err
	}
	for _, e := range edits {
		if !slices.Contains(res.Changed, e.Path) {
			res.Changed = append(res.Changed, e.Path)
		}
	}
	if err := a.Machine.Baseline(ctx, it); err != nil {
		return Result{}, fmt.Errorf("the check is red before any change, so a bump could not be verified: %w", err)
	}
	var written []string
	for _, p := range res.Changed {
		if err := a.Repo.Write(p, out[p]); err != nil {
			return Result{}, errors.Join(err, a.restore(ctx, it, files, out, written))
		}
		written = append(written, p)
	}
	err = a.Machine.Install(ctx, it, t)
	if err == nil {
		err = a.Machine.Verify(ctx, it, t)
	}
	if err != nil {
		return Result{}, errors.Join(err, a.restore(ctx, it, files, out, written))
	}
	return res, nil
}

// restore writes back what the bump read, then reinstalls it, so the machine
// follows the declarations again (ADR 0074 D5). A file that no longer holds
// exactly what the bump wrote was edited while the installers ran: it is kept,
// and nothing is reinstalled from a declaration that was not restored (ADR 0075).
func (a App) restore(ctx context.Context, it Item, files, out map[string]string, written []string) error {
	var restored, kept []string
	var errs []error
	for _, p := range written {
		now, err := a.Repo.Read(p)
		switch {
		case err != nil:
			errs = append(errs, err)
		case now != out[p]:
			kept = append(kept, p)
		default:
			errs = append(errs, a.Repo.Write(p, files[p]))
			restored = append(restored, p)
		}
	}
	if err := errors.Join(errs...); err != nil {
		return fmt.Errorf("could not restore %s: %w", strings.Join(written, ", "), err)
	}
	if len(kept) > 0 {
		back := "nothing else"
		if len(restored) > 0 {
			back = strings.Join(restored, ", ")
		}
		return fmt.Errorf("kept %s: it changed while the bump ran; restored %s; nothing reinstalled, so check the declarations and run the installer",
			strings.Join(kept, ", "), back)
	}
	if len(restored) == 0 {
		return nil // nothing was written, so nothing changed
	}
	if err := a.Machine.Install(ctx, it, Target{Version: it.Current, Commit: it.Commit}); err != nil {
		return fmt.Errorf("restored %s, but reinstalling %s failed: %w", strings.Join(restored, ", "), shown(it.Current), err)
	}
	return fmt.Errorf("restored %s and reinstalled %s", strings.Join(restored, ", "), shown(it.Current))
}

func (a App) bumpSkill(ctx context.Context, it Item, version string) (Result, error) {
	if version != "" {
		return Result{}, ErrSkillVersion
	}
	// skills_lock.py writes the record's new hash; the CLI cannot move a
	// skill back, so nothing here is restored on failure.
	if err := a.Machine.Install(ctx, it, Target{}); err != nil {
		return Result{}, err
	}
	// Report what the declaration says now, not what was hoped for.
	_, d, err := a.load()
	if err != nil {
		return Result{}, err
	}
	now, err := Resolve(d, it.Name)
	if err != nil {
		return Result{}, err
	}
	res := Result{Item: it, From: short(it.Current), To: short(now.Current)}
	if now.Current != it.Current {
		res.Changed = []string{SkillLock}
	}
	return res, nil
}

// target resolves the version argument and gathers the upstream facts.
func (a App) target(ctx context.Context, it Item, version string) (Target, Upstream, error) {
	var up Upstream
	if it.Kind == PiPackage {
		latest, all, err := a.Registry.Versions(ctx, it.Name)
		if err != nil {
			return Target{}, up, err
		}
		up.NpmVersions = all
		return TargetFor(it, version, latest), up, nil
	}
	latest := ""
	if version == "" {
		var err error
		if latest, err = a.Releases.Latest(ctx, it.Repo); err != nil {
			return Target{}, up, err
		}
	}
	t := TargetFor(it, version, latest)
	commit, err := a.Releases.Commit(ctx, it.Repo, t.Version)
	if err != nil {
		return t, up, fmt.Errorf("%s: no tag %s in %s: %w", it.Name, t.Version, it.Repo, err)
	}
	up.TagExists, t.Commit = true, commit
	manifest, err := a.Releases.File(ctx, it.Repo, t.Version, ".claude-plugin/marketplace.json")
	if err != nil {
		return t, up, err
	}
	var m struct {
		Plugins []struct {
			Name    string `json:"name"`
			Version string `json:"version"`
			Source  any    `json:"source"` // a path, or an object for a remote source
		} `json:"plugins"`
	}
	if err := json.Unmarshal(manifest, &m); err != nil {
		return t, up, fmt.Errorf("%s@%s marketplace.json: %w", it.Repo, t.Version, err)
	}
	up.PluginVersions = map[string]string{}
	for _, p := range m.Plugins {
		version := p.Version
		// Without a version in the marketplace entry, a plugin in this repo
		// carries it in its own plugin.json (EGM does).
		if dir, local := p.Source.(string); version == "" && local {
			if version, err = a.pluginVersion(ctx, it.Repo, t.Version, dir); err != nil {
				return t, up, err
			}
		}
		up.PluginVersions[p.Name] = version
	}
	if it.Kind == EGM {
		if up.RequiredPaths, err = a.Machine.EGMRequiredPaths(ctx); err != nil {
			return t, up, err
		}
		tree, err := a.Releases.Tree(ctx, it.Repo, t.Version)
		if err != nil {
			return t, up, err
		}
		for _, e := range tree {
			if !e.Dir {
				up.TreePaths = append(up.TreePaths, e.Path)
			}
		}
	}
	return t, up, nil
}

func (a App) pluginVersion(ctx context.Context, repo, ref, dir string) (string, error) {
	file := path.Join(dir, ".claude-plugin", "plugin.json")
	raw, err := a.Releases.File(ctx, repo, ref, file)
	if err != nil {
		return "", err
	}
	var p struct {
		Version string `json:"version"`
	}
	if err := json.Unmarshal(raw, &p); err != nil {
		return "", fmt.Errorf("%s@%s %s: %w", repo, ref, file, err)
	}
	return p.Version, nil
}

// Table lists every declared item with its newest version. One item that
// cannot be looked up gets a note instead of failing the whole table.
func (a App) Table(ctx context.Context) ([]Row, error) {
	_, d, err := a.load()
	if err != nil {
		return nil, err
	}
	trees := map[string]map[string]string{} // repo -> dir -> sha, at HEAD
	var rows []Row
	for _, it := range d.Items {
		r := Row{Kind: it.Kind, Name: it.Name, Current: it.Current}
		switch it.Kind {
		case Marketplace, EGM:
			latest, err := a.Releases.Latest(ctx, it.Repo)
			r.Latest, r.Newer, r.Note = latest, err == nil && latest != it.Current, errNote(err)
		case PiPackage:
			latest, _, err := a.Registry.Versions(ctx, it.Name)
			r.Latest, r.Note = latest, errNote(err)
			if it.Current == "" {
				r.Current = "unpinned"
			} else {
				r.Newer = err == nil && latest != it.Current
			}
		case Skill:
			dirs, ok := trees[it.Repo]
			if !ok {
				dirs, err = a.dirSHAs(ctx, it.Repo)
				if err != nil {
					r.Note = errNote(err)
				}
				trees[it.Repo] = dirs
			}
			sha, found := dirs[SkillDir(it)]
			r.Current, r.Latest = short(it.Current), short(sha)
			switch {
			case r.Note != "":
			case !found:
				r.Note = "not found upstream"
			case len(it.Current) != 40:
				r.Note = "declared hash is not a git tree SHA"
			default:
				r.Newer = sha != it.Current
			}
		}
		rows = append(rows, r)
	}
	return rows, nil
}

func (a App) dirSHAs(ctx context.Context, repo string) (map[string]string, error) {
	tree, err := a.Releases.Tree(ctx, repo, "HEAD")
	if err != nil {
		return nil, err
	}
	dirs := map[string]string{}
	for _, e := range tree {
		if e.Dir {
			dirs[e.Path] = e.SHA
		}
	}
	return dirs, nil
}

func errNote(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

func shown(v string) string {
	if v == "" {
		return "unpinned"
	}
	return v
}

func short(sha string) string {
	if len(sha) > 12 {
		return sha[:12]
	}
	return sha
}
