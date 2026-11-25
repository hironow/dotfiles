package rules

import (
	"maps"
	"regexp"
	"slices"
	"strings"
)

const (
	hostConfig  = "config/mise/config.toml"
	imageConfig = "config/mise/image-tools.toml"
)

var (
	exactVersion = regexp.MustCompile(`^\d+\.\d+\.\d+$`)
	sha256Sum    = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
)

// mqAssets is the release asset of mq for each platform mise installs it on.
// Explicit assets keep the os()/arch() templates out (they expand for the host
// and lock the wrong asset for the others) and leave out mq's helper CLIs.
var mqAssets = map[string]string{
	"macos-arm64":   "mq-aarch64-apple-darwin",
	"linux-x64":     "mq-x86_64-unknown-linux-gnu",
	"linux-arm64":   "mq-aarch64-unknown-linux-gnu",
	"windows-x64":   "mq-x86_64-pc-windows-msvc.exe",
	"windows-arm64": "mq-aarch64-pc-windows-msvc.exe",
}

func hostTool(in Inputs, name string) (any, bool) {
	return at(in[hostConfig], "tools", name)
}

// miseAgentTools: rtk filters command output and headroom's proxy compresses
// what reaches the model in every agent session, so both are installed on
// every OS (ADR 0047), headroom with its `proxy` extra.
func miseAgentTools() Rule {
	return Rule{
		ID:     "mise-agent-tools-on-every-os",
		Why:    "rtk and headroom (with its proxy) run in every agent session, on every OS (ADR 0047)",
		Inputs: []Input{{hostConfig, TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: "mise-agent-tools-on-every-os", path: hostConfig}
			for _, name := range []string{"rtk", "pypi:headroom-ai"} {
				spec, ok := hostTool(in, name)
				if !ok {
					r.add("[tools] must declare %s", name)
					continue
				}
				if _, gated := at(spec, "os"); gated {
					r.add("%s must not be limited by `os`: every OS runs it", name)
				}
			}
			if spec, ok := hostTool(in, "pypi:headroom-ai"); ok {
				extras, _ := str(spec, "extras")
				if !slices.Contains(strings.Split(extras, ","), "proxy") {
					r.add("pypi:headroom-ai must install its `proxy` extra (extras = %q)", extras)
				}
			}
			return r.out
		},
	}
}

// miseAWSCLI: the AWS CLI comes from AWS's own host as the archive for each
// CPU, checked against a pinned SHA-256, and no install script runs.
func miseAWSCLI() Rule {
	const id = "mise-aws-cli-verified"
	return Rule{
		ID:     id,
		Why:    "the AWS CLI is AWS's official archive per CPU, checksum-pinned, with no install script",
		Inputs: []Input{{hostConfig, TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: hostConfig}
			spec, ok := hostTool(in, "http:aws")
			if !ok {
				r.add("[tools] must declare http:aws")
				return r.out
			}
			ver, _ := str(spec, "version")
			if !exactVersion.MatchString(ver) {
				r.add("http:aws version %q must be an exact x.y.z", ver)
			}
			if osList := strs(spec, "os"); !sameSet(osList, []string{"macos/x64", "macos/arm64", "linux/x64", "linux/arm64"}) {
				r.add("http:aws os must be the four macOS and Linux targets, got %v", osList)
			}
			if v, _ := str(spec, "shared_extraction"); v != "false" {
				r.add("http:aws shared_extraction must be \"false\", got %q", v)
			}
			if v, _ := str(spec, "bin"); v != "aws" {
				r.add("http:aws bin must be \"aws\", got %q", v)
			}
			post, _ := str(spec, "postinstall")
			if strings.Contains(post, "{{") {
				r.add("http:aws postinstall must not hold a {{ }} template: the tools context is not there")
			}
			want := map[string]struct{ url, format, binPath string }{
				"linux-x64":   {"https://awscli.amazonaws.com/awscli-exe-linux-x86_64-" + ver + ".zip", "zip", "aws/dist"},
				"linux-arm64": {"https://awscli.amazonaws.com/awscli-exe-linux-aarch64-" + ver + ".zip", "zip", "aws/dist"},
				"macos-x64":   {"https://awscli.amazonaws.com/AWSCLIV2-" + ver + ".pkg", "raw", "payload"},
				"macos-arm64": {"https://awscli.amazonaws.com/AWSCLIV2-" + ver + ".pkg", "raw", "payload"},
			}
			sums := map[string]string{}
			for _, platform := range slices.Sorted(maps.Keys(want)) {
				w := want[platform]
				opts, ok := table(spec, "platforms", platform)
				if !ok {
					r.add("http:aws must declare platforms.%s", platform)
					continue
				}
				if v, _ := str(opts, "url"); v != w.url {
					r.add("http:aws %s url must be %s, got %q", platform, w.url, v)
				}
				sum, _ := str(opts, "checksum")
				if !sha256Sum.MatchString(sum) {
					r.add("http:aws %s checksum must be sha256:<64 hex>, got %q", platform, sum)
				}
				sums[platform] = sum
				if v, _ := str(opts, "format"); v != w.format {
					r.add("http:aws %s format must be %q, got %q", platform, w.format, v)
				}
				if v, _ := str(opts, "bin_path"); v != w.binPath {
					r.add("http:aws %s bin_path must be %q, got %q", platform, w.binPath, v)
				}
			}
			if sums["linux-x64"] != "" && sums["linux-x64"] == sums["linux-arm64"] {
				r.add("http:aws linux-x64 and linux-arm64 checksums must differ: they are two archives")
			}
			if sums["macos-x64"] != sums["macos-arm64"] {
				r.add("http:aws macos-x64 and macos-arm64 checksums must be equal: they are one universal package")
			}
			if mac := strings.TrimPrefix(sums["macos-arm64"], "sha256:"); mac == "" || !strings.Contains(post, mac) {
				r.add("http:aws postinstall must check the macOS package against its checksum")
			}
			return r.out
		},
	}
}

