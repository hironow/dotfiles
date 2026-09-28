package lease

import (
	"slices"
	"testing"
	"time"
)

// DecideL1 is the in-cluster drain's whole judgement: which of the model's
// L1 branches this tick takes, and what it leaves behind -- drain.json, the
// two replica counts, the suspends, and the one kind of pod it may delete.
// Rows are grouped the way the model's l1* actions are, and every row asserts
// the branch as well as the effects, for the same reason DecideL2's table
// asserts the Reason: the right effect for the wrong reason is a bug that
// shows up later.

const testGen = int64(7)

// l1Base is a live node with a readable lease that has an hour left, both
// resume paths open, no drain record, and two task actors at rest.
func l1Base() L1Observation {
	now := ref()
	return L1Observation{
		Now:     now,
		Lease:   Lease{Deadline: now.Add(time.Hour), WokenAt: now.Add(-2 * time.Hour), Generation: testGen},
		LeaseOK: true,
		Actors: []ActorObs{
			{UID: "a1", Task: "t1", State: ActorAtRest, Worker: "w1"},
			{UID: "a2", Task: "t2", State: ActorAtRest, Worker: "w2"},
		},
		RouterReplicas:     1,
		ControllerReplicas: 1,
		RouterPods:         1,
		ControllerPods:     1,
	}
}

// expired is l1Base with the deadline a minute ago.
func expired(o L1Observation) L1Observation {
	o.Lease.Deadline = o.Now.Add(-time.Minute)
	return o
}

// draining is o with a drain in flight about the current lease, begun
// `age` ago, and the router already closed by it.
func draining(o L1Observation, age time.Duration) L1Observation {
	o.Drain = Drain{
		Phase:           DrainDraining,
		Heartbeat:       o.Now.Add(-time.Minute),
		StartedAt:       o.Now.Add(-age),
		LeaseGeneration: o.Lease.Generation,
		Reason:          ReasonDeadlinePassed,
	}
	o.RouterReplicas, o.RouterPods = 0, 0
	return o
}

// withActor sets one actor's state.
func withActor(o L1Observation, uid string, s ActorState) L1Observation {
	o.Actors = slices.Clone(o.Actors)
	for i := range o.Actors {
		if o.Actors[i].UID == uid {
			o.Actors[i].State = s
		}
	}
	return o
}

// quiet is o with the controller down and both pods gone: the barrier's pod
// clauses hold.
func quiet(o L1Observation) L1Observation {
	o.ControllerReplicas, o.ControllerPods = 0, 0
	o.RouterReplicas, o.RouterPods = 0, 0
	return o
}

