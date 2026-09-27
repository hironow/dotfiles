package lease

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// The lockstep test the formal-methods rules require: exe/lease-constants.json
// is the single source, and three things mirror it -- this package, the Quint
// model, and (through jsondecode) the OpenTofu stack that builds the Scheduler
// cadences. A constant that exists in four places without a test is a constant
// that will disagree once, silently, and the disagreement will be between "when
// the code stops the cluster" and "when the cron says it should have".
//
// The Quint side of the lockstep is tests/unit/test_lease_constants_lockstep.py.

const constantsRelPath = "../../../../exe/lease-constants.json"

type constantsDoc struct {
	Timezone                  string `json:"timezone"`
	DefaultLeaseMinutes       int    `json:"default_lease_minutes"`
	MaxLeaseMinutes           int    `json:"max_lease_minutes"`
	L1TickMinutes             int    `json:"l1_tick_minutes"`
	DrainCeilingMinutes       int    `json:"drain_ceiling_minutes"`
	L2TickMinutes             int    `json:"l2_tick_minutes"`
	SlackMinutes              int    `json:"slack_minutes"`
	L3StopLocalHour           int    `json:"l3_daily_stop_local_hour"`
	NightlyCapLocalHour       int    `json:"nightly_cap_local_hour"`
	ForceGraceMinutes         int    `json:"force_grace_minutes"`
	HeartbeatStaleTicks       int    `json:"heartbeat_stale_ticks"`
	IdleZeroRunningMinutes    int    `json:"idle_zero_running_minutes"`
	LeaseReadFailureThreshold int    `json:"lease_read_failure_threshold"`
	TaskTTLDays               int    `json:"task_ttl_days"`
	TaskTTLWarningDays        int    `json:"task_ttl_warning_days"`
}

func loadConstants(t *testing.T) constantsDoc {
	t.Helper()
	path, err := filepath.Abs(constantsRelPath)
	if err != nil {
		t.Fatalf("resolving %s: %v", constantsRelPath, err)
	}
	raw, err := os.ReadFile(path) //nolint:gosec // fixed repo-relative path
	if err != nil {
		t.Fatalf("reading %s: %v", path, err)
	}
	var doc constantsDoc
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("parsing %s: %v", path, err)
	}
	return doc
}

func TestConstantsMatchTheSingleSource(t *testing.T) {
	doc := loadConstants(t)

	minutes := func(d time.Duration) int { return int(d / time.Minute) }
	days := func(d time.Duration) int { return int(d / (24 * time.Hour)) }

	checks := []struct {
		name string
		got  any
		want any
	}{
		{"timezone", TimezoneName, doc.Timezone},
		{"default_lease_minutes", minutes(DefaultLease), doc.DefaultLeaseMinutes},
		{"max_lease_minutes", minutes(MaxLease), doc.MaxLeaseMinutes},
		{"l1_tick_minutes", minutes(L1Tick), doc.L1TickMinutes},
		{"drain_ceiling_minutes", minutes(DrainCeiling), doc.DrainCeilingMinutes},
		{"l2_tick_minutes", minutes(L2Tick), doc.L2TickMinutes},
		{"slack_minutes", minutes(Slack), doc.SlackMinutes},
		{"l3_daily_stop_local_hour", L3StopHour, doc.L3StopLocalHour},
		{"nightly_cap_local_hour", NightlyCapHour, doc.NightlyCapLocalHour},
		{"force_grace_minutes", minutes(ForceGrace), doc.ForceGraceMinutes},
		{"heartbeat_stale_ticks", HeartbeatStaleTicks, doc.HeartbeatStaleTicks},
		{"idle_zero_running_minutes", minutes(IdleZeroRunning), doc.IdleZeroRunningMinutes},
		{"lease_read_failure_threshold", LeaseReadFailureThreshold, doc.LeaseReadFailureThreshold},
		{"task_ttl_days", days(TaskTTL), doc.TaskTTLDays},
		{"task_ttl_warning_days", days(TaskTTLWarning), doc.TaskTTLWarningDays},
	}

	for _, c := range checks {
		if c.got != c.want {
			t.Errorf("%s: Go has %v, exe/lease-constants.json has %v -- "+
				"the JSON is the source of truth; move both together", c.name, c.got, c.want)
		}
	}
}

func TestTheCapIsDerivedNotAsserted(t *testing.T) {
	// The formula the whole design rests on. If someone lengthens the drain
	// ceiling or slows an L2 tick without moving the cap, the safety margin
	// silently shrinks and L3 starts catching awake actors -- which on Substrate
	// v0.1.0 destroys them with no recovery. So the cap is recomputed and
	// compared, never merely read.
	if got := NightlyCapHourComputed(); got != NightlyCapHour {
		t.Fatalf("cap formula: L3StopHour(%d) - margin(%s) = %d, but NightlyCapHour is %d. "+
			"Changing L1Tick / DrainCeiling / L2Tick / Slack means re-deriving the cap.",
			L3StopHour, CapMargin(), got, NightlyCapHour)
	}
	if CapMargin() != time.Hour {
		t.Errorf("margin is %s; the formula in the plan sums to exactly 1h", CapMargin())
	}
}

func TestCapFormulaAlsoHoldsInTheJSON(t *testing.T) {
	// Same derivation, but over the JSON's own numbers, so the source of truth
	// cannot be internally inconsistent even before Go reads it.
	doc := loadConstants(t)
	margin := doc.L1TickMinutes + doc.DrainCeilingMinutes + doc.L2TickMinutes + doc.SlackMinutes
	if margin%60 != 0 {
		t.Fatalf("margin %d minutes is not a whole number of hours", margin)
	}
	if want := doc.L3StopLocalHour - margin/60; want != doc.NightlyCapLocalHour {
		t.Errorf("exe/lease-constants.json is self-inconsistent: cap should be %d, is %d",
			want, doc.NightlyCapLocalHour)
	}
}

func TestTimezoneResolves(t *testing.T) {
	loc := Location()
	if loc == nil {
		t.Fatal("Location() returned nil")
	}
	// Whatever route it took (tzdata or the fixed-offset fallback), the offset
	// for a known winter date must be +09:00. A wrong offset moves every
	// boundary by hours without failing anything else.
	_, offset := time.Date(2026, 1, 15, 12, 0, 0, 0, loc).Zone()
	if offset != 9*60*60 {
		t.Errorf("offset for the operator timezone is %d seconds, want %d", offset, 9*60*60)
	}
}

func TestLocationIsResolvedOnce(t *testing.T) {
	// time.LoadLocation reads and parses the zoneinfo file on every call, and
	// the seeded simulation asks for the zone on every simulated minute: 60 000
	// file reads per sweep made the gate's slowest step slow for no reason.
	// One resolution per process is also the only sane semantics -- a zone
	// that changed mid-run would move every boundary under a running decision.
	first, second := Location(), Location()
	if first != second {
		t.Fatal("Location() must return the same *time.Location on every call")
	}
}
