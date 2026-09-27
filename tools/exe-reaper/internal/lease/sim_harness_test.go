package lease

import (
	"fmt"
	"math/rand/v2"
	"strings"
	"time"
)

// A seeded, replayable simulation of the real decision code, checking the Quint
// model's invariants on every step.
//
// What it is FOR: the model proves the rules are consistent; this proves the
// shipped functions implement those rules under adversarial interleavings that
// no hand-written scenario would think of -- an extend landing in the same
// minute as a drain finishing, a node vanishing mid-drain, three read failures
// straddling a deadline.
//
// What it deliberately stubs: all I/O. GCS reads and writes, the setSize call,
// the Kubernetes API. Those are the parts a simulation cannot tell you anything
// true about. It never stubs the LOGIC: every transition below calls the same
// ShouldDrain / DecideL2 the binary calls.
//
// Outside the guarantee, stated so nobody mistakes a green run for more than it
// is: real clock skew between the operator's laptop and the enforcer; GCS
// generation preconditions actually being honoured by GCS; whether atelet really
// suspends an actor when asked; and anything about Substrate's own 60-second
// crash window other than "if the pool shrinks while an actor is awake, it dies".

// SimConfig bounds a run.
type SimConfig struct {
	Seed  uint64
	Steps int
	// MinuteStep is how far the clock advances per step. One minute matches L1's
	// tick, which is the finest granularity any rule cares about.
	MinuteStep time.Duration
}

// DefaultSimConfig is what the test uses when it is not sweeping seeds.
func DefaultSimConfig(seed uint64) SimConfig {
	return SimConfig{Seed: seed, Steps: 4000, MinuteStep: time.Minute}
}

// simState is the whole world the simulation models.
type simState struct {
	now time.Time

	lease   Lease
	leaseOK bool
	// readFailures is L2's carried count (it lives in enforce.json in reality,
	// because the job exits between ticks and has no memory of its own).
	readFailures int

	drain Drain

	nodes int
	// awake is the number of actors currently running on the node. An actor can
	// only exist while nodes == 1.
	awake int
	// lastStopCrashed records whether the MOST RECENT stop destroyed an awake
	// actor. Per-stop rather than sticky: a sticky flag makes every later
	// graceful stop look like the guilty one, which is a false positive the
	// first version of this simulation duly produced.
	lastStopCrashed bool
	// lastStopForced records whether that stop was a forced one, so the
	// graceful-stop invariant only judges the stops it is about.
	lastStopForced bool
	// lastStopByEnforcement distinguishes a stop the DESIGN made (L2 or L3) from
	// one the environment made (the node simply vanished). The design can be
	// held responsible for the first kind only; an invariant that judges the
	// second is over-strong, and the first version of this one duly failed on a
	// node that disappeared six minutes after a successful extend.
	lastStopByEnforcement bool
	// lastStopReason is the rule that fired, so an invariant can exclude the
	// cases it is not about.
	lastStopReason Reason

	zeroRunningSince time.Time
	// lastExtendAt is when a lease was last successfully extended, used by the
	// ExtendBeatsStaleDrained invariant.
	lastExtendAt time.Time
}

// SimViolation is an invariant failure, with everything needed to replay it.
type SimViolation struct {
	Seed      uint64
	Step      int
	Invariant string
	Detail    string
	Trace     []string
}

func (v SimViolation) Error() string {
	return fmt.Sprintf(
		"invariant %s violated at step %d (seed %d): %s\nreplay with EXE_REAPER_SIM_SEED=%d\ntrace:\n%s",
		v.Invariant, v.Step, v.Seed, v.Detail, v.Seed, strings.Join(v.Trace, "\n"),
	)
}

// SimStats counts what a run actually exercised.
//
// Not a test hook: a simulation that never reaches a forced stop passes while
// proving nothing, so "did this run visit the dangerous states" is a first-class
// result, printed by the gate when a seed list is widened.
type SimStats struct {
	Wakes          int
	Extends        int
	DrainsStarted  int
	DrainsFinished int
	DrainsFailed   int
	GracefulStops  int
	ForcedStops    int
	L3Stops        int
	ReadFailures   int
}