func TestDecideL1Branches(t *testing.T) {
	tests := []struct {
		name string
		obs  L1Observation
		want L1Branch
	}{
		// --- no trigger ---
		{"a live lease with both paths open does nothing", l1Base(), L1NoOp},
		{"a live lease with the router down reopens both paths", func() L1Observation {
			o := l1Base()
			o.RouterReplicas, o.RouterPods = 0, 0
			return o
		}(), L1Reopen},
		{"a live lease with the controller down reopens both paths", func() L1Observation {
			o := l1Base()
			o.ControllerReplicas = 0
			return o
		}(), L1Reopen},
		{"a live lease cancels a drain in flight", draining(l1Base(), time.Minute), L1Cancel},
		{"a live lease cancels a drained record, even a current one", func() L1Observation {
			o := l1Base()
			o.Drain = Drain{Phase: DrainDrained, LeaseGeneration: testGen}
			return o
		}(), L1Cancel},

		// --- begin ---
		{"an expired lease with no record begins a drain", expired(l1Base()), L1Begin},
		{"an unreadable lease begins a drain", func() L1Observation {
			o := l1Base()
			o.LeaseOK = false
			return o
		}(), L1Begin},
		{"a terminal record about an OLDER lease does not hold L1 back: it drains again", func() L1Observation {
			o := expired(l1Base())
			o.Drain = Drain{Phase: DrainDrained, LeaseGeneration: testGen - 1}
			return o
		}(), L1Begin},
		{"a drain-failed about an older lease also drains again", func() L1Observation {
			o := expired(l1Base())
			o.Drain = Drain{Phase: DrainFailed, LeaseGeneration: testGen - 1}
			return o
		}(), L1Begin},

		// --- settled ---
		{"a drained record about this lease settles: nothing left to do", func() L1Observation {
			o := expired(l1Base())
			o.Drain = Drain{Phase: DrainDrained, LeaseGeneration: testGen}
			return o
		}(), L1Settled},
		{"a drain-failed about this lease settles too", func() L1Observation {
			o := expired(l1Base())
			o.Drain = Drain{Phase: DrainFailed, LeaseGeneration: testGen}
			return o
		}(), L1Settled},
		{"with the lease unreadable a terminal record cannot be judged stale, so it settles", func() L1Observation {
			o := expired(l1Base())
			o.LeaseOK = false
			o.Drain = Drain{Phase: DrainDrained, LeaseGeneration: testGen - 1}
			return o
		}(), L1Settled},

		// --- lost ---
		{"a task actor crashed since the baseline is a loss", withActor(draining(expired(l1Base()), time.Minute), "a1", ActorCrashed), L1Lost},
		{"a crash is a loss even when the barrier otherwise holds", withActor(quiet(draining(expired(l1Base()), time.Minute)), "a1", ActorCrashed), L1Lost},
		{"an actor already crashed at the baseline is not a new loss", func() L1Observation {
			o := withActor(quiet(draining(expired(l1Base()), time.Minute)), "a1", ActorCrashed)
			o.Drain.BaselineCrashed = []string{"a1"}
			return o
		}(), L1Finish},
		{"an actor missing from the baseline that is crashed now counts as lost", func() L1Observation {
			o := quiet(draining(expired(l1Base()), time.Minute))
			o.Drain.BaselineCrashed = []string{"a1"}
			o.Actors = append(slices.Clone(o.Actors), ActorObs{UID: "a3", Task: "t3", State: ActorCrashed})
			return o
		}(), L1Lost},
		{"a golden actor's crash is a failed template, not a lost task", func() L1Observation {
			o := quiet(draining(expired(l1Base()), time.Minute))
			o.Actors = append(slices.Clone(o.Actors), ActorObs{UID: "g1", Golden: true, State: ActorCrashed})
			return o
		}(), L1Finish},

		// --- finish and its clauses ---
		{"nothing awake, no template, no pod: drained", quiet(draining(expired(l1Base()), time.Minute)), L1Finish},
		{"a controller pod still terminating holds `drained` back", func() L1Observation {
			o := quiet(draining(expired(l1Base()), time.Minute))
			o.ControllerPods = 1
			return o
		}(), L1Wait},
		{"a router pod still terminating holds `drained` back", func() L1Observation {
			o := quiet(draining(expired(l1Base()), time.Minute))
			o.RouterPods = 1
			return o
		}(), L1Wait},
		{"a template in flight holds `drained` back", func() L1Observation {
			o := quiet(draining(expired(l1Base()), time.Minute))
			o.TemplatesPending = true
			return o
		}(), L1Wait},
		{"an awake golden actor holds `drained` back", func() L1Observation {
			o := quiet(draining(expired(l1Base()), time.Minute))
			o.Actors = append(slices.Clone(o.Actors), ActorObs{UID: "g1", Golden: true, State: ActorAwake})
			return o
		}(), L1Wait},
		{"a checkpoint still writing holds `drained` back", withActor(quiet(draining(expired(l1Base()), time.Minute)), "a1", ActorCheckpointing), L1Wait},
		{"a router still scaled to one holds `drained` back, even with no pod up yet", func() L1Observation {
			o := quiet(draining(expired(l1Base()), time.Minute))
			o.RouterReplicas = 1
			return o
		}(), L1Wait},

		// --- the ceiling ---
		{"the ceiling spent with something awake gives up", withActor(draining(expired(l1Base()), DrainCeiling), "a1", ActorAwake), L1GiveUp},
		{"one second before the ceiling it keeps trying", withActor(draining(expired(l1Base()), DrainCeiling-time.Second), "a1", ActorAwake), L1Suspend},
		{"the ceiling spent with the barrier holding still finishes", quiet(draining(expired(l1Base()), DrainCeiling+time.Minute)), L1Finish},

		// --- suspend, quiesce, wait ---
		{"an awake task with the controller up is suspended", withActor(draining(expired(l1Base()), time.Minute), "a1", ActorAwake), L1Suspend},
		{"an awake task with the controller down brings the controller back", withActor(quiet(draining(expired(l1Base()), time.Minute)), "a1", ActorAwake), L1Resuspend},
		{"nothing awake with the controller up: quiesce it", draining(expired(l1Base()), time.Minute), L1Quiesce},
		{"nothing awake but a checkpoint writing, controller up: quiesce anyway", withActor(draining(expired(l1Base()), time.Minute), "a1", ActorCheckpointing), L1Quiesce},
		{"nothing awake, controller down, a checkpoint writing: wait", withActor(quiet(draining(expired(l1Base()), time.Minute)), "a1", ActorCheckpointing), L1Wait},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := DecideL1(tc.obs).Branch; got != tc.want {
				t.Errorf("branch: want %s, got %s", tc.want, got)
			}
		})
	}
}

