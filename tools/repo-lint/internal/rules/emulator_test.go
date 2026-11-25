package rules

import (
	"strings"
	"testing"
)

const healthDockerfileText = `FROM docker.io/library/golang:1.27.4-alpine AS builder
WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 go build -mod=readonly -trimpath -o /tcp-healthcheck .

FROM gcr.io/cloud-spanner-emulator/emulator:1.5.59 AS spanner
COPY --from=builder /tcp-healthcheck /usr/local/bin/tcp-healthcheck

FROM gcr.io/cloud-spanner-pg-adapter/pgadapter AS pgadapter
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client \
 && command -v pg_isready \
 && pg_isready --version \
 && rm -rf /var/lib/apt/lists/*
`

func healthService(target string, probe ...any) map[string]any {
	return map[string]any{
		"image":       "localhost/emulator-health-" + target + ":local",
		"pull_policy": "build",
		"build":       map[string]any{"context": "./healthcheck", "dockerfile": "Dockerfile", "target": target},
		"healthcheck": map[string]any{"test": probe, "interval": "30s", "timeout": "10s", "retries": float64(5), "start_period": "30s"},
	}
}

// emulatorCompose is an emulator/compose.yaml, as yq decodes it, that every
// emulator rule accepts.
func emulatorCompose() map[string]any {
	spanner := healthService("spanner", "CMD", "/usr/local/bin/tcp-healthcheck", "127.0.0.1:9010")
	spanner["ports"] = []any{"127.0.0.1:${SPANNER_GRPC_PORT:-9010}:9010"}
	return map[string]any{"services": map[string]any{
		"firebase":         map[string]any{"ports": []any{"127.0.0.1:${AUTH_PORT:-9099}:9099", "127.0.0.1:${FIRESTORE_PORT:-8080}:8080"}},
		"spanner-emulator": spanner,
		"pgadapter":        healthService("pgadapter", "CMD", "pg_isready", "-h", "localhost", "-p", "5432"),
		"bigtable":         map[string]any{"profiles": []any{"bigtable", "full"}, "ports": []any{"127.0.0.1:8086:8086"}},
		"search":           map[string]any{"profiles": []any{"search", "full"}},
		"psql":             map[string]any{"profiles": []any{"cli"}},
		"mcp-inspector": map[string]any{
			"profiles": []any{"inspect", "full"},
			"ports":    []any{"127.0.0.1:${MCP_INSPECTOR_PORT:-6274}:6274", "127.0.0.1:${MCP_INSPECTOR_PROXY_PORT:-6277}:6277"},
			"environment": []any{
				"ALLOWED_ORIGINS=http://localhost:${MCP_INSPECTOR_PORT:-6274},http://127.0.0.1:${MCP_INSPECTOR_PORT:-6274}",
				"MCP_AUTO_OPEN_ENABLED=false",
			},
		},
	}}
}

func emulatorInputs() Inputs {
	return Inputs{
		emuCompose:       emulatorCompose(),
		emuEnvExample:    "export FIREBASE_AUTH_EMULATOR_HOST=localhost:9099\nexport SPANNER_EMULATOR_HOST=localhost:9010\nexport X=http://localhost:5252\n",
		justfilePath:     "# Groups: bigtable search inspect full.\nemu-up-group cap:\n",
		emuDockerfiles:   map[string]any{"emulator/healthcheck/Dockerfile": healthDockerfileText, "emulator/firebase/Dockerfile": "FROM docker.io/library/node:24\n"},
		healthDockerfile: healthDockerfileText,
		imageConfig:      image(),
	}
}

func svc(in Inputs, name string) map[string]any {
	s, _ := table(in[emuCompose], "services", name)
	return s
}

