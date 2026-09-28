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
	// WokenAt is when the node was last woken: `wake` writes it, `extend` and
	// `sleep` carry it over. It is what restarts L1's idle clock, and nothing
	// else does -- an extend is not a new session (the model's finding 3).
	WokenAt time.Time `json:"wokenAt,omitzero"`
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
	// Reason is why L1 began this drain: ReasonDeadlinePassed, ReasonIdle or
	// ReasonLeaseUnreadable. Only an idle drain may stop the pool before its
	// lease's deadline (DecideL2).
	Reason Reason `json:"reason,omitempty"`
	// IdleSince is the first L1 tick that saw no task actor awake; zero while
	// one is. Carried here because L1 is a CronJob: a process per minute, with
	// no memory of the last one.
	IdleSince time.Time `json:"idleSince,omitzero"`
	// BaselineCrashed is every task actor that was already CRASHED when this
	// drain began. Any other crash before `drained` is a loss the drain must
	// report instead of calling it graceful (NoSilentLoss in the model).
	BaselineCrashed []string `json:"baselineCrashed,omitempty"`
	// WedgeSeen maps each actor stuck in DELETING while holding a worker to the
	// tick L1 first saw it so, for WedgeClear.
	WedgeSeen map[string]time.Time `json:"wedgeSeen,omitempty"`
	// Failure says why a drain-failed record failed: FailureCeiling or
	// FailureLost. Reporting only; L2 forces on either.
	Failure string `json:"failure,omitempty"`
}

// Why a drain failed.
const (
	FailureCeiling = "ceiling"
	FailureLost    = "lost"
)

// Stale reports whether this drain record describes a lease that has since been
// replaced.
func (d Drain) Stale(l Lease) bool {
	return d.Phase != DrainNone && d.LeaseGeneration != l.Generation
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
	// ReasonIdleDrained is L2 stopping a pool whose lease is still live: L1
	// finished an idle drain about this lease, and billing on to the deadline
	// would buy nothing.
	ReasonIdleDrained Reason = "idle-drained"
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

// --- L1 -----------------------------------------------------------------------

// ActorState is how L1 classifies an actor's Substrate state. The store's
// states map onto it in the reaper's Substrate client:
//
//	RUNNING, RESUMING, PAUSING, PAUSED   ActorAwake (a live sandbox)
//	SUSPENDING                           ActorCheckpointing (a suspend in flight)
//	SUSPENDED                            ActorAtRest
//	CRASHED                              ActorCrashed
//	DELETING                             ActorDeleting
//
// An actor whose worker pod is already gone still reads RUNNING until
// Substrate notices, so it is ActorAwake here: L1 cannot tell, and does not
// need to.
type ActorState string

const (
	ActorAtRest        ActorState = "at-rest"
	ActorAwake         ActorState = "awake"
	ActorCheckpointing ActorState = "checkpointing"
	ActorCrashed       ActorState = "crashed"
	ActorDeleting      ActorState = "deleting"
)

// ActorObs is one actor as L1 observed it this tick.
type ActorObs struct {
	UID   string
	State ActorState
	// Golden marks an actor in Substrate's ate-golden atespace, which its
	// template reconciler drives. L1 never suspends one; it waits for it.
	Golden bool
	// Task is the AX task whose actor this is (AX names the actor after the
	// task), or empty for a golden actor.
	Task string
	// Worker is the worker pod the actor is assigned to, if any.
	Worker string
	// ChangedAt is the actor's update_time in the store, which every write
	// moves. The drain does not read it; retention's TTL counts from it.
	ChangedAt time.Time
}

// L1Observation is everything L1 sees on one tick: the lease, its own record,
// every actor in every atespace, whether a template is still in flight, and
// the two resume paths it owns.
type L1Observation struct {
	Now     time.Time
	Lease   Lease
	LeaseOK bool
	Drain   Drain
	Actors  []ActorObs
	// TemplatesPending: some ActorTemplate's golden snapshot is neither
	// written nor failed, so Substrate's reconciler may resume a golden actor.
	TemplatesPending bool
	// The replica counts L1 set, and the pods actually present -- a
	// terminating pod still counts, because it can still execute a resume.
	RouterReplicas     int
	ControllerReplicas int
	RouterPods         int
	ControllerPods     int
}

// L1Branch is the rule one L1 tick took: the same names as the model's l1*
// actions, which is what lets TestDecideL1AgreesWithTheModel compare them.
type L1Branch string

const (
	L1NoOp      L1Branch = "NoOp"
	L1Reopen    L1Branch = "Reopen"
	L1Cancel    L1Branch = "Cancel"
	L1Begin     L1Branch = "Begin"
	L1Lost      L1Branch = "Lost"
	L1Finish    L1Branch = "Finish"
	L1GiveUp    L1Branch = "GiveUp"
	L1Resuspend L1Branch = "Resuspend"
	L1Suspend   L1Branch = "Suspend"
	L1Quiesce   L1Branch = "Quiesce"
	L1Wait      L1Branch = "Wait"
	L1Settled   L1Branch = "Settled"
)

// L1Decision is what one L1 tick does. Everything in it is a target state, so
// acting on it twice is harmless: the drain.json to hold, the replica counts to
// hold, the tasks to ask AX to suspend, and the worker pods to delete.
type L1Decision struct {
	Branch             L1Branch
	Drain              Drain
	RouterReplicas     int
	ControllerReplicas int
	// Suspend lists AX task names whose actors are awake: a suspend request
	// for each (idempotent in AX).
	Suspend []string
	// ClearWorkers lists worker pods to delete: each hosts only an actor stuck
	// in DELETING for WedgeClear or longer.
	ClearWorkers []string
}