func TestDecideL1BeginRecordsTheBaselineAndClosesTheRouter(t *testing.T) {
	// given an expired lease, one actor already crashed and one at rest
	o := withActor(expired(l1Base()), "a2", ActorCrashed)

	// when
	d := DecideL1(o)

	// then the record is `draining` about this lease, with the baseline
	if d.Branch != L1Begin || d.Drain.Phase != DrainDraining {
		t.Fatalf("want a begun drain, got %s / %s", d.Branch, d.Drain.Phase)
	}
	if d.Drain.LeaseGeneration != testGen || d.Drain.Reason != ReasonDeadlinePassed {
		t.Errorf("record about lease %d for %s, want %d for %s", d.Drain.LeaseGeneration, d.Drain.Reason, testGen, ReasonDeadlinePassed)
	}
	if !d.Drain.StartedAt.Equal(o.Now) || !d.Drain.Heartbeat.Equal(o.Now) {
		t.Errorf("started %s / heartbeat %s, want both %s", d.Drain.StartedAt, d.Drain.Heartbeat, o.Now)
	}
	if !slices.Equal(d.Drain.BaselineCrashed, []string{"a2"}) {
		t.Errorf("baseline %v, want [a2]", d.Drain.BaselineCrashed)
	}
	// and the router closes first; the controller stays up to carry the suspends
	if d.RouterReplicas != 0 || d.ControllerReplicas != 1 {
		t.Errorf("replicas router %d controller %d, want 0 and 1", d.RouterReplicas, d.ControllerReplicas)
	}
	if len(d.Suspend) != 0 || len(d.ClearWorkers) != 0 {
		t.Errorf("begin suspends %v and clears %v; it should do neither", d.Suspend, d.ClearWorkers)
	}
}

func TestDecideL1BeginKeepsTheLastGenerationWhenTheLeaseIsUnreadable(t *testing.T) {
	o := l1Base()
	o.LeaseOK = false
	o.Drain = Drain{LeaseGeneration: 5}

	d := DecideL1(o)

	if d.Drain.LeaseGeneration != 5 || d.Drain.Reason != ReasonLeaseUnreadable {
		t.Errorf("record about %d for %s, want 5 for %s", d.Drain.LeaseGeneration, d.Drain.Reason, ReasonLeaseUnreadable)
	}
}

func TestDecideL1SuspendsExactlyTheAwakeTaskActors(t *testing.T) {
	// given a drain, one awake task, one checkpointing, and an awake golden actor
	o := withActor(withActor(draining(expired(l1Base()), time.Minute), "a1", ActorAwake), "a2", ActorCheckpointing)
	o.Actors = append(o.Actors, ActorObs{UID: "g1", Golden: true, State: ActorAwake})

	d := DecideL1(o)

	if d.Branch != L1Suspend {
		t.Fatalf("branch %s, want Suspend", d.Branch)
	}
	if !slices.Equal(d.Suspend, []string{"t1"}) {
		t.Errorf("suspend %v, want [t1]: never a checkpoint already in flight, never a golden actor", d.Suspend)
	}
	if !d.Drain.Heartbeat.Equal(o.Now) {
		t.Errorf("heartbeat %s, want %s", d.Drain.Heartbeat, o.Now)
	}
}

func TestDecideL1QuiesceAndResuspendMoveOnlyTheController(t *testing.T) {
	q := DecideL1(draining(expired(l1Base()), time.Minute))
	if q.Branch != L1Quiesce || q.ControllerReplicas != 0 || q.RouterReplicas != 0 {
		t.Errorf("quiesce: %s router %d controller %d, want Quiesce 0 0", q.Branch, q.RouterReplicas, q.ControllerReplicas)
	}
	r := DecideL1(withActor(quiet(draining(expired(l1Base()), time.Minute)), "a1", ActorAwake))
	if r.Branch != L1Resuspend || r.ControllerReplicas != 1 || r.RouterReplicas != 0 {
		t.Errorf("resuspend: %s router %d controller %d, want Resuspend 0 1", r.Branch, r.RouterReplicas, r.ControllerReplicas)
	}
}

