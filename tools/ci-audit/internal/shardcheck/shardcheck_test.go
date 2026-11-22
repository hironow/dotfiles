package shardcheck_test

import (
	"fmt"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/ci-audit/internal/shardcheck"
)

// The ids below are shaped like the real suite: a plain test, a class method,
// parameters that hold "::", "/", "[", "]", spaces and "@".
var allIDs = []string{
	"tests/unit/test_a.py::test_one",
	"tests/unit/test_a.py::test_two",
	"tests/unit/test_b.py::TestThing::test_method",
	"tests/unit/test_b.py::test_param[npm:@openai/codex-latest]",
	"tests/unit/test_c.py::test_cmd[Help: lists targets]",
	"tests/unit/test_c.py::test_nested[a::b/c[d]]",
}

func TestKeyOfMapsANodeIDTheWayPytestWritesJUnit(t *testing.T) {
	cases := []struct {
		id    string
		class string
		name  string
	}{
		{"tests/unit/test_a.py::test_one", "tests.unit.test_a", "test_one"},
		{"tests/unit/test_b.py::TestThing::test_method", "tests.unit.test_b.TestThing", "test_method"},
		{"tests/unit/test_b.py::test_param[npm:@openai/codex-latest]", "tests.unit.test_b", "test_param[npm:@openai/codex-latest]"},
		{"tests/unit/test_c.py::test_cmd[Help: lists targets]", "tests.unit.test_c", "test_cmd[Help: lists targets]"},
		{"tests/unit/test_c.py::test_nested[a::b/c[d]]", "tests.unit.test_c", "test_nested[a::b/c[d]]"},
		{"tests/test_just_sandbox.py::test_x", "tests.test_just_sandbox", "test_x"},
	}
	for _, c := range cases {
		got := shardcheck.KeyOf(c.id)
		if got.Class != c.class || got.Name != c.name {
			t.Errorf("KeyOf(%q) = %+v, want class %q name %q", c.id, got, c.class, c.name)
		}
	}
}

func TestParseCollectedKeepsNodeIDsAndDropsPytestChatter(t *testing.T) {
	data := "tests/unit/test_a.py::test_one\n" +
		"tests/unit/test_c.py::test_cmd[Help: lists targets]\n" +
		"\n" +
		"5156 tests collected in 4.2s\n" +
		"/x/y.py:12: UserWarning: not an id\n"
	got := shardcheck.ParseCollected([]byte(data))
	want := []string{"tests/unit/test_a.py::test_one", "tests/unit/test_c.py::test_cmd[Help: lists targets]"}
	if strings.Join(got, "|") != strings.Join(want, "|") {
		t.Fatalf("ParseCollected = %q, want %q", got, want)
	}
}

// A Windows shard writes its list with CRLF line ends, and the gate that reads
// it runs on Linux.
func TestParseCollectedReadsAWindowsListWithCRLF(t *testing.T) {
	data := "tests/unit/test_a.py::test_one\r\n" +
		"tests/unit/test_c.py::test_cmd[Help: lists targets]\r\n" +
		"\r\n" +
		"2 tests collected in 3.10s\r\n"
	got := shardcheck.ParseCollected([]byte(data))
	want := []string{"tests/unit/test_a.py::test_one", "tests/unit/test_c.py::test_cmd[Help: lists targets]"}
	if strings.Join(got, "|") != strings.Join(want, "|") {
		t.Fatalf("ParseCollected = %q, want %q", got, want)
	}
}

func TestParseJUnitReadsEveryOutcome(t *testing.T) {
	data := `<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">
<testcase classname="tests.unit.test_a" name="test_one" time="0.5"/>
<testcase classname="tests.unit.test_a" name="test_two" time="1.25"><skipped type="pytest.skip" message="x"/></testcase>
<testcase classname="tests.unit.test_b.TestThing" name="test_method" time="2"><failure message="boom"/></testcase>
<testcase classname="tests.unit.test_b" name="test_param[npm:@openai/codex-latest]" time="0.1"><error message="e"/></testcase>
</testsuite></testsuites>`
	got, err := shardcheck.ParseJUnit([]byte(data))
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 4 {
		t.Fatalf("got %d cases, want 4: %+v", len(got), got)
	}
	wantOutcome := []string{"passed", "skipped", "failed", "error"}
	for i, c := range got {
		if c.Outcome != wantOutcome[i] {
			t.Errorf("case %d outcome = %q, want %q", i, c.Outcome, wantOutcome[i])
		}
	}
	if got[1].Seconds != 1.25 {
		t.Errorf("seconds = %v, want 1.25", got[1].Seconds)
	}
}

// shardsOf splits allIDs round-robin into n shards that each report what they
// were given, so a test can then damage one report.
func shardsOf(n int) []shardcheck.Shard {
	shards := make([]shardcheck.Shard, n)
	for i := range shards {
		shards[i].Name = fmt.Sprintf("shard-%d", i+1)
		shards[i].Collected = append([]string(nil), allIDs...)
	}
	for i, id := range allIDs {
		k := shardcheck.KeyOf(id)
		shards[i%n].Cases = append(shards[i%n].Cases, shardcheck.Case{Key: k, Seconds: float64(i + 1), Outcome: "passed"})
	}
	return shards
}

