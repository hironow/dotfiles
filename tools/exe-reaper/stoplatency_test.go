package main

import (
	"bytes"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ops"
)

// L2's stop-latency detector, through a whole tick (inbox M18, layer 3): the
// pool's target reads zero the moment setSize(0) is accepted, while the VM is
// still being deleted and still bills. A node that outlives StopLatency after
// its target went to zero is the Phase 4 incident -- a disruption budget
// holding the drain -- and it pages, once per stop.

// stopLatencyLines is every stop-latency line a tick wrote.
func stopLatencyLines(t *testing.T, out *bytes.Buffer) []contractLine {
	t.Helper()
	var found []contractLine
	for _, line := range contractLines(t, out) {
		if line.L2["event"] == "stop-latency" {
			found = append(found, line)
		}
	}
	return found
}

func TestAStopThatOutlivesItsLatencyPagesOnce(t *testing.T) {
	// given a pool whose target is zero while its VM is still there
	t0 := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.put(ops.LeaseObject, lease.Lease{Deadline: t0.Add(-2 * time.Hour)})
	cloud.targetSize, cloud.instances = 0, 1

	tick := func(at time.Time) []contractLine {
		t.Helper()
		var out bytes.Buffer
		cloud.tickAt(at, &out)
		if d := decisionLine(t, &out); d.L2["reason"] != string(lease.ReasonAlreadyStopped) {
			t.Fatalf("a pool at target zero is already stopped; got %+v", d)
		}
		return stopLatencyLines(t, &out)
	}

	// when the first tick sees it, it only remembers when
	if lines := tick(t0); len(lines) != 0 {
		t.Fatalf("first sight must not page: %+v", lines)
	}
	if rec := cloud.storedRecord(); !rec.StoppingSince.Equal(t0) {
		t.Fatalf("stoppingSince = %s, want %s", rec.StoppingSince, t0)
	}

	// then a tick past the latency pages, at ERROR
	lines := tick(t0.Add(lease.L2Tick))
	if len(lines) != 1 || lines[0].Severity != "ERROR" || lines[0].L2["notify"] != true {
		t.Fatalf("past the latency: want one ERROR stop-latency line with notify; got %+v", lines)
	}
	if lines[0].L2["instances"] != float64(1) || lines[0].L2["target"] != float64(0) {
		t.Errorf("the line must say what is there: %+v", lines[0].L2)
	}

	// and the next tick of the same stop repeats it quietly
	lines = tick(t0.Add(2 * lease.L2Tick))
	if len(lines) != 1 || lines[0].Severity != "WARNING" || lines[0].L2["notify"] != false {
		t.Fatalf("the same stop again: want one WARNING line without notify; got %+v", lines)
	}

	// until the node has gone, which clears the memory
	cloud.instances = 0
	if lines = tick(t0.Add(3 * lease.L2Tick)); len(lines) != 0 {
		t.Fatalf("a gone node must not page: %+v", lines)
	}
	if rec := cloud.storedRecord(); !rec.StoppingSince.IsZero() {
		t.Errorf("stoppingSince = %s after the node left, want zero", rec.StoppingSince)
	}
}

func TestAStopInsideItsLatencyNeverPages(t *testing.T) {
	t0 := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.put(ops.LeaseObject, lease.Lease{Deadline: t0.Add(-2 * time.Hour)})
	cloud.targetSize, cloud.instances = 0, 1

	var out bytes.Buffer
	cloud.tickAt(t0, &out)
	cloud.instances = 0 // gone within StopLatency, before L2 looks again
	out.Reset()
	cloud.tickAt(t0.Add(lease.L2Tick), &out)
	if lines := stopLatencyLines(t, &out); len(lines) != 0 {
		t.Fatalf("a stop inside its latency must not page: %+v", lines)
	}
}

func TestAStopLatencyPageIsNotAFailure(t *testing.T) {
	// The failed-execution alert pages on ERROR that is not a decision line;
	// the stop-latency page has its own alert, so its ERROR line must say
	// exactly which event it is (monitoring.tf excludes it by that name).
	t0 := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.put(ops.LeaseObject, lease.Lease{Deadline: t0.Add(-2 * time.Hour)})
	cloud.targetSize, cloud.instances = 0, 1
	var out bytes.Buffer
	cloud.tickAt(t0, &out)
	out.Reset()
	cloud.tickAt(t0.Add(lease.L2Tick), &out)
	for _, line := range contractLines(t, &out) {
		if line.Severity == "ERROR" && line.L2["event"] != "stop-latency" {
			t.Errorf("an ERROR line that is not the stop-latency page: %+v", line)
		}
	}
}
