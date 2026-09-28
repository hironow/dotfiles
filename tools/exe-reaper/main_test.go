package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ops"
)

// End to end through the shipped decision: with lease.json gone and the pool
// up, L2 waits on the first two ticks and forces on the third. This is the
// Phase 3 e2e "with lease.json deleted the pool returns to 0 after three ticks",
// minus the cloud.
func TestADeletedLeaseForcesOnTheThirdTick(t *testing.T) {
	now := time.Date(2026, 9, 27, 1, 0, 0, 0, time.UTC)
	failures := 0
	for tick := 1; tick <= 3; tick++ {
		l, ok := ops.LeaseFromRead(nil, 0, gcp.ErrNotFound)
		if !ok {
			failures++
		}
		d := lease.DecideL2(lease.Observation{
			Now: now, Lease: l, LeaseOK: ok, ConsecutiveReadFailures: failures, Nodes: 1,
		})
		wantForced := tick == lease.LeaseReadFailureThreshold
		if gotForced := d.Action == lease.ActionStopForced; gotForced != wantForced {
			t.Fatalf("tick %d: action %s (%s); forced = %v, want %v", tick, d.Action, d.Reason, gotForced, wantForced)
		}
		now = now.Add(lease.L2Tick)
	}
}

// L2's run of consecutive lease read failures lives in enforce.json between
// ticks. A tick advances it by lease.NextReadFailures, the rule the Quint model
// and the seeded simulation advance it by, and that rule resets the run while
// the pool is at zero.
func TestATickCarriesTheReadFailureRunByTheSharedRule(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	tests := []struct {
		name       string
		prev       int
		readable   bool
		targetSize int
		wantRun    int
		wantStop   bool
	}{
		{"a miss while the pool is up extends the run", 1, false, 1, 2, false},
		{"the third miss in a row stops the pool", 2, false, 1, 3, true},
		{"a readable lease ends the run", 2, true, 1, 0, false},
		// Carried across a stop, the run would make the first miss after the
		// next wake a blind stop of a lease nobody has yet failed to read.
		{"while the pool is at zero the run is reset, unreadable or not", 2, false, 0, 0, false},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			cloud := newFakeCloud(t)
			cloud.targetSize = tc.targetSize
			cloud.put(ops.EnforceObject, enforceRecord{ReadFailures: tc.prev})
			if tc.readable {
				cloud.put(ops.LeaseObject, lease.Lease{Deadline: now.Add(time.Hour)})
			}

			cloud.tickAt(now, io.Discard)

			if got := cloud.storedRecord().ReadFailures; got != tc.wantRun {
				t.Errorf("read-failure run after the tick = %d, want %d", got, tc.wantRun)
			}
			if stopped := len(cloud.setSizes()) > 0; stopped != tc.wantStop {
				t.Errorf("setSize called = %v, want %v (calls %v)", stopped, tc.wantStop, cloud.setSizes())
			}
		})
	}
}

// enforce.json is L2's only memory. A read of it that fails for any reason but
// "absent" must fail the tick: the job then exits non-zero, which is what the
// failed-execution alert sees. Swallowed, the old way, the record read as empty,
// the conditional write that followed lost to the object that was there, and
// the read-failure run could never advance -- silently, on every tick.
//
// The stop is still made. What cannot be read is L2's memory, not the lease,
// and a node past its deadline costs the same whether or not L2 can remember
// the tick before.
func TestAnUnreadableEnforcementRecordFailsTheTickButNotTheStop(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.targetSize = 1
	cloud.put(ops.LeaseObject, lease.Lease{Deadline: now.Add(-2 * time.Hour)})
	cloud.put(ops.EnforceObject, enforceRecord{ReadFailures: 1})
	before := cloud.object(ops.EnforceObject)
	cloud.getStatus[ops.EnforceObject] = http.StatusServiceUnavailable

	err := cloud.enforcer(io.Discard).tick(t.Context(), now, false)

	if err == nil || !strings.Contains(err.Error(), ops.EnforceObject) {
		t.Fatalf("tick error = %v, want one that names %s", err, ops.EnforceObject)
	}
	if got := cloud.setSizes(); !slices.Equal(got, []int{0}) {
		t.Errorf("setSize calls = %v, want [0]: the expired lease still stops the pool", got)
	}
	if after := cloud.object(ops.EnforceObject); after.generation != before.generation {
		t.Errorf("enforce.json was rewritten (generation %d -> %d) by a tick that could not read it",
			before.generation, after.generation)
	}
}

