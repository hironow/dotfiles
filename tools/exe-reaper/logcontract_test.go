package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
)

// The log contract `exe-reaper enforce` writes, and tofu/exe-platform's two L2
// alerts read (monitoring.tf, pinned in tests/l2_enforcer.tofutest.hcl): one
// JSON object per line on stdout, "severity" lifted by Cloud Run into the
// entry's level, L2's fields under exe_l2. A decision line (event "decision")
// once per tick, at ERROR exactly for the first forced stop of a lease
// generation; a failure line (event "failure") at ERROR as the last line before
// exit 1. The forced-stop alert pages on the first, the failed-execution alert
// on any other ERROR -- so this file is what makes either one fire, or not.

type contractLine struct {
	Severity string         `json:"severity"`
	Message  string         `json:"message"`
	L2       map[string]any `json:"exe_l2"`
}

// contractLines decodes everything a tick wrote. A line that is not a JSON
// object with a severity, a message and exe_l2.event fails the test: Cloud Run
// would log it as plain text that neither alert can match.
func contractLines(t *testing.T, out *bytes.Buffer) []contractLine {
	t.Helper()
	var lines []contractLine
	scanner := bufio.NewScanner(bytes.NewReader(out.Bytes()))
	for scanner.Scan() {
		var line contractLine
		if err := json.Unmarshal(scanner.Bytes(), &line); err != nil {
			t.Fatalf("not a JSON line: %q (%v)", scanner.Text(), err)
		}
		if line.Severity == "" || line.Message == "" || line.L2["event"] == nil {
			t.Fatalf("line misses severity, message or exe_l2.event: %q", scanner.Text())
		}
		lines = append(lines, line)
	}
	return lines
}

// decisionLine is the one decision line a tick wrote.
func decisionLine(t *testing.T, out *bytes.Buffer) contractLine {
	t.Helper()
	var found []contractLine
	for _, line := range contractLines(t, out) {
		if line.L2["event"] == "decision" {
			found = append(found, line)
		}
	}
	if len(found) != 1 {
		t.Fatalf("want exactly one decision line, got %d in:\n%s", len(found), out)
	}
	return found[0]
}

func TestEveryTickWritesOneDecisionLine(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.targetSize = 1
	cloud.put(leaseObject, lease.Lease{Deadline: now.Add(time.Hour)})
	generation := cloud.object(leaseObject).generation

	var out bytes.Buffer
	cloud.tickAt(now, &out)

	line := decisionLine(t, &out)
	want := map[string]any{
		"event":           "decision",
		"action":          "wait",
		"reason":          "within-lease",
		"notify":          false,
		"nodes":           float64(1),
		"readFailures":    float64(0),
		"leaseGeneration": float64(generation),
	}
	for key, value := range want {
		if line.L2[key] != value {
			t.Errorf("exe_l2.%s = %v, want %v (line %+v)", key, line.L2[key], value, line)
		}
	}
	if line.Severity != "INFO" {
		t.Errorf("a wait is INFO, got %s", line.Severity)
	}
}

// One stuck stop must page once, not on every tick all night: the stop is
// repeated while the pool reads as up, but only the first of a run of forced
// stops under one lease generation is at ERROR. A NEW lease that is forced
// pages again.
func TestAStuckForcedStopPagesOnce(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.targetSize = 1
	cloud.put(leaseObject, lease.Lease{Deadline: now.Add(-2 * time.Hour)})
	first := cloud.object(leaseObject).generation

	tick := func(at time.Time) contractLine {
		t.Helper()
		var out bytes.Buffer
		cloud.tickAt(at, &out)
		return decisionLine(t, &out)
	}

	line := tick(now)
	if line.L2["action"] != "stop-forced" || line.L2["notify"] != true || line.Severity != "ERROR" {
		t.Fatalf("first forced stop of generation %d: want stop-forced, notify, ERROR; got %+v", first, line)
	}
	if rec := cloud.storedRecord(); !rec.Notified || rec.LeaseGeneration != first {
		t.Fatalf("the record must say it paged, and for which generation: %+v", rec)
	}

	// The pool reads as up again with no new lease: the stop did not take, or
	// the size read is wrong. Stop again, quietly.
	cloud.targetSize = 1
	line = tick(now.Add(lease.L2Tick))
	if line.L2["action"] != "stop-forced" || line.L2["notify"] != false || line.Severity != "WARNING" {
		t.Fatalf("repeat forced stop of the same generation: want stop-forced, no notify, WARNING; got %+v", line)
	}
	if got := cloud.setSizes(); len(got) != 2 {
		t.Errorf("setSize calls = %v, want the stop made on both ticks", got)
	}

	// A new lease, which also ran out: that is a new forced stop to hear about.
	cloud.targetSize = 1
	cloud.put(leaseObject, lease.Lease{Deadline: now.Add(-time.Hour)})
	line = tick(now.Add(2 * lease.L2Tick))
	if line.L2["notify"] != true || line.Severity != "ERROR" {
		t.Fatalf("first forced stop of a new generation must page again; got %+v", line)
	}
}