func TestEmulatorGroupsMatchTheComposeProfiles(t *testing.T) {
	runCases(t, emulatorGroups(), emulatorInputs, []ruleCase{
		{"a group not documented", func(in Inputs) { in[justfilePath] = "# Groups: bigtable search full.\n" }, "inspect"},
		{"a documented group with no profile", func(in Inputs) {
			in[justfilePath] = "# Groups: bigtable search inspect full graph.\n"
		}, "graph"},
		{"the list is gone", func(in Inputs) { in[justfilePath] = "emu-up-group cap:\n" }, "# Groups:"},
	})
}

func TestEmulatorRunsNoPrometheusExporters(t *testing.T) {
	runCases(t, emulatorNoExporters(), emulatorInputs, []ruleCase{
		{"an exporter service", func(in Inputs) { set(in[emuCompose], map[string]any{}, "services", "postgres-exporter") }, "postgres-exporter"},
		{"an exporters profile", func(in Inputs) { svc(in, "search")["profiles"] = []any{"exporters"} }, "exporters"},
	})
}

func TestEmulatorEnvExampleUsesPublishedPorts(t *testing.T) {
	runCases(t, emulatorEnvPorts(), emulatorInputs, []ruleCase{
		{"a port compose does not publish", func(in Inputs) {
			in[emuEnvExample] = in[emuEnvExample].(string) + "export PUBSUB_EMULATOR_HOST=localhost:8085\n"
		}, "PUBSUB_EMULATOR_HOST"},
		{"no address at all", func(in Inputs) { in[emuEnvExample] = "# empty\n" }, "localhost"},
	})
}

func TestMCPInspectorStaysOnLoopbackWithItsAuth(t *testing.T) {
	inspector := func(in Inputs) map[string]any { return svc(in, "mcp-inspector") }
	runCases(t, emulatorMCPInspector(), emulatorInputs, []ruleCase{
		{"a port off loopback", func(in Inputs) {
			inspector(in)["ports"] = []any{"${MCP_INSPECTOR_PORT:-6274}:6274", "127.0.0.1:${MCP_INSPECTOR_PROXY_PORT:-6277}:6277"}
		}, "loopback"},
		{"the proxy port unpublished", func(in Inputs) {
			inspector(in)["ports"] = []any{"127.0.0.1:${MCP_INSPECTOR_PORT:-6274}:6274"}
		}, "6277"},
		{"no allowed origins", func(in Inputs) { inspector(in)["environment"] = []any{"MCP_AUTO_OPEN_ENABLED=false"} }, "ALLOWED_ORIGINS"},
		{"auto open on", func(in Inputs) {
			inspector(in)["environment"] = []any{"ALLOWED_ORIGINS=http://localhost:${MCP_INSPECTOR_PORT:-6274}", "MCP_AUTO_OPEN_ENABLED=true"}
		}, "MCP_AUTO_OPEN_ENABLED"},
		{"auth dropped", func(in Inputs) {
			inspector(in)["environment"] = append(inspector(in)["environment"].([]any), "DANGEROUSLY_OMIT_AUTH=true")
		}, "DANGEROUSLY_OMIT_AUTH"},
		{"no inspector", func(in Inputs) { set(in[emuCompose], nil, "services", "mcp-inspector") }, "mcp-inspector"},
	})
}

func TestEmulatorGoBuildersUseTheImageGo(t *testing.T) {
	runCases(t, emulatorGoBuilders(), emulatorInputs, []ruleCase{
		{"an older builder", func(in Inputs) {
			in[emuDockerfiles].(map[string]any)["emulator/x/Dockerfile"] = "FROM docker.io/library/golang:1.26.1-alpine AS b\n"
		}, "1.26.1"},
		{"an older builder for the build platform", func(in Inputs) {
			in[emuDockerfiles].(map[string]any)["emulator/x/Dockerfile"] = "FROM --platform=$BUILDPLATFORM docker.io/library/golang:1.26.2-alpine AS b\n"
		}, "1.26.2"},
		{"no builder at all", func(in Inputs) {
			in[emuDockerfiles] = map[string]any{"emulator/firebase/Dockerfile": "FROM node\n"}
		}, "no Go builder"},
	})
}

