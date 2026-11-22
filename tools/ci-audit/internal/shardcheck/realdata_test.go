package shardcheck_test

import (
	"os"
	"testing"

	"github.com/hironow/dotfiles/tools/ci-audit/internal/shardcheck"
)

// TestRealSuiteRoundTrip runs the id contract on a real pytest run: the list
// `pytest --collect-only -q` printed, and the JUnit of the same suite run with
// `-n auto --dist loadgroup`. Point both variables at them; without them the
// test is skipped, because the files are 1 MB of CI output.
func TestRealSuiteRoundTrip(t *testing.T) {
	collectedPath := os.Getenv("CI_AUDIT_REAL_COLLECTED")
	junitPath := os.Getenv("CI_AUDIT_REAL_JUNIT")
	if collectedPath == "" || junitPath == "" {
		t.Skip("CI_AUDIT_REAL_COLLECTED and CI_AUDIT_REAL_JUNIT are not set")
	}
	collectedData, err := os.ReadFile(collectedPath)
	if err != nil {
		t.Fatal(err)
	}
	junitData, err := os.ReadFile(junitPath)
	if err != nil {
		t.Fatal(err)
	}
	collected := shardcheck.ParseCollected(collectedData)
	cases, err := shardcheck.ParseJUnit(junitData)
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("collected %d ids, junit %d testcases", len(collected), len(cases))

	// One shard that ran everything: the proof must pass on a real run.
	whole := shardcheck.Check([]shardcheck.Shard{{Name: "whole", Collected: collected, Cases: cases}}, shardcheck.Options{})
	if !whole.OK() {
		t.Fatalf("a whole real run must pass: %v", whole.Problems)
	}
	if whole.Expected != len(collected) || whole.Executed != len(cases) {
		t.Fatalf("expected/executed = %d/%d, want %d/%d", whole.Expected, whole.Executed, len(collected), len(cases))
	}

	// Split the same run into three shards by position, then drop one case.
	three := make([]shardcheck.Shard, 3)
	for i := range three {
		three[i] = shardcheck.Shard{Name: "s" + string(rune('1'+i)), Collected: collected}
	}
	for i, c := range cases {
		three[i%3].Cases = append(three[i%3].Cases, c)
	}
	if r := shardcheck.Check(three, shardcheck.Options{}); !r.OK() {
		t.Fatalf("three shards of a real run must pass: %v", r.Problems)
	}
	three[1].Cases = three[1].Cases[1:]
	if r := shardcheck.Check(three, shardcheck.Options{}); r.OK() || len(r.Missing) != 1 {
		t.Fatalf("one dropped real case must fail with 1 missing, got ok=%v missing=%d", r.OK(), len(r.Missing))
	}
}