func TestCheckPassesWhenEveryShardRanItsShareOnce(t *testing.T) {
	r := shardcheck.Check(shardsOf(3), shardcheck.Options{MaxImbalance: 3})
	if !r.OK() {
		t.Fatalf("want OK, got problems: %v", r.Problems)
	}
	if r.Expected != len(allIDs) || r.Executed != len(allIDs) {
		t.Errorf("expected/executed = %d/%d, want %d", r.Expected, r.Executed, len(allIDs))
	}
}

func TestCheckFailsWhenOneCaseIsDroppedFromOneShard(t *testing.T) {
	shards := shardsOf(3)
	shards[1].Cases = shards[1].Cases[1:] // drop one case from one shard
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 10})
	if r.OK() {
		t.Fatal("a dropped case must fail the check")
	}
	if len(r.Missing) != 1 {
		t.Fatalf("missing = %v, want exactly 1", r.Missing)
	}
}

func TestCheckPassesForAnyNumberOfShardsThatEachRanSomething(t *testing.T) {
	for _, n := range []int{1, 2, 4, 6} {
		r := shardcheck.Check(shardsOf(n), shardcheck.Options{})
		if !r.OK() {
			t.Errorf("%d shards: %v", n, r.Problems)
		}
	}
}

func TestCheckFailsOnATestThatRanTwice(t *testing.T) {
	shards := shardsOf(3)
	shards[2].Cases = append(shards[2].Cases, shards[0].Cases[0])
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 10})
	if r.OK() || len(r.Duplicates) != 1 {
		t.Fatalf("want 1 duplicate and failure, got ok=%v duplicates=%v", r.OK(), r.Duplicates)
	}
}

func TestCheckFailsOnAnIDThatWasNeverCollected(t *testing.T) {
	// If a later xdist appends "@group" to a JUnit name, the id is not in the
	// collected set: the check must turn red, not strip the suffix.
	shards := shardsOf(3)
	shards[0].Cases[0].Key.Name += "@agent-hooks"
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 10})
	if r.OK() {
		t.Fatal("an unknown id must fail")
	}
	if len(r.Unexpected) != 1 || len(r.Missing) != 1 {
		t.Fatalf("unexpected=%v missing=%v, want 1 and 1", r.Unexpected, r.Missing)
	}
}

func TestCheckFailsWhenShardsCollectedDifferentLists(t *testing.T) {
	shards := shardsOf(3)
	shards[1].Collected = shards[1].Collected[:len(shards[1].Collected)-1]
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 10})
	if r.OK() || len(r.DifferingLists) != 1 || r.DifferingLists[0] != "shard-2" {
		t.Fatalf("want shard-2 flagged, got ok=%v differing=%v", r.OK(), r.DifferingLists)
	}
}

func TestCheckFailsOnAnEmptyShard(t *testing.T) {
	shards := shardsOf(3)
	shards = append(shards, shardcheck.Shard{Name: "shard-4", Collected: allIDs})
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 10})
	if r.OK() || len(r.EmptyShards) != 1 || r.EmptyShards[0] != "shard-4" {
		t.Fatalf("want shard-4 empty, got ok=%v empty=%v", r.OK(), r.EmptyShards)
	}
}

func TestCheckFailsWhenTheSlowestShardIsTooFarAboveTheMean(t *testing.T) {
	shards := shardsOf(3)
	shards[0].Cases[0].Seconds = 500 // one shard far slower than the others
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 1.5})
	if r.OK() {
		t.Fatalf("imbalance %.2f must fail a 1.5 limit", r.Imbalance)
	}
	ok := shardcheck.Check(shardsOf(3), shardcheck.Options{MaxImbalance: 1.5})
	if !ok.OK() {
		t.Fatalf("a balanced run failed: %v (imbalance %.2f)", ok.Problems, ok.Imbalance)
	}
}

// A module that calls pytest.skip(allow_module_level=True) has no collected
// ids, and every shard's JUnit holds one case for it: classname "" and the
// module as the name, skipped. That is a report about a module, not a test.
func moduleCase(module, outcome string) shardcheck.Case {
	return shardcheck.Case{Key: shardcheck.Key{Class: "", Name: module}, Outcome: outcome}
}

func TestCheckReportsAModuleSkippedAtCollectionAndDoesNotCountIt(t *testing.T) {
	shards := shardsOf(3)
	for i := range shards {
		shards[i].Cases = append(shards[i].Cases, moduleCase("tests.unit.test_posix_only", "skipped"))
	}
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 10})
	if !r.OK() {
		t.Fatalf("a module skipped at collection must not fail: %v", r.Problems)
	}
	if r.Executed != len(allIDs) {
		t.Errorf("executed = %d, want %d: a skipped module is not a test", r.Executed, len(allIDs))
	}
	if strings.Join(r.SkippedModules, ",") != "tests.unit.test_posix_only" {
		t.Errorf("skipped modules = %v, want the one module, listed once", r.SkippedModules)
	}
}

