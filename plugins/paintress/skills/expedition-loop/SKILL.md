---
name: expedition-loop
description: >-
  Core TDD cycle reference for the expedition agent's modify-test-commit
  workflow. This skill provides methodology knowledge, not the top-level
  entry point (use /expedition for that). Applicable when the user asks
  about "expedition TDD cycle", "modify-test-commit", "Red Green Refactor
  expedition", "3-strike rule", "expedition decision logic", or needs to
  understand how the internal fix cycle works. Primarily consumed as
  reference knowledge by the expedition agent.
version: 0.2.0
---

# Expedition Loop — Core Workflow Knowledge

The expedition loop follows a strict TDD cycle: pick issue, enter worktree, write failing test, implement minimum code, verify, commit, create PR.

## The Cycle (1 Issue = 1 Expedition)

```
1. PICK    → Read issue from Linear (ID, title, DoD checklist)
2. BRANCH  → git worktree add -b <prefix><issue-id> <repo>
3. READ    → Understand DoD, read relevant source files
4. RED     → Write a failing test that validates the fix
5. GREEN   → Write minimum code to make the test pass
6. VERIFY  → Run test_command (as configured in continent-config.yaml)
7. COMMIT  → git add -A && git commit -m "fix: <issue-id> <description>"
8. PR      → gh pr create --title "..." --body "..."
9. LOG     → Append result to journal.tsv
10. CLEAN  → git worktree remove <path>
```

## Immutable Rules

1. **TDD is mandatory**: Always write the failing test BEFORE implementation code
2. **Scope to issue**: Only modify files relevant to the issue's DoD
3. **Test command is sacred**: Never modify the test infrastructure
4. **3-strike rule**: If tests fail 3 times, retreat and log failure
5. **Journal is append-only**: Always log, regardless of outcome

## Decision Logic

```
Test command passes?
├─ YES → Commit → Create PR → Log "success"
└─ NO  → Attempt < 3?
   ├─ YES → Read error output → Fix → Retry
   └─ NO  → Categorize failure:
      ├─ Compilation error → Log "fail:compile"
      ├─ Test assertion    → Log "fail:test"
      └─ Timeout/hang     → Log "fail:timeout"
      All failures → Remove worktree, issue stays Backlog
```

For detailed examples of each branch, see `references/decision-logic.md`.

## Reading the Issue

Parse the Linear issue description for:
- **DoD checklist**: Each `- [ ]` item is a requirement
- **Files to Modify**: Specific source files mentioned
- **Dependencies**: Other issues that must be done first
- **Review Verdict**: Any caveats from plan review

If the issue lacks a clear DoD, log `skip:no-dod` and move to the next issue.

## TDD Discipline

### RED Phase
- Write ONE failing test that captures the bug or missing behavior
- Test name should describe the expected behavior (e.g., `TestValidateEmail_RejectsEmpty`)
- Run the test command to confirm it fails for the RIGHT reason

### GREEN Phase
- Write the MINIMUM code to make the test pass
- Do not add features beyond what the test requires
- Do not refactor yet

### VERIFY Phase
- Run the FULL test suite, not just the new test
- All existing tests must continue to pass
- If any test breaks, fix it before proceeding

## Commit Message Format

```
fix: #<issue-number> <short description>
```

Example: `fix: #123 add ValidateAxesPresent for partial axes detection`

## PR Format

```
gh pr create --title "fix: #<issue-number> <description>" --body "$(cat <<'EOF'
## Summary
<1-2 sentences>

## Changes
- <file1>: <what changed>
- <file2>: <what changed>

## Test plan
- [x] New test: <test name>
- [x] Full test suite passes
EOF
)"
```

## Error Recovery

### Compilation Error (attempt < 3)
Read the error output carefully. Common causes:
- Missing import → add import
- Type mismatch → fix types
- Undefined reference → check spelling and package

### Test Failure (attempt < 3)
Read the test output. Common causes:
- Wrong assertion value → re-read the DoD
- Missing setup → add test fixture
- Race condition → add synchronization

### Unrecoverable (attempt >= 3)
Stop trying. Log the failure with the last error message. Remove the worktree. The issue stays in Backlog for manual attention.

## Learning from Journal

Before starting a new expedition, read `journal.tsv` for patterns:
- If multiple `fail:compile` entries → check for systemic build issues
- If `fail:test` on related issues → look for shared dependencies
- Success patterns inform approach for similar issues

