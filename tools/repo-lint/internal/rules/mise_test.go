package rules

import (
	"strings"
	"testing"
)

const (
	linuxX64Sum   = "sha256:7a121264f2637a3b90767aaf5bdd43ee88b8c925a931d0479fa2ce22b1a2fa76"
	linuxArm64Sum = "sha256:5763332bdcb432c19ee122545856fd350c3bb306753212deedcfccc76f4d20c3"
	macSum        = "sha256:ec350e9e8e9ceb49ccd2cb7fcdc69f3b6a424f83dbae64f3dc6499157a5eca07"
	mqSum         = "sha256:1c08db356c9c4231df449d634f25802799b5f6ca92a7a3ef1c5c7fc682306464"
)

// host is a config/mise/config.toml that every mise rule accepts.
func host() map[string]any {
	aws := map[string]any{
		"version":           "2.39.6",
		"os":                []any{"macos/x64", "macos/arm64", "linux/x64", "linux/arm64"},
		"shared_extraction": "false",
		"bin":               "aws",
		"postinstall":       "check " + strings.TrimPrefix(macSum, "sha256:"),
		"platforms": map[string]any{
			"linux-x64":   map[string]any{"url": "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-2.39.6.zip", "checksum": linuxX64Sum, "format": "zip", "bin_path": "aws/dist"},
			"linux-arm64": map[string]any{"url": "https://awscli.amazonaws.com/awscli-exe-linux-aarch64-2.39.6.zip", "checksum": linuxArm64Sum, "format": "zip", "bin_path": "aws/dist"},
			"macos-x64":   map[string]any{"url": "https://awscli.amazonaws.com/AWSCLIV2-2.39.6.pkg", "checksum": macSum, "format": "raw", "bin_path": "payload"},
			"macos-arm64": map[string]any{"url": "https://awscli.amazonaws.com/AWSCLIV2-2.39.6.pkg", "checksum": macSum, "format": "raw", "bin_path": "payload"},
		},
	}
	mqPlatforms := map[string]any{}
	for platform, asset := range mqAssets {
		mqPlatforms[platform] = map[string]any{"asset_pattern": asset, "checksum": mqSum}
	}
	return map[string]any{
		"settings": map[string]any{
			"minimum_release_age": "0d",
			"npm":                 map[string]any{"package_manager": "bun"},
			"upgrade":             map[string]any{"auto_prune": false},
		},
		"env": map[string]any{"RTK_TELEMETRY_DISABLED": "1", "HEADROOM_BEACON": "off", "DO_NOT_TRACK": "1"},
		"tools": map[string]any{
			"rtk":                            "latest",
			"pypi:headroom-ai":               map[string]any{"version": "0.41.0", "extras": "proxy,code"},
			"http:aws":                       aws,
			"github:harehare/mq":             map[string]any{"version": "0.10.1", "os": []any{"macos/arm64", "linux/x64", "linux/arm64", "windows/x64", "windows/arm64"}, "rename_exe": "mq", "platforms": mqPlatforms},
			"just":                           "latest",
			"uv":                             "latest",
			"npm:typescript-language-server": "latest",
			"go:golang.org/x/tools/gopls":    "latest",
			"npm:@devcontainers/cli":         map[string]any{"version": "0.90.0", "bun_args": "--minimum-release-age=0"},
			"npm:@playwright/cli":            map[string]any{"version": "latest", "bun_args": "--minimum-release-age=0"},
			"bun":                            "latest",
			"go":                             "latest",
			"node":                           "lts",
			"rust":                           map[string]any{"version": "1.99.1"},
		},
	}
}

// image is a config/mise/image-tools.toml that every mise rule accepts.
func image() map[string]any {
	return map[string]any{
		"bootstrap": map[string]any{"mise": "2026.10.17"},
		"tools": map[string]any{
			"npm:@devcontainers/cli":      map[string]any{"version": "0.90.0", "bun_args": "--minimum-release-age=0"},
			"pypi:podman-compose":         map[string]any{"version": "1.6.0", "uvx_args": "--python 3.13 --exclude-newer 0d"},
			"go":                          "1.27.4",
			"aqua:golangci/golangci-lint": "2.15.0",
			"bun":                         "1.4.4",
			"uv":                          "0.13.9",
			"node":                        "24.22.3",
		},
	}
}

func miseInputs() Inputs {
	return Inputs{hostConfig: host(), imageConfig: image()}
}

func set(v any, value any, keys ...string) {
	t := v.(map[string]any)
	for _, k := range keys[:len(keys)-1] {
		t = t[k].(map[string]any)
	}
	if value == nil {
		delete(t, keys[len(keys)-1])
		return
	}
	t[keys[len(keys)-1]] = value
}

func findingsOf(t *testing.T, r Rule, in Inputs) []Finding {
	t.Helper()
	for _, input := range r.Inputs {
		if _, ok := in[input.Path]; !ok {
			t.Fatalf("%s reads %s, which the test does not give", r.ID, input.Path)
		}
	}
	return r.Check(in)
}

