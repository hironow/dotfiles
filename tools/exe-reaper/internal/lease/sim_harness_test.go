package lease

import (
	"fmt"
	"math/rand/v2"
	"slices"
	"strings"
	"time"
)

// A seeded, replayable simulation of the real decision code, checking the Quint
// model's invariants on every step.
//
// What it is FOR: the model proves the rules are consistent; this proves the
// shipped functions implement those rules under adversarial interleavings that
// no hand-written scenario would think of -- an extend landing in the same
// minute as a drain finishing, a raw resume executed by a controller pod that
// has not finished terminating, a worker pod dying mid-checkpoint, three read
// failures straddling a deadline.
//
// What it deliberately stubs: all I/O. GCS reads and writes, the setSize call,
// the Kubernetes API, AX, Substrate. Those are the parts a simulation cannot
// tell you anything true about. It never stubs the LOGIC: every L1 tick calls
// DecideL1, every L2 tick DecideL2, NextReadFailures and NextStopping, and
// every task start MayStartTask -- the functions the binaries call.
//
// Action boundary (model) -> I/O boundary (code) -> what covers it:
//
//	l1Tick          exe-reap: DecideL1, then drain.json, the two scale
//	                subresources, AX SuspendTask, pod deletes   -> this sim,
//	                TestDecideL1AgreesWithTheModel, internal/l1 tests
//	l2Tick          exe-reaper enforce: DecideL2 + NextStopping, then setSize
//	                and enforce.json                            -> this sim,
//	                TestDecideL2AgreesWithTheModel, main_test.go
//	wake/extend/    exe-reaper wake/extend/sleep: ClampDeadline and a
//	sleep           conditional lease.json write                -> this sim,
//	                main_test.go
//	resumes         ax-job/ax-exec (MayStartTask), raw `ax resume`, the
//	                router, Substrate's golden reconciler       -> this sim
//
// Outside the guarantee, stated so nobody mistakes a green run for more than it
// is: real clock skew between the operator's laptop and the enforcer; GCS
// generation preconditions actually being honoured by GCS; whether AX really
// suspends an actor when asked; Substrate's crash detection (it happens at a
// random moment here, or not at all); and the stop latency itself, which is
// the measured assumption StopLatency (a slow stop is SimConfig's
// ActualStopLatency, which TestSimulationCatchesASlowStop turns up).

// SimConfig bounds a run.
type SimConfig struct {
	Seed  uint64
	Steps int
	// MinuteStep is how far the clock advances per step. One minute matches L1's
	// tick, which is the finest granularity any rule cares about.
	MinuteStep time.Duration
	// ActualStopLatency is how long a node really takes to leave after
	// setSize(0). The design assumes StopLatency; a disruption budget holding
	// the drain is this set far higher.
	ActualStopLatency time.Duration
}

// DefaultSimConfig is what the test uses when it is not sweeping seeds.
//
// Two weeks of minutes per seed. The rarest paths -- a drain that starts late
// AND never finishes, a raw resume landing in a controller pod's last minutes
// -- need many drains per seed; the whole sweep still takes a few seconds.
func DefaultSimConfig(seed uint64) SimConfig {
	return SimConfig{Seed: seed, Steps: 20000, MinuteStep: time.Minute, ActualStopLatency: StopLatency}
}

type simActorState int

const (
	simAtRest simActorState = iota
	simAwake
	simCheckpointing
	simDoomed
	simCrashed
	simDeleting
	simGone
)

var simActorNames = map[simActorState]string{
	simAtRest: "at rest", simAwake: "awake", simCheckpointing: "checkpointing",
	simDoomed: "doomed", simCrashed: "crashed", simDeleting: "deleting", simGone: "gone",
}

// simActor is one task actor, as the world has it. The store's view -- what L1
// observes -- is derived from it: a doomed actor still reads RUNNING.
type simActor struct {
	state  simActorState
	doneAt time.Time // when a checkpoint in flight lands
}

