package main

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
)

// The L0 writes and the wrappers' check, against the fake GCS. lease.json has
// one writer (wake / extend / sleep, on the operator's Mac); keep.json has one
// too (keep / unkeep). Every write is conditional on the generation it read.

func (f *fakeCloud) client() *gcp.Client { return f.enforcer(nil).client }

func (f *fakeCloud) storedLease() lease.Lease {
	f.t.Helper()
	var l lease.Lease
	if err := json.Unmarshal(f.object(leaseObject).body, &l); err != nil {
		f.t.Fatalf("lease.json: %v", err)
	}
	return l
}

func TestWakeWritesWokenAtAndExtendAndSleepCarryIt(t *testing.T) {
	// given no lease yet
	cloud := newFakeCloud(t)
	t0 := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)

	// when the operator wakes, then extends, then sleeps
	if err := writeLease(t.Context(), cloud.client(), fakeBucket, t0, t0.Add(time.Hour), true); err != nil {
		t.Fatalf("wake: %v", err)
	}
	if got := cloud.storedLease(); !got.WokenAt.Equal(t0) {
		t.Fatalf("wake wrote wokenAt %s, want %s", got.WokenAt, t0)
	}
	if err := writeLease(t.Context(), cloud.client(), fakeBucket, t0.Add(10*time.Minute), t0.Add(3*time.Hour), false); err != nil {
		t.Fatalf("extend: %v", err)
	}
	if got := cloud.storedLease(); !got.WokenAt.Equal(t0) || !got.Deadline.Equal(t0.Add(3*time.Hour)) {
		t.Fatalf("extend wrote %+v; it must move the deadline and carry wokenAt %s", got, t0)
	}
	if err := writeLease(t.Context(), cloud.client(), fakeBucket, t0.Add(20*time.Minute), t0.Add(20*time.Minute), false); err != nil {
		t.Fatalf("sleep: %v", err)
	}
	// then only the wake moved the idle clock's anchor
	if got := cloud.storedLease(); !got.WokenAt.Equal(t0) {
		t.Fatalf("sleep lost wokenAt: %+v", got)
	}
}

func TestALeaseWriteThatLosesTheRaceIsRefused(t *testing.T) {
	cloud := newFakeCloud(t)
	t0 := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud.put(leaseObject, lease.Lease{Deadline: t0.Add(time.Hour), WokenAt: t0})
	// Another writer lands between this command's read and its write.
	cloud.afterGet = func(f *fakeCloud, object string, n int) {
		if object == leaseObject && n == 1 {
			f.store(leaseObject, []byte(`{"deadline":"2026-09-27T07:00:00Z"}`))
		}
	}
	err := writeLease(t.Context(), cloud.client(), fakeBucket, t0, t0.Add(2*time.Hour), false)
	if !errors.Is(err, errLeaseMoved) {
		t.Fatalf("want errLeaseMoved, got %v", err)
	}
}

func TestMayStart(t *testing.T) {
	t0 := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	tests := []struct {
		name     string
		lease    *lease.Lease
		drain    *lease.Drain
		need     time.Duration
		wantOK   bool
		wantText string
	}{
		{"a lease with room to spare", &lease.Lease{Deadline: t0.Add(time.Hour)}, nil, 30 * time.Minute, true, ""},
		{"a lease too short for the job", &lease.Lease{Deadline: t0.Add(20 * time.Minute)}, nil, 30 * time.Minute, false, "20m0s left"},
		{"an expired lease", &lease.Lease{Deadline: t0.Add(-time.Minute)}, nil, time.Minute, false, "deadline-passed"},
		{"no lease at all", nil, nil, time.Minute, false, "lease-unreadable"},
		{"a drain about this lease", &lease.Lease{Deadline: t0.Add(time.Hour)}, &lease.Drain{Phase: lease.DrainDraining, LeaseGeneration: 1}, time.Minute, false, "draining"},
		{"a drain about an older lease does not refuse", &lease.Lease{Deadline: t0.Add(time.Hour)}, &lease.Drain{Phase: lease.DrainDrained, LeaseGeneration: 0}, time.Minute, true, ""},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			cloud := newFakeCloud(t)
			if tc.lease != nil {
				cloud.put(leaseObject, *tc.lease) // generation 1
			}
			if tc.drain != nil {
				cloud.put(drainObject, *tc.drain)
			}
			ok, why, err := mayStart(t.Context(), cloud.client(), fakeBucket, t0, tc.need)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if ok != tc.wantOK || !strings.Contains(why, tc.wantText) {
				t.Errorf("mayStart = (%v, %q), want (%v, containing %q)", ok, why, tc.wantOK, tc.wantText)
			}
		})
	}
}

func TestKeepAddRemoveList(t *testing.T) {
	cloud := newFakeCloud(t)
	ctx, c := t.Context(), cloud.client()

	for _, task := range []string{"t2", "t1", "t2"} {
		if err := keepEdit(ctx, c, fakeBucket, task, true); err != nil {
			t.Fatalf("keep add %s: %v", task, err)
		}
	}
	got, err := keepList(ctx, c, fakeBucket)
	if err != nil || strings.Join(got, ",") != "t1,t2" {
		t.Fatalf("keep ls = %v (%v), want [t1 t2]: sorted, no duplicates", got, err)
	}
	if err := keepEdit(ctx, c, fakeBucket, "t2", false); err != nil {
		t.Fatalf("keep rm: %v", err)
	}
	if got, _ = keepList(ctx, c, fakeBucket); strings.Join(got, ",") != "t1" {
		t.Fatalf("after rm: %v, want [t1]", got)
	}
	// Removing what is not kept is not an error: the end state is the ask.
	if err := keepEdit(ctx, c, fakeBucket, "t9", false); err != nil {
		t.Fatalf("keep rm of an unkept task: %v", err)
	}
}

func TestKeepListOfNothingIsEmpty(t *testing.T) {
	cloud := newFakeCloud(t)
	got, err := keepList(t.Context(), cloud.client(), fakeBucket)
	if err != nil || len(got) != 0 {
		t.Fatalf("keep ls with no keep.json = %v (%v), want empty", got, err)
	}
}

func TestAKeepEditThatLosesTheRaceIsRefused(t *testing.T) {
	cloud := newFakeCloud(t)
	cloud.put(keepObject, keepRecord{Tasks: []string{"t1"}})
	cloud.afterGet = func(f *fakeCloud, object string, n int) {
		if object == keepObject && n == 1 {
			f.store(keepObject, []byte(`{"tasks":["t1","t3"]}`))
		}
	}
	if err := keepEdit(t.Context(), cloud.client(), fakeBucket, "t2", true); !errors.Is(err, errKeepMoved) {
		t.Fatalf("want errKeepMoved, got %v", err)
	}
}
