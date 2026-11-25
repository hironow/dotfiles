package rules

import (
	"fmt"
	"maps"
	"regexp"
	"slices"
	"strings"
)

const (
	emuCompose       = "emulator/compose.yaml"
	emuEnvExample    = "emulator/.env.local.example"
	justfilePath     = "justfile"
	emuDockerfiles   = "emulator/*/Dockerfile"
	healthDockerfile = "emulator/healthcheck/Dockerfile"
)

var (
	groupsLine = regexp.MustCompile(`(?m)^# Groups: ([a-z ]+)\.$`)
	// publishedPort is a loopback host port in a Compose port mapping, fixed
	// or as the default of a variable.
	publishedPort = regexp.MustCompile(`^127\.0\.0\.1:(?:\$\{\w+:-(\d+)\}|(\d+)):\d+$`)
	envLocalhost  = regexp.MustCompile(`(?m)^export (\w+)=localhost:(\d+)\s*$`)
	goBuilder     = regexp.MustCompile(`^docker\.io/library/golang:(\S+?)-`)
	// continuation is a backslash that continues an instruction on the next
	// line.
	continuation = regexp.MustCompile(`\\[ \t]*\n`)
	// stageLine is a Dockerfile FROM line: its image and, with AS, the stage
	// name.
	stageLine    = regexp.MustCompile(`(?mi)^FROM[ \t]+(?:--platform=\S+[ \t]+)?(\S+)(?:[ \t]+AS[ \t]+(\S+))?[ \t]*$`)
	spannerImage = regexp.MustCompile(`^gcr\.io/cloud-spanner-emulator/emulator:\d+\.\d+\.\d+$`)
	// runtimeConfig is an instruction that changes the upstream image's
	// configuration.
	runtimeConfig = regexp.MustCompile(`(?mi)^(USER|ENTRYPOINT|CMD|WORKDIR|ENV|EXPOSE|VOLUME|HEALTHCHECK)\b`)
	pgadapterAdds = regexp.MustCompile(`apt-get\s+upgrade|postgresql-server|COPY|curl|wget`)
)

const (
	inspectorUI     = "127.0.0.1:${MCP_INSPECTOR_PORT:-6274}:6274"
	inspectorOrigin = "http://localhost:${MCP_INSPECTOR_PORT:-6274}"
	probeCopy       = "COPY --from=builder /tcp-healthcheck /usr/local/bin/tcp-healthcheck"
)

func services(compose any) map[string]any {
	s, _ := table(compose, "services")
	return s
}

// composeProfiles is every profile a service of the Compose file joins.
func composeProfiles(compose any) map[string]bool {
	out := map[string]bool{}
	for _, svc := range services(compose) {
		for _, p := range strs(svc, "profiles") {
			out[p] = true
		}
	}
	return out
}

// envList is a service's `KEY=value` environment list as a map.
func envList(svc map[string]any) map[string]string {
	out := map[string]string{}
	for _, item := range strs(svc, "environment") {
		k, v, _ := strings.Cut(item, "=")
		out[k] = v
	}
	return out
}