// A blind stop has no lease to name, so it is keyed on the last generation L2
// read, and a run of them pages once, like any other.
func TestARunOfBlindStopsPagesOnce(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.targetSize = 1
	cloud.put(leaseObject, lease.Lease{Deadline: now.Add(8 * time.Hour)})
	generation := cloud.object(leaseObject).generation

	var lines []contractLine
	for tick := range 5 {
		if tick == 1 {
			cloud.getStatus[leaseObject] = http.StatusServiceUnavailable
		}
		cloud.targetSize = 1 // the stop on tick 3 is not seen to take
		var out bytes.Buffer
		cloud.tickAt(now.Add(time.Duration(tick)*lease.L2Tick), &out)
		lines = append(lines, decisionLine(t, &out))
	}

	paged := 0
	for i, line := range lines {
		if line.L2["notify"] == true {
			paged++
			if i != 3 || line.L2["reason"] != "lease-unreadable" || line.Severity != "ERROR" {
				t.Errorf("tick %d paged: %+v", i, line)
			}
		}
	}
	if paged != 1 {
		t.Errorf("paged %d times over ticks %+v, want once", paged, lines)
	}
	if rec := cloud.storedRecord(); rec.LeaseGeneration != generation {
		t.Errorf("blind stops are keyed on the last lease read (%d): %+v", generation, rec)
	}
}

// Found by the 3.7 e2e on the real platform. A forced stop paged for one lease;
// the pool went to zero; the operator woke it again, and the new lease was
// deleted before any tick read it. Three ticks later the blind stop carried the
// OLD lease's generation as its key -- the only one L2 had read -- and was
// taken for a repeat of the stop already paged for. It is a new stop. What
// makes a repeat is the tick right before it: a forced stop under the same key.
func TestAForcedStopAfterAnyOtherTickPages(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.targetSize = 1
	cloud.put(leaseObject, lease.Lease{Deadline: now.Add(-2 * time.Hour)})

	tick := func(n int) contractLine {
		t.Helper()
		var out bytes.Buffer
		cloud.tickAt(now.Add(time.Duration(n)*lease.L2Tick), &out)
		return decisionLine(t, &out)
	}

	if line := tick(0); line.L2["notify"] != true {
		t.Fatalf("the first forced stop must page: %+v", line)
	}
	if line := tick(1); line.L2["reason"] != "already-stopped" {
		t.Fatalf("the stop took, so the next tick finds the pool at zero: %+v", line)
	}

	// A new wake, and its lease is gone before any tick reads it.
	cloud.targetSize = 1
	cloud.put(leaseObject, lease.Lease{Deadline: now.Add(8 * time.Hour)})
	cloud.getStatus[leaseObject] = http.StatusNotFound

	var line contractLine
	for n := 2; n <= 4; n++ {
		line = tick(n)
	}
	if line.L2["reason"] != "lease-unreadable" || line.L2["notify"] != true || line.Severity != "ERROR" {
		t.Fatalf("the blind stop of the new wake must page; got %+v", line)
	}
}

// A dry run changes nothing, records nothing and so pages nothing.
func TestADryRunNeverPages(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.targetSize = 1
	cloud.put(leaseObject, lease.Lease{Deadline: now.Add(-2 * time.Hour)})

	var out bytes.Buffer
	if err := cloud.enforcer(&out).tick(t.Context(), now, true); err != nil {
		t.Fatal(err)
	}

	line := decisionLine(t, &out)
	if line.L2["action"] != "stop-forced" || line.L2["notify"] != false || line.Severity == "ERROR" {
		t.Errorf("dry run: want the forced decision reported without a page; got %+v", line)
	}
	if got := cloud.setSizes(); len(got) != 0 {
		t.Errorf("a dry run called setSize: %v", got)
	}
}

// What the tick worked around is WARNING, never ERROR: at ERROR it would page
// as a failed execution on a tick that did its job.
func TestAWorkaroundIsAWarningLine(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.sizeStatus = http.StatusForbidden
	cloud.put(leaseObject, lease.Lease{Deadline: now.Add(time.Hour)})

	var out bytes.Buffer
	cloud.tickAt(now, &out)

	warned := false
	for _, line := range contractLines(t, &out) {
		if line.Severity == "ERROR" {
			t.Errorf("a tick that succeeded wrote an ERROR line: %+v", line)
		}
		if line.L2["event"] == "warning" && line.Severity == "WARNING" &&
			strings.Contains(line.Message, "node pool size") {
			warned = true
		}
	}
	if !warned {
		t.Errorf("no WARNING line about the unreadable pool size in:\n%s", out.String())
	}
}

// A failed tick's last line is the failure line, and the exit code is 1: that
// pair is what the failed-execution alert and Cloud Run's own record see.
func TestAFailedTickEndsWithTheFailureLine(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.targetSize = 1
	cloud.setSizeStatus = http.StatusForbidden
	cloud.put(leaseObject, lease.Lease{Deadline: now.Add(-2 * time.Hour)})

	var out bytes.Buffer
	if code := cloud.enforcer(&out).run(t.Context(), now, false); code != 1 {
		t.Fatalf("exit code = %d, want 1", code)
	}

	lines := contractLines(t, &out)
	last := lines[len(lines)-1]
	if last.L2["event"] != "failure" || last.Severity != "ERROR" {
		t.Fatalf("last line = %+v, want the failure line at ERROR", last)
	}
	if msg, _ := last.L2["error"].(string); !strings.Contains(msg, "stopping the node pool") {
		t.Errorf("failure line should carry the error: %+v", last)
	}
	for _, line := range lines {
		if line.L2["event"] == "decision" && line.L2["notify"] == true {
			t.Errorf("a forced stop that was never made must not page as one: %+v", line)
		}
	}
}
