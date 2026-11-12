package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-bump/internal/bump"
)

// host is the Machine adapter: it runs the repo's own installers and checks,
// so a bump installs exactly what `just deploy` would.
type host struct {
	root     string
	out, err io.Writer
}

// Each program has its own helper, so every command name is a constant.
func (h host) just(ctx context.Context, args ...string) error {
	return h.run(exec.CommandContext(ctx, "just", args...))
}

// uv runs a repo script with the same interpreter the justfile's UV_RUN uses.
func (h host) uv(ctx context.Context, args ...string) error {
	// G204: args are this program's constants and a name Resolve matched to the declarations.
	return h.run(exec.CommandContext(ctx, "mise", append([]string{"exec", "--", "uv", "run", "--frozen"}, args...)...)) //nolint:gosec // G204: audited above
}

func (h host) pi(ctx context.Context, args ...string) error {
	return h.run(exec.CommandContext(ctx, "pi", args...))
}

func (h host) run(cmd *exec.Cmd) error {
	line := strings.Join(cmd.Args, " ")
	fmt.Fprintf(h.out, "==> %s\n", line)
	cmd.Dir, cmd.Stdout, cmd.Stderr = h.root, h.out, h.err
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("%s: %w", line, err)
	}
	return nil
}

func (h host) Baseline(ctx context.Context, it bump.Item) error {
	switch it.Kind {
	case bump.Marketplace:
		return h.just(ctx, "claude-plugins-install", "--check")
	case bump.EGM:
		return errors.Join(h.egmChecks(ctx), h.piDeclarationInstalled())
	case bump.PiPackage:
		return h.piDeclarationInstalled()
	case bump.Skill:
	}
	return nil
}

func (h host) Install(ctx context.Context, it bump.Item, t bump.Target) error {
	switch it.Kind {
	case bump.Marketplace:
		return h.just(ctx, "claude-plugins-install")
	case bump.EGM:
		// The same installers `just deploy` runs, in its order: Pi (the
		// bundle), Codex and Antigravity (they follow the Pi pin), Claude.
		return errors.Join(
			h.uv(ctx, bump.PiInstaller),
			h.uv(ctx, codexAgyStep),
			h.just(ctx, "claude-plugins-install"),
		)
	case bump.PiPackage:
		// The installer swaps a changed pin; `pi update` moves an unpinned
		// package to the newest version, which the installer never does.
		if err := h.uv(ctx, bump.PiInstaller); err != nil {
			return err
		}
		if t.Version == "" {
			return h.pi(ctx, "update", "--extension", "npm:"+it.Name)
		}
	case bump.Skill:
		return h.just(ctx, "skills-update", "--only", it.Name)
	}
	return nil
}

func (h host) Verify(ctx context.Context, it bump.Item, t bump.Target) error {
	switch it.Kind {
	case bump.Marketplace:
		return h.just(ctx, "claude-plugins-install", "--check")
	case bump.EGM:
		return h.egmChecks(ctx)
	case bump.PiPackage:
		source := "npm:" + it.Name
		if t.Version != "" {
			source += "@" + t.Version
		}
		return piInstalled(source)
	case bump.Skill:
	}
	return nil
}

func (h host) EGMRequiredPaths(ctx context.Context) ([]string, error) {
	cmd := exec.CommandContext(ctx, "mise", "exec", "--", "uv", "run", "--frozen", bump.PiInstaller, "--egm-required-paths") //nolint:gosec // G204: constants only
	cmd.Dir, cmd.Stderr = h.root, h.err
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("%s --egm-required-paths: %w", bump.PiInstaller, err)
	}
	return strings.Fields(string(bytes.ReplaceAll(out, []byte("\r"), nil))), nil
}

func piAgentDir() string {
	if dir := os.Getenv("PI_CODING_AGENT_DIR"); dir != "" {
		return dir
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".pi", "agent")
}

