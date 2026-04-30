---
name: review-gate
description: >-
  Post-PR code review cycle that automatically reviews and fixes issues
  before considering an expedition complete. Applicable when the user asks
  about "review gate", "auto review", "PR review cycle", "code review loop",
  or needs to understand how PRs are reviewed after expedition creates them.
version: 0.2.0
---

# Review Gate — Post-PR Code Review Cycle

After a successful expedition creates a PR, the Review Gate runs an automated
code review and iterates on fixes up to 3 times.

## Trigger

The Review Gate activates when:

- Expedition status is `success`
- A PR URL was created
- `review_cmd` is configured in `continent-config.yaml` (non-empty)

If `review_cmd` is empty or not set, the Review Gate is skipped.

## Review Cycle

```
REVIEW LOOP (max 3 cycles):
  1. Run review_cmd against the PR branch
  2. Check exit code:
     ├─ 0 (pass) → Review approved, expedition complete
     └─ non-zero (fail) → Review found issues
  3. If fail and cycle < 3:
     a. Read review output for actionable feedback
     b. Spawn expedition agent again with review context:
        "Fix review comments: <review output>"
     c. Agent modifies code, runs tests, commits, pushes
     d. Increment cycle counter
  4. If fail and cycle >= 3:
     → Log as "success:review-pending" (PR exists but has unresolved comments)
     → Record unresolved review comments in journal insight field
```

## Configuration

In `continent-config.yaml`:

Any command that:

- Exits 0 when the code passes review
- Exits non-zero when issues are found
- Outputs actionable feedback on stdout

Examples:

```yaml
# Using codex
review_cmd: "codex exec -m gpt-5.3-codex --skip-git-repo-check 'Review the diff on the current branch against main.'"

# Using a custom linter
review_cmd: "make lint && make typecheck"

# Disable review gate
review_cmd: ""
```

## Agent Re-invocation

When review finds issues, re-spawn the expedition agent with additional context:

```
Agent(
  subagent_type="paintress:expedition",
  prompt="Fix review comments for issue <ID>.\n\nReview feedback:\n<review_output>\n\nRepository: <worktree path>\nTest command: <test_command>\n\nFix the issues, run tests, commit, and push. Do NOT create a new PR.",
  run_in_background=false
)
```

The agent should:

1. Read the review feedback
2. Fix the issues in the existing worktree
3. Run tests to verify
4. Commit with message: `fix: #<number> address review comments`
5. Push to the existing branch (PR updates automatically)

## Status Values

| Status | Meaning |
|---|---|
| `success` | PR created and review passed (or no review_cmd configured) |
| `success:review-pending` | PR created but review has unresolved comments after 3 cycles |

## Journal Logging

After the review gate completes, update the journal entry's status:

- If review passed: keep `success`
- If review gave up after 3 cycles: change to `success:review-pending`

Include review cycle count in the description: `(reviewed: N/3 cycles)`