// simStop is what the most recent stop decision was, and what it found.
type simStop struct {
	graceful bool
	byL2     bool
	reason   Reason
	// crashed: the stop took the target to zero with something awake (task
	// actor, checkpoint in flight, doomed actor, golden actor).
	crashed bool
	// silentLoss: a graceful stop after a task actor crashed since its
	// drain's baseline.
	silentLoss bool
	// despiteLiveLease: L2 stopped a lease it could read before that lease's
	// deadline, other than by the idle rule -- the model's
	// stoppedDespiteLiveLease, set the same way, at the stop.
	despiteLiveLease bool
}

// simState is the whole world the simulation models.
type simState struct {
	now time.Time

	lease   Lease
	leaseOK bool
	// readFailures, stoppingSince and stopAlarm are L2's carried memory (in
	// enforce.json in reality: the job exits between ticks).
	readFailures  int
	stoppingSince time.Time
	stopAlarm     bool

	drain Drain

	// The pool: nodes counts BILLING instances; stopping is "target zero, the
	// node still there", until nodeGoneAt.
	nodes      int
	stopping   bool
	nodeGoneAt time.Time

	actors          [2]simActor
	goldenAwake     bool
	templatePending bool

	// The replica counts L1 set, and the pods actually there. A scale-down
	// takes effect when the pod has terminated (…PodGoneAt).
	routerReplicas, controllerReplicas int
	routerPod, controllerPod           bool
	routerPodGoneAt, controllerPodGone time.Time

	// L1's ways of failing: dead until the node goes, not scheduled for a
	// while, or its suspend requests ignored for the rest of this drain.
	l1Dead          bool
	l1PausedUntil   time.Time
	suspendsIgnored bool

	lastStop     simStop
	lastExtendAt time.Time
	clearedLive  bool
	rates        simRates
	latency      time.Duration
}

// simRates are the per-seed odds of the failure modes, as "one in N" per
// opportunity. Varied by seed so the sweep spends some seeds where L1 mostly
// works and some where it mostly does not: a single fixed rate either never
// reaches a forced branch or never lets a drain finish.
type simRates struct {
	ignoreOneIn int // per drain started with an actor awake: AX never acts
	crashOneIn  int // per minute with the node up: L1 dies
	pauseOneIn  int // per minute with the node up: L1 not scheduled
	podLossIn   int // per minute with something awake: a worker pod dies
	rawResumeIn int // per minute: a raw `ax resume`
}

func ratesFor(seed uint64) simRates {
	return simRates{
		ignoreOneIn: 2 + int(seed%5),
		crashOneIn:  300 + 150*int(seed%4),
		pauseOneIn:  200 + 100*int(seed%3),
		podLossIn:   300 + 100*int(seed%3),
		rawResumeIn: 40 + 20*int(seed%3),
	}
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
// result, asserted by TestSimulationReachesTheDangerousStates.
type SimStats struct {
	Wakes            int
	Extends          int
	DrainsStarted    int
	StaleRedrains    int
	DrainsFinished   int
	DrainsFailedLost int
	DrainsFailedCeil int
	Resuspends       int
	GoldenWaits      int
	GracefulStops    int
	IdleStops        int
	ForcedStops      int
	// ForcedStops by the rule that fired, one field per forced branch of
	// DecideL2 (fields rather than a map so the struct stays comparable for the
	// determinism test).
	ForcedLeaseUnreadable int
	ForcedDrainFailed     int
	ForcedGraceExpired    int
	ForcedHeartbeatStale  int
	L3Stops               int
	ReadFailures          int
	RawResumesDuringDrain int
	WorkerPodsLost        int
	WedgesCleared         int
	StopLatencyAlarms     int
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
		now:            time.Date(2026, 9, 27, 10, 0, 0, 0, Location()),
		leaseOK:        true,
		routerReplicas: 1, controllerReplicas: 1,
		rates:   ratesFor(cfg.Seed),
		latency: cfg.ActualStopLatency,
	}

	stats := &SimStats{}
	// The LAST traceLines events, not the first: a violation at step 14 000 is
	// explained by what happened just before it, and the opening hours of the
	// run explain nothing.
	const traceLines = 400
	trace := make([]string, 0, 2*traceLines)
	record := func(format string, args ...any) {
		if len(trace) == cap(trace) {
			trace = append(trace[:0], trace[traceLines:]...)
		}
		trace = append(trace, fmt.Sprintf("  %s %s", s.now.Format("01-02 15:04"), fmt.Sprintf(format, args...)))
	}

	for step := range cfg.Steps {
		// Every step: advance the clock, then let each actor act. Order within
		// a step is fixed (operator, L1, L2, L3, environment) because that is
		// the real causal order: a human acts, then the in-cluster loop sees
		// it, then the out-of-cluster one.
		s.now = s.now.Add(cfg.MinuteStep)

		simOperator(s, rng, record, stats)
		simL1(s, rng, record, stats)
		simL2(s, record, stats)
		simL3(s, record, stats)
		simEnvironment(s, rng, record, stats)

		if v := checkInvariants(s, cfg.Seed, step, lastLines(trace, traceLines)); v != nil {
			return *stats, v
		}
	}
	return *stats, nil
}

