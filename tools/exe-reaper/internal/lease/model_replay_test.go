package lease

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

// The Quint model and DecideL2 are two encodings of one table, plan section
// 3.2's L2 rule, and nothing but a comparison keeps two encodings equal: they
// once disagreed on both of the rule's boundaries (the model forced at once on
// an expired lease with no drain record, and exactly at the grace) while each
// passed its own tests.
//
// So `just spec-check` samples traces of the model's l2WorldStep -- random
// rows of the table, each followed by the tick that decides it, sometimes by a
// second tick that carries the read-failure run -- into a fresh directory as
// ITF (the Informal Trace Format), and hands the directory to this test in
// EXE_REAPER_L2_TRACES. Every L2 tick in those traces is replayed through
// DecideL2 and NextReadFailures, and must land in the same branch.

// l2TracesEnv names the directory of ITF traces to replay.
const l2TracesEnv = "EXE_REAPER_L2_TRACES"

// The model's L2 branches, by the Decision tag its enforce.last records.
var modelL2Branches = []string{
	"AlreadyStopped",
	"LeaseLive",
	"WaitedOnReadFailure",
	"StoppedOnReadFailures",
	"StoppedOnDrained",
	"WaitedForDrain",
	"StoppedForced",
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
	case d.Action == ActionWait && (d.Reason == ReasonDrainingWithHeartbeat || d.Reason == ReasonAwaitingDrain):
		return "WaitedForDrain"
	case d.Action == ActionStopForced &&
		(d.Reason == ReasonDrainFailed || d.Reason == ReasonHeartbeatStale || d.Reason == ReasonGraceExpired):
		return "StoppedForced"
	}
	return fmt.Sprintf("<no model branch for %+v>", d)
}

func TestDecideL2AgreesWithTheModel(t *testing.T) {
	dir := os.Getenv(l2TracesEnv)
	if dir == "" {
		t.Skipf("needs %s; `just spec-check` samples the model's traces into it and runs this", l2TracesEnv)
	}
	files, err := filepath.Glob(filepath.Join(dir, "*.itf.json"))
	if err != nil || len(files) == 0 {
		t.Fatalf("%s=%s holds no *.itf.json traces (%v): the model produced nothing to replay", l2TracesEnv, dir, err)
	}

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
			obs := before.observation(after.Clock.Now)
			got := DecideL2(obs)
			if branch := modelBranch(got); branch != after.Enforce.Last {
				t.Errorf("%s, step %d: the model took %s, DecideL2 %+v (%s)\n  model state before the tick: %s",
					filepath.Base(file), i, after.Enforce.Last, got, branch, before)
			}
			if obs.ConsecutiveReadFailures != after.Enforce.LeaseReadFailures {
				t.Errorf("%s, step %d: read-failure run: the model carries %d, NextReadFailures %d\n  model state before the tick: %s",
					filepath.Base(file), i, after.Enforce.LeaseReadFailures, obs.ConsecutiveReadFailures, before)
			}
			if stops := got.Action != ActionWait; stops != (after.Cluster.Nodes == 0 && before.Cluster.Nodes > 0) {
				t.Errorf("%s, step %d: DecideL2 %+v, but the model's pool went %d -> %d",
					filepath.Base(file), i, got, before.Cluster.Nodes, after.Cluster.Nodes)
			}
			replayed[after.Enforce.Last]++
		}
	}

	// A replay that never reached a branch says nothing about it.
	for _, branch := range modelL2Branches {
		if replayed[branch] == 0 {
			t.Errorf("no sampled trace reached the model's %s branch (replayed: %v)", branch, replayed)
		}
	}
	t.Logf("replayed %d traces: %v", len(files), replayed)
}

// The model's state variables, decoded from ITF. Only what L2 reads, plus the
// pool, the enforcer's record and the clock to check its outcome.
type modelState struct {
	Clock struct {
		Now int64
	}
	Lease struct {
		Deadline int64
		Gen      int64
		Readable bool
	}
	Drain struct {
		State     string
		Heartbeat int64
		StartedAt int64
		LeaseGen  int64
	}
	Enforce struct {
		Last              string
		Gen               int64
		LeaseReadFailures int
	}
	Cluster struct {
		Nodes int
	}
}

func (s modelState) String() string {
	return fmt.Sprintf("lease{deadline %d gen %d readable %v} drain{%s heartbeat %d gen %d} run %d nodes %d",
		s.Lease.Deadline, s.Lease.Gen, s.Lease.Readable,
		s.Drain.State, s.Drain.Heartbeat, s.Drain.LeaseGen, s.Enforce.LeaseReadFailures, s.Cluster.Nodes)
}

// modelEpoch anchors the model's abstract minutes to a real instant. Any
// instant works: the L2 rule compares only differences, never local hours.
var modelEpoch = time.Date(2026, 9, 27, 0, 0, 0, 0, time.UTC)

func atModelMinute(m int64) time.Time {
	return modelEpoch.Add(time.Duration(m) * time.Minute)
}

// observation is what the enforcer would see on a tick at minute now, in the
// world this state describes.
func (s modelState) observation(now int64) Observation {
	phases := map[string]DrainPhase{
		"DrainNone":   DrainNone,
		"Draining":    DrainDraining,
		"Drained":     DrainDrained,
		"DrainFailed": DrainFailed,
	}
	return Observation{
		Now:     atModelMinute(now),
		Lease:   Lease{Deadline: atModelMinute(s.Lease.Deadline), Generation: s.Lease.Gen},
		LeaseOK: s.Lease.Readable,
		ConsecutiveReadFailures: NextReadFailures(
			s.Enforce.LeaseReadFailures, s.Lease.Readable, s.Cluster.Nodes),
		Drain: Drain{
			Phase:           phases[s.Drain.State],
			Heartbeat:       atModelMinute(s.Drain.Heartbeat),
			LeaseGeneration: s.Drain.LeaseGen,
			StartedAt:       atModelMinute(s.Drain.StartedAt),
		},
		Nodes: s.Cluster.Nodes,
	}
}

// loadModelTrace decodes one ITF trace into model states.
//
// ITF spells an integer {"#bigint": "N"} and a sum-type value {"tag": "X",
// "value": ...}, and qualifies each variable with its module path
// ("lease::leaseCore::drain"); decoding goes through a plain-JSON rewrite of
// both, then matches variables by their last segment.
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
// number, a variant becomes its tag (the L2 table only uses nullary ones), and
// records recurse. Sets and tuples are not needed and are left alone.
func fromITF(v any) any {
	m, ok := v.(map[string]any)
	if !ok {
		return v
	}
	if big, ok := m["#bigint"].(string); ok {
		n, err := strconv.ParseInt(big, 10, 64)
		if err != nil {
			return big
		}
		return n
	}
	if tag, ok := m["tag"].(string); ok && len(m) == 2 {
		return tag
	}
	out := make(map[string]any, len(m))
	for k, inner := range m {
		out[k] = fromITF(inner)
	}
	return out
}
