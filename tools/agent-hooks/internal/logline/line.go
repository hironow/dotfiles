// Package logline turns raw hook facts into log lines of fixed values.
package logline

import (
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// Release is the build's release ID, set with -ldflags -X; otherwise "dev".
var Release = "dev"

// SaltSize is the number of bytes in a usable log salt.
const SaltSize = 32

// The error codes a line can carry.
const (
	ErrInputUnreadable = ir.RuleInputUnreadable
	ErrShimBroken      = ir.RuleShimBroken
	ErrHookFailed      = ir.RuleHookFailed
	ErrRewriteDropped  = "rewrite.dropped"
	ErrToolFailed      = "tool.failed"
	ErrAnswerFailed    = "answer.failed"
	ErrUsage           = "usage"
)

// The mismatch codes a line can carry.
const (
	MismatchEnvelope  = "envelope"
	MismatchInput     = "input"
	MismatchMapping   = "mapping"
	MismatchUnchecked = "unchecked"
)

// Firing is one run's raw facts. Its strings are never copied without checks.
type Firing struct {
	Usage    bool          // the binary did not understand its arguments
	Harness  string        // the harness argument, as given
	Event    string        // the event argument, as given
	Hook     string        // the --hook value, as given
	Call     *ir.Call      // the decoded call, or nil when there is none
	Outcome  ir.Outcome    // the final outcome
	Error    string        // an Err* code, or ""
	Mismatch string        // a Mismatch* code, or ""
	Duration time.Duration // from the start of the run to the answer written
	Wd       string        // the binary's physical working directory
}

// Line holds fixed values, measured numbers, a time, and lowercase hex ids.
type Line struct {
	Time       string  `json:"time"`
	Release    string  `json:"release"`
	Harness    string  `json:"harness"`
	Event      string  `json:"event"`
	Tool       string  `json:"tool"`
	Kind       string  `json:"kind"`
	Hook       string  `json:"hook"`
	Outcome    string  `json:"outcome"`
	Rule       string  `json:"rule,omitzero"`
	DurationMs float64 `json:"durationMs"`
	Program    string  `json:"program,omitzero"`
	Subcommand string  `json:"subcommand,omitzero"`
	Extension  string  `json:"extension,omitzero"`
	Project    string  `json:"project,omitzero"`
	Error      string  `json:"error,omitzero"`
	Mismatch   string  `json:"mismatch,omitzero"`
	TraceID    string  `json:"traceId"`
	SpanID     string  `json:"spanId"`
}

// Build turns a firing into a line. Only a salt of SaltSize bytes is usable.
// The shell supplies the time, span, and fallback trace.
func Build(f Firing, salt []byte, now time.Time, span [8]byte, fallbackTrace [16]byte) Line {
	l := Line{
		Time: now.UTC().Format("2006-01-02T15:04:05.000Z"), Release: Release,
		Harness: "other", TraceID: hex.EncodeToString(fallbackTrace[:]), SpanID: hex.EncodeToString(span[:]),
	}
	if _, ok := harnessTools[f.Harness]; ok {
		l.Harness = f.Harness
	}
	if f.Usage {
		l.Error = ErrUsage
		return l
	}
	l.Event = "other"
	if f.Event == "pre" || f.Event == "post" {
		l.Event = f.Event
	}
	l.Tool, l.Kind = "other", "none"
	if f.Call != nil && f.Call.Kind != "" {
		l.Kind = "other"
		switch f.Call.Kind {
		case ir.KindShell, ir.KindWrite, ir.KindEdit, ir.KindNotebook, ir.KindPatch:
			l.Kind = f.Call.Kind
		}
		if _, ok := harnessTools[l.Harness][f.Call.Tool]; ok {
			l.Tool = f.Call.Tool
		}
	}
	l.Hook = fixed(f.Hook, hooks)
	l.Outcome = "other"
	switch f.Outcome.Action {
	case ir.Pass, ir.Block, ir.Forward, ir.Rewrite:
		l.Outcome = f.Outcome.Action.String()
	}
	l.Rule = optional(f.Outcome.Rule, rules)
	l.DurationMs = float64(f.Duration.Microseconds()) / 1000
	l.Error = optional(f.Error, errorCodes)
	l.Mismatch = optional(f.Mismatch, mismatches)
	if f.Call != nil {
		switch f.Call.Kind {
		case ir.KindShell:
			if command := f.Call.Fields[ir.FieldCommand]; command.IsString {
				l.Program, l.Subcommand = commandDetails(command.Text)
			}
		case ir.KindWrite, ir.KindEdit, ir.KindNotebook, ir.KindPatch:
			l.Extension = fileExtension(f.Call)
		}
	}
	l.identify(f, salt)
	return l
}

// Marshal returns one JSON object followed by a newline, under 4096 bytes.
func (l Line) Marshal() ([]byte, error) {
	var encoded []byte
	var err error
	if l.Event == "" && l.Error == ErrUsage {
		encoded, err = json.Marshal(struct {
			Time    string `json:"time"`
			Release string `json:"release"`
			Harness string `json:"harness"`
			Error   string `json:"error"`
			TraceID string `json:"traceId"`
			SpanID  string `json:"spanId"`
		}{l.Time, l.Release, l.Harness, l.Error, l.TraceID, l.SpanID})
	} else {
		encoded, err = json.Marshal(l)
	}
	if err != nil {
		return nil, fmt.Errorf("marshal log line: %w", err)
	}
	if len(encoded)+1 >= 4096 {
		return nil, errors.New("log line must be shorter than 4096 bytes")
	}
	return append(encoded, '\n'), nil
}
