// Package lease holds the auto-sleep's decision logic, and nothing else.
//
// Everything in this package is pure: it takes a clock reading and the three
// lease objects and returns a decision. No I/O, no cloud client, no globals.
// That is deliberate — this is the code that decides to stop a cluster and
// destroy whatever is running on it, so it has to be exhaustively testable
// without a cluster, and it has to be the same code the seeded simulation
// drives against the Quint model's invariants.
//
// The four layers (docs/plan/exe-google-ax.md section 3.2):
//
//	L0  the lease itself: a wake always carries a deadline (this package clamps it)
//	L1  in-cluster graceful drain, every minute (trigger rule lives here)
//	L2  out-of-cluster enforcement, every 10 minutes (the three-way rule lives here)
//	L3  a daily unconditional stop, with no logic at all
package lease

import (
	"sync"
	"time"
)

// The numbers below mirror exe/lease-constants.json, which is the single source
// of truth: OpenTofu reads it with jsondecode to build the Scheduler cadences,
// the Quint model mirrors it, and constants_test.go fails if this file drifts
// from it. Three mirrors, three lockstep tests, one source.
const (
	// TimezoneName is the local time the nightly boundaries are expressed in.
	// Not UTC: the operator reasons about "03:00" and so must the code.
	TimezoneName = "Asia/Tokyo"

	// DefaultLease is what `exe-wake` with no argument asks for.
	DefaultLease = 120 * time.Minute

	// MaxLease is the ceiling on ONE wake or extend. It is not a ceiling on
	// total uptime: repeated extends are allowed, and each one is a deliberate
	// act by the operator. A request above this is refused, not clamped --
	// silently shortening what someone asked for is worse than saying no.
	MaxLease = 480 * time.Minute

	// L1Tick is how often the in-cluster drain loop runs.
	L1Tick = 1 * time.Minute

	// DrainCeiling is how long L1 may spend suspending actors before it gives
	// up and records drain-failed.
	DrainCeiling = 30 * time.Minute

	// L2Tick is how often the out-of-cluster enforcer runs.
	L2Tick = 10 * time.Minute

	// Slack is the margin in the cap formula below. It exists so that the
	// worst-case chain of ticks still finishes before L3 fires.
	Slack = 19 * time.Minute

	// L3StopHour is the local hour at which the unconditional daily stop runs.
	L3StopHour = 4

	// NightlyCapHour is the local hour past which no lease may extend. It is
	// STORED here for readability but never trusted: NightlyCap() recomputes it
	// from the other four constants, and the tests assert the two agree.
	NightlyCapHour = 3

	// ForceGrace is how long past a deadline L2 waits for a well-behaved drain
	// before forcing the stop anyway. Decision Q14, refined by review #2: a
	// healthy drain that is still making progress gets deadline + this much.
	ForceGrace = 45 * time.Minute

	// HeartbeatStaleTicks is how many L2 ticks a drain heartbeat may be old
	// before L2 treats the drain as dead rather than slow.
	HeartbeatStaleTicks = 2

	// IdleZeroRunning is how long the cluster must have zero running tasks
	// before L1 drains it on idleness rather than on the deadline.
	IdleZeroRunning = 30 * time.Minute

	// LeaseReadFailureThreshold is how many CONSECUTIVE failures to read the
	// lease make L2 force a stop. One or two do nothing: a transient GCS error
	// must not cost someone their work, and L1 is already draining if the lease
	// is genuinely unreadable from inside.
	LeaseReadFailureThreshold = 3

	// TaskTTL is how long a task may sit suspended before the reaper deletes
	// it; TaskTTLWarning is how far ahead exe-status warns (decision Q15).
	TaskTTL        = 30 * 24 * time.Hour
	TaskTTLWarning = 7 * 24 * time.Hour
)

// HeartbeatStaleAfter is the wall-clock window a drain heartbeat may be older
// than before L2 stops believing it.
func HeartbeatStaleAfter() time.Duration {
	return HeartbeatStaleTicks * L2Tick
}

// AwakeBound is how long past its deadline a node can stay up while L2 can read
// the lease: the grace, which nothing outlasts, plus one L2 period for the tick
// that lands after it. Plan section 3.2's "期限 + 45 分 + L2 の周期 10 分",
// and the bound the model's NodesEventuallyZero and the simulation check.
func AwakeBound() time.Duration {
	return ForceGrace + L2Tick
}

// BlindAwakeBound is the same bound when L2 cannot read the lease. The
// three-strike rule forbids forcing on the first two misses however late they
// come, so the first tick past the grace can be followed by threshold - 1 more.
func BlindAwakeBound() time.Duration {
	return AwakeBound() + L2Tick*(LeaseReadFailureThreshold-1)
}

// CapMargin is the total time the stopping chain can take in the worst case:
// one L1 tick to notice, a full drain ceiling to finish, one L2 tick to
// enforce, plus slack.
func CapMargin() time.Duration {
	return L1Tick + DrainCeiling + L2Tick + Slack
}

// NightlyCapHourComputed derives the cap hour from L3's hour and the margin,
// rather than trusting NightlyCapHour.
//
// This is the formula the whole design rests on: if no lease may pass this
// hour, then in normal operation L3 can never fire while an actor is awake --
// and on Agent Substrate v0.1.0, a stop that catches an awake actor destroys it
// with no recovery. A test asserts the computed value equals the stored one, so
// changing any of L1Tick / DrainCeiling / L2Tick / Slack without moving the cap
// fails the gate instead of quietly shortening the safety margin.
func NightlyCapHourComputed() int {
	margin := CapMargin()
	if margin%time.Hour != 0 {
		// The formula only makes sense on an hour boundary; a non-integral
		// margin means someone changed a constant without re-deriving the cap.
		return -1
	}
	return L3StopHour - int(margin/time.Hour)
}

// Location resolves the operator's timezone, falling back to a fixed +09:00
// offset when the host has no tzdata (a scratch container, most likely).
// Falling back rather than failing is right here: the fallback is correct for
// this timezone, and a reaper that refuses to run because tzdata is missing is
// a reaper that does not stop the cluster.
//
// Resolved once per process. time.LoadLocation reads and parses the zoneinfo
// file on every call, and the seeded simulation asks on every simulated minute.
func Location() *time.Location {
	return location()
}

var location = sync.OnceValue(func() *time.Location {
	if loc, err := time.LoadLocation(TimezoneName); err == nil {
		return loc
	}
	return time.FixedZone("JST", 9*60*60)
})