type miseCase struct {
	name   string
	file   string // hostConfig or imageConfig
	value  any    // nil deletes the key
	keys   []string
	expect string // a part of the finding's message
}

func runMiseCases(t *testing.T, r Rule, cases []miseCase) {
	t.Helper()
	if got := findingsOf(t, r, miseInputs()); len(got) != 0 {
		t.Fatalf("%s rejects the accepted config: %v", r.ID, got)
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			in := miseInputs()
			set(in[c.file], c.value, c.keys...)
			got := findingsOf(t, r, in)
			if len(got) == 0 {
				t.Fatalf("%s accepted %s", r.ID, c.name)
			}
			var joined strings.Builder
			for _, f := range got {
				if f.Rule != r.ID {
					t.Errorf("finding names rule %q, want %q", f.Rule, r.ID)
				}
				joined.WriteString(f.Message + "\n")
			}
			if !strings.Contains(joined.String(), c.expect) {
				t.Errorf("findings %q do not mention %q", joined.String(), c.expect)
			}
		})
	}
}

func TestMiseAgentToolsRunOnEveryOS(t *testing.T) {
	runMiseCases(t, miseAgentTools(), []miseCase{
		{"rtk missing", hostConfig, nil, []string{"tools", "rtk"}, "rtk"},
		{"headroom missing", hostConfig, nil, []string{"tools", "pypi:headroom-ai"}, "pypi:headroom-ai"},
		{"headroom without the proxy extra", hostConfig, "code", []string{"tools", "pypi:headroom-ai", "extras"}, "proxy"},
		{"rtk limited to some OSes", hostConfig, map[string]any{"version": "latest", "os": []any{"macos/arm64"}}, []string{"tools", "rtk"}, "os"},
		{"headroom limited to some OSes", hostConfig, []any{"linux/x64"}, []string{"tools", "pypi:headroom-ai", "os"}, "os"},
	})
}

func TestMiseAWSCLIIsTheVerifiedOfficialRelease(t *testing.T) {
	aws := []string{"tools", "http:aws"}
	p := func(platform, key string) []string {
		return append(append([]string{}, aws...), "platforms", platform, key)
	}
	runMiseCases(t, miseAWSCLI(), []miseCase{
		{"windows target", hostConfig, []any{"macos/x64", "macos/arm64", "linux/x64", "linux/arm64", "windows/x64"}, append(append([]string{}, aws...), "os"), "os"},
		{"shared extraction", hostConfig, "true", append(append([]string{}, aws...), "shared_extraction"), "shared_extraction"},
		{"template in postinstall", hostConfig, "{{ tools }} " + strings.TrimPrefix(macSum, "sha256:"), append(append([]string{}, aws...), "postinstall"), "{{"},
		{"postinstall without the macOS checksum", hostConfig, "true", append(append([]string{}, aws...), "postinstall"), "postinstall"},
		{"another binary", hostConfig, "aws2", append(append([]string{}, aws...), "bin"), "bin"},
		{"unofficial host", hostConfig, "https://example.com/awscli-exe-linux-x86_64-2.39.6.zip", p("linux-x64", "url"), "url"},
		{"x64 points at the arm archive", hostConfig, "https://awscli.amazonaws.com/awscli-exe-linux-aarch64-2.39.6.zip", p("linux-x64", "url"), "url"},
		{"url of another version", hostConfig, "https://awscli.amazonaws.com/AWSCLIV2-2.39.5.pkg", p("macos-arm64", "url"), "url"},
		{"no checksum", hostConfig, nil, p("linux-arm64", "checksum"), "checksum"},
		{"md5 checksum", hostConfig, "md5:0123", p("linux-arm64", "checksum"), "checksum"},
		{"linux checksums equal", hostConfig, linuxX64Sum, p("linux-arm64", "checksum"), "differ"},
		{"macOS checksums differ", hostConfig, linuxX64Sum, p("macos-x64", "checksum"), "equal"},
		{"linux not a zip", hostConfig, "raw", p("linux-x64", "format"), "format"},
		{"linux bin path", hostConfig, "aws", p("linux-x64", "bin_path"), "bin_path"},
		{"macOS format", hostConfig, "zip", p("macos-x64", "format"), "format"},
		{"macOS bin path", hostConfig, "aws/dist", p("macos-arm64", "bin_path"), "bin_path"},
		{"a platform missing", hostConfig, nil, p("macos-x64", "url")[:5], "macos-x64"},
	})
}

