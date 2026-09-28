package main

import (
	"context"
	"fmt"
	"slices"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ops"
)

var t0 = time.Date(2026, 9, 28, 3, 0, 0, 0, time.UTC)

// live is a lease with an hour left, woken two hours ago.
func live(w *world) {
	w.put(ops.LeaseObject, lease.Lease{Deadline: t0.Add(time.Hour), WokenAt: t0.Add(-2 * time.Hour)})
}

// expired is a lease whose deadline passed a minute ago.
func expired(w *world) {
	w.put(ops.LeaseObject, lease.Lease{Deadline: t0.Add(-time.Minute), WokenAt: t0.Add(-2 * time.Hour)})
}

// draining writes a drain in flight about the current lease, begun `age` ago,
// with the router already closed by it.
func draining(w *world, age time.Duration) {
	w.put(ops.DrainObject, lease.Drain{
		Phase:           lease.DrainDraining,
		Heartbeat:       t0.Add(-time.Minute),
		StartedAt:       t0.Add(-age),
		LeaseGeneration: w.objects[ops.LeaseObject].generation,
		Reason:          lease.ReasonDeadlinePassed,
	})
	w.replicas[router], w.pods[router] = 0, 0
}

func tick(t *testing.T, w *world, now time.Time) (*logBuffer, error) {
	t.Helper()
	out := &logBuffer{}
	err := w.reaper(out).tick(context.Background(), now)
	return out, err
}

func index(calls []string, call string) int { return slices.Index(calls, call) }

func TestAQuietLiveLeaseRecordsTheIdleClockOnceAndActsOnNothing(t *testing.T) {
	// given a live lease and nothing awake
	w := newWorld(t)
	live(w)
	w.actors = []lease.ActorObs{{UID: "u1", Task: "exe/p1", State: lease.ActorAtRest}}

	// when L1 ticks for the first time, it starts the idle clock -- a record
	// only it writes, because each tick is a new process
	out, err := tick(t, w, t0)
	if err != nil {
		t.Fatal(err)
	}
	if d := w.drain(); !d.IdleSince.Equal(t0) || d.Phase != lease.DrainNone {
		t.Errorf("record %+v, want no drain and idleSince %s", d, t0)
	}
	if got := out.decision(t)["branch"]; got != string(lease.L1NoOp) {
		t.Errorf("branch %v, want NoOp", got)
	}

	// and a minute later nothing has changed, so nothing is written
	w.puts = nil
	if _, err := tick(t, w, t0.Add(time.Minute)); err != nil {
		t.Fatal(err)
	}
	if len(w.puts) != 0 {
		t.Errorf("an unchanged record was written again: %v", w.puts)
	}
	// and no tick touched the cluster
	for _, c := range w.calls {
		if slices.Contains([]string{"k8s.SetScale", "ax.Suspend", "k8s.DeletePod"}, firstWord(c)) {
			t.Errorf("a quiet tick acted: %s", c)
		}
	}
}

func firstWord(s string) string {
	for i, c := range s {
		if c == ' ' {
			return s[:i]
		}
	}
	return s
}

func TestTheActorsAreReadBeforeTheLease(t *testing.T) {
	// The baseline of a drain begun this tick is complete before the lease
	// is read (plan D2 step 1): a crash during the listing precedes the
	// drain, and anything later is caught against the baseline.
	w := newWorld(t)
	expired(w)
	if _, err := tick(t, w, t0); err != nil {
		t.Fatal(err)
	}
	actors, templates := index(w.calls, "substrate.Actors"), index(w.calls, "substrate.TemplatesPending")
	leaseRead, drainRead := index(w.calls, "gcs.Get lease.json"), index(w.calls, "gcs.Get drain.json")
	if actors < 0 || templates < 0 || leaseRead < 0 || drainRead < 0 {
		t.Fatalf("missing reads: %v", w.calls)
	}
	if actors > leaseRead || templates > leaseRead {
		t.Errorf("the lease was read before the actors: %v", w.calls)
	}
}