// "Absent" is not a failure: it is the very first tick, and the record is
// created under the create-only precondition.
func TestAMissingEnforcementRecordIsTheFirstTick(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.targetSize = 1
	cloud.put(ops.LeaseObject, lease.Lease{Deadline: now.Add(time.Hour)})

	cloud.tickAt(now, io.Discard)

	if rec := cloud.storedRecord(); rec.Action != string(lease.ActionWait) {
		t.Errorf("first record = %+v, want a wait", rec)
	}
}

// A record L2 cannot parse is replaced, not a reason to stop recording. Only L2
// writes it, so it can only be garbage from an L2 that crashed mid-write or a
// human; refusing to overwrite it would fail every tick from then on.
func TestAGarbledEnforcementRecordIsReplaced(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	cloud := newFakeCloud(t)
	cloud.targetSize = 1
	cloud.put(ops.LeaseObject, lease.Lease{Deadline: now.Add(time.Hour)})
	cloud.put(ops.EnforceObject, "not a record")

	cloud.tickAt(now, io.Discard)

	if rec := cloud.storedRecord(); rec.Action != string(lease.ActionWait) {
		t.Errorf("record after the tick = %+v, want a fresh wait", rec)
	}
}

// A tick reads the lease, then the drain record and the pool size, then decides
// -- and an `exe-extend` can land in between. A stop decided on the lease
// before it would take down a node its operator has just been granted more
// time on. So the lease is read again right before setSize, and a stop decided
// on anything but the lease as it now stands is abandoned: the next tick
// decides on the new one (review finding #8).
func TestAStopIsAbandonedWhenTheLeaseMovesDuringTheTick(t *testing.T) {
	now := time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC)
	extended := lease.Lease{Deadline: now.Add(2 * time.Hour)}

	tests := []struct {
		name  string
		setup func(cloud *fakeCloud)
		// moveOnGet is the GET of lease.json before which it changes: 2 is
		// the re-read right before setSize.
		moveOnGet int
		move      func(f *fakeCloud)
		wantStop  bool
	}{
		{
			name: "an extend lands between the read and the stop",
			setup: func(cloud *fakeCloud) {
				cloud.put(ops.LeaseObject, lease.Lease{Deadline: now.Add(-2 * time.Hour)})
			},
			moveOnGet: 2,
			move: func(f *fakeCloud) {
				body, _ := json.Marshal(extended)
				f.store(ops.LeaseObject, body)
			},
			wantStop: false,
		},
		{
			// Blind: decided without a lease; a lease that can be read again
			// is newer information than the three misses.
			name: "a blind stop, and the lease is readable again",
			setup: func(cloud *fakeCloud) {
				cloud.put(ops.LeaseObject, extended)
				cloud.put(ops.EnforceObject, enforceRecord{ReadFailures: 2})
				cloud.getStatus[ops.LeaseObject] = http.StatusServiceUnavailable
			},
			moveOnGet: 2,
			move:      func(f *fakeCloud) { delete(f.getStatus, ops.LeaseObject) },
			wantStop:  false,
		},
		{
			name: "nothing moved: the stop is made",
			setup: func(cloud *fakeCloud) {
				cloud.put(ops.LeaseObject, lease.Lease{Deadline: now.Add(-2 * time.Hour)})
			},
			wantStop: true,
		},
		{
			// A failed re-read is no evidence that anything moved.
			name: "the re-read fails: the stop is made",
			setup: func(cloud *fakeCloud) {
				cloud.put(ops.LeaseObject, lease.Lease{Deadline: now.Add(-2 * time.Hour)})
			},
			moveOnGet: 2,
			move:      func(f *fakeCloud) { f.getStatus[ops.LeaseObject] = http.StatusServiceUnavailable },
			wantStop:  true,
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			cloud := newFakeCloud(t)
			cloud.targetSize = 1
			tc.setup(cloud)
			if tc.move != nil {
				cloud.beforeGet = func(f *fakeCloud, object string, n int) {
					if object == ops.LeaseObject && n == tc.moveOnGet {
						tc.move(f)
					}
				}
			}

			var out bytes.Buffer
			cloud.tickAt(now, &out)

			if stopped := len(cloud.setSizes()) > 0; stopped != tc.wantStop {
				t.Fatalf("stopped = %v, want %v\n%s", stopped, tc.wantStop, out.String())
			}
			if !tc.wantStop && !strings.Contains(out.String(), "lease changed") {
				t.Errorf("an abandoned stop should say why:\n%s", out.String())
			}
		})
	}
}