func TestDecideL1HoldsTheRouterShutThroughoutADrain(t *testing.T) {
	// Begin closes the router, but the scale call that does it can fail after
	// `draining` is written, and the next tick is a new process. So every tick
	// of a drain in progress holds the router at zero, whatever branch it
	// takes: a drain with the router open is one a connection can undo.
	rows := map[L1Branch]L1Observation{
		L1Lost:      withActor(draining(expired(l1Base()), time.Minute), "a1", ActorCrashed),
		L1GiveUp:    withActor(draining(expired(l1Base()), DrainCeiling), "a1", ActorAwake),
		L1Resuspend: withActor(quiet(draining(expired(l1Base()), time.Minute)), "a1", ActorAwake),
		L1Suspend:   withActor(draining(expired(l1Base()), time.Minute), "a1", ActorAwake),
		L1Quiesce:   draining(expired(l1Base()), time.Minute),
		L1Wait:      withActor(quiet(draining(expired(l1Base()), time.Minute)), "a1", ActorCheckpointing),
	}
	for want, o := range rows {
		o.RouterReplicas, o.RouterPods = 1, 1 // the scale-down that failed
		d := DecideL1(o)
		if d.Branch != want {
			t.Errorf("%s row took %s", want, d.Branch)
			continue
		}
		if d.RouterReplicas != 0 {
			t.Errorf("%s left the router at %d, want 0", want, d.RouterReplicas)
		}
	}
}

func TestDecideL1FinishAndFailureRecords(t *testing.T) {
	f := DecideL1(quiet(draining(expired(l1Base()), time.Minute)))
	if f.Drain.Phase != DrainDrained || !f.Drain.Heartbeat.Equal(ref()) || f.Drain.LeaseGeneration != testGen {
		t.Errorf("finish wrote %+v", f.Drain)
	}
	lost := DecideL1(withActor(draining(expired(l1Base()), time.Minute), "a1", ActorCrashed))
	if lost.Drain.Phase != DrainFailed || lost.Drain.Failure != FailureLost {
		t.Errorf("lost wrote %s / %q, want drain-failed / %q", lost.Drain.Phase, lost.Drain.Failure, FailureLost)
	}
	ceiling := DecideL1(withActor(draining(expired(l1Base()), DrainCeiling), "a1", ActorAwake))
	if ceiling.Drain.Phase != DrainFailed || ceiling.Drain.Failure != FailureCeiling {
		t.Errorf("ceiling wrote %s / %q, want drain-failed / %q", ceiling.Drain.Phase, ceiling.Drain.Failure, FailureCeiling)
	}
}

func TestDecideL1SettledWritesNoHeartbeat(t *testing.T) {
	// A heartbeat means "a drain is in progress". Writing one from a settled
	// record would turn L2's staleness test into "is L1 alive", which it is not.
	o := expired(l1Base())
	old := o.Now.Add(-20 * time.Minute)
	o.Drain = Drain{Phase: DrainDrained, LeaseGeneration: testGen, Heartbeat: old, IdleSince: o.Now.Add(-time.Hour)}

	d := DecideL1(o)

	if d.Branch != L1Settled || !d.Drain.Heartbeat.Equal(old) {
		t.Errorf("settled %s with heartbeat %s, want the old %s untouched", d.Branch, d.Drain.Heartbeat, old)
	}
}

func TestDecideL1CancelReopensBothPaths(t *testing.T) {
	o := quiet(l1Base())
	o.Drain = Drain{Phase: DrainDrained, LeaseGeneration: testGen - 1, Reason: ReasonIdle, BaselineCrashed: []string{"a1"}}

	d := DecideL1(o)

	if d.Branch != L1Cancel || d.Drain.Phase != DrainNone || d.Drain.LeaseGeneration != testGen {
		t.Errorf("cancel: %s wrote %+v", d.Branch, d.Drain)
	}
	if d.Drain.Reason != "" || len(d.Drain.BaselineCrashed) != 0 {
		t.Errorf("cancel kept the old drain's reason %q and baseline %v", d.Drain.Reason, d.Drain.BaselineCrashed)
	}
	if d.RouterReplicas != 1 || d.ControllerReplicas != 1 {
		t.Errorf("cancel left router %d controller %d, want both 1", d.RouterReplicas, d.ControllerReplicas)
	}
}

