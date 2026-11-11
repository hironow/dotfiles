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
		return errors.Join(
			h.just(ctx, "claude-plugins-install", "--check"),
			h.uv(ctx, bump.PiInstaller, "--verify-egm"),
		)
	case bump.PiPackage:
		return piInstalled(it.Source, it.Name, it.Current)
	case bump.Skill:
	}
	return nil
}

func (h host) Install(ctx context.Context, it bump.Item, t bump.Target) error {
	switch it.Kind {
	case bump.Marketplace:
		return h.just(ctx, "claude-plugins-install")
	case bump.EGM:
		return h.just(ctx, "egm-install-native")
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
		return errors.Join(
			h.just(ctx, "claude-plugins-install", "--check"),
			h.uv(ctx, bump.PiInstaller, "--verify-egm"),
			codexEGMAt(ctx, t.Commit),
		)
	case bump.PiPackage:
		source := "npm:" + it.Name
		if t.Version != "" {
			source += "@" + t.Version
		}
		return piInstalled(source, it.Name, t.Version)
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

// piInstalled checks Pi's settings name the source and, for a pin, that the
// installed package.json carries that version.
func piInstalled(source, name, version string) error {
	dir := piAgentDir()
	raw, err := os.ReadFile(filepath.Join(dir, "settings.json"))
	if err != nil {
		return err
	}
	var settings struct {
		Packages []any `json:"packages"`
	}
	if err := json.Unmarshal(raw, &settings); err != nil {
		return fmt.Errorf("pi settings.json: %w", err)
	}
	var sources []string
	for _, p := range settings.Packages {
		switch v := p.(type) {
		case string:
			sources = append(sources, v)
		case map[string]any:
			if s, ok := v["source"].(string); ok {
				sources = append(sources, s)
			}
		}
	}
	if !slices.Contains(sources, source) {
		return fmt.Errorf("pi settings.json does not name %s", source)
	}
	manifest, err := os.ReadFile(filepath.Join(dir, "npm", "node_modules", filepath.FromSlash(name), "package.json"))
	if err != nil {
		return fmt.Errorf("pi has no files for %s: %w", name, err)
	}
	var pkg struct {
		Version string `json:"version"`
	}
	if err := json.Unmarshal(manifest, &pkg); err != nil {
		return fmt.Errorf("%s package.json: %w", name, err)
	}
	if version != "" && pkg.Version != version {
		return fmt.Errorf("pi has %s %s, want %s", name, pkg.Version, version)
	}
	return nil
}

// codexEGMAt checks Codex's EGM marketplace checkout is at the commit.
func codexEGMAt(ctx context.Context, commit string) error {
	out, err := exec.CommandContext(ctx, "codex", "plugin", "marketplace", "list", "--json").Output()
	if err != nil {
		return fmt.Errorf("codex plugin marketplace list: %w", err)
	}
	var list struct {
		Marketplaces []struct {
			Name string `json:"name"`
			Root string `json:"root"`
		} `json:"marketplaces"`
	}
	if err := json.Unmarshal(out, &list); err != nil {
		return fmt.Errorf("codex plugin marketplace list: %w", err)
	}
	for _, m := range list.Marketplaces {
		if m.Name != "egm" {
			continue
		}
		// G204: the root is the checkout Codex itself reported, passed as one argv entry.
		head, err := exec.CommandContext(ctx, "git", "-C", m.Root, "rev-parse", "HEAD").Output() //nolint:gosec // G204: audited above
		if err != nil {
			return fmt.Errorf("codex egm checkout: %w", err)
		}
		if got := strings.TrimSpace(string(head)); got != commit {
			return fmt.Errorf("codex egm is at %s, want %s", got, commit)
		}
		return nil
	}
	return errors.New("codex has no egm marketplace")
}
