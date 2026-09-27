package lease

import (
	"errors"
	"fmt"
	"time"
)

// DrainPhase is L1's progress, as recorded in drain.json.
type DrainPhase string

const (
	// DrainNone means L1 has not started, or its record was invalidated by a
	// successful extend.
	DrainNone DrainPhase = ""
	// DrainDraining means L1 is working: the router is down and actors are
	// being suspended. The heartbeat is what makes this distinguishable from a
	// crashed L1.
	DrainDraining DrainPhase = "draining"
	// DrainDrained means every actor is suspended and the pool is safe to
	// shrink without losing state.
	DrainDrained DrainPhase = "drained"
	// DrainFailed means L1 hit the ceiling and gave up. State may be lost if
	// the pool shrinks now, but decision Q14 puts the cost ceiling first.
	DrainFailed DrainPhase = "drain-failed"
)

// Lease is the operator's object: the only thing that authorises a node to run.
// Exactly one writer (wake / extend / sleep), and every write is conditional on
// Generation so two operators racing cannot both win.
type Lease struct {
	// Deadline is when the node stops being authorised. Always set: there is no
	// representation of an unbounded lease, which is the point of the design.
	Deadline time.Time `json:"deadline"`
	// Generation is the GCS object generation the value was read at. It is what
	// makes "extend invalidates a stale drained record" decidable: a drain
	// record carries the generation it was drained against.
	Generation int64 `json:"-"`
}

// Drain is L1's object. Exactly one writer: the in-cluster reaper.
type Drain struct {
	Phase DrainPhase `json:"phase"`
	// Heartbeat is refreshed on every L1 tick while draining. L2 reads it to
	// tell a slow drain from a dead one.
	Heartbeat time.Time `json:"heartbeat"`
	// LeaseGeneration is the lease this record describes. A successful extend
	// bumps the lease generation, which strands this record -- exactly the
	// "extend invalidates a prior drained" requirement, decided by comparison
	// rather than by L1 remembering to clean up after itself.
	LeaseGeneration int64 `json:"leaseGeneration"`
	// StartedAt is when this drain began, used against DrainCeiling.
	StartedAt time.Time `json:"startedAt"`
}

// Stale reports whether this drain record describes a lease that has since been
// replaced.
func (d Drain) Stale(l Lease) bool {
	return d.Phase != DrainNone && d.LeaseGeneration != l.Generation
}

// Enforce is L2's object: a record of what it decided and when. Exactly one
// writer, and nothing reads it to make a decision -- it exists so a human can
// reconstruct why the cluster stopped.
type Enforce struct {
	At       time.Time `json:"at"`
	Action   string    `json:"action"`
	Reason   string    `json:"reason"`
	Notified bool      `json:"notified"`
}

// Observation is everything L2 sees on one tick. Grouping it in a struct rather
// than passing six arguments keeps the decision function's signature stable as
// the design grows, and makes the table-driven tests readable.
type Observation struct {
	Now time.Time
	// Lease and LeaseOK: LeaseOK false means this tick could not read it.
	Lease   Lease
	LeaseOK bool
	// ConsecutiveReadFailures counts ticks in a row that failed, including this
	// one. It is carried in enforce.json, because L2 is a job that exits: it
	// has no memory of its own.
	ConsecutiveReadFailures int
	Drain                   Drain
	// Nodes is the node pool's current size.
	Nodes int
}

// Action is what L2 does on a tick.
type Action string

const (
	// ActionWait means do nothing. The most common outcome, and the one that
	// has to be right: a spurious stop destroys work.
	ActionWait Action = "wait"
	// ActionStopGraceful shrinks the pool knowing nothing is awake.
	ActionStopGraceful Action = "stop-graceful"
	// ActionStopForced shrinks the pool anyway, and notifies, because the cost
	// ceiling wins over the work (decision Q14).
	ActionStopForced Action = "stop-forced"
)

// Reason is the specific rule that fired. Kept as a distinct type so the
// decision tables assert on the rule, not just the action -- two different bugs
// can produce the right action for the wrong reason, and only one of them shows
// up later.
type Reason string

const (
	ReasonAlreadyStopped        Reason = "already-stopped"
	ReasonWithinLease           Reason = "within-lease"
	ReasonTransientReadFailure  Reason = "transient-read-failure"
	ReasonLeaseUnreadable       Reason = "lease-unreadable"
	ReasonDrained               Reason = "drained"
	ReasonDrainFailed           Reason = "drain-failed"
	ReasonDrainingWithHeartbeat Reason = "draining-with-heartbeat"
	ReasonHeartbeatStale        Reason = "heartbeat-stale"
	ReasonGraceExpired          Reason = "grace-expired"
	ReasonAwaitingDrain         Reason = "awaiting-drain"
	// L1 trigger reasons. Separate from L2's because the two layers answer
	// different questions: L1 asks "should I start draining?", L2 asks "may I
	// shrink the pool?".
	ReasonDeadlinePassed Reason = "deadline-passed"
	ReasonIdle           Reason = "idle-zero-running"
	ReasonAuthorised     Reason = "authorised"
)

// Decision is L2's verdict for one tick.
type Decision struct {
	Action Action
	Reason Reason
}

// Notify reports whether this decision should page the operator. Only a forced
// stop does: a graceful stop is the system working.
func (d Decision) Notify() bool {
	return d.Action == ActionStopForced
}

// Errors the L0 commands return. Sentinels rather than strings so the CLI can
// choose an exit code and the tests can assert without matching prose.
var (
	// ErrLeaseTooLong is a request above MaxLease. Refused, not clamped.
	ErrLeaseTooLong = errors.New("requested lease exceeds the maximum for a single wake or extend")
	// ErrInsideCapWindow is a wake attempted between the nightly cap and L3.
	// There is no lease that both respects the cap and is longer than zero, so
	// the honest answer is no.
	ErrInsideCapWindow = errors.New("inside the nightly cap window: a lease now could not outlive the daily stop")
	// ErrNonPositiveLease is a zero or negative request.
	ErrNonPositiveLease = errors.New("requested lease must be positive")
)

// LeaseTooLongError wraps ErrLeaseTooLong with the numbers, because "8h max" is
// the single most likely thing for an operator to be surprised by.
func LeaseTooLongError(requested time.Duration) error {
	return fmt.Errorf("%w: asked for %s, maximum is %s", ErrLeaseTooLong, requested, MaxLease)
}
