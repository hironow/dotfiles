package lease

import (
	"os"
	"strconv"
	"sync"
	"testing"
	"time"
)

// The gate side of the simulation. A sweep of fixed seeds by default; a single
// seed when EXE_REAPER_SIM_SEED is set, which is how a failure reported by CI is
// replayed locally -- the failure message prints the exact variable to set.

// simSeeds is fixed, not time-derived: a gate that cannot fail the same way
// twice is not a gate. Widen it deliberately when the model grows.
var simSeeds = []uint64{1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987}

// sweepResult is one seed's outcome in the fixed sweep.
type sweepResult struct {
	stats     SimStats
	violation *SimViolation
}

// sweep runs the fixed seed sweep once per test binary. Two tests read it --
// one for the invariants, one for coverage -- and each full sweep takes seconds,
// so they share one run instead of paying for two identical ones.
var sweep = sync.OnceValue(func() []sweepResult {
	results := make([]sweepResult, 0, len(simSeeds))
	for _, seed := range simSeeds {
		s, v := SimulateWithStats(DefaultSimConfig(seed))
		results = append(results, sweepResult{stats: s, violation: v})
	}
	return results
})

// skipSweepInShortMode keeps the seconds-long sweep out of `go test -short`
// (the fast `just go-test` gate). It still runs in full under `just
// spec-check`, which `just check` calls, so the gate as a whole never skips it.
func skipSweepInShortMode(t *testing.T) {
	t.Helper()
	if testing.Short() {
		t.Skip("seed sweep runs under `just spec-check`, not in -short mode")
	}
}

func TestSimulationHoldsTheInvariants(t *testing.T) {
	if raw := os.Getenv("EXE_REAPER_SIM_SEED"); raw != "" {
		seed, err := strconv.ParseUint(raw, 10, 64)
		if err != nil {
			t.Fatalf("EXE_REAPER_SIM_SEED=%q is not a uint64: %v", raw, err)
		}
		if v := Simulate(DefaultSimConfig(seed)); v != nil {
			t.Fatal(v.Error())
		}
		return
	}

	skipSweepInShortMode(t)
	for _, r := range sweep() {
		if r.violation != nil {
			t.Fatal(r.violation.Error())
		}
	}
}

func TestSimulationIsDeterministic(t *testing.T) {
	// Replay has to be real replay: if two runs of one seed could diverge, the
	// seed printed in a failure message would be useless.
	cfg := DefaultSimConfig(4242)
	cfg.Steps = 500

	statsA, a := SimulateWithStats(cfg)
	statsB, b := SimulateWithStats(cfg)

	if statsA != statsB {
		t.Fatalf("same seed produced different coverage: %+v vs %+v", statsA, statsB)
	}
	switch {
	case a == nil && b == nil:
	case a == nil || b == nil:
		t.Fatalf("same seed produced different outcomes: %v vs %v", a, b)
	case a.Invariant != b.Invariant || a.Step != b.Step:
		t.Fatalf("same seed produced different violations: %+v vs %+v", a, b)
	}
}

func TestSimulationReachesTheDangerousStates(t *testing.T) {
	// A green simulation that never wakes a node, never drains and never forces
	// a stop proves nothing at all. Coverage is therefore asserted, not assumed:
	// across the seed sweep every interesting transition must occur at least
	// once, including the ones the invariants are about.
	skipSweepInShortMode(t)
	total := SimStats{}
	for _, r := range sweep() {
		if r.violation != nil {
			t.Fatal(r.violation.Error())
		}
		s := r.stats
		total.Wakes += s.Wakes
		total.Extends += s.Extends
		total.DrainsStarted += s.DrainsStarted
		total.DrainsFinished += s.DrainsFinished
		total.DrainsFailed += s.DrainsFailed
		total.GracefulStops += s.GracefulStops
		total.ForcedStops += s.ForcedStops
		total.ForcedLeaseUnreadable += s.ForcedLeaseUnreadable
		total.ForcedDrainFailed += s.ForcedDrainFailed
		total.ForcedGraceExpired += s.ForcedGraceExpired
		total.ForcedHeartbeatStale += s.ForcedHeartbeatStale
		total.L3Stops += s.L3Stops
		total.ReadFailures += s.ReadFailures
	}

	// Every forced branch of DecideL2 by name, not "forced stops" in total: a
	// sweep whose every forced stop was a lease-read failure proves nothing
	// about the drain-failed, heartbeat and grace rules, and for a long time
	// that is exactly what this sweep was.
	required := []struct {
		name string
		got  int
	}{
		{"wakes", total.Wakes},
		{"extends", total.Extends},
		{"drains started", total.DrainsStarted},
		{"drains finished", total.DrainsFinished},
		{"drains failed", total.DrainsFailed},
		{"graceful stops", total.GracefulStops},
		{"forced stops", total.ForcedStops},
		{"forced stops: lease unreadable", total.ForcedLeaseUnreadable},
		{"forced stops: drain failed", total.ForcedDrainFailed},
		{"forced stops: grace expired", total.ForcedGraceExpired},
		{"forced stops: heartbeat stale", total.ForcedHeartbeatStale},
		{"L3 stops", total.L3Stops},
		{"lease read failures", total.ReadFailures},
	}
	for _, r := range required {
		if r.got == 0 {
			t.Errorf("the seed sweep never reached: %s -- the simulation is inert "+
				"for that transition and proves nothing about it (coverage: %+v)",
				r.name, total)
		}
	}
	t.Logf("coverage across %d seeds: %+v", len(simSeeds), total)
}

func TestSimulationCatchesADeliberatelyBrokenBound(t *testing.T) {
	// Proof the harness can actually fail, at the plan's bound and not at some
	// looser one. Rather than breaking the production rules to test the
	// harness, this drives the invariant checker directly with states on each
	// side of each bound.
	tests := []struct {
		name         string
		pastDeadline time.Duration
		readFailures int
		wantViolated bool
	}{
		{"at the bound, a readable lease is still in time", AwakeBound(), 0, false},
		{"a minute past it, a readable lease is not", AwakeBound() + time.Minute, 0, true},
		{"a run of read misses may go past the readable bound", AwakeBound() + time.Minute, 2, false},
		{"but not past the blind one", BlindAwakeBound() + time.Minute, 2, true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			s := &simState{
				now:          ref().Add(tc.pastDeadline),
				nodes:        1,
				lease:        Lease{Deadline: ref(), Generation: 1},
				leaseOK:      tc.readFailures == 0,
				readFailures: tc.readFailures,
			}
			v := checkInvariants(s, 0, 0, nil)
			switch {
			case !tc.wantViolated && v != nil:
				t.Fatalf("no violation expected, got %s: %s", v.Invariant, v.Detail)
			case tc.wantViolated && v == nil:
				t.Fatal("a pool still up past its bound must violate NodesEventuallyZero")
			case tc.wantViolated && v.Invariant != "NodesEventuallyZero":
				t.Fatalf("wrong invariant fired: %s", v.Invariant)
			}
		})
	}
}
