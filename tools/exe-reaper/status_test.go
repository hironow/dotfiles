package main

import (
	"slices"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
)

// exe-status reads tasks.json while the node sleeps and warns about tasks the
// TTL will delete (plan D10: "deleted at the first wake after 30 days", with
// a 7-day notice).

func TestTheTtlNoticeNamesTasksDueWithinTheWarning(t *testing.T) {
	now := time.Date(2026, 10, 20, 3, 0, 0, 0, time.UTC)
	rec := lease.TasksRecord{Tasks: []lease.TaskRecord{
		{Task: "exe/soon", Suspended: true, DeleteAt: now.Add(3 * 24 * time.Hour)},
		{Task: "exe/due", Suspended: true, DeleteAt: now.Add(-time.Hour)},
		{Task: "exe/later", Suspended: true, DeleteAt: now.Add(lease.TaskTTLWarning + time.Hour)},
		{Task: "exe/kept", Suspended: true, Kept: true},
		{Task: "exe/running"},
	}}

	got := ttlNotice(rec, now)
	want := []string{
		"exe/due is past its TTL and is deleted at the next wake (keep it: just exe-keep add exe/due)",
		"exe/soon is deleted at the first wake after 2026-10-23T12:00:00+09:00 (keep it: just exe-keep add exe/soon)",
	}
	if !slices.Equal(got, want) {
		t.Errorf("notice:\n got %q\nwant %q", got, want)
	}
}

func TestTheDrainLineSaysWhatThePhaseMeans(t *testing.T) {
	idle := time.Date(2026, 9, 28, 5, 8, 3, 0, time.UTC)
	tests := []struct {
		drain lease.Drain
		want  string
	}{
		{lease.Drain{}, "none"},
		{lease.Drain{IdleSince: idle}, "none (nothing awake since 2026-09-28T14:08:03+09:00)"},
		{
			lease.Drain{Phase: lease.DrainDraining, Heartbeat: idle, LeaseGeneration: 7, Reason: lease.ReasonDeadlinePassed},
			"draining for deadline-passed (heartbeat 2026-09-28T14:08:03+09:00, lease generation 7)",
		},
		{
			lease.Drain{Phase: lease.DrainFailed, Heartbeat: idle, LeaseGeneration: 7, Reason: lease.ReasonIdle, Failure: lease.FailureLost},
			"drain-failed (lost) for idle-zero-running (heartbeat 2026-09-28T14:08:03+09:00, lease generation 7)",
		},
	}
	for _, tc := range tests {
		if got := describeDrain(tc.drain); got != tc.want {
			t.Errorf("describeDrain(%+v)\n got %q\nwant %q", tc.drain, got, tc.want)
		}
	}
}