func miseMQ() Rule {
	const id = "mise-mq-checksummed"
	return Rule{
		ID:     id,
		Why:    "mq installs one explicit, checksum-pinned asset per platform",
		Inputs: []Input{{hostConfig, TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: hostConfig}
			spec, ok := hostTool(in, "github:harehare/mq")
			if !ok {
				r.add("[tools] must declare github:harehare/mq")
				return r.out
			}
			targets := make([]string, 0, len(mqAssets))
			for platform := range mqAssets {
				targets = append(targets, strings.Replace(platform, "-", "/", 1))
			}
			if osList := strs(spec, "os"); !sameSet(osList, targets) {
				r.add("github:harehare/mq os must be %v, got %v", slices.Sorted(slices.Values(targets)), osList)
			}
			if v, _ := str(spec, "rename_exe"); v != "mq" {
				r.add("github:harehare/mq rename_exe must be \"mq\", got %q", v)
			}
			platforms, _ := table(spec, "platforms")
			for _, platform := range slices.Sorted(maps.Keys(platforms)) {
				if _, known := mqAssets[platform]; !known {
					r.add("github:harehare/mq platforms.%s is not one of its targets", platform)
				}
			}
			for _, platform := range slices.Sorted(maps.Keys(mqAssets)) {
				opts, ok := table(platforms, platform)
				if !ok {
					r.add("github:harehare/mq must declare platforms.%s", platform)
					continue
				}
				if v, _ := str(opts, "asset_pattern"); v != mqAssets[platform] {
					r.add("github:harehare/mq %s asset_pattern must be %q, got %q", platform, mqAssets[platform], v)
				}
				if v, _ := str(opts, "checksum"); !sha256Sum.MatchString(v) {
					r.add("github:harehare/mq %s checksum must be sha256:<64 hex>, got %q", platform, v)
				}
			}
			return r.out
		},
	}
}

// telemetryOff is the whole [env] of the host config: the agent tools'
// telemetry stays off, and no cooldown variable comes back.
var telemetryOff = map[string]any{"RTK_TELEMETRY_DISABLED": "1", "HEADROOM_BEACON": "off", "DO_NOT_TRACK": "1"}

func miseHostSettings() Rule {
	const id = "mise-host-settings"
	return Rule{
		ID:     id,
		Why:    "the host keeps mise's own cooldown off, installs npm tools with bun, tracks the newest release, and turns telemetry off",
		Inputs: []Input{{hostConfig, TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: hostConfig}
			cfg := in[hostConfig]
			if v, _ := str(cfg, "settings", "minimum_release_age"); v != "0d" {
				r.add("settings.minimum_release_age must be \"0d\" (the cooldown lives in uv and bun), got %q", v)
			}
			// npm's default `auto` installs claude-code as a 500-byte stub (ADR 0036).
			if v, _ := str(cfg, "settings", "npm", "package_manager"); v != "bun" {
				r.add("settings.npm.package_manager must be \"bun\", got %q", v)
			}
			for _, name := range []string{"just", "uv", "npm:typescript-language-server", "go:golang.org/x/tools/gopls"} {
				if v, _ := hostTool(in, name); v != "latest" {
					r.add("tool %s must be \"latest\", got %v", name, v)
				}
			}
			env, _ := table(cfg, "env")
			if !maps.Equal(env, telemetryOff) {
				r.add("[env] must be exactly %v, got %v", telemetryOff, env)
			}
			// mise reads this setting only after it has found the configs, so it
			// never ignores a Windows home's config from WSL; .zshrc sets
			// MISE_IGNORED_CONFIG_PATHS instead.
			if _, ok := at(cfg, "settings", "ignored_config_paths"); ok {
				r.add("settings.ignored_config_paths has no effect here; .zshrc sets MISE_IGNORED_CONFIG_PATHS")
			}
			// The default true queues a prune a day after each `mise up`; on
			// Windows a running tool cannot be removed, so every new terminal
			// warned. `just disk-gc` prunes on demand instead.
			if v, ok := at(cfg, "settings", "upgrade", "auto_prune"); !ok || v != false {
				r.add("settings.upgrade.auto_prune must be false (just disk-gc prunes on demand), got %v", v)
			}
			return r.out
		},
	}
}