func TestAnExpiredLeaseBeginsADrainAndClosesTheRouterOnlyOnceItIsRecorded(t *testing.T) {
	// given an expired lease, one task awake and one already crashed
	w := newWorld(t)
	expired(w)
	w.actors = []lease.ActorObs{
		{UID: "u1", Task: "exe/p1", State: lease.ActorAwake, Worker: "exe/w-a/pa"},
		{UID: "u2", Task: "exe/p2", State: lease.ActorCrashed},
	}

	out, err := tick(t, w, t0)
	if err != nil {
		t.Fatal(err)
	}

	// then `draining` is recorded about this lease, with the baseline
	d := w.drain()
	if d.Phase != lease.DrainDraining || d.LeaseGeneration != w.objects[ops.LeaseObject].generation {
		t.Errorf("record %+v, want draining about lease %d", d, w.objects[ops.LeaseObject].generation)
	}
	if !slices.Equal(d.BaselineCrashed, []string{"u2"}) {
		t.Errorf("baseline %v, want [u2]", d.BaselineCrashed)
	}
	// and the router goes to zero, after the record and never before it
	put, scale := index(w.calls, "gcs.Put drain.json"), index(w.calls, "k8s.SetScale "+router+" 0")
	if put < 0 || scale < 0 || scale < put {
		t.Errorf("want the record written, then the router closed: %v", w.calls)
	}
	if len(w.suspended) != 0 {
		t.Errorf("begin suspended %v; it only closes the router", w.suspended)
	}
	if got := out.decision(t)["branch"]; got != string(lease.L1Begin) {
		t.Errorf("branch %v, want Begin", got)
	}
}

func TestADrainAsksAXToSuspendEachAwakeTask(t *testing.T) {
	w := newWorld(t)
	expired(w)
	draining(w, time.Minute)
	w.actors = []lease.ActorObs{
		{UID: "u1", Task: "exe/p1", State: lease.ActorAwake},
		{UID: "u2", Task: "exe/p2", State: lease.ActorCheckpointing},
		{UID: "g1", Golden: true, State: lease.ActorAwake},
	}

	if _, err := tick(t, w, t0); err != nil {
		t.Fatal(err)
	}
	if !slices.Equal(w.suspended, []string{"exe/p1"}) {
		t.Errorf("suspended %v, want [exe/p1]: never a checkpoint in flight, never a golden actor", w.suspended)
	}
	if d := w.drain(); !d.Heartbeat.Equal(t0) {
		t.Errorf("heartbeat %s, want %s", d.Heartbeat, t0)
	}
}

func TestTheDrainQuiescesTheControllerAndFinishesOnlyWhenEveryPodIsGone(t *testing.T) {
	// given a drain with nothing awake and the controller still up
	w := newWorld(t)
	expired(w)
	draining(w, time.Minute)
	w.actors = []lease.ActorObs{{UID: "u1", Task: "exe/p1", State: lease.ActorAtRest}}

	// then the controller goes to zero
	if _, err := tick(t, w, t0); err != nil {
		t.Fatal(err)
	}
	if index(w.calls, "k8s.SetScale "+controller+" 0") < 0 {
		t.Fatalf("the controller was not quiesced: %v", w.calls)
	}
	if d := w.drain(); d.Phase != lease.DrainDraining {
		t.Fatalf("phase %s with the controller pod still up, want draining", d.Phase)
	}

	// and while its pod is still terminating, the drain waits
	if _, err := tick(t, w, t0.Add(time.Minute)); err != nil {
		t.Fatal(err)
	}
	if d := w.drain(); d.Phase != lease.DrainDraining {
		t.Fatalf("phase %s with a controller pod terminating, want draining", d.Phase)
	}

	// and once it is gone, `drained`
	w.pods[controller] = 0
	if _, err := tick(t, w, t0.Add(2*time.Minute)); err != nil {
		t.Fatal(err)
	}
	if d := w.drain(); d.Phase != lease.DrainDrained {
		t.Errorf("phase %s with nothing left, want drained", d.Phase)
	}
}

func TestARecordWriteThatLosesTheRaceActsOnNothing(t *testing.T) {
	// Only one L1 runs at a time (the CronJob forbids overlap), but a manual
	// run can still land beside it. Its record stands; this tick's decision
	// was about the one before it, so it does nothing and the next tick
	// decides again.
	w := newWorld(t)
	expired(w)
	w.actors = []lease.ActorObs{{UID: "u1", Task: "exe/p1", State: lease.ActorAwake}}
	w.putErr[ops.DrainObject] = fmt.Errorf("drain.json: %w", gcp.ErrPreconditionFailed)

	out, err := tick(t, w, t0)
	if err != nil {
		t.Fatalf("a lost race is not a failure: %v", err)
	}
	for _, c := range w.calls {
		if slices.Contains([]string{"k8s.SetScale", "ax.Suspend", "k8s.DeletePod"}, firstWord(c)) {
			t.Errorf("acted after losing the race: %s", c)
		}
	}
	if !slices.Contains(out.events(), "warning/WARNING") {
		t.Errorf("events %v, want a warning", out.events())
	}
}

