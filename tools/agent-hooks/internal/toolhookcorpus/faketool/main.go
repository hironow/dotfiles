//go:build !windows

// Command faketool stands in for rtk, mise, uv, and gofmt when the agent-hook
// binary runs the tool-hooks corpus as a real process. Each fake is a script
// whose shebang runs faketool, so the kernel hands faketool the script's path
// as the caller gave it to execve, unresolved, as it handed it to the
// generator's Python fakes. The script's second line is its config (the root
// and the fake's label). faketool logs one JSON line per run to
// <root>/invocations.jsonl and answers as <root>/fakes.json says, by the same
// rules as the generator's fakes: only rtk reads its stdin.
package main

import (
	"bufio"
	"io"
	"os"
	"path"
	"path/filepath"
	"slices"
	"syscall"

	json "github.com/goccy/go-json/v2"
)

type config struct {
	Root  string `json:"root"`
	Label string `json:"label"`
}

type answer struct {
	Stdout []byte `json:"stdout"`
	Stderr []byte `json:"stderr"`
	Exit   int    `json:"exit"`
}

type rule struct {
	Stdout  []byte            `json:"stdout"`
	Stderr  []byte            `json:"stderr"`
	Exit    int               `json:"exit"`
	Default *answer           `json:"default"`
	Clean   *answer           `json:"clean"`
	Checks  map[string]answer `json:"checks"`
}

// The environment variables a fake records, as the generator's fakes do.
var recordedEnv = []string{"PATH", "HOME", "AGENT_HOOK_PROBE"}

func main() {
	os.Exit(run())
}

func run() int {
	if len(os.Args) < 2 {
		return 99
	}
	script, args := os.Args[1], os.Args[2:]
	cfg, err := readConfig(script)
	if err != nil {
		return 98
	}
	rules := map[string]rule{}
	if err := readJSON(filepath.Join(cfg.Root, "fakes.json"), &rules); err != nil {
		return 97
	}
	chosen := choose(rules[cfg.Label], args)
	var stdin *string
	if path.Base(cfg.Label) == "rtk" {
		data, err := io.ReadAll(os.Stdin)
		if err != nil {
			return 96
		}
		text := string(data)
		stdin = &text
	}
	cwd, err := syscall.Getwd()
	if err != nil {
		return 95
	}
	env := map[string]*string{}
	for _, name := range recordedEnv {
		if value, ok := os.LookupEnv(name); ok {
			env[name] = &value
		} else {
			env[name] = nil
		}
	}
	record, err := json.Marshal(map[string]any{
		"tool": cfg.Label, "argv": append([]string{script}, args...), "stdin": stdin,
		"cwd": cwd, "env": env, "answer": chosen,
	})
	if err != nil {
		return 94
	}
	log, err := os.OpenFile(filepath.Join(cfg.Root, "invocations.jsonl"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		return 93
	}
	_, err = log.Write(append(record, '\n'))
	if closeErr := log.Close(); err != nil || closeErr != nil {
		return 92
	}
	_, _ = os.Stdout.Write(chosen.Stdout)
	_, _ = os.Stderr.Write(chosen.Stderr)
	return chosen.Exit
}

// choose is the generator's fake rule: one answer; or for uv, `ruff check
// <path>` without --fix answers by path (Clean when the path has none), and
// anything else answers Default.
func choose(r rule, args []string) answer {
	chosen := answer{Stdout: r.Stdout, Stderr: r.Stderr, Exit: r.Exit}
	if r.Default != nil {
		chosen = *r.Default
	}
	if r.Checks != nil && slices.Contains(args, "check") && !slices.Contains(args, "--fix") && len(args) > 0 {
		if found, ok := r.Checks[args[len(args)-1]]; ok {
			return found
		}
		if r.Clean != nil {
			return *r.Clean
		}
	}
	return chosen
}

func readConfig(script string) (config, error) {
	// The kernel hands faketool the path of the fake's own script (its
	// shebang); a test wrote that script.
	file, err := os.Open(script) //nolint:gosec // G703: audited above
	if err != nil {
		return config{}, err
	}
	defer file.Close()
	lines := bufio.NewScanner(file)
	lines.Scan() // the shebang
	lines.Scan()
	var cfg config
	err = json.Unmarshal(lines.Bytes(), &cfg)
	return cfg, err
}

func readJSON(name string, v any) error {
	data, err := os.ReadFile(name)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, v)
}