// --- the world's derived views --------------------------------------------------

func (s *simState) nodeLive() bool          { return s.nodes == 1 && !s.stopping }
func (s *simState) routerServing() bool     { return s.nodeLive() && s.routerPod }
func (s *simState) controllerServing() bool { return s.nodeLive() && s.controllerPod }

func (s *simState) target() int {
	if s.nodeLive() {
		return 1
	}
	return 0
}

// actorsIn is the indexes of actors in any of the given states.
func (s *simState) actorsIn(states ...simActorState) []int {
	var out []int
	for i := range s.actors {
		if slices.Contains(states, s.actors[i].state) {
			out = append(out, i)
		}
	}
	return out
}

func (s *simState) anythingAwake() bool {
	return len(s.actorsIn(simAwake, simCheckpointing, simDoomed)) > 0 || s.goldenAwake
}

func simUID(i int) string    { return fmt.Sprintf("a%d", i+1) }
func simTask(i int) string   { return fmt.Sprintf("t%d", i+1) }
func simWorker(i int) string { return fmt.Sprintf("w%d", i+1) }

// l1Observation is what the in-cluster reaper would read on this tick: the
// store's view of every actor (doomed ones still read RUNNING), the golden
// flag, the replica counts it set and the pods actually there.
func (s *simState) l1Observation() L1Observation {
	o := L1Observation{
		Now: s.now, Lease: s.lease, LeaseOK: s.leaseOK, Drain: s.drain,
		TemplatesPending:   s.templatePending,
		RouterReplicas:     s.routerReplicas,
		ControllerReplicas: s.controllerReplicas,
	}
	if s.routerPod {
		o.RouterPods = 1
	}
	if s.controllerPod {
		o.ControllerPods = 1
	}
	for i, a := range s.actors {
		state := ActorAtRest
		switch a.state {
		case simGone:
			continue
		case simAwake, simDoomed:
			state = ActorAwake
		case simCheckpointing:
			state = ActorCheckpointing
		case simCrashed:
			state = ActorCrashed
		case simDeleting:
			state = ActorDeleting
		}
		o.Actors = append(o.Actors, ActorObs{UID: simUID(i), Task: simTask(i), Worker: simWorker(i), State: state})
	}
	if s.goldenAwake {
		o.Actors = append(o.Actors, ActorObs{UID: "golden", Golden: true, State: ActorAwake})
	}
	return o
}

// --- the operator ----------------------------------------------------------------

