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