// `exe-reaper wake 5m` used to parse no flags, ignore the "5m" and authorise
// the default two hours: the operator asked for five minutes and got a node
// that bills for two hours (review finding #7). A positional argument is now
// refused before anything is read or written, and the refusal says how to ask.
func TestAPositionalArgumentIsRefused(t *testing.T) {
	// Empty, so that a regression fails on the environment rather than
	// reaching for a real bucket.
	for _, name := range []string{envBucket, envSetSizeURI, envProject, envZone, envCluster, envNodePool} {
		t.Setenv(name, "")
	}
	commands := []struct {
		name string
		run  func(args []string) error
	}{
		{"wake", func(args []string) error { return cmdLease(t.Context(), args, true) }},
		{"extend", func(args []string) error { return cmdLease(t.Context(), args, false) }},
		{"sleep", func(args []string) error { return cmdSleep(t.Context(), args) }},
		{"status", func(args []string) error { return cmdStatus(t.Context(), args) }},
	}
	for _, c := range commands {
		t.Run(c.name, func(t *testing.T) {
			err := c.run([]string{"5m"})
			if !errors.Is(err, errPositionalArgs) {
				t.Fatalf("%s 5m: error %v, want errPositionalArgs", c.name, err)
			}
			if !strings.Contains(err.Error(), `"5m"`) {
				t.Errorf("the refusal should name the argument: %v", err)
			}
		})
	}

	if err := cmdLease(t.Context(), []string{"5m"}, true); !strings.Contains(err.Error(), "-for 5m") {
		t.Errorf("wake's refusal should say how to ask for a duration: %v", err)
	}

	// The job refuses one too, through its failure line.
	var out bytes.Buffer
	if code := runEnforce(t.Context(), []string{"5m"}, &out); code != 1 ||
		!strings.Contains(out.String(), `unexpected argument \"5m\"`) {
		t.Errorf("enforce 5m: exit %d, output %s", code, out.String())
	}
}

// Every command runs under one deadline, set where the process starts. Each
// HTTP request has its own 30 s timeout, but a command makes several, and an
// L2 tick against a Google API that accepts connections and never answers
// would run into Cloud Run's 120 s task limit and be killed without a word
// (review finding #9). The deadline ends it first, with the failure line.
func TestEveryCommandRunsUnderADeadline(t *testing.T) {
	ctx, cancel := commandContext(t.Context())
	defer cancel()

	deadline, ok := ctx.Deadline()
	if !ok {
		t.Fatal("commandContext must set a deadline")
	}
	if left := time.Until(deadline); left <= 0 || left > commandTimeout {
		t.Errorf("deadline in %s, want within (0, %s]", left, commandTimeout)
	}
}

// What the deadline buys: a tick whose every request hangs gives up when its
// context does, and says so in its failure line.
func TestATickGivesUpAtItsDeadline(t *testing.T) {
	cloud := newFakeCloud(t)
	cloud.hang.Store(true)
	ctx, cancel := context.WithTimeout(t.Context(), 200*time.Millisecond)
	defer cancel()

	var out bytes.Buffer
	started := time.Now()
	code := cloud.enforcer(&out).run(ctx, time.Date(2026, 9, 27, 5, 0, 0, 0, time.UTC), false)

	if code != 1 {
		t.Fatalf("exit code = %d, want 1", code)
	}
	if took := time.Since(started); took > 5*time.Second {
		t.Errorf("the tick took %s to give up; the deadline was 200ms", took)
	}
	if !strings.Contains(out.String(), "context deadline exceeded") {
		t.Errorf("the failure line should say the deadline ran out:\n%s", out.String())
	}
}

// A pool size L2 cannot read counts as "may be up", never as "asleep". Asleep
// is DecideL2's first rule ("nothing to do"), so reading an error as zero makes
// the money stop inert exactly when its view of the pool is broken. "May be up"
// costs at most a redundant setSize(0), which L3 shows is a harmless 200 on a
// pool that is already at zero.
func TestAnUnreadablePoolSizeCountsAsUp(t *testing.T) {
	cases := []struct {
		name string
		size int
		err  error
		want int
	}{
		{"a read size is used as is", 2, nil, 2},
		{"a read zero is asleep", 0, nil, 0},
		{"an unreadable size is up, not asleep", 0, errors.New("403 on the instance group"), 1},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := nodesForDecision(tc.size, tc.err); got != tc.want {
				t.Fatalf("nodesForDecision(%d, %v) = %d, want %d", tc.size, tc.err, got, tc.want)
			}
		})
	}
}
