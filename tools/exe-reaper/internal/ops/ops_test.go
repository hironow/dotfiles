package ops

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
			got, ok := LeaseFromRead(tc.body, tc.generation, tc.err)
			if ok != tc.wantOK {
				t.Fatalf("ok = %v, want %v", ok, tc.wantOK)
			}
			if !got.Deadline.Equal(tc.wantLease.Deadline) || got.Generation != tc.wantLease.Generation {
				t.Fatalf("lease = %+v, want %+v", got, tc.wantLease)
			}
		})
	}
}
