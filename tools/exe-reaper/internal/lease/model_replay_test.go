package lease

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"testing"
	"time"
)

// The Quint model and the Go decisions are two encodings of one design, and
// nothing but a comparison keeps two encodings equal: the L2 table once
// disagreed on both of its boundaries (the model forced at once on an expired
// lease with no drain record, and exactly at the grace) while each passed its
// own tests.
//
// So `just spec-check` samples traces of the model's l2WorldStep and
// l1WorldStep -- random observations, each followed by the tick that decides
// it -- into fresh directories as ITF (the Informal Trace Format), and hands
// them to these tests in EXE_REAPER_L2_TRACES and EXE_REAPER_L1_TRACES. Every
// tick in them is replayed through DecideL2 or DecideL1, which must land in the
// same branch and leave the same state behind.

const (
	l2TracesEnv = "EXE_REAPER_L2_TRACES"
	l1TracesEnv = "EXE_REAPER_L1_TRACES"
)

// The model's L2 branches, by the Decision tag its enforce.last records.
var modelL2Branches = []string{
	"AlreadyStopped",
	"LeaseLive",
	"WaitedOnReadFailure",
	"StoppedOnReadFailures",
	"StoppedOnDrained",
	"StoppedOnIdleDrained",
	"WaitedForDrain",
	"StoppedForced",
}

// The model's L1 branches, by the name its l1Last ghost records.
var modelL1Branches = []string{
	"NoOp", "Reopen", "Cancel", "Begin", "Lost", "Finish", "GiveUp",
	"Resuspend", "Suspend", "Stall", "Quiesce", "Wait", "Settled",
}

// modelBranch is the model's Decision tag for a DecideL2 verdict. The model
// is coarser than the Go table in two places: it records every wait for L1 as
// WaitedForDrain (a draining record inside the window, or no record inside
// it) and every forced stop that read the lease as StoppedForced (drain-failed,
// a stale heartbeat, the grace spent). The reason tables in decide_test.go pin
// the finer split.
func modelBranch(d Decision) string {
	switch {
	case d == Decision{ActionWait, ReasonAlreadyStopped}:
		return "AlreadyStopped"
	case d == Decision{ActionWait, ReasonWithinLease}:
		return "LeaseLive"
	case d == Decision{ActionWait, ReasonTransientReadFailure}:
		return "WaitedOnReadFailure"
	case d == Decision{ActionStopForced, ReasonLeaseUnreadable}:
		return "StoppedOnReadFailures"
	case d == Decision{ActionStopGraceful, ReasonDrained}:
		return "StoppedOnDrained"
	case d == Decision{ActionStopGraceful, ReasonIdleDrained}:
		return "StoppedOnIdleDrained"
	case d.Action == ActionWait && (d.Reason == ReasonDrainingWithHeartbeat || d.Reason == ReasonAwaitingDrain):
		return "WaitedForDrain"
	case d.Action == ActionStopForced &&
		(d.Reason == ReasonDrainFailed || d.Reason == ReasonHeartbeatStale || d.Reason == ReasonGraceExpired):
		return "StoppedForced"
	}
	return fmt.Sprintf("<no model branch for %+v>", d)
}