func simOperator(s *simState, rng *rand.Rand, record func(string, ...any), stats *SimStats) {
	switch {
	case !s.nodeLive() && rng.IntN(40) == 0:
		requested := time.Duration(1+rng.IntN(int(MaxLease/time.Minute))) * time.Minute
		deadline, _, err := ClampDeadline(s.now, requested)
		if err != nil {
			return
		}
		s.lease = Lease{Deadline: deadline, WokenAt: s.now, Generation: s.lease.Generation + 1}
		// A new node: a fresh CronJob, and pods as the replica counts L1 left
		// say. The write reached GCS, so reads work again; L2's run of read
		// failures is L2's own and is NOT reset here.
		s.nodes, s.stopping = 1, false
		s.routerPod = s.routerReplicas == 1
		s.controllerPod = s.controllerReplicas == 1
		s.l1Dead, s.l1PausedUntil, s.suspendsIgnored = false, time.Time{}, false
		s.leaseOK = true
		stats.Wakes++
		record("wake until %s (gen %d)", deadline.Format("15:04"), s.lease.Generation)

	case s.nodes == 1 && rng.IntN(60) == 0:
		requested := time.Duration(1+rng.IntN(int(MaxLease/time.Minute))) * time.Minute
		deadline, _, err := ClampDeadline(s.now, requested)
		if err != nil {
			return
		}
		s.lease = Lease{Deadline: deadline, WokenAt: s.lease.WokenAt, Generation: s.lease.Generation + 1}
		s.lastExtendAt = s.now
		stats.Extends++
		record("extend until %s (gen %d)", deadline.Format("15:04"), s.lease.Generation)

	case s.nodes == 1 && rng.IntN(120) == 0:
		s.lease = Lease{Deadline: s.now, WokenAt: s.lease.WokenAt, Generation: s.lease.Generation + 1}
		record("sleep (deadline now, gen %d)", s.lease.Generation)

	case s.controllerServing() && rng.IntN(15) == 0:
		// ax-job / ax-exec: the guard the simulation once found missing --
		// once L1 has begun tidying up, nothing new may start through them.
		idle := s.actorsIn(simAtRest)
		if len(idle) == 0 {
			return
		}
		if ok, _ := MayStartTask(s.now, s.lease, s.leaseOK, s.drain); !ok {
			return
		}
		s.actors[idle[0]].state = simAwake
		record("ax-job resumes %s", simUID(idle[0]))

	case s.controllerServing() && rng.IntN(rawResumeOdds(s)) == 0:
		// A raw `ax resume`, bypassing every guard: executed by whatever
		// controller pod is there, drain or no drain.
		idle := s.actorsIn(simAtRest)
		if len(idle) == 0 {
			return
		}
		s.actors[idle[0]].state = simAwake
		if s.drain.Phase == DrainDraining {
			stats.RawResumesDuringDrain++
		}
		record("raw ax resume of %s (drain %q)", simUID(idle[0]), s.drain.Phase)

	case s.controllerServing() && rng.IntN(200) == 0:
		// `ax delete task`: the actor goes -- or, as in Phase 4, the delete
		// wedges in DELETING and holds its worker.
		cands := s.actorsIn(simAtRest, simAwake)
		if len(cands) == 0 {
			return
		}
		i := cands[0]
		if rng.IntN(2) == 0 {
			s.actors[i].state = simDeleting
			record("delete of %s wedges", simUID(i))
		} else {
			s.actors[i].state = simGone
			record("%s deleted", simUID(i))
		}
	}
}

// --- L1 ----------------------------------------------------------------------------

func simL1(s *simState, rng *rand.Rand, record func(string, ...any), stats *SimStats) {
	if !s.nodeLive() || s.l1Dead || s.now.Before(s.l1PausedUntil) {
		return
	}
	if rng.IntN(s.rates.crashOneIn) == 0 {
		s.l1Dead = true
		record("L1 dies (no more ticks until the node goes)")
		return
	}
	if rng.IntN(s.rates.pauseOneIn) == 0 {
		s.l1PausedUntil = s.now.Add(time.Duration(5+rng.IntN(36)) * time.Minute)
		record("L1 is not scheduled until %s", s.l1PausedUntil.Format("15:04"))
		return
	}

	before := s.drain
	d := DecideL1(s.l1Observation())
	s.drain = d.Drain
	noteL1Branch(s, rng, record, stats, d, before)
	simScale(s, rng, d.RouterReplicas, &s.routerReplicas, &s.routerPod, &s.routerPodGoneAt)
	simScale(s, rng, d.ControllerReplicas, &s.controllerReplicas, &s.controllerPod, &s.controllerPodGone)
	applySuspends(s, rng, record, d.Suspend)
	applyClears(s, record, stats, d.ClearWorkers)
}