func miseAgeExemptPins() Rule {
	const id = "mise-age-exempt-pins"
	return Rule{
		ID:     id,
		Why:    "the tools that skip the release-age cooldown are exact pins, the same on host and image",
		Inputs: []Input{{hostConfig, TOML}, {imageConfig, TOML}},
		Check: func(in Inputs) []Finding {
			var out []Finding
			const cli = "npm:@devcontainers/cli"
			var versions []string
			for _, path := range []string{hostConfig, imageConfig} {
				r := &report{rule: id, path: path}
				spec, ok := table(in[path], "tools", cli)
				if !ok {
					r.add("[tools] must declare %s as a table with version and bun_args", cli)
					out = append(out, r.out...)
					continue
				}
				for key := range spec {
					if key != "version" && key != "bun_args" {
						r.add("%s holds only version and bun_args, not %s", cli, key)
					}
				}
				v, _ := str(spec, "version")
				if !exactVersion.MatchString(v) {
					r.add("%s version must be an exact x.y.z, got %q", cli, v)
				}
				versions = append(versions, v)
				if b, _ := str(spec, "bun_args"); b != "--minimum-release-age=0" {
					r.add("%s bun_args must be \"--minimum-release-age=0\", got %q", cli, b)
				}
				out = append(out, r.out...)
			}
			if len(versions) == 2 && versions[0] != versions[1] {
				r := &report{rule: id, path: imageConfig}
				r.add("%s version %q must equal the host's %q", cli, versions[1], versions[0])
				out = append(out, r.out...)
			}
			r := &report{rule: id, path: imageConfig}
			const compose = "pypi:podman-compose"
			if spec, ok := table(in[imageConfig], "tools", compose); !ok {
				r.add("[tools] must declare %s", compose)
			} else {
				if v, _ := str(spec, "version"); !exactVersion.MatchString(v) {
					r.add("%s version must be an exact x.y.z, got %q", compose, v)
				}
				if v, _ := str(spec, "uvx_args"); !strings.Contains(v, "--exclude-newer 0d") {
					r.add("%s uvx_args must hold --exclude-newer 0d, got %q", compose, v)
				}
			}
			return append(out, r.out...)
		},
	}
}

func miseImageBakesGoLint() Rule {
	const id = "mise-image-bakes-go-lint"
	return Rule{
		ID:     id,
		Why:    "the image bakes Go and golangci-lint, so `just check` runs go-lint inside it",
		Inputs: []Input{{imageConfig, TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: imageConfig}
			for _, name := range []string{"go", "aqua:golangci/golangci-lint"} {
				if _, ok := at(in[imageConfig], "tools", name); !ok {
					r.add("[tools] must declare %s", name)
				}
			}
			return r.out
		},
	}
}

var playwrightVersion = regexp.MustCompile(`^(latest|\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?)$`)

func misePlaywrightCLIVersion() Rule {
	const id = "mise-playwright-cli-version"
	return Rule{
		ID:     id,
		Why:    "the playwright-cli skill runs `playwright-cli` from PATH; it is `latest` or an exact pin, never a range or `next`",
		Inputs: []Input{{hostConfig, TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: hostConfig}
			spec, ok := hostTool(in, "npm:@playwright/cli")
			if !ok {
				r.add("[tools] must declare npm:@playwright/cli")
				return r.out
			}
			if v := version(spec); !playwrightVersion.MatchString(v) {
				r.add("npm:@playwright/cli version must be latest or x.y.z, got %q", v)
			}
			// `playwright` is the test runner, which ships no playwright-cli.
			tools, _ := table(in[hostConfig], "tools")
			for _, name := range slices.Sorted(maps.Keys(tools)) {
				if name == "playwright" || strings.HasSuffix(name, ":playwright") {
					r.add("%s is the Playwright test runner, not playwright-cli; declare npm:@playwright/cli", name)
				}
			}
			return r.out
		},
	}
}
