package lease

import (
	"slices"
	"time"
)

// DecideL1 is the in-cluster drain's judgement for one tick: the same thirteen
// branches as the model's l1Tick in exe/spec/lease.qnt (the model's Suspend and
// Stall are one decision here -- whether AX acts on a suspend request is the
// environment's business, not L1's), in the same order.
//
// Every tick first OBSERVES, whatever it then decides:
//   - the idle clock: the first tick that saw no task actor awake, carried in
//     drain.json because each CronJob run is a new process;
//   - wedges: every actor stuck in DELETING, with the tick it was first seen
//     so, and the worker pod of any stuck for WedgeClear, to delete.
//
// Then one branch decides. Without a trigger: nothing (NoOp), put both resume
// paths back (Reopen), or cancel a drain (Cancel). With one:
//
//	Begin      the baseline of what is already CRASHED, `draining`, and the
//	           router to 0 -- also when the terminal record is about an older
//	           lease (review note, Phase 3: `sleep` after an idle drain)
//	Lost       a task actor crashed since the baseline: `drain-failed`, so L2
//	           forces and pages rather than calling a loss graceful
//	Finish     the barrier holds: nothing awake anywhere, no template in
//	           flight, no router or controller pod left -- `drained`
//	GiveUp     the ceiling is spent: `drain-failed`
//	Resuspend  something is awake and the controller is down: bring it back
//	Suspend    something is awake: ask AX to suspend it
//	Quiesce    nothing awake: the controller to 0
//	Wait       nothing to ask for, not done yet
//	Settled    the terminal record is about this lease: nothing to do
//
// L1 never touches the pool. The pool is L2's.
func DecideL1(o L1Observation) L1Decision {
	d := L1Decision{
		Drain:              o.Drain,
		RouterReplicas:     o.RouterReplicas,
		ControllerReplicas: o.ControllerReplicas,
	}
	d.Drain.IdleSince = observedIdleSince(o)
	d.Drain.WedgeSeen, d.ClearWorkers = observedWedges(o)

	trigger, reason := l1Trigger(o, d.Drain.IdleSince)
	phase := o.Drain.Phase

	if !trigger {
		switch {
		case phase != DrainNone:
			d.Branch = L1Cancel
			d.Drain = Drain{
				Phase:           DrainNone,
				Heartbeat:       o.Now,
				StartedAt:       o.Now,
				LeaseGeneration: o.Lease.Generation,
				IdleSince:       d.Drain.IdleSince,
				WedgeSeen:       d.Drain.WedgeSeen,
			}
			d.RouterReplicas, d.ControllerReplicas = 1, 1
		case o.RouterReplicas == 0 || o.ControllerReplicas == 0:
			d.Branch = L1Reopen
			d.RouterReplicas, d.ControllerReplicas = 1, 1
		default:
			d.Branch = L1NoOp
		}
		return d
	}

	gen := o.Drain.LeaseGeneration
	if o.LeaseOK {
		gen = o.Lease.Generation
	}
	staleTerminal := (phase == DrainDrained || phase == DrainFailed) &&
		o.LeaseOK && o.Drain.LeaseGeneration != o.Lease.Generation

	if phase == DrainNone || staleTerminal {
		d.Branch = L1Begin
		d.Drain.Phase = DrainDraining
		d.Drain.Heartbeat = o.Now
		d.Drain.StartedAt = o.Now
		d.Drain.LeaseGeneration = gen
		d.Drain.Reason = reason
		d.Drain.BaselineCrashed = crashedTasks(o.Actors)
		d.Drain.Failure = ""
		d.RouterReplicas = 0
		return d
	}

	if phase != DrainDraining {
		d.Branch = L1Settled
		return d
	}

	// A drain in progress: every branch below heartbeats.
	d.Drain.Heartbeat = o.Now
	d.Drain.LeaseGeneration = gen
	awake := awakeTasks(o.Actors)

	switch {
	case lostSinceBaseline(o.Actors, o.Drain.BaselineCrashed):
		d.Branch = L1Lost
		d.Drain.Phase = DrainFailed
		d.Drain.Failure = FailureLost
	case barrierHolds(o):
		d.Branch = L1Finish
		d.Drain.Phase = DrainDrained
	case !o.Now.Before(o.Drain.StartedAt.Add(DrainCeiling)):
		d.Branch = L1GiveUp
		d.Drain.Phase = DrainFailed
		d.Drain.Failure = FailureCeiling
	case len(awake) > 0 && o.ControllerReplicas == 0:
		d.Branch = L1Resuspend
		d.ControllerReplicas = 1
	case len(awake) > 0:
		d.Branch = L1Suspend
		d.Suspend = awake
	case o.ControllerReplicas == 1:
		d.Branch = L1Quiesce
		d.ControllerReplicas = 0
	default:
		d.Branch = L1Wait
	}
	return d
}