// Simulate runs one seeded trace and returns the first invariant violation, or
// nil. The trace is kept in memory and only printed on failure: a passing run
// should be silent, or the gate becomes noise nobody reads.
func Simulate(cfg SimConfig) *SimViolation {
	_, v := SimulateWithStats(cfg)
	return v
}

// SimulateWithStats is Simulate plus the coverage counters.
func SimulateWithStats(cfg SimConfig) (SimStats, *SimViolation) {
	rng := rand.New(rand.NewPCG(cfg.Seed, cfg.Seed^0x9e3779b97f4a7c15))

	// Start asleep at a fixed instant, well away from any boundary so that the
	// first few steps are not all about the cap window.
	s := &simState{
		now:     time.Date(2026, 9, 27, 10, 0, 0, 0, Location()),
		leaseOK: true,
		nodes:   0,
	}

	stats := &SimStats{}
	trace := make([]string, 0, cfg.Steps)
	record := func(format string, args ...any) {
		if len(trace) < 400 { // enough to diagnose; not enough to drown the log
			trace = append(trace, fmt.Sprintf("  %s %s", s.now.Format("15:04"), fmt.Sprintf(format, args...)))
		}
	}

	for step := range cfg.Steps {
		// Every step: advance the clock, then let a randomly chosen subset of
		// the actors act. Order within a step is fixed (operator, L1, L2, L3)
		// because that is the real causal order: a human acts, then the
		// in-cluster loop sees it, then the out-of-cluster one.
		s.now = s.now.Add(cfg.MinuteStep)

		simOperator(s, rng, record, stats)
		simL1(s, rng, record, stats)
		simL2(s, record, stats)
		simL3(s, record, stats)
		simEnvironment(s, rng, record, stats)

		if v := checkInvariants(s, cfg.Seed, step, trace); v != nil {
			return *stats, v
		}
	}
	return *stats, nil
}

func simOperator(s *simState, rng *rand.Rand, record func(string, ...any), stats *SimStats) {
	switch {
	case s.nodes == 0 && rng.IntN(40) == 0:
		requested := time.Duration(1+rng.IntN(int(MaxLease/time.Minute))) * time.Minute
		deadline, _, err := ClampDeadline(s.now, requested)
		if err != nil {
			return
		}
		s.lease = Lease{Deadline: deadline, Generation: s.lease.Generation + 1}
		s.nodes = 1
		s.leaseOK = true
		s.readFailures = 0
		s.zeroRunningSince = s.now
		stats.Wakes++
		record("wake until %s (gen %d)", deadline.Format("15:04"), s.lease.Generation)

	case s.nodes == 1 && rng.IntN(60) == 0:
		requested := time.Duration(1+rng.IntN(int(MaxLease/time.Minute))) * time.Minute
		deadline, _, err := ClampDeadline(s.now, requested)
		if err != nil {
			return
		}
		s.lease = Lease{Deadline: deadline, Generation: s.lease.Generation + 1}
		s.lastExtendAt = s.now
		stats.Extends++
		record("extend until %s (gen %d)", deadline.Format("15:04"), s.lease.Generation)

	case s.nodes == 1 && rng.IntN(120) == 0:
		s.lease = Lease{Deadline: s.now, Generation: s.lease.Generation + 1}
		record("sleep (deadline now, gen %d)", s.lease.Generation)

	case s.nodes == 1 && s.awake == 0 && rng.IntN(15) == 0:
		// The guard the simulation found missing: once L1 has begun tidying up,
		// nothing new may start, or L2's entirely correct graceful stop kills it.
		if ok, _ := MayStartTask(s.now, s.lease, s.leaseOK, s.drain); !ok {
			return
		}
		s.awake++
		s.zeroRunningSince = time.Time{}
		record("operator starts a task (awake=%d)", s.awake)
	}
}