// noteL1Branch counts and records what one L1 tick decided.
func noteL1Branch(s *simState, rng *rand.Rand, record func(string, ...any), stats *SimStats, d L1Decision, before Drain) {
	switch d.Branch {
	case L1Begin:
		stats.DrainsStarted++
		if before.Phase == DrainDrained || before.Phase == DrainFailed {
			stats.StaleRedrains++
		}
		s.suspendsIgnored = len(s.actorsIn(simAwake)) > 0 && rng.IntN(s.rates.ignoreOneIn) == 0
		record("L1 begins draining (%s, gen %d)", d.Drain.Reason, d.Drain.LeaseGeneration)
	case L1Finish:
		stats.DrainsFinished++
		record("L1 reports drained")
	case L1Lost:
		stats.DrainsFailedLost++
		record("L1: a task actor crashed since the baseline -> drain-failed (lost)")
	case L1GiveUp:
		stats.DrainsFailedCeil++
		record("L1 gives up: ceiling spent")
	case L1Resuspend:
		stats.Resuspends++
		record("L1 brings the controller back to suspend again")
	case L1Wait:
		if s.templatePending || s.goldenAwake {
			stats.GoldenWaits++
		}
	case L1Cancel:
		record("L1 cancels the drain")
	}
}

// applySuspends asks AX to suspend. AX needs the controller pod to act -- and
// this drain's AX may be ignoring the requests.
func applySuspends(s *simState, rng *rand.Rand, record func(string, ...any), tasks []string) {
	if len(tasks) > 0 && s.controllerServing() && !s.suspendsIgnored {
		for i := range s.actors {
			if !slices.Contains(tasks, simTask(i)) {
				continue
			}
			switch s.actors[i].state {
			case simAwake:
				s.actors[i] = simActor{state: simCheckpointing, doneAt: s.now.Add(time.Duration(rng.IntN(8)) * time.Minute)}
				record("%s checkpointing", simUID(i))
			case simDoomed:
				// Its pod is gone: the suspend workflow crashes it.
				s.actors[i].state = simCrashed
				record("%s: suspend found its pod gone -> CRASHED", simUID(i))
			}
		}
	}
}

// applyClears deletes the worker pods L1 named, and notes whether any hosted
// something live (ClearingNeverLosesState).
func applyClears(s *simState, record func(string, ...any), stats *SimStats, workers []string) {
	for _, w := range workers {
		for i := range s.actors {
			if simWorker(i) != w {
				continue
			}
			if st := s.actors[i].state; st == simAwake || st == simCheckpointing || st == simDoomed {
				s.clearedLive = true
			}
			s.actors[i].state = simGone
			stats.WedgesCleared++
			record("L1 deletes %s's worker pod %s", simUID(i), w)
		}
	}
}

// simScale applies a replica count: up starts the pod at once (the
// conservative direction -- a resume path open sooner), down leaves the pod
// running until it has terminated a few minutes later.
func simScale(s *simState, rng *rand.Rand, want int, replicas *int, pod *bool, goneAt *time.Time) {
	if want == *replicas {
		return
	}
	*replicas = want
	if want == 1 {
		*pod = s.nodeLive()
		*goneAt = time.Time{}
		return
	}
	*goneAt = s.now.Add(time.Duration(rng.IntN(4)) * time.Minute)
}

// --- L2 ----------------------------------------------------------------------------