func TestAReadThatFailsDecidesNothing(t *testing.T) {
	// A tick that cannot see everything decides nothing: a partial view is how
	// a drain finishes over an actor it never saw (plan D5).
	tests := []struct {
		name    string
		breakIt func(w *world)
	}{
		{"the actor list", func(w *world) { w.actorsErr = errBoom }},
		{"the template list", func(w *world) { w.templateErr = errBoom }},
		{"a replica count", func(w *world) { w.scaleErr = errBoom }},
		{"the drain record", func(w *world) { w.getErr[ops.DrainObject] = errBoom }},
		{"a drain record that is not one", func(w *world) {
			w.objects[ops.DrainObject] = storedObject{body: []byte(`{"phase":`), generation: 99}
		}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			w := newWorld(t)
			expired(w)
			w.actors = []lease.ActorObs{{UID: "u1", Task: "exe/p1", State: lease.ActorAwake}}
			tc.breakIt(w)

			out, err := tick(t, w, t0)
			if err == nil {
				t.Fatal("the tick succeeded on a failed read")
			}
			if len(w.puts) != 0 {
				t.Errorf("wrote %v on a failed read", w.puts)
			}
			for _, c := range w.calls {
				if slices.Contains([]string{"k8s.SetScale", "ax.Suspend", "k8s.DeletePod"}, firstWord(c)) {
					t.Errorf("acted on a failed read: %s", c)
				}
			}
			if events := out.events(); slices.Contains(events, "decision/INFO") || slices.Contains(events, "decision/NOTICE") {
				t.Errorf("events %v: a tick that read nothing whole decided something", events)
			}
		})
	}
}

func TestAnUnreadableLeaseIsATriggerNotAFailure(t *testing.T) {
	// The lease is the operator's. L1 cannot read it means nothing authorises
	// the node: drain (the model's LeaseUnreadable trigger).
	w := newWorld(t)
	live(w)
	w.getErr[ops.LeaseObject] = errBoom

	if _, err := tick(t, w, t0); err != nil {
		t.Fatalf("an unreadable lease failed the tick: %v", err)
	}
	if d := w.drain(); d.Phase != lease.DrainDraining || d.Reason != lease.ReasonLeaseUnreadable {
		t.Errorf("record %s / %s, want draining for %s", d.Phase, d.Reason, lease.ReasonLeaseUnreadable)
	}
}

func TestAWedgedWorkerPodIsDeletedAsTheStoreNamedIt(t *testing.T) {
	w := newWorld(t)
	live(w)
	w.put(ops.DrainObject, lease.Drain{WedgeSeen: map[string]time.Time{"u1": t0.Add(-lease.WedgeClear)}})
	w.actors = []lease.ActorObs{{UID: "u1", Task: "exe/p1", State: lease.ActorDeleting, Worker: "exe/w-a/pa"}}

	if _, err := tick(t, w, t0); err != nil {
		t.Fatal(err)
	}
	if !slices.Equal(w.deleted, []string{"exe/w-a/pa"}) {
		t.Errorf("deleted %v, want [exe/w-a/pa]", w.deleted)
	}
	if d := w.drain(); len(d.WedgeSeen) != 0 {
		t.Errorf("a cleared wedge is still remembered: %v", d.WedgeSeen)
	}
}

func TestWhatTheTickWorksAroundIsAWarningNotAFailure(t *testing.T) {
	tests := []struct {
		name  string
		setup func(w *world)
	}{
		{"a task AX does not have", func(w *world) {
			expired(w)
			draining(w, time.Minute)
			w.actors = []lease.ActorObs{{UID: "u1", Task: "exe/p1", State: lease.ActorAwake}}
			w.noTask["exe/p1"] = true
		}},
		{"a worker pod replaced under its name", func(w *world) {
			live(w)
			w.put(ops.DrainObject, lease.Drain{WedgeSeen: map[string]time.Time{"u1": t0.Add(-lease.WedgeClear)}})
			w.actors = []lease.ActorObs{{UID: "u1", Task: "exe/p1", State: lease.ActorDeleting, Worker: "exe/w-a/pa"}}
			w.replaced["exe/w-a/pa"] = true
		}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			w := newWorld(t)
			tc.setup(w)
			out, err := tick(t, w, t0)
			if err != nil {
				t.Fatalf("the tick failed: %v", err)
			}
			if !slices.Contains(out.events(), "warning/WARNING") {
				t.Errorf("events %v, want a warning", out.events())
			}
		})
	}
}