func TestDecideL2AgreesWithTheModel(t *testing.T) {
	files := traceFiles(t, l2TracesEnv, "`just spec-check` samples the model's L2 traces into it and runs this")

	replayed := map[string]int{}
	for _, file := range files {
		states := loadModelTrace(t, file)
		for i := 1; i < len(states); i++ {
			before, after := states[i-1], states[i]
			// l2Tick is the only action that advances enforce.gen, by exactly
			// one; the re-rolls of l2World reset it to zero.
			if after.Enforce.Gen != before.Enforce.Gen+1 {
				continue
			}
			where := fmt.Sprintf("%s, step %d", filepath.Base(file), i)
			now := after.Clock.Now
			obs := before.l2Observation(now)
			got := DecideL2(obs)
			if branch := modelBranch(got); branch != after.Enforce.Last {
				t.Errorf("%s: the model took %s, DecideL2 %+v (%s)\n  model state before the tick: %s",
					where, after.Enforce.Last, got, branch, before)
			}
			if obs.ConsecutiveReadFailures != after.Enforce.LeaseReadFailures {
				t.Errorf("%s: read-failure run: the model carries %d, NextReadFailures %d\n  model state before the tick: %s",
					where, after.Enforce.LeaseReadFailures, obs.ConsecutiveReadFailures, before)
			}
			modelStops := before.target() == 1 && after.target() == 0
			if stops := got.Action != ActionWait; stops != modelStops {
				t.Errorf("%s: DecideL2 %+v, but the model's target went %d -> %d",
					where, got, before.target(), after.target())
			}
			since, alarm := NextStopping(atMinuteOrZero(before.Enforce.StoppingSince),
				before.target(), before.Cluster.Nodes, atModelMinute(now))
			if want := atMinuteOrZero(after.Enforce.StoppingSince); !since.Equal(want) {
				t.Errorf("%s: stop-latency detector: the model remembers %s, NextStopping %s", where, want, since)
			}
			if wantAlarm := after.Enforce.StopLatencyAlarm; (before.Enforce.StopLatencyAlarm || alarm) != wantAlarm {
				t.Errorf("%s: stop-latency alarm: the model has %v, NextStopping raised %v", where, wantAlarm, alarm)
			}
			replayed[after.Enforce.Last]++
		}
	}
	requireEveryBranch(t, "L2", modelL2Branches, replayed, len(files))
}

func TestDecideL1AgreesWithTheModel(t *testing.T) {
	files := traceFiles(t, l1TracesEnv, "`just spec-check` samples the model's L1 traces into it and runs this")

	replayed := map[string]int{}
	for _, file := range files {
		states := loadModelTrace(t, file)
		for i := 1; i < len(states); i++ {
			before, after := states[i-1], states[i]
			// Every l1Tick counts itself in the ghost; the re-rolls reset it.
			if after.L1Last.Ticks != before.L1Last.Ticks+1 {
				continue
			}
			where := fmt.Sprintf("%s, step %d", filepath.Base(file), i)
			obs := before.l1Observation(after.Clock.Now)
			got := DecideL1(obs)
			modelBranch := after.L1Last.Branch
			// The model's Suspend and Stall are one decision: whether AX acts
			// on the suspend request is the environment's business.
			wantBranch := modelBranch
			if wantBranch == "Stall" {
				wantBranch = string(L1Suspend)
			}
			if string(got.Branch) != wantBranch {
				t.Errorf("%s: the model took %s, DecideL1 %s\n  model state before the tick: %s",
					where, modelBranch, got.Branch, before)
				continue
			}
			if diff := after.drainDiff(got.Drain); diff != "" {
				t.Errorf("%s (%s): drain.json differs: %s\n  model state before the tick: %s",
					where, modelBranch, diff, before)
			}
			if got.RouterReplicas != after.Cluster.RouterReplicas || got.ControllerReplicas != after.Cluster.ControllerReplicas {
				t.Errorf("%s (%s): replicas: the model has router %d controller %d, DecideL1 %d %d",
					where, modelBranch, after.Cluster.RouterReplicas, after.Cluster.ControllerReplicas,
					got.RouterReplicas, got.ControllerReplicas)
			}
			var wantSuspend []string
			if modelBranch == "Suspend" || modelBranch == "Stall" {
				for _, a := range append(slices.Clone(before.Cluster.Awake), before.Cluster.Doomed...) {
					wantSuspend = append(wantSuspend, modelTask(a))
				}
				slices.Sort(wantSuspend)
			}
			if !slices.Equal(got.Suspend, wantSuspend) {
				t.Errorf("%s (%s): suspends: the model's %v, DecideL1 %v", where, modelBranch, wantSuspend, got.Suspend)
			}
			var wantClear []string
			for _, a := range before.Cluster.Deleting {
				if !slices.Contains(after.Cluster.Deleting, a) {
					wantClear = append(wantClear, modelWorker(a))
				}
			}
			slices.Sort(wantClear)
			if !slices.Equal(got.ClearWorkers, wantClear) {
				t.Errorf("%s (%s): cleared pods: the model's %v, DecideL1 %v", where, modelBranch, wantClear, got.ClearWorkers)
			}
			replayed[modelBranch]++
		}
	}
	requireEveryBranch(t, "L1", modelL1Branches, replayed, len(files))
}

