package logline_test

import (
	"math"
	"reflect"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

func TestMarshalParseRoundTripAndKeyOrder(t *testing.T) {
	for _, line := range []logline.Line{
		build(logline.Firing{}), build(logline.Firing{Usage: true}),
		build(logline.Firing{Error: logline.ErrUsage}),
		build(logline.Firing{
			Harness: "claude", Event: "pre", Hook: "command-guard",
			Call:    &ir.Call{Kind: ir.KindShell, Tool: "Bash", Fields: map[string]ir.Value{ir.FieldCommand: stringValue("git status")}},
			Outcome: ir.Outcome{Action: ir.Block, Rule: ir.RuleHookFailed}, Error: logline.ErrHookFailed, Mismatch: logline.MismatchMapping,
		}),
	} {
		encoded, err := line.Marshal()
		if err != nil {
			t.Fatal(err)
		}
		if !strings.HasSuffix(string(encoded), "}\n") || strings.Count(string(encoded), "\n") != 1 {
			t.Fatalf("not one newline-terminated JSON object: %q", encoded)
		}
		parsed, err := logline.Parse(encoded)
		if err != nil || !reflect.DeepEqual(parsed, line) {
			t.Errorf("round trip = %#v, %v; want %#v", parsed, err, line)
		}
		position := -1
		for _, key := range []string{"time", "release", "harness", "event", "tool", "kind", "hook", "outcome", "rule", "durationMs", "program", "subcommand", "extension", "project", "error", "mismatch", "traceId", "spanId"} {
			next := strings.Index(string(encoded), `"`+key+`":`)
			if next == -1 {
				continue
			}
			if next <= position {
				t.Errorf("%s is out of order: %s", key, encoded)
			}
			position = next
		}
	}
}

func TestParseRefusesUnknownMembersAndNonObjects(t *testing.T) {
	for _, text := range []string{
		"", " \n", "null", "[]", `"text"`, "5", "true", "{}{}", "{} trailing", "{",
		`{"unexpected":"value"}`, `{"time":"x","unexpected":{}}`, `{"durationMs":"1"}`,
		`{"error":"usage","unknown":true}`, `{"time":"one","time":"two"}`,
	} {
		t.Run(text, func(t *testing.T) {
			if _, err := logline.Parse([]byte(text)); err == nil {
				t.Errorf("Parse accepted %q", text)
			}
		})
	}
}

func TestMarshalReportsAnUnencodableNumber(t *testing.T) {
	line := build(logline.Firing{})
	line.DurationMs = math.NaN()
	if _, err := line.Marshal(); err == nil {
		t.Fatal("Marshal accepted NaN")
	}
}

func TestMarshalKeepsEvenAnOversizedReleaseBelowTheLineLimit(t *testing.T) {
	line := build(logline.Firing{})
	encoded, err := line.Marshal()
	if err != nil {
		t.Fatal(err)
	}
	// The public release variable has no length bound. Leave room for the
	// newline, and require Marshal to refuse the boundary itself.
	line.Release = strings.Repeat("r", 4095-len(encoded)+len(line.Release))
	encoded, err = line.Marshal()
	if err != nil || len(encoded) != 4095 {
		t.Fatalf("largest permitted line = %d bytes, %v; want 4095", len(encoded), err)
	}
	line.Release += "r"
	if encoded, err := line.Marshal(); err == nil || len(encoded) != 0 {
		t.Fatalf("4096-byte line was not refused: %d bytes, %v", len(encoded), err)
	}
}
