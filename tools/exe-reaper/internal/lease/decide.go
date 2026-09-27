package lease

import "time"

// NextNightlyCap returns the first nightly-cap boundary strictly after now, in
// the operator's timezone.
//
// "Strictly after" matters: called exactly at 03:00:00 it returns tomorrow's
// 03:00, not the instant itself, so a lease is never created with a zero
// lifetime. The window check below is what actually stops a wake at that hour.
func NextNightlyCap(now time.Time) time.Time {
	loc := Location()
	local := now.In(loc)
	cap := time.Date(local.Year(), local.Month(), local.Day(), NightlyCapHour, 0, 0, 0, loc)
	if !cap.After(local) {
		cap = cap.AddDate(0, 0, 1)
	}
	return cap
}

// InCapWindow reports whether now falls in [NightlyCapHour, L3StopHour) local
// time -- the hour in which the daily stop is imminent and no lease can be
// honoured.
func InCapWindow(now time.Time) bool {
	hour := now.In(Location()).Hour()
	return hour >= NightlyCapHour && hour < L3StopHour
}

// ClampDeadline turns a requested duration into an actual deadline.
//
// Two different treatments, on purpose:
//
//   - A request longer than MaxLease is REFUSED. Silently shortening what
//     someone asked for means they believe they have eight hours when they have
//     two, and they find out when their work is gone.
//   - A deadline past the nightly cap is CLAMPED, and the caller is told by the
//     returned bool. That direction is safe to do quietly-but-visibly: the
//     operator still gets the longest lease that exists, and the alternative
//     (refusing every evening request) would make the tool unusable after
//     19:00.
//
// Inside the cap window there is no lease to give, so that is an error too.
func ClampDeadline(now time.Time, requested time.Duration) (deadline time.Time, clamped bool, err error) {
	if requested <= 0 {
		return time.Time{}, false, ErrNonPositiveLease
	}
	if requested > MaxLease {
		return time.Time{}, false, LeaseTooLongError(requested)
	}
	if InCapWindow(now) {
		return time.Time{}, false, ErrInsideCapWindow
	}

	deadline = now.Add(requested)
	if capAt := NextNightlyCap(now); deadline.After(capAt) {
		return capAt, true, nil
	}
	return deadline, false, nil
}

// ShouldDrainForIdle is L1's second trigger: the cluster is authorised but
// nobody is using it.
//
// zeroRunningSince is when the running-task count last became zero, or the zero
// value if something is running. Taking a timestamp rather than a count is what
// makes the rule "zero for thirty minutes" instead of "zero right now" -- a task
// that finishes and is immediately followed by another must not start the clock.
func ShouldDrainForIdle(now, zeroRunningSince time.Time) bool {
	if zeroRunningSince.IsZero() {
		return false
	}
	return !now.Before(zeroRunningSince.Add(IdleZeroRunning))
}

// ShouldDrain is L1's full trigger rule: the deadline has passed, or the
// cluster has been idle long enough, or the lease could not be read at all.
//
// The last one is not paranoia. If L1 cannot read the lease it cannot know it is
// still authorised, and the safe reading of "unknown" for something that costs
// money by the hour is "not authorised". It drains gracefully, so nothing is
// lost if the read failure was transient.
func ShouldDrain(now time.Time, l Lease, leaseOK bool, zeroRunningSince time.Time) (bool, Reason) {
	if !leaseOK {
		return true, ReasonLeaseUnreadable
	}
	if !now.Before(l.Deadline) {
		return true, ReasonDeadlinePassed
	}
	if ShouldDrainForIdle(now, zeroRunningSince) {
		return true, ReasonIdle
	}
	return false, ReasonAuthorised
}