func TestMiseMQAssetsArePinnedPerPlatform(t *testing.T) {
	mq := []string{"tools", "github:harehare/mq"}
	k := func(rest ...string) []string { return append(append([]string{}, mq...), rest...) }
	runMiseCases(t, miseMQ(), []miseCase{
		{"a target dropped", hostConfig, []any{"macos/arm64", "linux/x64", "linux/arm64", "windows/x64"}, k("os"), "os"},
		{"a platform missing", hostConfig, nil, k("platforms", "windows-arm64"), "windows-arm64"},
		{"a platform for no target", hostConfig, map[string]any{"asset_pattern": "mq-x86_64-apple-darwin", "checksum": mqSum}, k("platforms", "macos-x64"), "macos-x64"},
		{"templated asset", hostConfig, "mq-{{ arch() }}-unknown-linux-gnu", k("platforms", "linux-x64", "asset_pattern"), "asset_pattern"},
		{"no checksum", hostConfig, nil, k("platforms", "linux-arm64", "checksum"), "checksum"},
		{"short checksum", hostConfig, "sha256:1234", k("platforms", "linux-arm64", "checksum"), "checksum"},
		{"renamed executable", hostConfig, "mq-cli", k("rename_exe"), "rename_exe"},
	})
}

func TestMiseHostSettingsKeepTheCooldownAndTelemetryOff(t *testing.T) {
	runMiseCases(t, miseHostSettings(), []miseCase{
		{"release age set", hostConfig, "7d", []string{"settings", "minimum_release_age"}, "minimum_release_age"},
		{"npm backend auto", hostConfig, "auto", []string{"settings", "npm", "package_manager"}, "package_manager"},
		{"just pinned", hostConfig, "1.59.0", []string{"tools", "just"}, "just"},
		{"uv pinned", hostConfig, "0.13.9", []string{"tools", "uv"}, "uv"},
		{"typescript language server pinned", hostConfig, "5.0.0", []string{"tools", "npm:typescript-language-server"}, "typescript-language-server"},
		{"gopls missing", hostConfig, nil, []string{"tools", "go:golang.org/x/tools/gopls"}, "gopls"},
		{"telemetry back on", hostConfig, nil, []string{"env", "DO_NOT_TRACK"}, "env"},
		{"cooldown variable", hostConfig, "7 days", []string{"env", "UV_EXCLUDE_NEWER"}, "env"},
		{"ignored config paths", hostConfig, []any{"/mnt/c/Users"}, []string{"settings", "ignored_config_paths"}, "ignored_config_paths"},
		{"auto prune back on", hostConfig, true, []string{"settings", "upgrade", "auto_prune"}, "auto_prune"},
		{"auto prune left to the default", hostConfig, nil, []string{"settings", "upgrade"}, "auto_prune"},
	})
}

func TestMiseAgeExemptPinsMatchAndStayExempt(t *testing.T) {
	cli := []string{"tools", "npm:@devcontainers/cli"}
	k := func(base []string, rest ...string) []string { return append(append([]string{}, base...), rest...) }
	compose := []string{"tools", "pypi:podman-compose"}
	runMiseCases(t, miseAgeExemptPins(), []miseCase{
		{"host and image differ", imageConfig, "0.91.0", k(cli, "version"), "version"},
		{"host cli unpinned", hostConfig, "latest", k(cli, "version"), "version"},
		{"host cli not exempt", hostConfig, nil, k(cli, "bun_args"), "bun_args"},
		{"image cli another flag", imageConfig, "--minimum-release-age=1", k(cli, "bun_args"), "bun_args"},
		{"image cli an extra key", imageConfig, "x", k(cli, "postinstall"), "postinstall"},
		{"compose missing", imageConfig, nil, compose, "pypi:podman-compose"},
		{"compose unpinned", imageConfig, "latest", k(compose, "version"), "version"},
		{"compose not exempt", imageConfig, "--python 3.13", k(compose, "uvx_args"), "exclude-newer"},
	})
}

func TestMiseImageBakesGoAndGolangciLint(t *testing.T) {
	runMiseCases(t, miseImageBakesGoLint(), []miseCase{
		{"no go", imageConfig, nil, []string{"tools", "go"}, "go"},
		{"no golangci-lint", imageConfig, nil, []string{"tools", "aqua:golangci/golangci-lint"}, "golangci-lint"},
	})
}

func TestMisePlaywrightCLIVersionIsLatestOrExact(t *testing.T) {
	pw := []string{"tools", "npm:@playwright/cli"}
	runMiseCases(t, misePlaywrightCLIVersion(), []miseCase{
		{"missing", hostConfig, nil, pw, "npm:@playwright/cli"},
		{"range", hostConfig, "^0.1.0", append(append([]string{}, pw...), "version"), "version"},
		{"next channel", hostConfig, "next", append(append([]string{}, pw...), "version"), "version"},
		{"empty", hostConfig, "", append(append([]string{}, pw...), "version"), "version"},
		{"the test runner declared", hostConfig, "latest", []string{"tools", "npm:playwright"}, "npm:playwright"},
	})
	in := miseInputs()
	for _, ok := range []any{"0.1.2", "0.1.2-alpha.1", "latest", map[string]any{"version": "1.2.3"}} {
		set(in[hostConfig], ok, "tools", "npm:@playwright/cli")
		if got := misePlaywrightCLIVersion().Check(in); len(got) != 0 {
			t.Errorf("rejects %v: %v", ok, got)
		}
	}
}
