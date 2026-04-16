# Decision Logic

## scan-fix Mode

The metric is Semgrep findings count. Lower is better.

| findings_before | findings_after | Code Complexity | Decision |
|----------------|---------------|-----------------|----------|
| N              | 0             | any             | **keep** — all findings resolved |
| N              | < N           | simple          | **keep** — net reduction with clean fix |
| N              | < N           | complex         | **keep** — net reduction, acceptable tradeoff |
| N              | N             | simpler code    | **keep** — same findings but code improved |
| N              | N             | same/complex    | **revert** — no improvement |
| N              | > N           | any             | **revert** — fix introduced new violations |

### Complexity Assessment

- **simple**: Rename, reorder, delete unused code, add type annotation
- **complex**: Extract method/class, introduce new abstraction, restructure module

### Special Cases

- If a fix resolves findings in one category but introduces findings in another
  category, treat as **revert** — cross-category regression is not acceptable.
- If the fix changes only whitespace or formatting with no finding change, **revert**.
- Code deletion that maintains or reduces findings is always **keep**.

## spec-review Mode

The metric is an LLM quality score (1-10) per guardrails category.
The score is inverted to `10 - score` so that lower values = better
(consistent with scan-fix findings count).

| score_before | score_after | Decision |
|-------------|-------------|----------|
| S           | < S         | **keep** — quality improved |
| S           | S           | **revert** — no improvement |
| S           | > S         | **revert** — quality degraded |

### Scoring Criteria by Category

Apply the guardrails rules conceptually to type definitions and interfaces:

- **naming**: Are type names responsibility-specific? No ambiguous suffixes?
- **type-safety**: Are domain primitives used? No `any` or raw primitives for domain concepts?
- **immutability**: Are data structures immutable by default? Frozen dataclasses?
- **encapsulation**: Is the Law of Demeter respected in type interfaces?
- **structure**: One type per file? Clear module boundaries?
- **complexity**: No deep inheritance (3+ levels)? No unnecessary generics?
- **layer-dependency**: Do types respect layer boundaries? No infra imports in domain?
- **repository**: Are repository interfaces properly named and placed?
- **error-handling**: Are error types specific? No broad catch-all error types?
- **security**: No secrets in type defaults? No sensitive data in log-friendly toString?
- **backward-compat**: No version-branching in type definitions?

### Score Scale

- **9-10**: Exemplary — follows all guardrails principles
- **7-8**: Good — minor improvements possible
- **5-6**: Acceptable — some violations present
- **3-4**: Needs work — multiple violations
- **1-2**: Poor — fundamental design issues

## Infinite Loop Prevention

### Oscillation Detection

If the last 3 iterations for a category show alternating keep/revert
(e.g., keep → revert → keep → revert), stop and move to the next category.
This indicates the fix and the revert are fighting each other.

### Diminishing Returns

If the last 2 kept iterations each improved findings by only 1, and there
are still many findings remaining, consider moving to the next category
and returning later with a different strategy.

### Total Budget

The total number of iterations across all categories should not exceed
`max_iterations_per_category * number_of_active_categories`. Report
progress after each category completion.