func simL2(s *simState, record func(string, ...any), stats *SimStats) {
	// L2 only runs on its tick.
	if s.now.Minute()%int(L2Tick/time.Minute) != 0 {
		return
	}
	target := s.target()
	s.readFailures = NextReadFailures(s.readFailures, s.leaseOK, target)
	since, alarm := NextStopping(s.stoppingSince, target, s.nodes, s.now)
	s.stoppingSince = since
	if alarm && !s.stopAlarm {
		stats.StopLatencyAlarms++
		record("L2: the node is still billing %s after its target went to zero -> alarm", s.now.Sub(since))
	}
	s.stopAlarm = s.stopAlarm || alarm

	d := DecideL2(Observation{
		Now: s.now, Lease: s.lease, LeaseOK: s.leaseOK,
		ConsecutiveReadFailures: s.readFailures, Drain: s.drain, Nodes: target,
	})
	if d.Action == ActionWait {
		return
	}
	stop := simStop{
		graceful: d.Action == ActionStopGraceful, byL2: true, reason: d.Reason,
		despiteLiveLease: s.leaseOK && s.now.Before(s.lease.Deadline) &&
			d.Reason != ReasonLeaseUnreadable && d.Reason != ReasonIdleDrained,
	}
	if stop.graceful {
		stats.GracefulStops++
		if d.Reason == ReasonIdleDrained {
			stats.IdleStops++
		}
		for i, a := range s.actors {
			if a.state == simCrashed && !slices.Contains(s.drain.BaselineCrashed, simUID(i)) {
				stop.silentLoss = true
			}
		}
	} else {
		stats.ForcedStops++
		switch d.Reason {
		case ReasonLeaseUnreadable:
			stats.ForcedLeaseUnreadable++
		case ReasonDrainFailed:
			stats.ForcedDrainFailed++
		case ReasonGraceExpired:
			stats.ForcedGraceExpired++
		case ReasonHeartbeatStale:
			stats.ForcedHeartbeatStale++
		}
	}
	requestStop(s, record, fmt.Sprintf("L2 %s (%s)", d.Action, d.Reason), stop)
}

// --- L3 ----------------------------------------------------------------------------

func simL3(s *simState, record func(string, ...any), stats *SimStats) {
	local := s.now.In(Location())
	if local.Hour() != L3StopHour || local.Minute() != 0 || !s.nodeLive() {
		return
	}
	// No logic, by design. That is the point of L3.
	stats.L3Stops++
	requestStop(s, record, "L3 daily stop", simStop{})
}

// requestStop takes the pool's target to zero. Everything on the node is
// evicted -- the reaper, the router and controller pods, every worker pod -- so
// anything with a live sandbox is doomed. The node itself bills on until
// nodeGoneAt.
func requestStop(s *simState, record func(string, ...any), why string, stop simStop) {
	stop.crashed = s.anythingAwake()
	s.lastStop = stop
	for i := range s.actors {
		if st := s.actors[i].state; st == simAwake || st == simCheckpointing {
			s.actors[i].state = simDoomed
		}
	}
	s.goldenAwake = false
	s.routerPod, s.controllerPod = false, false
	s.stopping = true
	s.nodeGoneAt = s.now.Add(s.latency)
	if stop.crashed {
		record("%s -- something awake is doomed", why)
	} else {
		record("%s", why)
	}
}

// --- the environment -----------------------------------------------------------------

func simEnvironment(s *simState, rng *rand.Rand, record func(string, ...any), stats *SimStats) {
	simInfrastructure(s, record)
	simActorsLive(s, rng, record, stats)
	simGolden(s, rng, record)
	simFailures(s, rng, record, stats)
}