func TestDecideL1IdleClock(t *testing.T) {
	// The idle clock is L1's own observation, carried in drain.json from one
	// CronJob run to the next.
	tests := []struct {
		name       string
		obs        L1Observation
		wantIdle   time.Time
		wantBranch L1Branch
	}{
		{
			name:     "the first tick with nothing awake starts the clock",
			obs:      l1Base(),
			wantIdle: ref(), wantBranch: L1NoOp,
		},
		{
			name: "an awake task stops it",
			obs: func() L1Observation {
				o := withActor(l1Base(), "a1", ActorAwake)
				o.Drain.IdleSince = o.Now.Add(-10 * time.Minute)
				return o
			}(),
			wantIdle: time.Time{}, wantBranch: L1NoOp,
		},
		{
			name: "a checkpoint in flight stops it too",
			obs: func() L1Observation {
				o := withActor(l1Base(), "a1", ActorCheckpointing)
				o.Drain.IdleSince = o.Now.Add(-10 * time.Minute)
				return o
			}(),
			wantIdle: time.Time{}, wantBranch: L1NoOp,
		},
		{
			name: "an awake golden actor does not: it is Substrate's work, not the operator's",
			obs: func() L1Observation {
				o := l1Base()
				o.Actors = append(slices.Clone(o.Actors), ActorObs{UID: "g1", Golden: true, State: ActorAwake})
				o.Drain.IdleSince = o.Now.Add(-10 * time.Minute)
				return o
			}(),
			wantIdle: ref().Add(-10 * time.Minute), wantBranch: L1NoOp,
		},
		{
			name: "thirty idle minutes after the wake drain the cluster",
			obs: func() L1Observation {
				o := l1Base()
				o.Drain.IdleSince = o.Now.Add(-IdleZeroRunning)
				return o
			}(),
			wantIdle: ref().Add(-IdleZeroRunning), wantBranch: L1Begin,
		},
		{
			name: "one minute short is not enough",
			obs: func() L1Observation {
				o := l1Base()
				o.Drain.IdleSince = o.Now.Add(-IdleZeroRunning + time.Minute)
				return o
			}(),
			wantIdle: ref().Add(-IdleZeroRunning + time.Minute), wantBranch: L1NoOp,
		},
		{
			// A wake is a new session: the clock counts from the later of the two.
			name: "a recent wake restarts the clock",
			obs: func() L1Observation {
				o := l1Base()
				o.Drain.IdleSince = o.Now.Add(-2 * IdleZeroRunning)
				o.Lease.WokenAt = o.Now.Add(-10 * time.Minute)
				return o
			}(),
			wantIdle: ref().Add(-2 * IdleZeroRunning), wantBranch: L1NoOp,
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			d := DecideL1(tc.obs)
			if d.Branch != tc.wantBranch {
				t.Errorf("branch %s, want %s", d.Branch, tc.wantBranch)
			}
			if !d.Drain.IdleSince.Equal(tc.wantIdle) {
				t.Errorf("idleSince %s, want %s", d.Drain.IdleSince, tc.wantIdle)
			}
		})
	}
	if d := DecideL1(func() L1Observation {
		o := l1Base()
		o.Drain.IdleSince = o.Now.Add(-IdleZeroRunning)
		return o
	}()); d.Drain.Reason != ReasonIdle {
		t.Errorf("an idle drain records reason %q, want %q", d.Drain.Reason, ReasonIdle)
	}
}

func TestDecideL1Wedges(t *testing.T) {
	// given an actor stuck in DELETING on w1
	o := withActor(l1Base(), "a1", ActorDeleting)

	// when L1 first sees it, it only remembers when
	first := DecideL1(o)
	if seen := first.Drain.WedgeSeen["a1"]; !seen.Equal(o.Now) || len(first.ClearWorkers) != 0 {
		t.Fatalf("first sight: seen %s, cleared %v; want seen now, nothing cleared", seen, first.ClearWorkers)
	}

	// and one second short of WedgeClear it still waits
	o.Drain.WedgeSeen = map[string]time.Time{"a1": o.Now.Add(-WedgeClear + time.Second)}
	if d := DecideL1(o); len(d.ClearWorkers) != 0 {
		t.Errorf("cleared %v before WedgeClear", d.ClearWorkers)
	}

	// then at WedgeClear it deletes that worker's pod and forgets the wedge
	o.Drain.WedgeSeen = map[string]time.Time{"a1": o.Now.Add(-WedgeClear)}
	d := DecideL1(o)
	if !slices.Equal(d.ClearWorkers, []string{"w1"}) {
		t.Errorf("cleared %v, want [w1]", d.ClearWorkers)
	}
	if _, still := d.Drain.WedgeSeen["a1"]; still {
		t.Error("a cleared wedge is still remembered")
	}

	// and a wedge that resolved on its own is forgotten
	o = l1Base()
	o.Drain.WedgeSeen = map[string]time.Time{"a1": o.Now.Add(-time.Hour)}
	if d := DecideL1(o); len(d.Drain.WedgeSeen) != 0 || len(d.ClearWorkers) != 0 {
		t.Errorf("a resolved wedge left %v and cleared %v", d.Drain.WedgeSeen, d.ClearWorkers)
	}
}

