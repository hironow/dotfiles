package lease

import (
	"errors"
	"testing"
	"time"
)

// These are decision TABLES rather than scenario tests, because the thing under
// test is a set of rules whose ORDER is the design. Every row names the rule it
// exercises, and every row asserts the Reason as well as the Action: two
// different bugs can produce the right action for the wrong reason, and only one
// of them shows up later, in production, at 04:00.
//
// The rules come from docs/plan/exe-google-ax.md section 3.2 and are mirrored by
// exe/spec/lease.qnt. Changing a row here without changing the model (or the
// other way round) is exactly what the constants lockstep test and the seeded
// simulation exist to catch.

// A fixed instant well away from any boundary, so a test that is not ABOUT the
// nightly cap cannot accidentally depend on it. 14:00 JST.
func ref() time.Time {
	return time.Date(2026, 9, 27, 14, 0, 0, 0, Location())
}

func TestClampDeadline(t *testing.T) {
	loc := Location()

	tests := []struct {
		name      string
		now       time.Time
		requested time.Duration
		want      time.Time
		clamped   bool
		wantErr   error
	}{
		{
			name:      "a default lease in the middle of the day is untouched",
			now:       ref(),
			requested: DefaultLease,
			want:      ref().Add(DefaultLease),
		},
		{
			name:      "the maximum is allowed exactly",
			now:       ref(),
			requested: MaxLease,
			want:      ref().Add(MaxLease),
		},
		{
			name:      "one second over the maximum is refused, not shortened",
			now:       ref(),
			requested: MaxLease + time.Second,
			wantErr:   ErrLeaseTooLong,
		},
		{
			name:      "zero is refused",
			now:       ref(),
			requested: 0,
			wantErr:   ErrNonPositiveLease,
		},
		{
			name:      "negative is refused",
			now:       ref(),
			requested: -time.Minute,
			wantErr:   ErrNonPositiveLease,
		},
		{
			// 22:00 + 8h would be 06:00, past L3 entirely. The cap is what stops
			// the daily forced stop from landing on an awake actor.
			name:      "an evening maximum is clamped down to the nightly cap",
			now:       time.Date(2026, 9, 27, 22, 0, 0, 0, loc),
			requested: MaxLease,
			want:      time.Date(2026, 9, 28, NightlyCapHour, 0, 0, 0, loc),
			clamped:   true,
		},
		{
			name:      "a lease that ends exactly at the cap is not reported as clamped",
			now:       time.Date(2026, 9, 28, 1, 0, 0, 0, loc),
			requested: 2 * time.Hour,
			want:      time.Date(2026, 9, 28, NightlyCapHour, 0, 0, 0, loc),
		},
		{
			name:      "just before the cap window, only minutes are available",
			now:       time.Date(2026, 9, 28, 2, 50, 0, 0, loc),
			requested: time.Hour,
			want:      time.Date(2026, 9, 28, NightlyCapHour, 0, 0, 0, loc),
			clamped:   true,
		},
		{
			name:      "inside the cap window a wake is refused outright",
			now:       time.Date(2026, 9, 28, NightlyCapHour, 30, 0, 0, loc),
			requested: DefaultLease,
			wantErr:   ErrInsideCapWindow,
		},
		{
			name:      "at the cap hour exactly, still refused",
			now:       time.Date(2026, 9, 28, NightlyCapHour, 0, 0, 0, loc),
			requested: DefaultLease,
			wantErr:   ErrInsideCapWindow,
		},
		{
			name:      "once L3 has fired, waking is allowed again",
			now:       time.Date(2026, 9, 28, L3StopHour, 0, 0, 0, loc),
			requested: DefaultLease,
			want:      time.Date(2026, 9, 28, L3StopHour, 0, 0, 0, loc).Add(DefaultLease),
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, clamped, err := ClampDeadline(tc.now, tc.requested)
			if tc.wantErr != nil {
				if !errors.Is(err, tc.wantErr) {
					t.Fatalf("want error %v, got %v", tc.wantErr, err)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if !got.Equal(tc.want) {
				t.Errorf("deadline: want %s, got %s", tc.want, got)
			}
			if clamped != tc.clamped {
				t.Errorf("clamped: want %v, got %v", tc.clamped, clamped)
			}
		})
	}
}

func TestClampDeadlineNeverPassesTheCap(t *testing.T) {
	// A property, not a case: whatever minute of the day we ask from, and
	// whatever duration up to the maximum, the resulting deadline never lands in
	// the window where L3 could catch an awake actor. This is the invariant the
	// Quint model calls L3NeverHitsAwakeActor.
	loc := Location()
	day := time.Date(2026, 9, 27, 0, 0, 0, 0, loc)

	for minute := 0; minute < 24*60; minute += 7 {
		now := day.Add(time.Duration(minute) * time.Minute)
		for _, d := range []time.Duration{time.Minute, DefaultLease, MaxLease} {
			deadline, _, err := ClampDeadline(now, d)
			if errors.Is(err, ErrInsideCapWindow) {
				continue
			}
			if err != nil {
				t.Fatalf("now=%s d=%s: unexpected error %v", now, d, err)
			}
			if h := deadline.In(loc).Hour(); h >= NightlyCapHour && h < L3StopHour {
				// Landing exactly on the cap boundary is fine; inside is not.
				capAt := time.Date(deadline.In(loc).Year(), deadline.In(loc).Month(),
					deadline.In(loc).Day(), NightlyCapHour, 0, 0, 0, loc)
				if !deadline.Equal(capAt) {
					t.Fatalf("now=%s d=%s produced deadline %s inside the cap window",
						now, d, deadline)
				}
			}
		}
	}
}

func TestShouldDrain(t *testing.T) {
	now := ref()
	live := Lease{Deadline: now.Add(time.Hour), Generation: 1}
	expired := Lease{Deadline: now.Add(-time.Minute), Generation: 1}

	tests := []struct {
		name             string
		lease            Lease
		leaseOK          bool
		zeroRunningSince time.Time
		want             bool
		wantReason       Reason
	}{
		{
			name:  "an authorised, busy cluster is left alone",
			lease: live, leaseOK: true,
			want: false, wantReason: ReasonAuthorised,
		},
		{
			name:  "the deadline passing is the primary trigger",
			lease: expired, leaseOK: true,
			want: true, wantReason: ReasonDeadlinePassed,
		},
		{
			// Unverifiable authorisation for something billed by the hour is
			// not authorisation. A graceful drain loses nothing if the read
			// failure was transient.
			name:  "an unreadable lease drains rather than assuming permission",
			lease: live, leaseOK: false,
			want: true, wantReason: ReasonLeaseUnreadable,
		},
		{
			name:  "idle for exactly the threshold drains",
			lease: live, leaseOK: true,
			zeroRunningSince: now.Add(-IdleZeroRunning),
			want:             true, wantReason: ReasonIdle,
		},
		{
			name:  "idle for one minute less does not",
			lease: live, leaseOK: true,
			zeroRunningSince: now.Add(-IdleZeroRunning + time.Minute),
			want:             false, wantReason: ReasonAuthorised,
		},
		{
			// The rule is "zero for thirty minutes", not "zero right now": a
			// task finishing and another starting must not start the clock.
			name:  "something running means the idle clock is not even started",
			lease: live, leaseOK: true,
			zeroRunningSince: time.Time{},
			want:             false, wantReason: ReasonAuthorised,
		},
		{
			name:  "an expired lease wins over a not-yet-idle cluster",
			lease: expired, leaseOK: true,
			zeroRunningSince: now.Add(-time.Minute),
			want:             true, wantReason: ReasonDeadlinePassed,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, reason := ShouldDrain(now, tc.lease, tc.leaseOK, tc.zeroRunningSince)
			if got != tc.want || reason != tc.wantReason {
				t.Errorf("want (%v, %s), got (%v, %s)", tc.want, tc.wantReason, got, reason)
			}
		})
	}
}