// observedIdleSince is L1's idle clock after this tick: zero while a task
// actor is awake or mid-checkpoint, else the first tick that saw none. Golden
// actors do not count -- they are Substrate's work, not the operator's.
func observedIdleSince(o L1Observation) time.Time {
	for _, a := range o.Actors {
		if !a.Golden && (a.State == ActorAwake || a.State == ActorCheckpointing) {
			return time.Time{}
		}
	}
	if o.Drain.IdleSince.IsZero() {
		return o.Now
	}
	return o.Drain.IdleSince
}

// observedWedges carries the wedge record forward and picks the worker pods to
// delete. Only an actor in DELETING that still holds a worker is a wedge: a
// SUSPENDING actor may be mid-checkpoint, and deleting its pod would crash it
// (the model's ClearingNeverLosesState).
func observedWedges(o L1Observation) (map[string]time.Time, []string) {
	var seen map[string]time.Time
	var clear []string
	for _, a := range o.Actors {
		if a.State != ActorDeleting || a.Worker == "" {
			continue
		}
		first, ok := o.Drain.WedgeSeen[a.UID]
		if !ok {
			first = o.Now
		}
		if !o.Now.Before(first.Add(WedgeClear)) {
			clear = append(clear, a.Worker)
			continue
		}
		if seen == nil {
			seen = map[string]time.Time{}
		}
		seen[a.UID] = first
	}
	slices.Sort(clear)
	return seen, clear
}

// l1Trigger is L1's drain trigger: the lease cannot be read, the deadline has
// passed, or nothing has been awake for IdleZeroRunning counted from the later
// of the idle clock and the last wake.
func l1Trigger(o L1Observation, idleSince time.Time) (bool, Reason) {
	switch {
	case !o.LeaseOK:
		return true, ReasonLeaseUnreadable
	case !o.Now.Before(o.Lease.Deadline):
		return true, ReasonDeadlinePassed
	case idleSince.IsZero():
		return false, ReasonAuthorised
	}
	start := idleSince
	if o.Lease.WokenAt.After(start) {
		start = o.Lease.WokenAt
	}
	if !o.Now.Before(start.Add(IdleZeroRunning)) {
		return true, ReasonIdle
	}
	return false, ReasonAuthorised
}

// crashedTasks is the baseline: every task actor already CRASHED.
func crashedTasks(actors []ActorObs) []string {
	var out []string
	for _, a := range actors {
		if !a.Golden && a.State == ActorCrashed {
			out = append(out, a.UID)
		}
	}
	slices.Sort(out)
	return out
}

// awakeTasks is the AX tasks whose actors are awake: the suspends to ask for.
// Not a checkpoint already in flight, and never a golden actor.
func awakeTasks(actors []ActorObs) []string {
	var out []string
	for _, a := range actors {
		if !a.Golden && a.State == ActorAwake && a.Task != "" {
			out = append(out, a.Task)
		}
	}
	slices.Sort(out)
	return out
}

// lostSinceBaseline reports a task actor CRASHED now that was not in the
// baseline. A row the baseline's paginated read missed counts as lost: the
// conservative direction.
func lostSinceBaseline(actors []ActorObs, baseline []string) bool {
	for _, a := range actors {
		if !a.Golden && a.State == ActorCrashed && !slices.Contains(baseline, a.UID) {
			return true
		}
	}
	return false
}

// barrierHolds is the model's drainDoneIn: nothing awake or mid-checkpoint in
// any atespace, no template in flight, the controller at 0, and no router or
// controller pod left that could still execute a resume.
func barrierHolds(o L1Observation) bool {
	for _, a := range o.Actors {
		if a.State == ActorAwake || a.State == ActorCheckpointing {
			return false
		}
	}
	return !o.TemplatesPending &&
		o.ControllerReplicas == 0 && o.ControllerPods == 0 && o.RouterPods == 0
}

// NextStopping is L2's stop-latency detector (inbox M18, layer 3). The target
// size reads zero the moment setSize(0) is accepted, while the node still
// bills; `instances` is what is really there. The first tick that sees the node
// still there remembers when, and a later one past StopLatency raises the
// alarm. Once nothing is left -- or the pool is live again -- the memory
// clears.
func NextStopping(prev time.Time, target, instances int, now time.Time) (time.Time, bool) {
	if target != 0 || instances == 0 {
		return time.Time{}, false
	}
	if prev.IsZero() {
		return now, false
	}
	return prev, now.Sub(prev) > StopLatency
}
