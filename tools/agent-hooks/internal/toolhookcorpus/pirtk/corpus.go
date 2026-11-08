// Package pirtk records the vendored rtk extension's behavior under Pi 1.4.0.
// The oracle runs the extension itself; the corpus also names the deliberate
// differences the agent-hook binary must implement.
package pirtk

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
	"unicode"
	"unicode/utf8"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pipath/pioracle"
)

// Scenario specifies the command, environment and fake rtk for one run.
type Scenario struct {
	Name    string            `json:"name"`
	Command any               `json:"command"`
	Env     map[string]string `json:"env"`
	Fake    Fake              `json:"fake"`
	kind    scenarioKind
}

// Fake is the PATH placement and answers of the scenario's rtk program.
type Fake struct {
	Path    string  `json:"path"`
	Version Version `json:"version"`
	Rewrite Rewrite `json:"rewrite"`
}

// Version answers the extension's session-start version probe.
type Version struct {
	Exit   int    `json:"exit"`
	Stdout string `json:"stdout"`
}

// Rewrite specifies bytes and process behavior, including malformed UTF-8.
type Rewrite struct {
	Exit      int    `json:"exit"`
	StdoutB64 string `json:"stdoutB64"`
	PauseAt   int    `json:"pauseAt"`
	LateB64   string `json:"lateB64"`
	// LateMs is how long after rtk starts its background child writes
	// LateB64: inside Pi's 100 ms grace after the exit, or past it.
	LateMs  int    `json:"lateMs"`
	Signal  bool   `json:"signal"`
	SleepMs int    `json:"sleepMs"`
	Stderr  string `json:"stderr"`
}

// Answer is observed from node and the fake's NUL-separated argv log.
type Answer struct {
	Registered bool       `json:"piRegistered"`
	Argv       [][]string `json:"piArgv"`
	Command    any        `json:"piCommand"`
}

// Header pins both upstream versions: Pi and the exact vendored extension.
type Header struct {
	Pi    string `json:"pi"`
	RtkTs string `json:"rtkTs"`
}

// Entry is one corpus line after its header. A nil BinaryCommand is a pass.
type Entry struct {
	Scenario
	Answer
	Differences   []string `json:"differences"`
	BinaryCommand *string  `json:"binaryCommand"`
}

// Render writes a version/hash header followed by each observed oracle run.
func Render(extension []byte, scenarios []Scenario, answers []Answer) ([]byte, error) {
	if len(scenarios) != len(answers) {
		return nil, errors.New("a scenario and an answer go together")
	}
	var out bytes.Buffer
	if err := appendLine(&out, Header{Pi: pioracle.PiVersion, RtkTs: fmt.Sprintf("%x", sha256.Sum256(extension))}); err != nil {
		return nil, err
	}
	for i, scenario := range scenarios {
		entry := Entry{Scenario: scenario, Answer: answers[i], Differences: []string{}}
		original, isString := scenario.Command.(string)
		if command, ok := entry.Answer.Command.(string); ok && isString && command != original {
			entry.BinaryCommand = &command
		}
		if err := applyDifference(&entry, scenario); err != nil {
			return nil, err
		}
		if err := appendLine(&out, entry); err != nil {
			return nil, err
		}
	}
	return out.Bytes(), nil
}

// applyDifference sets what the binary must do for a scenario with a named
// difference, from the scenario's own bytes, never from the binary's policy
// or process adapter. The observed Pi answer stays untouched.
func applyDifference(entry *Entry, scenario Scenario) error {
	if scenario.kind == "" {
		return nil
	}
	entry.Differences = []string{string(scenario.kind)}
	switch scenario.kind {
	case relativePath, signalDeath, invalidUTF8:
		entry.BinaryCommand = nil
		return nil
	default:
		// The binary rewrites with the whole output, read at once.
		command, err := wholeOutput(scenario.Fake.Rewrite)
		if err != nil {
			return fmt.Errorf("%s: %w", scenario.Name, err)
		}
		entry.BinaryCommand = &command
		return nil
	}
}

// wholeOutput is a fake's stdout and late tail, read at once, without the
// ASCII whitespace around it. Its scenarios use no other whitespace, where
// JavaScript's trim and this one would differ.
func wholeOutput(rewrite Rewrite) (string, error) {
	stdout, err := base64.StdEncoding.DecodeString(rewrite.StdoutB64)
	if err != nil {
		return "", err
	}
	late, err := base64.StdEncoding.DecodeString(rewrite.LateB64)
	if err != nil {
		return "", err
	}
	whole := string(stdout) + string(late)
	if !utf8.ValidString(whole) {
		return "", errors.New("the whole output is not UTF-8")
	}
	trimmed := strings.Trim(whole, " \t\n\r")
	if strings.TrimFunc(trimmed, unicode.IsSpace) != trimmed {
		return "", errors.New("the output has whitespace beyond ASCII at an end")
	}
	return trimmed, nil
}

func appendLine(out *bytes.Buffer, value any) error {
	line, err := json.Marshal(value, json.Deterministic(true))
	if err != nil {
		return err
	}
	out.Write(pioracle.ASCIILine(line))
	out.WriteByte('\n')
	return nil
}

// Parse reads the header and scenario lines Render wrote.
func Parse(corpus []byte) (Header, []Entry, error) {
	lines := bytes.Split(bytes.TrimSuffix(corpus, []byte("\n")), []byte("\n"))
	var header Header
	if err := json.Unmarshal(lines[0], &header, json.RejectUnknownMembers(true)); err != nil {
		return Header{}, nil, fmt.Errorf("header: %w", err)
	}
	if header.Pi != pioracle.PiVersion {
		return Header{}, nil, fmt.Errorf("the corpus is Pi %s's, not %s's", header.Pi, pioracle.PiVersion)
	}
	entries := make([]Entry, 0, len(lines)-1)
	for i, line := range lines[1:] {
		var entry Entry
		if err := json.Unmarshal(line, &entry, json.RejectUnknownMembers(true)); err != nil {
			return Header{}, nil, fmt.Errorf("line %d: %w", i+2, err)
		}
		entries = append(entries, entry)
	}
	return header, entries, nil
}