func TestDecideL2(t *testing.T) {
	now := ref()
	gen := int64(7)
	live := Lease{Deadline: now.Add(time.Hour), Generation: gen}
	expired := Lease{Deadline: now.Add(-time.Minute), Generation: gen}
	longExpired := Lease{Deadline: now.Add(-ForceGrace - time.Minute), Generation: gen}

	draining := func(hb time.Time, g int64) Drain {
		return Drain{Phase: DrainDraining, Heartbeat: hb, LeaseGeneration: g, StartedAt: hb}
	}

	tests := []struct {
		name string
		obs  Observation
		want Decision
	}{
		{
			name: "a pool already at zero is never touched",
			obs:  Observation{Now: now, Lease: longExpired, LeaseOK: true, Nodes: 0},
			want: Decision{ActionWait, ReasonAlreadyStopped},
		},
		{
			name: "an authorised cluster is never stopped by L2",
			obs:  Observation{Now: now, Lease: live, LeaseOK: true, Nodes: 1},
			want: Decision{ActionWait, ReasonWithinLease},
		},
		{
			// The single most dangerous simplification available in this
			// function: forcing on the first read failure would destroy work
			// every time GCS hiccups.
			name: "one read failure does nothing",
			obs:  Observation{Now: now, Lease: expired, LeaseOK: false, ConsecutiveReadFailures: 1, Nodes: 1},
			want: Decision{ActionWait, ReasonTransientReadFailure},
		},
		{
			name: "two read failures still do nothing",
			obs:  Observation{Now: now, Lease: expired, LeaseOK: false, ConsecutiveReadFailures: 2, Nodes: 1},
			want: Decision{ActionWait, ReasonTransientReadFailure},
		},
		{
			name: "the third consecutive read failure forces the stop",
			obs:  Observation{Now: now, Lease: expired, LeaseOK: false, ConsecutiveReadFailures: 3, Nodes: 1},
			want: Decision{ActionStopForced, ReasonLeaseUnreadable},
		},
		{
			name: "read failures force even while the last known lease was live",
			obs:  Observation{Now: now, Lease: live, LeaseOK: false, ConsecutiveReadFailures: 3, Nodes: 1},
			want: Decision{ActionStopForced, ReasonLeaseUnreadable},
		},
		{
			name: "drained is the happy path: stop, no page",
			obs: Observation{
				Now: now, Lease: expired, LeaseOK: true, Nodes: 1,
				Drain: Drain{Phase: DrainDrained, LeaseGeneration: gen},
			},
			want: Decision{ActionStopGraceful, ReasonDrained},
		},
		{
			name: "drain-failed forces, because the cost ceiling wins",
			obs: Observation{
				Now: now, Lease: expired, LeaseOK: true, Nodes: 1,
				Drain: Drain{Phase: DrainFailed, LeaseGeneration: gen},
			},
			want: Decision{ActionStopForced, ReasonDrainFailed},
		},
		{
			name: "a slow drain with a fresh heartbeat is waited for",
			obs: Observation{
				Now: now, Lease: expired, LeaseOK: true, Nodes: 1,
				Drain: draining(now.Add(-L2Tick), gen),
			},
			want: Decision{ActionWait, ReasonDrainingWithHeartbeat},
		},
		{
			name: "a heartbeat exactly at the stale boundary is still trusted",
			obs: Observation{
				Now: now, Lease: expired, LeaseOK: true, Nodes: 1,
				Drain: draining(now.Add(-HeartbeatStaleAfter()), gen),
			},
			want: Decision{ActionWait, ReasonDrainingWithHeartbeat},
		},
		{
			name: "one second past it is a dead drain, not a slow one",
			obs: Observation{
				Now: now, Lease: expired, LeaseOK: true, Nodes: 1,
				Drain: draining(now.Add(-HeartbeatStaleAfter()-time.Second), gen),
			},
			want: Decision{ActionStopForced, ReasonHeartbeatStale},
		},
		{
			// L1 runs every minute; L2 every ten. A deadline that passed a
			// moment ago must not be forced before L1 has had a chance.
			name: "no drain record yet, just past the deadline: wait for L1",
			obs:  Observation{Now: now, Lease: expired, LeaseOK: true, Nodes: 1},
			want: Decision{ActionWait, ReasonAwaitingDrain},
		},
		{
			// No record about this lease reads as a heartbeat that stopped AT
			// the deadline: L1 gets the same window a draining L1 gets between
			// two heartbeats, and not the whole grace. A live L1 writes
			// `draining` within a minute of the deadline, so silence for the
			// full window means it is not running.
			name: "no drain record, exactly one heartbeat window after the deadline: still wait",
			obs: Observation{
				Now: now, Lease: Lease{Deadline: now.Add(-HeartbeatStaleAfter()), Generation: gen},
				LeaseOK: true, Nodes: 1,
			},
			want: Decision{ActionWait, ReasonAwaitingDrain},
		},
		{
			name: "no drain record, one second past that window: force as a stopped heartbeat",
			obs: Observation{
				Now: now, Lease: Lease{Deadline: now.Add(-HeartbeatStaleAfter() - time.Second), Generation: gen},
				LeaseOK: true, Nodes: 1,
			},
			want: Decision{ActionStopForced, ReasonHeartbeatStale},
		},
		{
			name: "no drain record and the grace has expired: force",
			obs:  Observation{Now: now, Lease: longExpired, LeaseOK: true, Nodes: 1},
			want: Decision{ActionStopForced, ReasonGraceExpired},
		},
		{
			// The grace is unconditional: past it, not even a heartbeat that
			// keeps arriving buys more time. L1 gives up at its own ceiling, so
			// a heartbeat this late is an L1 that is broken in a way that
			// keeps writing, or a clock that disagrees -- and the plan's bound,
			// deadline + ForceGrace + one L2 tick, has to hold through both.
			name: "past the grace a fresh heartbeat buys nothing: force",
			obs: Observation{
				Now: now, Lease: Lease{Deadline: now.Add(-ForceGrace - time.Second), Generation: gen},
				LeaseOK: true, Nodes: 1,
				Drain: draining(now, gen),
			},
			want: Decision{ActionStopForced, ReasonGraceExpired},
		},
		{
			name: "exactly at the grace a fresh heartbeat is still waited for",
			obs: Observation{
				Now: now, Lease: Lease{Deadline: now.Add(-ForceGrace), Generation: gen},
				LeaseOK: true, Nodes: 1,
				Drain: draining(now, gen),
			},
			want: Decision{ActionWait, ReasonDrainingWithHeartbeat},
		},
		{
			// Nothing is awake once L1 says so for this lease, so the stop is
			// graceful whenever L2 first sees it -- paging for it would be a
			// false alarm on the channel that carries the real ones.
			name: "a drained record is a graceful stop even past the grace",
			obs: Observation{
				Now: now, Lease: longExpired, LeaseOK: true, Nodes: 1,
				Drain: Drain{Phase: DrainDrained, LeaseGeneration: gen},
			},
			want: Decision{ActionStopGraceful, ReasonDrained},
		},
		{
			name: "drain-failed past the grace is still reported as drain-failed",
			obs: Observation{
				Now: now, Lease: longExpired, LeaseOK: true, Nodes: 1,
				Drain: Drain{Phase: DrainFailed, LeaseGeneration: gen},
			},
			want: Decision{ActionStopForced, ReasonDrainFailed},
		},
		{
			// A heartbeat is judged by its own age, not by the deadline: one
			// last written before the deadline (an idle drain whose L1 then
			// died) is already stale the moment the lease runs out.
			name: "a draining heartbeat older than the window is stale even just past the deadline",
			obs: Observation{
				Now: now, Lease: expired, LeaseOK: true, Nodes: 1,
				Drain: draining(now.Add(-HeartbeatStaleAfter()-time.Minute), gen),
			},
			want: Decision{ActionStopForced, ReasonHeartbeatStale},
		},
		{
			// This is how an extend invalidates an earlier `drained` without L1
			// having to remember to clean up: the record names the generation it
			// drained, and the new lease has a different one.
			name: "a drained record from a previous lease is ignored",
			obs: Observation{
				Now: now, Lease: Lease{Deadline: now.Add(-time.Minute), Generation: gen + 1}, LeaseOK: true, Nodes: 1,
				Drain: Drain{Phase: DrainDrained, LeaseGeneration: gen},
			},
			want: Decision{ActionWait, ReasonAwaitingDrain},
		},
		{
			name: "a stale drained record cannot stop a re-extended, live lease",
			obs: Observation{
				Now: now, Lease: Lease{Deadline: now.Add(2 * time.Hour), Generation: gen + 1}, LeaseOK: true, Nodes: 1,
				Drain: Drain{Phase: DrainDrained, LeaseGeneration: gen},
			},
			want: Decision{ActionWait, ReasonWithinLease},
		},
		{
			name: "a stale draining record does not count as a heartbeat either",
			obs: Observation{
				Now: now, Lease: longExpired, LeaseOK: true, Nodes: 1,
				Drain: draining(now, gen-1),
			},
			want: Decision{ActionStopForced, ReasonGraceExpired},
		},
		{
			// ...it counts as no record: the window runs from the deadline,
			// however fresh the older lease's heartbeat is.
			name: "a stale draining record past the heartbeat window forces as a stopped heartbeat",
			obs: Observation{
				Now: now, Lease: Lease{Deadline: now.Add(-HeartbeatStaleAfter() - time.Second), Generation: gen},
				LeaseOK: true, Nodes: 1,
				Drain: draining(now, gen-1),
			},
			want: Decision{ActionStopForced, ReasonHeartbeatStale},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := DecideL2(tc.obs)
			if got != tc.want {
				t.Errorf("want %+v, got %+v", tc.want, got)
			}
		})
	}
}