func simL1(s *simState, rng *rand.Rand, record func(string, ...any), stats *SimStats) {
	if s.nodes == 0 {
		return
	}
	should, reason := ShouldDrain(s.now, s.lease, s.leaseOK, s.zeroRunningSince)
	if !should {
		// A live lease cancels an in-progress drain and reopens the router.
		if s.drain.Phase == DrainDraining || s.drain.Phase == DrainDrained {
			s.drain = Drain{}
			record("L1 cancels the drain: %s", reason)
		}
		return
	}

	switch s.drain.Phase {
	case DrainNone, DrainFailed:
		if s.drain.Stale(s.lease) || s.drain.Phase == DrainNone {
			s.drain = Drain{
				Phase: DrainDraining, Heartbeat: s.now,
				LeaseGeneration: s.lease.Generation, StartedAt: s.now,
			}
			stats.DrainsStarted++
			record("L1 begins draining (%s)", reason)
		}
	case DrainDraining:
		if s.now.After(s.drain.StartedAt.Add(DrainCeiling)) {
			s.drain.Phase = DrainFailed
			stats.DrainsFailed++
			record("L1 gives up: ceiling blown")
			return
		}
		// A stalled L1 stops heartbeating; that is the case L2's stale-heartbeat
		// rule exists for, so it has to be reachable.
		if rng.IntN(25) == 0 {
			record("L1 stalls (no heartbeat)")
			return
		}
		s.drain.Heartbeat = s.now
		if s.awake > 0 {
			s.awake--
			record("L1 suspends an actor (awake=%d)", s.awake)
			return
		}
		s.drain.Phase = DrainDrained
		stats.DrainsFinished++
		record("L1 reports drained")
	}
}

func simL2(s *simState, record func(string, ...any), stats *SimStats) {
	// L2 only runs on its tick.
	if s.now.Minute()%int(L2Tick/time.Minute) != 0 {
		return
	}
	if !s.leaseOK {
		s.readFailures++
	} else {
		s.readFailures = 0
	}

	d := DecideL2(Observation{
		Now: s.now, Lease: s.lease, LeaseOK: s.leaseOK,
		ConsecutiveReadFailures: s.readFailures, Drain: s.drain, Nodes: s.nodes,
	})
	switch d.Action {
	case ActionWait:
		return
	case ActionStopGraceful, ActionStopForced:
		s.lastStopForced = d.Action == ActionStopForced
		s.lastStopReason = d.Reason
		if s.lastStopForced {
			stats.ForcedStops++
		} else {
			stats.GracefulStops++
		}
		shrinkBy(s, record, fmt.Sprintf("L2 %s (%s)", d.Action, d.Reason), true)
	}
}

func simL3(s *simState, record func(string, ...any), stats *SimStats) {
	local := s.now.In(Location())
	if local.Hour() != L3StopHour || local.Minute() != 0 {
		return
	}
	if s.nodes == 0 {
		return
	}
	// No logic, by design. That is the point of L3.
	s.lastStopForced = true
	stats.L3Stops++
	shrinkBy(s, record, "L3 daily stop", true)
}

func simEnvironment(s *simState, rng *rand.Rand, record func(string, ...any), stats *SimStats) {
	// The router resumes a suspended actor without going through the
	// controller. It really does this, which is why L1 closes the router first.
	if ok, _ := MayStartTask(s.now, s.lease, s.leaseOK, s.drain); ok &&
		s.nodes == 1 && s.awake == 0 && rng.IntN(50) == 0 {
		s.awake++
		s.zeroRunningSince = time.Time{}
		record("router auto-resumes an actor (awake=%d)", s.awake)
	}
	if s.nodes == 1 && s.awake == 0 && s.zeroRunningSince.IsZero() {
		s.zeroRunningSince = s.now
	}
	// GCS read failures come and go.
	if s.leaseOK && rng.IntN(120) == 0 {
		s.leaseOK = false
		stats.ReadFailures++
		record("lease reads start failing")
	} else if !s.leaseOK && rng.IntN(6) == 0 {
		s.leaseOK = true
		record("lease reads recover")
	}
	// The node disappears on its own occasionally.
	if s.nodes == 1 && rng.IntN(400) == 0 {
		s.lastStopForced = true
		shrink(s, record, "node lost")
	}
}

// shrink is the one place the pool size changes, so the crash rule lives here
// and cannot be forgotten at one of several call sites.
func shrink(s *simState, record func(string, ...any), why string) {
	shrinkBy(s, record, why, false)
}