// DecideL2 is the out-of-cluster enforcer's three-way rule (section 3.2).
//
// Order is the whole content of this function, so it is written as a flat
// sequence of guarded returns rather than nested conditions. Each return is one
// row of the decision table in decide_test.go.
//
// The rules, in the order they must be evaluated:
//
//  1. Already at zero: nothing to do, whatever else is true.
//  2. Three consecutive failures to read the lease: force. L2 cannot verify
//     authorisation, and unverifiable authorisation for something billed by the
//     hour is not authorisation.
//  3. One or two failures: WAIT. This is the rule most likely to be "simplified"
//     into forcing on the first failure, which would destroy work every time
//     GCS hiccups. L1 is already draining if the lease is genuinely gone.
//  4. A drain record from a previous lease is ignored entirely -- that is how a
//     successful extend invalidates an earlier `drained`, without L1 having to
//     remember to clean up.
//  5. Deadline not passed: wait -- unless L1 finished an IDLE drain about this
//     lease. Nothing has been awake for IdleZeroRunning and everything is
//     suspended, so billing on until the deadline would buy nothing (review
//     note, Phase 3). That is the only stop before a deadline.
//  6. drained: stop gracefully. Nothing is awake; this is the happy path, at
//     any time past the deadline.
//  7. drain-failed: force. L1 said it could not finish.
//  8. past deadline + grace: force, UNCONDITIONALLY. Only rules 9 and 10 can
//     wait, and this is what bounds them: no heartbeat, however fresh, buys
//     time past the grace, so a node is up for at most deadline + ForceGrace +
//     one L2 tick while the lease is readable.
//  9. draining with a heartbeat inside HeartbeatStaleAfter: wait. A slow drain
//     is not a dead one. A staler heartbeat is a dead L1: force.
//  10. no record about this lease: judged as a heartbeat that stopped AT the
//     deadline. A live L1 writes `draining` within a minute of it, so silence
//     for a whole heartbeat window means L1 is not running: force.
func DecideL2(o Observation) Decision {
	if o.Nodes == 0 {
		return Decision{ActionWait, ReasonAlreadyStopped}
	}

	if o.ConsecutiveReadFailures >= LeaseReadFailureThreshold {
		return Decision{ActionStopForced, ReasonLeaseUnreadable}
	}
	if !o.LeaseOK || o.ConsecutiveReadFailures > 0 {
		return Decision{ActionWait, ReasonTransientReadFailure}
	}

	phase := o.Drain.Phase
	if o.Drain.Stale(o.Lease) {
		phase = DrainNone
	}

	if o.Now.Before(o.Lease.Deadline) {
		if phase == DrainDrained && o.Drain.Reason == ReasonIdle {
			return Decision{ActionStopGraceful, ReasonIdleDrained}
		}
		return Decision{ActionWait, ReasonWithinLease}
	}

	switch phase {
	case DrainDrained:
		return Decision{ActionStopGraceful, ReasonDrained}
	case DrainFailed:
		return Decision{ActionStopForced, ReasonDrainFailed}
	}

	if o.Now.After(o.Lease.Deadline.Add(ForceGrace)) {
		return Decision{ActionStopForced, ReasonGraceExpired}
	}

	heartbeat, waiting := o.Lease.Deadline, ReasonAwaitingDrain
	if phase == DrainDraining {
		heartbeat, waiting = o.Drain.Heartbeat, ReasonDrainingWithHeartbeat
	}
	if !o.Now.After(heartbeat.Add(HeartbeatStaleAfter())) {
		return Decision{ActionWait, waiting}
	}
	return Decision{ActionStopForced, ReasonHeartbeatStale}
}

// NextReadFailures advances L2's run of consecutive lease read failures by one
// tick. L2 is a job that exits between ticks, so the run lives in enforce.json
// and is carried forward here.
//
// While the pool is at zero the run is reset, readable or not: there is nothing
// for a blind stop to stop, and a run carried across a stop would make the
// first miss after the next wake a blind stop of a lease nobody has yet failed
// to read three times.
func NextReadFailures(prev int, leaseOK bool, nodes int) int {
	if nodes == 0 || leaseOK {
		return 0
	}
	return prev + 1
}

// MayStartTask reports whether a new task may be started right now.
//
// This guard was found missing by the seeded simulation, which produced:
//
//	12:46  sleep (deadline now)
//	12:46  L1 begins draining
//	12:47  L1 reports drained
//	12:50  a task starts
//	12:50  L2 stops the pool gracefully -- and crashes that task
//
// The plan states the rule in prose ("ax-job / ax-exec do not start a new task
// once the lease is draining or later"), but prose in a document does not stop
// anything. Without this function the NoCrashOnGracefulSleep invariant is false:
// L2 is entitled to shrink the pool the moment it sees `drained`, and anything
// started after that point dies in a stop that was, from L2's side, correct.
//
// Two conditions, both necessary:
//   - the lease must still authorise the node, and
//   - L1 must not have begun tidying up.
//
// Note it does NOT accept a stale drain record as a reason to refuse: a
// successful extend bumps the generation, which reopens the cluster for work.
// That is the same generation comparison DecideL2 uses, for the same reason.
func MayStartTask(now time.Time, l Lease, leaseOK bool, d Drain) (bool, Reason) {
	if !leaseOK {
		return false, ReasonLeaseUnreadable
	}
	if !now.Before(l.Deadline) {
		return false, ReasonDeadlinePassed
	}
	if !d.Stale(l) {
		switch d.Phase {
		case DrainDraining:
			return false, ReasonDrainingWithHeartbeat
		case DrainDrained:
			return false, ReasonDrained
		case DrainFailed:
			return false, ReasonDrainFailed
		}
	}
	return true, ReasonAuthorised
}