// piProblems lists what this machine lacks of the declared Pi npm sources:
// a source Pi's settings do not name, a package with no files, or a pinned
// version that differs. Git sources (EGM) are checked by --verify-egm.
func piProblems(declared, configured []string, installed map[string]string) []string {
	var problems []string
	for _, source := range declared {
		name, pin, isNpm := bump.NpmName(source)
		if !isNpm {
			continue
		}
		version, has := installed[name]
		switch {
		case !slices.Contains(configured, source):
			problems = append(problems, "pi settings.json does not name "+source)
		case !has:
			problems = append(problems, "pi has no files for "+name)
		case pin != "" && version != pin:
			problems = append(problems, fmt.Sprintf("pi has %s %s, want %s", name, version, pin))
		}
	}
	return problems
}

// piState reads Pi's configured sources and the installed version of each
// named package (a package without files is absent from the map).
func piState(names []string) ([]string, map[string]string, error) {
	dir := piAgentDir()
	raw, err := os.ReadFile(filepath.Join(dir, "settings.json"))
	if err != nil {
		return nil, nil, err
	}
	var settings struct {
		Packages []any `json:"packages"`
	}
	if err := json.Unmarshal(raw, &settings); err != nil {
		return nil, nil, fmt.Errorf("pi settings.json: %w", err)
	}
	var configured []string
	for _, p := range settings.Packages {
		switch v := p.(type) {
		case string:
			configured = append(configured, v)
		case map[string]any:
			if s, ok := v["source"].(string); ok {
				configured = append(configured, s)
			}
		}
	}
	installed := map[string]string{}
	for _, name := range names {
		manifest, err := os.ReadFile(filepath.Join(dir, "npm", "node_modules", filepath.FromSlash(name), "package.json"))
		if err != nil {
			continue
		}
		var pkg struct {
			Version string `json:"version"`
		}
		if err := json.Unmarshal(manifest, &pkg); err != nil {
			return nil, nil, fmt.Errorf("%s package.json: %w", name, err)
		}
		installed[name] = pkg.Version
	}
	return configured, installed, nil
}

// piInstalled checks this machine has the given Pi sources.
func piInstalled(sources ...string) error {
	var names []string
	for _, s := range sources {
		if name, _, ok := bump.NpmName(s); ok {
			names = append(names, name)
		}
	}
	configured, installed, err := piState(names)
	if err != nil {
		return err
	}
	if problems := piProblems(sources, configured, installed); len(problems) > 0 {
		return errors.New(strings.Join(problems, "; "))
	}
	return nil
}

// piDeclarationInstalled checks every npm source in pi-packages.json, not
// just the one a bump moves: the Pi installer installs every declared
// source, so an uncommitted, not yet installed hand edit would ride along.
func (h host) piDeclarationInstalled() error {
	raw, err := os.ReadFile(filepath.Join(h.root, filepath.FromSlash(bump.PiPackages)))
	if err != nil {
		return err
	}
	var declared []string
	if err := json.Unmarshal(raw, &declared); err != nil {
		return fmt.Errorf("%s: %w", bump.PiPackages, err)
	}
	if err := piInstalled(declared...); err != nil {
		return fmt.Errorf("%w (an edit in %s that is not installed yet would also be installed; install or revert it first)", err, bump.PiPackages)
	}
	return nil
}

// codexAgyStep is the deploy step that gives Codex and Antigravity EGM.
const codexAgyStep = "scripts/codex_agy_plugins.py"

// egmChecks are the EGM checks of every agent that can report: Claude,
// the Pi bundle, and Codex (skipped where Codex is not installed).
func (h host) egmChecks(ctx context.Context) error {
	return errors.Join(
		h.just(ctx, "claude-plugins-install", "--check"),
		h.uv(ctx, bump.PiInstaller, "--verify-egm"),
		h.uv(ctx, codexAgyStep, "--check"),
	)
}