func TestAnActionThatFailsFailsTheTickAndTheRecordStands(t *testing.T) {
	// The record is written before anything is done, so a failed action
	// leaves the drain recorded, and the next tick does it again: every
	// decision is a target state (L1Decision).
	w := newWorld(t)
	expired(w)
	w.setErr = errBoom

	out, err := tick(t, w, t0)
	if err == nil {
		t.Fatal("a failed scale-down reported success")
	}
	if d := w.drain(); d.Phase != lease.DrainDraining {
		t.Errorf("phase %s, want the drain recorded despite the failed action", d.Phase)
	}
	if !slices.Contains(out.events(), "failure/ERROR") {
		t.Errorf("events %v, want a failure line", out.events())
	}
}

func TestADryRunDecidesAndLogsButWritesAndActsOnNothing(t *testing.T) {
	w := newWorld(t)
	expired(w)
	w.actors = []lease.ActorObs{{UID: "u1", Task: "exe/p1", State: lease.ActorAwake}}

	out := &logBuffer{}
	r := w.reaper(out)
	r.dryRun = true
	if err := r.tick(context.Background(), t0); err != nil {
		t.Fatal(err)
	}
	if len(w.puts) != 0 {
		t.Errorf("a dry run wrote %v", w.puts)
	}
	for _, c := range w.calls {
		if slices.Contains([]string{"k8s.SetScale", "ax.Suspend", "k8s.DeletePod"}, firstWord(c)) {
			t.Errorf("a dry run acted: %s", c)
		}
	}
	line := out.decision(t)
	if line["branch"] != string(lease.L1Begin) || line["dryRun"] != true {
		t.Errorf("decision %v, want Begin with dryRun", line)
	}
}

func TestTheDecisionLineSaysWhatTheTickSawAndDid(t *testing.T) {
	w := newWorld(t)
	expired(w)
	draining(w, time.Minute)
	w.pending = true
	w.actors = []lease.ActorObs{
		{UID: "u1", Task: "exe/p1", State: lease.ActorAwake},
		{UID: "u2", Task: "exe/p2", State: lease.ActorAtRest},
	}

	out, err := tick(t, w, t0)
	if err != nil {
		t.Fatal(err)
	}
	line := out.decision(t)
	want := map[string]any{
		"event":            "decision",
		"branch":           string(lease.L1Suspend),
		"phase":            string(lease.DrainDraining),
		"reason":           string(lease.ReasonDeadlinePassed),
		"leaseReadable":    true,
		"leaseGeneration":  float64(w.objects[ops.LeaseObject].generation),
		"awake":            float64(1),
		"templatesPending": true,
		"router":           float64(0),
		"controller":       float64(1),
	}
	for k, v := range want {
		if line[k] != v {
			t.Errorf("%s = %v, want %v", k, line[k], v)
		}
	}
	if s, _ := line["suspend"].([]any); len(s) != 1 || s[0] != "exe/p1" {
		t.Errorf("suspend = %v, want [exe/p1]", line["suspend"])
	}
}

func TestSeverityFollowsWhatTheBranchMeans(t *testing.T) {
	// INFO for a tick with nothing to report, NOTICE for one that changed
	// something, WARNING for a drain that failed: L2 forces and pages on it,
	// so this line is the reader's why, not a second page.
	w := newWorld(t)
	expired(w)
	draining(w, lease.DrainCeiling)
	w.actors = []lease.ActorObs{{UID: "u1", Task: "exe/p1", State: lease.ActorAwake}}

	out, err := tick(t, w, t0)
	if err != nil {
		t.Fatal(err)
	}
	if got := out.events(); !slices.Contains(got, "decision/WARNING") {
		t.Errorf("a drain that gave up logged %v, want decision/WARNING", got)
	}
}