func TestHealthDockerfileAddsOnlyTheProbes(t *testing.T) {
	edit := func(old, new string) func(Inputs) {
		return func(in Inputs) {
			in[healthDockerfile] = strings.Replace(healthDockerfileText, old, new, 1)
		}
	}
	runCases(t, emulatorHealthDockerfile(), emulatorInputs, []ruleCase{
		{"builder on another Go", edit("golang:1.27.4-alpine", "golang:1.26.1-alpine"), "builder"},
		{"cgo on", edit("CGO_ENABLED=0 ", ""), "CGO_ENABLED=0"},
		{"build without readonly modules", edit("-mod=readonly ", ""), "go build"},
		{"spanner base unpinned", edit("emulator:1.5.59", "emulator:latest"), "spanner"},
		{"pgadapter base replaced", edit("gcr.io/cloud-spanner-pg-adapter/pgadapter AS", "docker.io/library/postgres AS"), "pgadapter"},
		{"spanner stage does more", edit("COPY --from=builder /tcp-healthcheck /usr/local/bin/tcp-healthcheck\n", "COPY --from=builder /tcp-healthcheck /usr/local/bin/tcp-healthcheck\nRUN true\n"), "spanner stage"},
		{"runtime user changed", edit("&& rm -rf /var/lib/apt/lists/*\n", "&& rm -rf /var/lib/apt/lists/*\nUSER nobody\n"), "USER"},
		{"server installed", edit("postgresql-client", "postgresql-client postgresql-server"), "postgresql-server"},
		{"download tool", edit("&& command -v pg_isready", "&& curl -fsS https://example.invalid && command -v pg_isready"), "curl"},
		{"no version check", edit(" && pg_isready --version \\\n", " \\\n"), "pg_isready --version"},
		{"apt lists kept", edit(" \\\n && rm -rf /var/lib/apt/lists/*", ""), "apt/lists"},
		{"pgadapter stage emptied behind a trailing space", func(in Inputs) {
			head, _, _ := strings.Cut(healthDockerfileText, " AS pgadapter\n")
			in[healthDockerfile] = head + " AS pgadapter \n"
		}, "postgresql-client"},
		{"spanner stage named with a trailing space", edit(" AS spanner\n", " AS spanner \nRUN true\n"), "only copy the probe"},
		{"no pgadapter stage", func(in Inputs) {
			head, _, _ := strings.Cut(healthDockerfileText, "FROM gcr.io/cloud-spanner-pg-adapter")
			in[healthDockerfile] = head
		}, "pgadapter stage"},
	})
}

func TestHealthServicesBuildLocallyAndProbeWithoutAShell(t *testing.T) {
	runCases(t, emulatorHealthServices(), emulatorInputs, []ruleCase{
		{"pulled not built", func(in Inputs) { svc(in, "pgadapter")["pull_policy"] = "always" }, "pull_policy"},
		{"another target", func(in Inputs) { set(svc(in, "spanner-emulator"), "pgadapter", "build", "target") }, "target"},
		{"another context", func(in Inputs) { set(svc(in, "pgadapter"), "./other", "build", "context") }, "context"},
		{"a registry image", func(in Inputs) { svc(in, "spanner-emulator")["image"] = "gcr.io/x/health:1" }, "image"},
		{"other timings", func(in Inputs) { set(svc(in, "pgadapter"), float64(3), "healthcheck", "retries") }, "retries"},
		{"shell probe", func(in Inputs) {
			set(svc(in, "spanner-emulator"), []any{"CMD-SHELL", "nc -z 127.0.0.1 9010"}, "healthcheck", "test")
		}, "spanner-emulator healthcheck"},
		{"pgadapter probe changed", func(in Inputs) {
			set(svc(in, "pgadapter"), []any{"CMD", "pg_isready"}, "healthcheck", "test")
		}, "pgadapter healthcheck"},
		{"no pgadapter", func(in Inputs) { set(in[emuCompose], nil, "services", "pgadapter") }, "no pgadapter service"},
	})
}