// emulatorGroups: `just emu-up-group` lists its groups in the justfile, and
// they are the Compose profiles except the `cli` tools.
func emulatorGroups() Rule {
	const id = "emulator-groups-documented"
	return Rule{
		ID:     id,
		Why:    "the justfile's `# Groups:` line of emu-up-group names every emulator Compose profile except `cli`",
		Inputs: []Input{{Path: justfilePath, Format: Text}, {Path: emuCompose, Format: YAML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			text, _ := in[justfilePath].(string)
			found := groupsLine.FindStringSubmatch(text)
			if found == nil {
				r.add("the `# Groups: <names>.` line of emu-up-group is gone")
				return r.out
			}
			documented := map[string]bool{}
			for name := range strings.FieldsSeq(found[1]) {
				documented[name] = true
			}
			groups := composeProfiles(in[emuCompose])
			delete(groups, "cli")
			for _, name := range slices.Sorted(maps.Keys(groups)) {
				if !documented[name] {
					r.add("compose profile %q is missing from the `# Groups:` line", name)
				}
			}
			for _, name := range slices.Sorted(maps.Keys(documented)) {
				if !groups[name] {
					r.add("the `# Groups:` line names %q, which no compose profile has", name)
				}
			}
			return r.out
		},
	}
}

// emulatorNoExporters: nothing scrapes Prometheus exporters since telemetry is
// the upstream otel-lgtm image (ADR 0072).
func emulatorNoExporters() Rule {
	const id = "emulator-no-prometheus-exporters"
	return Rule{
		ID:     id,
		Why:    "nothing scrapes a Prometheus exporter since telemetry is upstream otel-lgtm (ADR 0072)",
		Inputs: []Input{{Path: emuCompose, Format: YAML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: emuCompose}
			for _, name := range slices.Sorted(maps.Keys(services(in[emuCompose]))) {
				if strings.HasSuffix(name, "-exporter") {
					r.add("remove the Prometheus exporter service %q", name)
				}
			}
			if composeProfiles(in[emuCompose])["exporters"] {
				r.add("remove the `exporters` profile")
			}
			return r.out
		},
	}
}

// emulatorEnvPorts: each `localhost:<port>` address in the env example is a
// host port compose.yaml publishes.
func emulatorEnvPorts() Rule {
	const id = "emulator-env-example-ports"
	return Rule{
		ID:     id,
		Why:    "the env example's localhost addresses reach the host ports compose.yaml publishes",
		Inputs: []Input{{Path: emuEnvExample, Format: Text}, {Path: emuCompose, Format: YAML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: emuEnvExample}
			published := map[string]bool{}
			for _, svc := range services(in[emuCompose]) {
				for _, port := range strs(svc, "ports") {
					if m := publishedPort.FindStringSubmatch(port); m != nil {
						published[m[1]+m[2]] = true
					}
				}
			}
			text, _ := in[emuEnvExample].(string)
			pairs := envLocalhost.FindAllStringSubmatch(text, -1)
			if len(pairs) == 0 {
				r.add("the env example names no `export NAME=localhost:<port>` address")
			}
			for _, p := range pairs {
				if !published[p[2]] {
					r.add("%s=localhost:%s points at a port compose.yaml does not publish on the host; use its default host port", p[1], p[2])
				}
			}
			return r.out
		},
	}
}

// emulatorMCPInspector: the Inspector UI runs in the browser and calls its
// proxy directly on <page host>:6277 (upstream client/src/utils/configUtils.ts).
// The proxy accepts only the origins in ALLOWED_ORIGINS and needs its session
// token.
func emulatorMCPInspector() Rule {
	const id = "emulator-mcp-inspector-loopback-auth"
	return Rule{
		ID:     id,
		Why:    "the MCP Inspector publishes its UI and proxy on loopback only and keeps the proxy's origin check and token",
		Inputs: []Input{{Path: emuCompose, Format: YAML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: emuCompose}
			svc, ok := table(in[emuCompose], "services", "mcp-inspector")
			if !ok {
				r.add("compose.yaml has no mcp-inspector service")
				return r.out
			}
			ports := strs(svc, "ports")
			for _, p := range ports {
				if !strings.HasPrefix(p, "127.0.0.1:") {
					r.add("bind every Inspector port to loopback: %s", p)
				}
			}
			if !slices.Contains(ports, inspectorUI) {
				r.add("publish the Inspector UI as %s", inspectorUI)
			}
			if !slices.ContainsFunc(ports, func(p string) bool { return strings.HasSuffix(p, ":6277") }) {
				r.add("publish the proxy port 6277; the browser UI calls it directly")
			}
			env := envList(svc)
			if !slices.Contains(strings.Split(env["ALLOWED_ORIGINS"], ","), inspectorOrigin) {
				r.add("set ALLOWED_ORIGINS to include %s so the proxy accepts the published UI", inspectorOrigin)
			}
			if env["MCP_AUTO_OPEN_ENABLED"] != "false" {
				r.add("set MCP_AUTO_OPEN_ENABLED=false; there is no browser inside the container")
			}
			if _, ok := env["DANGEROUSLY_OMIT_AUTH"]; ok {
				r.add("remove DANGEROUSLY_OMIT_AUTH; keep the proxy's auth token")
			}
			return r.out
		},
	}
}

// emulatorGoBuilders: the emulator's Go builder images use the Go version the
// dev container image bakes.
func emulatorGoBuilders() Rule {
	const id = "emulator-go-builders-use-the-image-go"
	return Rule{
		ID:     id,
		Why:    "every emulator Go builder image uses the Go version of config/mise/image-tools.toml",
		Inputs: []Input{{Path: emuDockerfiles, Format: Text, Glob: true}, {Path: imageConfig, Format: TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: emuDockerfiles}
			goVersion, ok := str(in[imageConfig], "tools", "go")
			if !ok {
				r.addAt(imageConfig, "[tools] go must be a version")
				return r.out
			}
			files, _ := in[emuDockerfiles].(map[string]any)
			builders := 0
			for _, path := range slices.Sorted(maps.Keys(files)) {
				text, _ := files[path].(string)
				for _, s := range dockerStages(text) {
					m := goBuilder.FindStringSubmatch(s.image)
					if m == nil {
						continue
					}
					builders++
					if m[1] != goVersion {
						r.addAt(path, "the Go builder uses golang:%s; use %s from %s", m[1], goVersion, imageConfig)
					}
				}
			}
			if builders == 0 {
				r.add("no Go builder (FROM docker.io/library/golang:<version>-...) in any emulator Dockerfile")
			}
			return r.out
		},
	}
}

// stage is one build stage of a Dockerfile: the image of its FROM line, its
// name (lower case; "" without AS), and the text up to the next FROM line.
type stage struct {
	image, name, body string
}

// dockerStages reads a Dockerfile's stages. It first joins each continued
// line to the next with nothing between them, as BuildKit's parser does.
func dockerStages(text string) []stage {
	text = continuation.ReplaceAllString(text, "")
	lines := stageLine.FindAllStringSubmatchIndex(text, -1)
	out := make([]stage, 0, len(lines))
	for i, m := range lines {
		end := len(text)
		if i+1 < len(lines) {
			end = lines[i+1][0]
		}
		s := stage{image: text[m[2]:m[3]], body: text[m[1]:end]}
		if m[4] >= 0 {
			s.name = strings.ToLower(text[m[4]:m[5]])
		}
		out = append(out, s)
	}
	return out
}

// emulatorHealthDockerfile: the health images add a probe to the upstream
// spanner and pgadapter images and change nothing else.
func emulatorHealthDockerfile() Rule {
	const id = "emulator-health-dockerfile"
	return Rule{
		ID:     id,
		Why:    "the health images only add a probe to the pinned upstream spanner and pgadapter images",
		Inputs: []Input{{Path: healthDockerfile, Format: Text}, {Path: imageConfig, Format: TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: healthDockerfile}
			text, _ := in[healthDockerfile].(string)
			goVersion, _ := str(in[imageConfig], "tools", "go")
			for _, want := range []string{"CGO_ENABLED=0", "go build -mod=readonly -trimpath -o /tcp-healthcheck ."} {
				if !strings.Contains(text, want) {
					r.add("the Dockerfile must contain %q", want)
				}
			}
			stages := dockerStages(text)
			named := func(name string) (int, bool) {
				i := slices.IndexFunc(stages, func(s stage) bool { return s.name == name })
				if i < 0 {
					r.add("the Dockerfile has no %s stage", name)
				}
				return i, i >= 0
			}
			builder := "docker.io/library/golang:" + goVersion + "-alpine"
			if i, ok := named("builder"); ok && stages[i].image != builder {
				r.add("the builder stage must be FROM %s, the image Go", builder)
			}
			if i, ok := named("spanner"); ok {
				if !spannerImage.MatchString(stages[i].image) {
					r.add("the spanner stage must be FROM gcr.io/cloud-spanner-emulator/emulator:<x.y.z>, not %s", stages[i].image)
				}
				if strings.TrimSpace(stages[i].body) != probeCopy {
					r.add("the spanner stage must only copy the probe: %s", probeCopy)
				}
				for _, runtime := range stages[i:] {
					for _, m := range runtimeConfig.FindAllString(runtime.body, -1) {
						r.add("the runtime stages keep the upstream image configuration; remove %s", m)
					}
				}
			}
			if i, ok := named("pgadapter"); ok {
				const pgadapter = "gcr.io/cloud-spanner-pg-adapter/pgadapter"
				if stages[i].image != pgadapter {
					r.add("the pgadapter stage must be FROM %s, not %s", pgadapter, stages[i].image)
				}
				for _, want := range []string{
					"apt-get install -y --no-install-recommends postgresql-client",
					"command -v pg_isready",
					"pg_isready --version",
					"rm -rf /var/lib/apt/lists/*",
				} {
					if !strings.Contains(stages[i].body, want) {
						r.add("the pgadapter stage must run %q", want)
					}
				}
				for _, m := range pgadapterAdds.FindAllString(stages[i].body, -1) {
					r.add("the pgadapter stage only installs postgresql-client; remove %q", m)
				}
			}
			return r.out
		},
	}
}

// healthProbes is each health service, its build target, and its probe.
var healthProbes = []struct {
	service, target string
	test            []string
}{
	{"spanner-emulator", "spanner", []string{"CMD", "/usr/local/bin/tcp-healthcheck", "127.0.0.1:9010"}},
	{"pgadapter", "pgadapter", []string{"CMD", "pg_isready", "-h", "localhost", "-p", "5432"}},
}

// emulatorHealthServices: the health services build their image locally from
// the health Dockerfile and probe without a shell.
func emulatorHealthServices() Rule {
	const id = "emulator-health-services"
	return Rule{
		ID:     id,
		Why:    "the spanner and pgadapter services build the local health images and probe them without a shell",
		Inputs: []Input{{Path: emuCompose, Format: YAML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: emuCompose}
			for _, h := range healthProbes {
				svc, ok := table(in[emuCompose], "services", h.service)
				if !ok {
					r.add("compose.yaml has no %s service", h.service)
					continue
				}
				for _, c := range []struct {
					keys []string
					want string
				}{
					{[]string{"build", "context"}, "./healthcheck"},
					{[]string{"build", "dockerfile"}, "Dockerfile"},
					{[]string{"build", "target"}, h.target},
					{[]string{"image"}, "localhost/emulator-health-" + h.target + ":local"},
					{[]string{"pull_policy"}, "build"},
					{[]string{"healthcheck", "interval"}, "30s"},
					{[]string{"healthcheck", "timeout"}, "10s"},
					{[]string{"healthcheck", "retries"}, "5"},
					{[]string{"healthcheck", "start_period"}, "30s"},
				} {
					if got, _ := at(svc, c.keys...); fmt.Sprint(got) != c.want {
						r.add("%s %s must be %s, not %v", h.service, strings.Join(c.keys, "."), c.want, got)
					}
				}
				if test := strs(svc, "healthcheck", "test"); !slices.Equal(test, h.test) {
					r.add("%s healthcheck test must be %q, an image-local probe with no shell", h.service, h.test)
				}
			}
			return r.out
		},
	}
}