// simInfrastructure: the node leaving, and scale-downs taking effect.
func simInfrastructure(s *simState, record func(string, ...any)) {
	// The node leaves stop latency after its target went to zero.
	if s.stopping && !s.now.Before(s.nodeGoneAt) {
		s.nodes, s.stopping = 0, false
		record("the node is gone")
	}
	// Scale-downs take effect.
	if !s.routerPodGoneAt.IsZero() && !s.now.Before(s.routerPodGoneAt) {
		s.routerPod, s.routerPodGoneAt = false, time.Time{}
	}
	if !s.controllerPodGone.IsZero() && !s.now.Before(s.controllerPodGone) {
		s.controllerPod, s.controllerPodGone = false, time.Time{}
	}
}

// simActorsLive: checkpoints landing, crashes being detected, and the router
// auto-resuming.
func simActorsLive(s *simState, rng *rand.Rand, record func(string, ...any), _ *SimStats) {
	// Checkpoints land.
	for i := range s.actors {
		if s.actors[i].state == simCheckpointing && s.nodeLive() && !s.now.Before(s.actors[i].doneAt) {
			s.actors[i] = simActor{state: simAtRest}
		}
	}
	// Substrate notices a doomed actor's pod is gone -- whenever it does.
	if doomed := s.actorsIn(simDoomed); len(doomed) > 0 && rng.IntN(20) == 0 {
		s.actors[doomed[0]].state = simCrashed
		record("%s CRASHED (detected)", simUID(doomed[0]))
	}
	// The router auto-resumes on a connection; it does not read the lease.
	if s.routerServing() && rng.IntN(50) == 0 {
		if idle := s.actorsIn(simAtRest); len(idle) > 0 {
			s.actors[idle[0]].state = simAwake
			record("router auto-resumes %s", simUID(idle[0]))
		}
	}
}

// simGolden: the controller creates a template, Substrate's own reconciler
// resumes its golden actor, and the flow settles.
func simGolden(s *simState, rng *rand.Rand, record func(string, ...any)) {
	switch {
	case s.controllerServing() && !s.templatePending && rng.IntN(300) == 0:
		s.templatePending = true
		record("a template for a new image")
	case s.nodeLive() && s.templatePending && !s.goldenAwake && rng.IntN(3) == 0:
		s.goldenAwake = true
		record("Substrate resumes the golden actor")
	case s.nodeLive() && s.templatePending && rng.IntN(8) == 0:
		s.templatePending, s.goldenAwake = false, false
		record("the golden flow settles")
	}
}

// simFailures: a worker pod dying, GCS failing, the node vanishing.
func simFailures(s *simState, rng *rand.Rand, record func(string, ...any), stats *SimStats) {
	// A worker pod dies on its own under an awake or checkpointing actor.
	if live := s.actorsIn(simAwake, simCheckpointing); s.nodeLive() && len(live) > 0 && rng.IntN(podLossOdds(s)) == 0 {
		s.actors[live[0]].state = simDoomed
		stats.WorkerPodsLost++
		record("%s's worker pod dies", simUID(live[0]))
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
		requestStop(s, record, "node lost", simStop{})
		s.nodes, s.stopping = 0, false
	}
}

// lastLines is the tail of a trace, at most n lines.
func lastLines(trace []string, n int) []string {
	if len(trace) <= n {
		return trace
	}
	return trace[len(trace)-n:]
}

