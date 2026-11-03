package guardcorpus

import (
	"bytes"
	_ "embed"
	"testing"

	"github.com/goccy/go-json/jsontext"
)

// payloads.jsonl is every payload run through every old hook script as Claude
// Code and Codex run them, written by `just hook-payload-corpus`
// (scripts/hook_payload_corpus.py) and checked by
// tests/unit/test_hook_payload_corpus.py.
//
//go:embed payloads.jsonl
var payloadCorpus string

// The difference IDs: how a run's expected answer follows from its legacy run.
const (
	DifferenceNone           = ""                // the binary answers as the script did, byte for byte
	DifferenceUnreadable     = "unreadable"      // not one JSON value: the binary blocks it
	DifferenceReferenceLimit = "reference-limit" // past a reference's limit: answered as its base
	DifferencePassDiagnostic = "pass-diagnostic" // the script passed noisily: the binary passes silently
	DifferenceNULWarning     = "nul-warning"     // bash warned of a NUL before blocking: the binary does not
)

// Payload is one stdin and what each hook script made of it.
type Payload struct {
	Line      int          `json:"-"`         // its line in payloads.jsonl
	Name      string       `json:"name"`      // what the payload tests
	Stdin     []byte       `json:"stdin"`     // the payload, as stored or joined from StdinRuns
	StdinRuns []StdinRun   `json:"stdinRuns"` // a long payload, as stored
	Base      string       `json:"base"`      // the payload this one adds an unused member to, if any
	Runs      []PayloadRun `json:"runs"`
}

// StdinRun is Count copies of Bytes.
type StdinRun struct {
	Bytes []byte `json:"bytes"`
	Count int    `json:"count"`
}

// PayloadRun is one hook script run on a payload, as one harness runs it.
type PayloadRun struct {
	Harness    string         `json:"harness"`    // "claude" or "codex"
	Hook       string         `json:"hook"`       // the hook id
	Basename   string         `json:"basename"`   // the basename(1) flavor, "bsd" or "gnu"; files guard only
	Difference string         `json:"difference"` // one of the Difference IDs
	Legacy     jsontext.Value `json:"legacy"`     // what the script did; the Python test reads it
	ExpectedGo Answer         `json:"expectedGo"` // what the binary must do
}

// Answer is a process's answer: its exit code and what it wrote.
type Answer struct {
	Exit   int    `json:"exit"`
	Stdout string `json:"stdout"`
	Stderr string `json:"stderr"`
}

// Payloads returns every payload of payloads.jsonl.
func Payloads(tb testing.TB) []Payload {
	tb.Helper()
	return decodeLines(tb, "payloads.jsonl", payloadCorpus, func(p *Payload, line int) {
		p.Line = line
		if p.StdinRuns != nil {
			var joined bytes.Buffer
			for _, run := range p.StdinRuns {
				joined.Write(bytes.Repeat(run.Bytes, run.Count))
			}
			p.Stdin = joined.Bytes()
		}
	})
}