func TestOnlyForcedStopsPage(t *testing.T) {
	// A graceful stop is the system working; paging on it trains the operator to
	// ignore the channel that also carries the forced stops.
	if (Decision{ActionStopGraceful, ReasonDrained}).Notify() {
		t.Error("a graceful stop must not page")
	}
	if (Decision{ActionWait, ReasonWithinLease}).Notify() {
		t.Error("waiting must not page")
	}
	if !(Decision{ActionStopForced, ReasonHeartbeatStale}).Notify() {
		t.Error("a forced stop must page")
	}
}

func TestExtendAfterDrainedIsDecidedByGenerationNotByCleanup(t *testing.T) {
	// Spelled out as its own test because it is a named requirement ("a
	// successful extend invalidates an earlier drained") and because the naive
	// implementation -- have extend delete drain.json -- breaks the one-writer
	// rule: only L1 may write that object.
	now := ref()
	drained := Drain{Phase: DrainDrained, LeaseGeneration: 4}

	before := Lease{Deadline: now.Add(-time.Minute), Generation: 4}
	if got := DecideL2(Observation{Now: now, Lease: before, LeaseOK: true, Nodes: 1, Drain: drained}); got.Action != ActionStopGraceful {
		t.Fatalf("before the extend, drained should stop the pool; got %+v", got)
	}

	after := Lease{Deadline: now.Add(time.Hour), Generation: 5}
	if got := DecideL2(Observation{Now: now, Lease: after, LeaseOK: true, Nodes: 1, Drain: drained}); got.Action != ActionWait {
		t.Fatalf("after the extend, the stale drained record must not stop it; got %+v", got)
	}
}

func TestNextReadFailures(t *testing.T) {
	// L2 is a job that exits between ticks, so the run of consecutive lease
	// read failures is carried in enforce.json and advanced here, one tick at a
	// time. The model's l2 branches and the simulation advance it through this
	// same rule.
	tests := []struct {
		name    string
		prev    int
		leaseOK bool
		nodes   int
		want    int
	}{
		{"a readable lease ends the run", 2, true, 1, 0},
		{"the first miss starts a run", 0, false, 1, 1},
		{"a further miss extends it", 2, false, 1, 3},
		// Carried across a stop, a run would make the first miss after the
		// next wake a blind stop of a lease nobody has failed to read yet.
		{"while the pool is at zero the run is reset, unreadable or not", 2, false, 0, 0},
		{"and a readable lease at zero leaves it reset", 0, true, 0, 0},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := NextReadFailures(tc.prev, tc.leaseOK, tc.nodes); got != tc.want {
				t.Errorf("NextReadFailures(%d, %v, %d) = %d, want %d", tc.prev, tc.leaseOK, tc.nodes, got, tc.want)
			}
		})
	}
}
