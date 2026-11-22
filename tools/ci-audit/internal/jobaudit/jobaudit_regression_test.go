package jobaudit_test

import (
	"testing"

	"github.com/hironow/dotfiles/tools/ci-audit/internal/jobaudit"
)

// A real job from the audit data (run 44281477187, "bun check"): setup-uv took
// 3 s and the recipe step 1 s. Choosing the longest step called setup-uv the
// recipe and reported running = 3 s; the owner's jq numbers said 1 s.
func TestAShortRecipeIsNotMistakenForALongerSetupAction(t *testing.T) {
	j := jobaudit.Job{
		Name: "bun check", RunID: 44281477187, Attempt: 1, Conclusion: "success",
		Created: at(0), Started: at(2), Completed: at(15),
		Steps: []jobaudit.Step{
			step("Set up job", 5, 7),
			step("Run actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0", 7, 9),
			step("Run oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6", 9, 10),
			step("Run astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990", 10, 13),
			step("Install just", 13, 13),
			step("Run just js-typecheck", 13, 14),
			step("Post Run astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990", 14, 14),
			step("Post Run actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0", 14, 14),
			step("Complete job", 14, 15),
		},
	}
	got := jobaudit.Split(j)
	if got.Running != 1 {
		t.Fatalf("running = %v, want 1 (Run just js-typecheck)", got.Running)
	}
	if got.Setup != 2+2+1+3+0 {
		t.Fatalf("setup = %v, want 8", got.Setup)
	}
	if got.After != 0+0+1 {
		t.Fatalf("after = %v, want 1", got.After)
	}
}

func TestAnActionThatRunsLongerThanTheRecipeStillCountsAsSetup(t *testing.T) {
	j := jobaudit.Job{
		Name: "slow cache restore", RunID: 1, Attempt: 1, Conclusion: "success",
		Created: at(0), Started: at(1), Completed: at(60),
		Steps: []jobaudit.Step{
			step("Set up job", 1, 2),
			step("Run actions/cache@abcdef0123456789abcdef0123456789abcdef01", 2, 40),
			step("Run just js-lint", 40, 45),
			step("Post Run actions/cache@abcdef0123456789abcdef0123456789abcdef01", 45, 58),
			step("Complete job", 58, 60),
		},
	}
	got := jobaudit.Split(j)
	if got.Running != 5 {
		t.Fatalf("running = %v, want 5", got.Running)
	}
	if got.Setup != 1+38 {
		t.Fatalf("setup = %v, want 39 (job set-up and the cache restore)", got.Setup)
	}
	if got.After != 13+2 {
		t.Fatalf("after = %v, want 15 (the cache save and complete)", got.After)
	}
}

func TestAJobWithOnlyActionStepsReportsItsWholeBodyAsSetup(t *testing.T) {
	j := jobaudit.Job{
		Name: "only actions", RunID: 1, Attempt: 1, Conclusion: "success",
		Created: at(0), Started: at(1), Completed: at(10),
		Steps: []jobaudit.Step{step("Set up job", 1, 3), step("Run actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", 3, 8), step("Complete job", 8, 10)},
	}
	got := jobaudit.Split(j)
	if got.Running != 0 {
		t.Fatalf("running = %v, want 0: nothing in this job is the job's own work", got.Running)
	}
}
