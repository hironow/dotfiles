# Expedition Decision Logic — Detailed Reference

## Decision Tree with Examples

### Branch 1: Test Passes on First Attempt

**Situation**: Write test → implement → `<test_command>` passes immediately.

**Action**: Commit, create PR, log `success`.

**Example**:

```
Issue: #169 ValidateDMail rejects empty body
Test: TestValidateDMail_EmptyBody_IsInvalid
Impl: Add strings.TrimSpace check in ValidateDMail
Result: All tests pass on first run → success
```

### Branch 2: Test Fails, Fixed Within 3 Attempts

**Situation**: Test fails but error is understandable and fixable.

**Attempt 1 failure → read error → fix → retry**

**Example**:

```
Issue: #110 SanitizeTargets
Attempt 1: Forgot to import "strings" → compilation error
Fix: Add import
Attempt 2: All tests pass → success
```

### Branch 3: Compilation Error After 3 Attempts

**Situation**: Cannot get the code to compile after 3 tries.

**Action**: Log `fail:compile`, remove worktree, move on.

**Example**:

```
Issue: #116 TrimCheckHistory
Attempt 1: Type mismatch in function signature
Attempt 2: Fixed signature but broke existing caller
Attempt 3: Circular dependency introduced
Decision: fail:compile — needs architectural review
```

### Branch 4: Test Logic Error After 3 Attempts

**Situation**: Code compiles but tests fail with wrong assertions.

**Action**: Log `fail:test`, remove worktree, move on.

**Example**:

```
Issue: #142 DMailIdempotencyKey
Attempt 1: Hash includes wrong fields
Attempt 2: Sort order wrong for determinism
Attempt 3: Still non-deterministic on different inputs
Decision: fail:test — needs deeper understanding of hash requirements
```

### Branch 5: Timeout

**Situation**: Test command hangs or exceeds reasonable time.

**Action**: Kill process, log `fail:timeout`, remove worktree.

### Branch 6: Skip — No DoD

**Situation**: Issue description has no clear checklist or requirements.

**Action**: Log `skip:no-dod`, move to next issue.

### Branch 7: Skip — Conflict

**Situation**: Branch already exists or PR is open for this issue.

**Action**: Log `skip:conflict`, move to next issue.

## Journal Entry Examples

```tsv
issue commit status pr_url description
MY-473 51b52b7 success https://github.com/hironow/amadeus/pull/58 #123 partial axes handling
MY-486 - skip - #207 duplicate of #124
MY-529 - fail:compile - #053 type mismatch after 3 attempts
MY-520 a23db96 success https://github.com/hironow/amadeus/pull/58 #169 empty body guard
MY-999 - skip:no-dod - No DoD checklist in description
MY-998 - fail:timeout - Test hung after 120s
```

## Simplicity Criterion (from autoresearch)

When the fix works but introduces significant complexity:

```
Fix passes tests?
├─ YES: Is the fix simple?
│  ├─ Net code deletion → ALWAYS KEEP (simpler is better)
│  ├─ < 50 lines added → KEEP (reasonable scope)
│  ├─ 50-200 lines added → KEEP but note in PR description
│  └─ > 200 lines added → Consider splitting into multiple PRs
└─ NO: Follow 3-strike rule
```

For expedition purposes, we ALWAYS keep test-passing fixes (unlike autoresearch which reverts marginal improvements). The issue either gets fixed or it doesn't.