func traceFiles(t *testing.T, env, how string) []string {
	t.Helper()
	dir := os.Getenv(env)
	if dir == "" {
		t.Skipf("needs %s; %s", env, how)
	}
	files, err := filepath.Glob(filepath.Join(dir, "*.itf.json"))
	if err != nil || len(files) == 0 {
		t.Fatalf("%s=%s holds no *.itf.json traces (%v): the model produced nothing to replay", env, dir, err)
	}
	return files
}

// requireEveryBranch fails a replay that never reached a branch: it says
// nothing about it.
func requireEveryBranch(t *testing.T, layer string, branches []string, replayed map[string]int, traces int) {
	t.Helper()
	for _, branch := range branches {
		if replayed[branch] == 0 {
			t.Errorf("no sampled trace reached the model's %s %s branch (replayed: %v)", layer, branch, replayed)
		}
	}
	t.Logf("replayed %d %s traces: %v", traces, layer, replayed)
}

// The model's state variables, decoded from ITF.
type modelState struct {
	Clock struct {
		Now int64
	}
	Lease struct {
		Deadline int64
		Gen      int64
		Readable bool
		WokenAt  int64
	}
	Drain struct {
		State           string
		Heartbeat       int64
		StartedAt       int64
		LeaseGen        int64
		Reason          string
		IdleSince       int64
		BaselineCrashed []int64
		WedgeSeen       map[string]int64
	}
	Enforce struct {
		Last              string
		Gen               int64
		LeaseReadFailures int
		StoppingSince     int64
		StopLatencyAlarm  bool
	}
	Cluster struct {
		Nodes              int
		Stopping           bool
		Awake              []int64
		Checkpointing      []int64
		Doomed             []int64
		Crashed            []int64
		Deleting           []int64
		Gone               []int64
		GoldenAwake        bool
		TemplatePending    bool
		RouterReplicas     int
		ControllerReplicas int
		RouterPod          bool
		ControllerPod      bool
	}
	L1Last struct {
		Branch string
		Ticks  int64
	}
}

func (s modelState) String() string {
	return fmt.Sprintf("lease{deadline %d gen %d readable %v woken %d} drain{%s %s heartbeat %d started %d gen %d idle %d baseline %v wedges %v} "+
		"run %d nodes %d stopping %v awake %v checkpointing %v doomed %v crashed %v deleting %v gone %v golden %v template %v "+
		"router %d/%v controller %d/%v",
		s.Lease.Deadline, s.Lease.Gen, s.Lease.Readable, s.Lease.WokenAt,
		s.Drain.State, s.Drain.Reason, s.Drain.Heartbeat, s.Drain.StartedAt, s.Drain.LeaseGen, s.Drain.IdleSince,
		s.Drain.BaselineCrashed, s.Drain.WedgeSeen,
		s.Enforce.LeaseReadFailures, s.Cluster.Nodes, s.Cluster.Stopping,
		s.Cluster.Awake, s.Cluster.Checkpointing, s.Cluster.Doomed, s.Cluster.Crashed, s.Cluster.Deleting, s.Cluster.Gone,
		s.Cluster.GoldenAwake, s.Cluster.TemplatePending,
		s.Cluster.RouterReplicas, s.Cluster.RouterPod, s.Cluster.ControllerReplicas, s.Cluster.ControllerPod)
}

// modelEpoch anchors the model's abstract minutes to a real instant. Any
// instant works: the rules compare only differences, never local hours.
var modelEpoch = time.Date(2026, 9, 27, 0, 0, 0, 0, time.UTC)

func atModelMinute(m int64) time.Time {
	return modelEpoch.Add(time.Duration(m) * time.Minute)
}

// atMinuteOrZero reads the model's -1 ("none") as the zero time.
func atMinuteOrZero(m int64) time.Time {
	if m < 0 {
		return time.Time{}
	}
	return atModelMinute(m)
}

// The model's actors are 1 and 2; these are their names on the Go side.
func modelActor(a int64) string  { return fmt.Sprintf("a%d", a) }
func modelTask(a int64) string   { return fmt.Sprintf("t%d", a) }
func modelWorker(a int64) string { return fmt.Sprintf("w%d", a) }

var modelPhases = map[string]DrainPhase{
	"DrainNone":   DrainNone,
	"Draining":    DrainDraining,
	"Drained":     DrainDrained,
	"DrainFailed": DrainFailed,
}

var modelReasons = map[string]Reason{
	"NoReason":        "",
	"DeadlinePassed":  ReasonDeadlinePassed,
	"IdleZeroRunning": ReasonIdle,
	"LeaseUnreadable": ReasonLeaseUnreadable,
}

