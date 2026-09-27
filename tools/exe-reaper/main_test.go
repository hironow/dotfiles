package main

import (
	"errors"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
)

// L2's view of lease.json, from one read. The rows that matter are the ones
// where the object is NOT a readable lease: every one of them has to count as a
// read failure, because that is what gives L1 its two ticks to drain before L2
// forces (section 3.2), and what the Quint model's leaseReadBreaks means by
// "the object was deleted, the bucket is 503-ing".
func TestLeaseFromRead(t *testing.T) {
	deadline := time.Date(2026, 9, 27, 1, 0, 0, 0, time.UTC)
	valid := []byte(`{"deadline":"2026-09-27T01:00:00Z"}`)

	cases := []struct {
		name       string
		body       []byte
		generation int64
		err        error
		wantOK     bool
		wantLease  lease.Lease
	}{
		{
			name: "a readable lease carries the generation of the SAME read", body: valid, generation: 7,
			wantOK: true, wantLease: lease.Lease{Deadline: deadline, Generation: 7},
		},
		{
			// Deleted is not "expired long ago". Read that way, a deleted lease
			// forces the pool on the next tick, over the top of an L1 drain that
			// is saving the actors; read as a failure, L1 gets its two ticks.
			name: "a deleted lease is a read failure, not an expired lease", err: gcp.ErrNotFound,
			wantOK: false,
		},
		{
			name: "a transport error is a read failure", err: errors.New("503 from GCS"),
			wantOK: false,
		},
		{
			name: "an unparsable body is a read failure", body: []byte(`{"deadline":`), generation: 3,
			wantOK: false,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, ok := leaseFromRead(tc.body, tc.generation, tc.err)
			if ok != tc.wantOK {
				t.Fatalf("ok = %v, want %v", ok, tc.wantOK)
			}
			if !got.Deadline.Equal(tc.wantLease.Deadline) || got.Generation != tc.wantLease.Generation {
				t.Fatalf("lease = %+v, want %+v", got, tc.wantLease)
			}
		})
	}
}

// End to end through the shipped decision: with lease.json gone and the pool
// up, L2 waits on the first two ticks and forces on the third. This is the
// Phase 3 e2e "with lease.json deleted the pool returns to 0 after three ticks",
// minus the cloud.
func TestADeletedLeaseForcesOnTheThirdTick(t *testing.T) {
	now := time.Date(2026, 9, 27, 1, 0, 0, 0, time.UTC)
	failures := 0
	for tick := 1; tick <= 3; tick++ {
		l, ok := leaseFromRead(nil, 0, gcp.ErrNotFound)
		if !ok {
			failures++
		}
		d := lease.DecideL2(lease.Observation{
			Now: now, Lease: l, LeaseOK: ok, ConsecutiveReadFailures: failures, Nodes: 1,
		})
		wantForced := tick == lease.LeaseReadFailureThreshold
		if gotForced := d.Action == lease.ActionStopForced; gotForced != wantForced {
			t.Fatalf("tick %d: action %s (%s); forced = %v, want %v", tick, d.Action, d.Reason, gotForced, wantForced)
		}
		now = now.Add(lease.L2Tick)
	}
}

// A pool size L2 cannot read counts as "may be up", never as "asleep". Asleep
// is DecideL2's first rule ("nothing to do"), so reading an error as zero makes
// the money stop inert exactly when its view of the pool is broken. "May be up"
// costs at most a redundant setSize(0), which L3 shows is a harmless 200 on a
// pool that is already at zero.
func TestAnUnreadablePoolSizeCountsAsUp(t *testing.T) {
	cases := []struct {
		name string
		size int
		err  error
		want int
	}{
		{"a read size is used as is", 2, nil, 2},
		{"a read zero is asleep", 0, nil, 0},
		{"an unreadable size is up, not asleep", 0, errors.New("403 on the instance group"), 1},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := nodesForDecision(tc.size, tc.err); got != tc.want {
				t.Fatalf("nodesForDecision(%d, %v) = %d, want %d", tc.size, tc.err, got, tc.want)
			}
		})
	}
}
