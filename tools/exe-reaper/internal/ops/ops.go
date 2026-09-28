// Package ops names the objects in the ops bucket and reads the lease out of
// one, for every binary that touches them: the operator's CLI and L2's
// enforcer (exe-reaper) and L1's reaper (exe-reap).
//
// Each object has exactly one writer, declared in exe/lease-constants.json
// (_writers). tofu/exe-platform/iam.tf grants each service identity write
// access to its own objects and no others, and
// tests/unit/test_lease_constants_lockstep.py fails if a name here is one that
// table does not declare.
package ops

import (
	"encoding/json"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
)

const (
	// LeaseObject is the operator's lease (L0: wake / extend / sleep).
	LeaseObject = "lease.json"
	// DrainObject is L1's drain record.
	DrainObject = "drain.json"
	// EnforceObject is L2's record of its last tick.
	EnforceObject = "enforce.json"
	// KeepObject lists the tasks the operator exempted from the task TTL. One
	// writer, like the lease: `keep add|rm` on the operator's Mac.
	KeepObject = "keep.json"
)

// LeaseFromRead is the view of one read of LeaseObject: the lease, and whether
// it was readable at all.
//
// The generation comes from the SAME read as the body. It is what a drain
// record is checked against, and a second read for it could return a newer
// generation than the body it is paired with -- an extend landing in between
// would then make an old `drained` look current.
//
// A deleted lease is a read failure, not an expired lease, exactly as the Quint
// model's leaseReadBreaks has it ("the object was deleted, the bucket is
// 503-ing"). The difference is who stops the pool: read as expired-long-ago, a
// deleted lease is forced on the very next tick, over the top of an L1 drain that
// is saving the actors; read as a failure, L1 gets its two ticks, and L2 forces on
// the third.
func LeaseFromRead(body []byte, generation int64, err error) (lease.Lease, bool) {
	if err != nil {
		return lease.Lease{}, false
	}
	var l lease.Lease
	if json.Unmarshal(body, &l) != nil {
		return lease.Lease{}, false
	}
	l.Generation = generation
	return l, true
}