func checkInvariants(s *simState, seed uint64, step int, trace []string) *SimViolation {
	fail := func(name, detail string) *SimViolation {
		return &SimViolation{Seed: seed, Step: step, Invariant: name, Detail: detail, Trace: trace}
	}

	// NoCrashOnGracefulSleep: a stop that claims to be graceful never found
	// anything awake. The ordering of L1's whole procedure exists for this.
	if s.lastStop.graceful && s.lastStop.crashed {
		return fail("NoCrashOnGracefulSleep",
			"a graceful stop took the pool away with something awake")
	}

	// NoSilentLoss: nor did it follow a crash since its drain's baseline.
	if s.lastStop.graceful && s.lastStop.silentLoss {
		return fail("NoSilentLoss",
			"a graceful stop followed a task actor's crash during its drain")
	}

	// DrainedRecordStaysTrue, the lemma: while a `drained` record exists,
	// nothing can wake an actor and nothing is awake.
	if s.drain.Phase == DrainDrained {
		var why []string
		if s.routerPod {
			why = append(why, "a router pod")
		}
		if s.controllerPod {
			why = append(why, "a controller pod")
		}
		if n := s.actorsIn(simAwake, simCheckpointing, simDoomed); len(n) > 0 {
			why = append(why, fmt.Sprintf("actors %v not at rest", n))
		}
		if s.goldenAwake || s.templatePending {
			why = append(why, "golden work")
		}
		if len(why) > 0 {
			return fail("DrainedRecordStaysTrue", "`drained` stands with "+strings.Join(why, ", "))
		}
	}

	// ClearingNeverLosesState: L1 never deleted a pod hosting anything live.
	if s.clearedLive {
		return fail("ClearingNeverLosesState", "L1 deleted the worker pod of a live actor")
	}

	// L3NeverHitsAwakeActor: no lease may authorise a node past the cap, so in
	// normal operation L3 cannot land on one. Checked as a state property: a
	// deadline still in the FUTURE is never inside the window between the cap
	// and L3. (`exe-sleep` legitimately leaves a deadline there in the past:
	// an expired deadline authorises nothing.)
	if s.nodes == 1 && s.lease.Deadline.After(s.now) {
		local := s.lease.Deadline.In(Location())
		capAt := time.Date(local.Year(), local.Month(), local.Day(), NightlyCapHour, 0, 0, 0, Location())
		if local.After(capAt) && local.Hour() < L3StopHour {
			return fail("L3NeverHitsAwakeActor",
				fmt.Sprintf("a live lease deadline %s falls inside the cap window",
					local.Format(time.RFC3339)))
		}
	}

	// ExtendBeatsStaleDrained: no stop L2 took from a lease it could read lands
	// before that lease's deadline. Judged at the stop, as the model judges it
	// (stoppedDespiteLiveLease): only L2's stops (a vanishing node or L3 obey
	// no lease); not a stop blind on three unreadable ticks (L2 cannot know
	// the lease is live); and not an idle stop about the current lease, which
	// is the rule itself -- nothing was awake for IdleZeroRunning. An extend
	// that comes AFTER a stop, while the node is still leaving, is no race: an
	// earlier version of this check judged by the extend's time and the sim
	// duly produced that false positive.
	if s.lastStop.byL2 && s.lastStop.despiteLiveLease {
		return fail("ExtendBeatsStaleDrained",
			fmt.Sprintf("L2 stopped (%s) a lease it could read before its deadline", s.lastStop.reason))
	}

	// NodesEventuallyZero, about BILLING: a node still there -- live or
	// stopping -- past deadline + bound. AwakeBound while L2's last read of the
	// lease succeeded, BlindAwakeBound whatever the reads did.
	if s.nodes == 1 && !s.lease.Deadline.IsZero() {
		bound := BlindAwakeBound()
		if s.readFailures == 0 {
			bound = AwakeBound()
		}
		if s.now.After(s.lease.Deadline.Add(bound)) {
			return fail("NodesEventuallyZero",
				fmt.Sprintf("deadline passed %s ago (bound %s, read failures %d, stopping %v) and the node still bills",
					s.now.Sub(s.lease.Deadline), bound, s.readFailures, s.stopping))
		}
	}

	return nil
}

func (a simActorState) String() string { return simActorNames[a] }

// rawResumeOdds and podLossOdds make the interleavings the drain exists for --
// a raw resume, or a worker pod dying, WHILE a drain runs -- common enough for
// the sweep to reach them many times, not once by luck.
func rawResumeOdds(s *simState) int {
	if s.drain.Phase == DrainDraining {
		return 8
	}
	return s.rates.rawResumeIn
}

func podLossOdds(s *simState) int {
	if s.drain.Phase == DrainDraining {
		return 60
	}
	return s.rates.podLossIn
}
