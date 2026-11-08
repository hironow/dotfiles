package pirtk

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	json "github.com/goccy/go-json/v2"
)

const oracleScript = `import { pathToFileURL } from "node:url";
process.stdin.setEncoding("utf8");
let input = "";
for await (const chunk of process.stdin) input += chunk;
const config = JSON.parse(input);
const { execCommand } = await import(pathToFileURL(config.execModule).href);
const { default: extension } = await import(pathToFileURL(config.extension).href);
const handlers = new Map();
await extension({
  on(name, fn) {
    const callbacks = handlers.get(name) ?? [];
    callbacks.push(fn);
    handlers.set(name, callbacks);
  },
  exec(c, a, o) { return execCommand(c, a, process.cwd(), o); }
});
const event = {type: "tool_call", toolName: "bash", toolCallId: "t",
  input: {command: config.command}};
const callbacks = handlers.get("tool_call") ?? [];
for (const fn of callbacks) await fn(event, {signal: undefined});
process.stdout.write(JSON.stringify({registered: callbacks.length > 0, command: event.input.command}));
`

// Run executes each scenario in an isolated directory with only its fake rtk
// and /usr/bin and /bin on PATH. It never invokes the host's rtk.
func Run(node, root, extension string, scenarios []Scenario) ([]Answer, error) {
	answers := make([]Answer, 0, len(scenarios))
	for _, scenario := range scenarios {
		answer, err := runScenario(node, root, extension, scenario)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", scenario.Name, err)
		}
		answers = append(answers, answer)
	}
	return answers, nil
}

func runScenario(node, root, extension string, scenario Scenario) (Answer, error) {
	dir, err := os.MkdirTemp("", "pi-rtk-")
	if err != nil {
		return Answer{}, err
	}
	defer os.RemoveAll(dir)
	bin := filepath.Join(dir, "bin")
	if err := os.Mkdir(bin, 0o700); err != nil {
		return Answer{}, err
	}
	script, err := fakeScript(scenario)
	if err != nil {
		return Answer{}, err
	}
	if err := os.WriteFile(filepath.Join(bin, "rtk"), []byte(script), 0o600); err != nil {
		return Answer{}, err
	}
	if err := os.Chmod(filepath.Join(bin, "rtk"), 0o700); err != nil {
		return Answer{}, err
	}
	log := filepath.Join(dir, "argv")
	if err := os.WriteFile(log, nil, 0o600); err != nil {
		return Answer{}, err
	}
	input, err := json.Marshal(struct {
		ExecModule string `json:"execModule"`
		Extension  string `json:"extension"`
		Command    any    `json:"command"`
	}{filepath.Join(root, "dist", "core", "exec.js"), extension, scenario.Command})
	if err != nil {
		return Answer{}, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	// Resolve the fixed program through the same PATH as FindPackage. Refuse a
	// changed discovery; all variable input goes through stdin, never executable code.
	command := exec.CommandContext(ctx, "node", "--input-type=module", "-e", oracleScript)
	if command.Path != node {
		return Answer{}, errors.New("node on PATH changed after Pi discovery")
	}
	command.Stdin = bytes.NewReader(input)
	command.Dir = dir
	command.Env, err = scenarioEnv(dir, log, scenario)
	if err != nil {
		return Answer{}, err
	}
	command.WaitDelay = time.Second
	var stdout, stderr bytes.Buffer
	command.Stdout, command.Stderr = &stdout, &stderr
	if err := command.Run(); err != nil {
		return Answer{}, fmt.Errorf("node: %w: %s", err, strings.TrimSpace(stderr.String()))
	}
	var observed struct {
		Registered bool `json:"registered"`
		Command    any  `json:"command"`
	}
	if err := json.Unmarshal(stdout.Bytes(), &observed, json.RejectUnknownMembers(true)); err != nil {
		return Answer{}, fmt.Errorf("node's answer: %w", err)
	}
	logged, err := os.ReadFile(log)
	if err != nil {
		return Answer{}, err
	}
	argv, err := parseArgv(logged)
	if err != nil {
		return Answer{}, err
	}
	return Answer{Registered: observed.Registered, Command: observed.Command, Argv: argv}, nil
}

func scenarioEnv(dir, log string, scenario Scenario) ([]string, error) {
	// node is started by its path; the fake needs only /usr/bin and /bin.
	// No other directory goes on PATH, so no host rtk can answer.
	paths := []string{"/usr/bin", "/bin"}
	switch scenario.Fake.Path {
	case "absolute":
		paths = append([]string{filepath.Join(dir, "bin")}, paths...)
	case "relative":
		paths = append([]string{"bin"}, paths...)
	case "absent":
	default:
		return nil, fmt.Errorf("unknown fake PATH placement %q", scenario.Fake.Path)
	}
	env := []string{"PATH=" + strings.Join(paths, string(os.PathListSeparator)), "HOME=" + dir, "RTK_LOG=" + log}
	for key, value := range scenario.Env {
		if key != "RTK_DISABLED" {
			return nil, fmt.Errorf("unexpected scenario environment key %q", key)
		}
		env = append(env, key+"="+value)
	}
	return env, nil
}

func parseArgv(log []byte) ([][]string, error) {
	argv := [][]string{}
	if len(log) == 0 {
		return argv, nil
	}
	if log[len(log)-1] != 0x1e {
		return nil, errors.New("incomplete fake argv record")
	}
	for record := range bytes.SplitSeq(log[:len(log)-1], []byte{0x1e}) {
		if len(record) == 0 || record[len(record)-1] != 0 {
			return nil, errors.New("fake argv record lacks its final NUL")
		}
		argv = append(argv, strings.Split(string(record[:len(record)-1]), "\x00"))
	}
	return argv, nil
}
