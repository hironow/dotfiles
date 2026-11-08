package logline_test

import (
	"reflect"
	"strings"
	"testing"
	"time"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

func build(f logline.Firing) logline.Line {
	return logline.Build(f, nil, time.Date(2026, time.November, 5, 12, 34, 56, 789123456,
		time.FixedZone("offset", 9*60*60)), [8]byte{1}, [16]byte{2})
}

func TestBuildMeasuresMillisecondsToMicrosecondPrecision(t *testing.T) {
	for _, c := range []struct {
		duration time.Duration
		number   string
	}{
		{0, "0"},
		{999, "0"},
		{1000, "0.001"},
		{1234567, "1.234"},
		{time.Second, "1000"},
		{-1234567, "-1.234"},
		{time.Duration(1<<63 - 1), "9223372036854.775"},
	} {
		encoded, err := build(logline.Firing{Duration: c.duration}).Marshal()
		if err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(string(encoded), `"durationMs":`+c.number+",") {
			t.Errorf("duration %s: %s; want JSON number %s", c.duration, encoded, c.number)
		}
	}
}

func members(t *testing.T, line logline.Line) map[string]any {
	t.Helper()
	encoded, err := line.Marshal()
	if err != nil {
		t.Fatal(err)
	}
	var got map[string]any
	if err := json.Unmarshal(encoded, &got); err != nil {
		t.Fatal(err)
	}
	return got
}

func TestBuildWritesTheRequiredFieldsAndUsageKeys(t *testing.T) {
	for _, c := range []struct {
		name   string
		firing logline.Firing
		want   map[string]any
	}{
		{
			name: "a normal line keeps zero duration",
			want: map[string]any{
				"time": "2026-11-05T03:34:56.789Z", "release": "dev", "harness": "other",
				"event": "other", "tool": "other", "kind": "none", "hook": "other", "outcome": "pass",
				"durationMs": float64(0), "traceId": "02000000000000000000000000000000", "spanId": "0100000000000000",
			},
		},
		{
			name: "usage has exactly six keys and uses the fallback trace",
			firing: logline.Firing{
				Usage: true, Harness: "claude", Event: "pre", Hook: "command-guard",
				Call:     &ir.Call{Kind: ir.KindShell, Tool: "Bash"},
				Outcome:  ir.Outcome{Action: ir.Block, Rule: ir.RuleHookFailed},
				Duration: time.Second, Error: logline.ErrHookFailed, Mismatch: logline.MismatchInput, Wd: "/project",
			},
			want: map[string]any{
				"time": "2026-11-05T03:34:56.789Z", "release": "dev", "harness": "claude",
				"error": "usage", "traceId": "02000000000000000000000000000000", "spanId": "0100000000000000",
			},
		},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := members(t, build(c.firing)); !reflect.DeepEqual(got, c.want) {
				t.Fatalf("line = %#v; want %#v", got, c.want)
			}
		})
	}
}