// target is the pool's target size, which L2 reads as its size.
func (s modelState) target() int {
	if s.Cluster.Nodes == 1 && !s.Cluster.Stopping {
		return 1
	}
	return 0
}

func (s modelState) lease() Lease {
	return Lease{
		Deadline:   atModelMinute(s.Lease.Deadline),
		WokenAt:    atModelMinute(s.Lease.WokenAt),
		Generation: s.Lease.Gen,
	}
}

func (s modelState) drain() Drain {
	d := Drain{
		Phase:           modelPhases[s.Drain.State],
		Heartbeat:       atModelMinute(s.Drain.Heartbeat),
		StartedAt:       atModelMinute(s.Drain.StartedAt),
		LeaseGeneration: s.Drain.LeaseGen,
		Reason:          modelReasons[s.Drain.Reason],
		IdleSince:       atMinuteOrZero(s.Drain.IdleSince),
	}
	for _, a := range s.Drain.BaselineCrashed {
		d.BaselineCrashed = append(d.BaselineCrashed, modelActor(a))
	}
	slices.Sort(d.BaselineCrashed)
	for k, v := range s.Drain.WedgeSeen {
		if d.WedgeSeen == nil {
			d.WedgeSeen = map[string]time.Time{}
		}
		a, _ := strconv.ParseInt(k, 10, 64)
		d.WedgeSeen[modelActor(a)] = atModelMinute(v)
	}
	return d
}

// l2Observation is what the enforcer would see on a tick at minute now, in
// the world this state describes.
func (s modelState) l2Observation(now int64) Observation {
	return Observation{
		Now:                     atModelMinute(now),
		Lease:                   s.lease(),
		LeaseOK:                 s.Lease.Readable,
		ConsecutiveReadFailures: NextReadFailures(s.Enforce.LeaseReadFailures, s.Lease.Readable, s.target()),
		Drain:                   s.drain(),
		Nodes:                   s.target(),
	}
}

// l1Observation is what the in-cluster reaper would see on a tick at minute
// now. An actor the model calls doomed reads RUNNING in the store, which is
// exactly what L1 cannot tell apart; a gone one is not listed at all.
func (s modelState) l1Observation(now int64) L1Observation {
	o := L1Observation{
		Now:                atModelMinute(now),
		Lease:              s.lease(),
		LeaseOK:            s.Lease.Readable,
		Drain:              s.drain(),
		TemplatesPending:   s.Cluster.TemplatePending,
		RouterReplicas:     s.Cluster.RouterReplicas,
		ControllerReplicas: s.Cluster.ControllerReplicas,
	}
	if s.Cluster.RouterPod {
		o.RouterPods = 1
	}
	if s.Cluster.ControllerPod {
		o.ControllerPods = 1
	}
	for _, a := range []int64{1, 2} {
		state := ActorAtRest
		switch {
		case slices.Contains(s.Cluster.Gone, a):
			continue
		case slices.Contains(s.Cluster.Awake, a), slices.Contains(s.Cluster.Doomed, a):
			state = ActorAwake
		case slices.Contains(s.Cluster.Checkpointing, a):
			state = ActorCheckpointing
		case slices.Contains(s.Cluster.Crashed, a):
			state = ActorCrashed
		case slices.Contains(s.Cluster.Deleting, a):
			state = ActorDeleting
		}
		o.Actors = append(o.Actors, ActorObs{UID: modelActor(a), Task: modelTask(a), Worker: modelWorker(a), State: state})
	}
	if s.Cluster.GoldenAwake {
		o.Actors = append(o.Actors, ActorObs{UID: "golden", Golden: true, State: ActorAwake})
	}
	return o
}