func TestDecideL1NeverClearsAPodHostingAnythingLive(t *testing.T) {
	// The guard the model's ClearingNeverLosesState states: only DELETING is a
	// wedge. Elapsed time alone cannot tell a stuck checkpoint from a slow one.
	for _, s := range []ActorState{ActorAwake, ActorCheckpointing, ActorAtRest, ActorCrashed} {
		o := withActor(l1Base(), "a1", s)
		o.Drain.WedgeSeen = map[string]time.Time{"a1": o.Now.Add(-24 * time.Hour)}
		if d := DecideL1(o); len(d.ClearWorkers) != 0 {
			t.Errorf("an actor in state %s had its worker %v cleared", s, d.ClearWorkers)
		}
	}
	// nor a DELETING actor with no worker to delete
	o := withActor(l1Base(), "a1", ActorDeleting)
	o.Actors[0].Worker = ""
	o.Drain.WedgeSeen = map[string]time.Time{"a1": o.Now.Add(-time.Hour)}
	if d := DecideL1(o); len(d.ClearWorkers) != 0 {
		t.Errorf("cleared %v for an actor with no worker", d.ClearWorkers)
	}
}

func TestDecideL1NeverClearsAWorkerThatAlsoHostsALiveActor(t *testing.T) {
	// A worker can host more than one actor (WorkerResources.actors), and
	// deleting its pod takes every one of them. So a wedge is cleared only when
	// every actor on that worker is a wedge old enough to clear. The model has
	// one worker per actor and cannot say this; this test does.
	o := withActor(l1Base(), "a1", ActorDeleting)
	o.Actors[1].Worker = "w1" // a2 shares a1's worker
	o.Drain.WedgeSeen = map[string]time.Time{"a1": o.Now.Add(-WedgeClear)}
	for _, s := range []ActorState{ActorAwake, ActorCheckpointing, ActorAtRest, ActorCrashed} {
		o := withActor(o, "a2", s)
		if d := DecideL1(o); len(d.ClearWorkers) != 0 {
			t.Errorf("with a %s actor on w1 as well, cleared %v", s, d.ClearWorkers)
		}
	}

	// and a second wedge on the same worker that is still young holds it too
	young := withActor(o, "a2", ActorDeleting)
	young.Drain.WedgeSeen = map[string]time.Time{"a1": o.Now.Add(-WedgeClear), "a2": o.Now.Add(-time.Minute)}
	if d := DecideL1(young); len(d.ClearWorkers) != 0 {
		t.Errorf("with a young wedge on w1 as well, cleared %v", d.ClearWorkers)
	}

	// but two wedges both old enough clear their shared worker, once
	both := withActor(o, "a2", ActorDeleting)
	both.Drain.WedgeSeen = map[string]time.Time{"a1": o.Now.Add(-WedgeClear), "a2": o.Now.Add(-WedgeClear)}
	if d := DecideL1(both); !slices.Equal(d.ClearWorkers, []string{"w1"}) {
		t.Errorf("two ripe wedges on w1 cleared %v, want [w1]", d.ClearWorkers)
	}
}

func TestDecideL1WedgesClearInEveryBranch(t *testing.T) {
	// Wedge clearing is part of observing, not a branch: it happens during a
	// drain as well, so a wedge cannot hold `drained` back forever either.
	o := withActor(draining(expired(l1Base()), time.Minute), "a2", ActorDeleting)
	o.Drain.WedgeSeen = map[string]time.Time{"a2": o.Now.Add(-WedgeClear)}
	if d := DecideL1(o); !slices.Equal(d.ClearWorkers, []string{"w2"}) {
		t.Errorf("during a drain cleared %v, want [w2]", d.ClearWorkers)
	}
}