// shrinkBy is shrink with an explicit answer to "was this the design's doing?".
func shrinkBy(s *simState, record func(string, ...any), why string, byEnforcement bool) {
	s.lastStopByEnforcement = byEnforcement
	s.lastStopCrashed = s.awake > 0
	if s.lastStopCrashed {
		record("%s -- %d awake actor(s) CRASHED", why, s.awake)
		s.awake = 0
	} else {
		record("%s", why)
	}
	s.nodes = 0
	s.drain = Drain{}
	s.zeroRunningSince = time.Time{}
}

func checkInvariants(s *simState, seed uint64, step int, trace []string) *SimViolation {
	fail := func(name, detail string) *SimViolation {
		return &SimViolation{Seed: seed, Step: step, Invariant: name, Detail: detail, Trace: trace}
	}

	// NoCrashOnGracefulSleep: a stop that was not forced must never have caught
	// an awake actor. This is the invariant the whole ordering of L1's steps
	// exists to preserve.
	if s.lastStopCrashed && !s.lastStopForced {
		return fail("NoCrashOnGracefulSleep",
			"an actor was crashed by a stop that was not a forced one")
	}

	// L3NeverHitsAwakeActor: no lease may authorise a node past the cap, so in
	// normal operation L3 cannot land on one. Checked as a state property: the
	// deadline is never inside the window between the cap and L3.
	//
	// Only a deadline still in the FUTURE is judged. `exe-sleep` works by setting
	// the deadline to now, so a cluster stopped at 03:06 legitimately carries a
	// deadline inside the window -- it is already expired, L1 drains immediately,
	// and nothing is authorised. The first version of this invariant flagged
	// exactly that and was wrong: an expired deadline authorises nothing, which
	// is the property that matters.
	if s.nodes == 1 && s.lease.Deadline.After(s.now) {
		local := s.lease.Deadline.In(Location())
		capAt := time.Date(local.Year(), local.Month(), local.Day(), NightlyCapHour, 0, 0, 0, Location())
		if local.After(capAt) && local.Hour() < L3StopHour {
			return fail("L3NeverHitsAwakeActor",
				fmt.Sprintf("a live lease deadline %s falls inside the cap window",
					local.Format(time.RFC3339)))
		}
	}

	// ExtendBeatsStaleDrained: within one L2 tick of a successful extend, an
	// enforcement stop must not happen. A stale `drained` record stopping a
	// freshly extended lease is the exact bug the generation comparison
	// prevents.
	//
	// Scoped twice, each time because the simulation produced a trace showing
	// the unscoped version was wrong:
	//
	//   - only stops the DESIGN made count. A node that simply vanishes six
	//     minutes after an extend is not something any rule can prevent.
	//   - a stop because the lease was UNREADABLE for three consecutive ticks
	//     is excluded. L2 is a job that runs every ten minutes and sees only
	//     what it can read; if it cannot read the lease it cannot know an extend
	//     happened, and forcing is then the documented, intended behaviour. The
	//     requirement is about a stale drain record, not about blindness.
	if !s.lastExtendAt.IsZero() && s.nodes == 0 && s.lastStopByEnforcement &&
		s.lastStopReason != ReasonLeaseUnreadable &&
		s.now.Sub(s.lastExtendAt) <= L2Tick && s.lease.Deadline.After(s.now) {
		return fail("ExtendBeatsStaleDrained",
			fmt.Sprintf("the pool was stopped (%s) within one L2 tick of a successful extend",
				s.lastStopReason))
	}

	// NodesEventuallyZero, as a bounded safety property rather than a liveness
	// one: if the deadline passed longer ago than the worst-case stopping chain
	// plus the grace, the pool must not still be up. Expressed this way because
	// a simulation can falsify a bound but cannot prove eventual behaviour.
	if s.nodes == 1 && !s.lease.Deadline.IsZero() {
		bound := ForceGrace + CapMargin() + L2Tick
		if s.now.After(s.lease.Deadline.Add(bound)) {
			return fail("NodesEventuallyZero",
				fmt.Sprintf("deadline passed %s ago (bound %s) and the pool is still up",
					s.now.Sub(s.lease.Deadline), bound))
		}
	}

	return nil
}