// drainDiff compares the drain.json DecideL1 wrote with the model's, field by
// field; the Go-only Failure field is reporting and not in the model.
func (s modelState) drainDiff(got Drain) string {
	want := s.drain()
	var diffs []string
	if got.Phase != want.Phase {
		diffs = append(diffs, fmt.Sprintf("phase %q != %q", got.Phase, want.Phase))
	}
	if !got.Heartbeat.Equal(want.Heartbeat) {
		diffs = append(diffs, fmt.Sprintf("heartbeat %s != %s", got.Heartbeat, want.Heartbeat))
	}
	if !got.StartedAt.Equal(want.StartedAt) {
		diffs = append(diffs, fmt.Sprintf("startedAt %s != %s", got.StartedAt, want.StartedAt))
	}
	if got.LeaseGeneration != want.LeaseGeneration {
		diffs = append(diffs, fmt.Sprintf("leaseGeneration %d != %d", got.LeaseGeneration, want.LeaseGeneration))
	}
	if got.Reason != want.Reason {
		diffs = append(diffs, fmt.Sprintf("reason %q != %q", got.Reason, want.Reason))
	}
	if !got.IdleSince.Equal(want.IdleSince) {
		diffs = append(diffs, fmt.Sprintf("idleSince %s != %s", got.IdleSince, want.IdleSince))
	}
	if !slices.Equal(got.BaselineCrashed, want.BaselineCrashed) {
		diffs = append(diffs, fmt.Sprintf("baseline %v != %v", got.BaselineCrashed, want.BaselineCrashed))
	}
	if len(got.WedgeSeen) != len(want.WedgeSeen) {
		diffs = append(diffs, fmt.Sprintf("wedges %v != %v", got.WedgeSeen, want.WedgeSeen))
	} else {
		for k, v := range want.WedgeSeen {
			if !got.WedgeSeen[k].Equal(v) {
				diffs = append(diffs, fmt.Sprintf("wedges %v != %v", got.WedgeSeen, want.WedgeSeen))
				break
			}
		}
	}
	return strings.Join(diffs, "; ")
}

// loadModelTrace decodes one ITF trace into model states.
//
// ITF spells an integer {"#bigint": "N"}, a set {"#set": [...]}, a map
// {"#map": [[k, v], ...]} and a sum-type value {"tag": "X", "value": ...}, and
// qualifies each variable with its module path ("lease::leaseCore::drain");
// decoding goes through a plain-JSON rewrite of all of them, then matches
// variables by their last segment.
func loadModelTrace(t *testing.T, path string) []modelState {
	t.Helper()
	raw, err := os.ReadFile(path) //nolint:gosec // a trace file in the directory spec-check created
	if err != nil {
		t.Fatalf("reading %s: %v", path, err)
	}
	var trace struct {
		States []map[string]any `json:"states"`
	}
	if err := json.Unmarshal(raw, &trace); err != nil {
		t.Fatalf("%s is not ITF: %v", path, err)
	}
	if len(trace.States) == 0 {
		t.Fatalf("%s has no states", path)
	}

	states := make([]modelState, 0, len(trace.States))
	for i, st := range trace.States {
		plain := map[string]any{}
		for name, value := range st {
			if name == "#meta" {
				continue
			}
			plain[name[strings.LastIndex(name, "::")+len("::"):]] = fromITF(value)
		}
		buf, err := json.Marshal(plain)
		if err != nil {
			t.Fatalf("%s, state %d: %v", path, i, err)
		}
		var s modelState
		if err := json.Unmarshal(buf, &s); err != nil {
			t.Fatalf("%s, state %d does not decode as the lease model: %v", path, i, err)
		}
		states = append(states, s)
	}
	return states
}

// fromITF rewrites ITF's encodings into plain JSON values: a #bigint becomes a
// number, a #set a list, a #map an object keyed by the key's plain form, a
// variant its tag (the model only uses nullary ones), and records recurse.
func fromITF(v any) any {
	switch x := v.(type) {
	case []any:
		out := make([]any, len(x))
		for i, inner := range x {
			out[i] = fromITF(inner)
		}
		return out
	case map[string]any:
		if big, ok := x["#bigint"].(string); ok {
			n, err := strconv.ParseInt(big, 10, 64)
			if err != nil {
				return big
			}
			return n
		}
		if set, ok := x["#set"].([]any); ok {
			return fromITF(set)
		}
		if pairs, ok := x["#map"].([]any); ok {
			out := make(map[string]any, len(pairs))
			for _, p := range pairs {
				kv, _ := p.([]any)
				if len(kv) == 2 {
					out[fmt.Sprint(fromITF(kv[0]))] = fromITF(kv[1])
				}
			}
			return out
		}
		if tag, ok := x["tag"].(string); ok && len(x) == 2 {
			return tag
		}
		out := make(map[string]any, len(x))
		for k, inner := range x {
			out[k] = fromITF(inner)
		}
		return out
	}
	return v
}
