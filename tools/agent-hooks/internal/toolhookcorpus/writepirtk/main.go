// Command writepirtk records the vendored rtk extension under Pi 1.4.0.
package main

import (
	"bytes"
	"encoding/base64"
	"errors"
	"fmt"
	"os"
	"os/user"
	"path/filepath"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pipath/pioracle"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/toolhookcorpus/pirtk"
)

func main() {
	if err := writeCorpus(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func writeCorpus() error {
	node, root, err := pioracle.FindPackage()
	if err != nil {
		return err
	}
	extension, err := filepath.Abs("../../config/pi/extensions/rtk.ts")
	if err != nil {
		return err
	}
	source, err := os.ReadFile(extension)
	if err != nil {
		return err
	}
	scenarios := pirtk.Scenarios()
	answers, err := pirtk.Run(node, root, extension, scenarios)
	if err != nil {
		return err
	}
	privatePaths, err := privateDirectories()
	if err != nil {
		return err
	}
	corpus, err := renderPublicCorpus(source, scenarios, answers, privatePaths)
	if err != nil {
		return err
	}
	module, err := os.OpenRoot(".")
	if err != nil {
		return err
	}
	defer module.Close()
	return module.WriteFile("internal/toolhookcorpus/pi-rtk.jsonl", corpus, 0o600)
}

func privateDirectories() ([]string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return nil, fmt.Errorf("working directory: %w", err)
	}
	account, err := user.Current()
	if err != nil {
		return nil, fmt.Errorf("home directory: %w", err)
	}
	paths := []string{cwd, os.Getenv("HOME"), account.HomeDir, os.TempDir()}
	for _, path := range paths {
		if path == "" {
			continue
		}
		real, err := filepath.EvalSymlinks(path)
		if err != nil {
			return nil, fmt.Errorf("private directory: %w", err)
		}
		paths = append(paths, real)
	}
	return paths, nil
}

func renderPublicCorpus(extension []byte, scenarios []pirtk.Scenario, answers []pirtk.Answer, privatePaths []string) ([]byte, error) {
	corpus, err := pirtk.Render(extension, scenarios, answers)
	if err != nil {
		return nil, err
	}
	var rawOutput bytes.Buffer
	for _, scenario := range scenarios {
		for _, encoded := range []string{scenario.Fake.Rewrite.StdoutB64, scenario.Fake.Rewrite.LateB64} {
			decoded, err := base64.StdEncoding.DecodeString(encoded)
			if err != nil {
				return nil, fmt.Errorf("fake output: %w", err)
			}
			rawOutput.Write(decoded)
			rawOutput.WriteByte(0)
		}
	}
	for _, path := range privatePaths {
		if path == "" {
			continue
		}
		encoded, err := json.Marshal(path)
		if err != nil {
			return nil, err
		}
		// Match the JSON-escaped spelling too, including Windows separators,
		// and its ASCII spelling, as the corpus writes a path that is not ASCII.
		spelled := encoded[1 : len(encoded)-1]
		if bytes.Contains(corpus, spelled) || bytes.Contains(corpus, pioracle.ASCIILine(spelled)) ||
			bytes.Contains(rawOutput.Bytes(), []byte(path)) {
			return nil, errors.New("refusing to write a corpus containing a local directory")
		}
	}
	return corpus, nil
}