// A shard whose report holds only a module that skipped itself ran no test:
// it is empty, and its time still counts toward the imbalance.
func TestCheckFailsOnAShardThatOnlySkippedAModule(t *testing.T) {
	shards := shardsOf(3)
	shards = append(shards, shardcheck.Shard{
		Name: "shard-4", Collected: allIDs,
		Cases: []shardcheck.Case{moduleCase("tests.unit.test_posix_only", "skipped")},
	})
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 10})
	if r.OK() || len(r.EmptyShards) != 1 || r.EmptyShards[0] != "shard-4" {
		t.Fatalf("want shard-4 empty, got ok=%v empty=%v", r.OK(), r.EmptyShards)
	}
	if _, ok := r.ShardSeconds["shard-4"]; !ok {
		t.Fatalf("shard-4 is missing from the shard times: %v", r.ShardSeconds)
	}
}

func TestCheckFailsOnAModuleThatFailedToCollect(t *testing.T) {
	shards := shardsOf(3)
	shards[1].Cases = append(shards[1].Cases, moduleCase("tests.unit.test_broken", "error"))
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 10})
	if r.OK() {
		t.Fatal("a module that failed to collect must fail the check")
	}
	if !strings.Contains(strings.Join(r.Problems, "\n"), "tests.unit.test_broken") {
		t.Fatalf("the module is not named: %v", r.Problems)
	}
}

// evenShards gives each of n shards the same work: per shard, `tests` tests of
// one second each in the committed durations, run at that shard's speed.
func evenShards(speeds []float64, tests int) ([]shardcheck.Shard, map[string]float64) {
	baseline := map[string]float64{}
	var ids []string
	for s := range speeds {
		for i := range tests {
			id := fmt.Sprintf("tests/unit/test_s%d.py::test_%d", s, i)
			ids = append(ids, id)
			baseline[id] = 1
		}
	}
	shards := make([]shardcheck.Shard, len(speeds))
	for s, speed := range speeds {
		shards[s].Name = fmt.Sprintf("shard-%d", s+1)
		shards[s].Collected = ids
		for i := range tests {
			k := shardcheck.KeyOf(fmt.Sprintf("tests/unit/test_s%d.py::test_%d", s, i))
			shards[s].Cases = append(shards[s].Cases, shardcheck.Case{Key: k, Seconds: speed, Outcome: "passed"})
		}
	}
	return shards, baseline
}

// One runner ran 2.5 times slower than the others (raw max/mean 2.5/1.5 =
// 1.67). The split was even, so the check must stay green: a slow runner is
// not stale durations.
func TestCheckIgnoresAShardWhoseRunnerWasSlower(t *testing.T) {
	shards, baseline := evenShards([]float64{2.5, 1, 1}, 20)
	raw := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 1.5})
	if raw.OK() {
		t.Fatalf("without the committed durations the raw imbalance %.2f should exceed 1.5", raw.Imbalance)
	}
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 1.5, Baseline: baseline})
	if !r.OK() {
		t.Fatalf("a slower runner failed the check: %v (imbalance %.2f)", r.Problems, r.Imbalance)
	}
	if r.Imbalance > 1.01 {
		t.Errorf("imbalance = %.2f, want about 1.00 once each shard's speed is factored out", r.Imbalance)
	}
}

// A slow test that the committed durations do not know (a new test) lands in
// one shard: that is stale durations, and the check must turn red even when
// the runners ran at the same speed.
func TestCheckFailsOnASlowTestTheDurationsDoNotKnow(t *testing.T) {
	shards, baseline := evenShards([]float64{1, 1, 1}, 20)
	k := shardcheck.KeyOf("tests/unit/test_new.py::test_slow")
	for i := range shards {
		shards[i].Collected = append(append([]string(nil), shards[i].Collected...), "tests/unit/test_new.py::test_slow")
	}
	shards[0].Cases = append(shards[0].Cases, shardcheck.Case{Key: k, Seconds: 30, Outcome: "passed"})
	r := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: 1.5, Baseline: baseline})
	if r.OK() {
		t.Fatalf("a 30 s test unknown to the durations must fail the balance (imbalance %.2f)", r.Imbalance)
	}
}

func TestCheckWritesDurationsKeyedByNodeID(t *testing.T) {
	r := shardcheck.Check(shardsOf(3), shardcheck.Options{MaxImbalance: 10})
	if len(r.Durations) != len(allIDs) {
		t.Fatalf("durations = %d, want %d", len(r.Durations), len(allIDs))
	}
	for _, id := range allIDs {
		if _, ok := r.Durations[id]; !ok {
			t.Errorf("no duration for %q", id)
		}
	}
}
