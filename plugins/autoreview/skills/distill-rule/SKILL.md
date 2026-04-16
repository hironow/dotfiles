---
name: distill-rule
description: >
  This skill should be used when the user asks to "distill a rule",
  "create a semgrep rule from this finding", "turn this into a rule",
  "codify this pattern", "prevent this from recurring",
  "extract a semgrep rule", "add a guardrail for this",
  or wants to convert a code review finding or bad code pattern into a
  reusable Semgrep rule with test cases. Also triggered after a review
  loop when patterns emerge that should be automated.
version: 0.1.0
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
---

# Distill Rule

Convert code review findings into reusable Semgrep rules. Each invocation
produces a rule YAML file and a corresponding test file, placed in the
review target project's `.semgrep/` directory.

## Input Sources

Accept rule extraction requests from any of these sources:

1. **Review results** — Parse review-results.tsv for kept fixes. Analyze
   the before/after diff to extract the violation pattern.
2. **Manual specification** — User describes a bad pattern to catch.
3. **Code example** — User points to specific code that should or should
   not be flagged.

## Distillation Process

### 1. Identify the Pattern

For review-results input:
```bash
# Get the diff of a kept fix
git show <commit> --stat
git show <commit> -- <file>
```

Analyze what changed. The "before" code is the violation pattern; the
"after" code is the expected fix.

For manual input, ask the user to provide:
- A code example that SHOULD trigger the rule (true positive)
- A code example that should NOT trigger (true negative)
- Which languages the rule applies to

### 2. Determine Rule Category

Map the finding to one of the 11 guardrails categories:
naming, type-safety, immutability, encapsulation, structure, complexity,
layer-dependency, repository, error-handling, security, backward-compat.

If none fit, propose a new category name and confirm with the user.

### 3. Choose Rule Technique

Select the appropriate Semgrep pattern technique:

| Technique | When to Use |
|-----------|-------------|
| `pattern` | Single code pattern to match |
| `pattern-either` | Multiple variant patterns |
| `pattern-not` | Exclude false positives |
| `patterns` (AND) | Combine conditions |
| `pattern-regex` | String/naming conventions |
| `metavariable-regex` | Constrain matched identifiers |
| `pattern-inside` | Scope to specific contexts |

Consult `references/rule-templates.md` for complete template examples.

### 4. Write the Rule YAML

Create the rule file at:
```
<project>/.semgrep/<category>/<rule-name>-<language>.yaml
```

Follow this structure:
```yaml
rules:
  - id: <category>.<descriptive-name>-<language>
    languages: [<language>]
    severity: WARNING    # or ERROR for security rules
    message: >-
      [WHY] <Explain why this pattern is problematic. Be specific about
      the architectural principle being violated.>
      [HOW] <Concrete fix instructions with code examples.>
    <pattern-technique>: <pattern>
    metadata:
      category: <category>
      rule-origin: autoreview/distill-rule
```

Naming conventions for `id`:
- Use the category as prefix: `naming.ambiguous-suffix-python`
- Use hyphens for multi-word names
- Append language suffix

### 5. Write Test File

Create the test file at:
```
<project>/.semgrep/tests/<category>/<language>/<test_name>_test.<ext>
```

Extensions: `.py` for Python, `.ts` for TypeScript, `.go` for Go.

Test file format — annotate each case with `ruleid` or `ok` comments:
```
# ruleid: <rule-id>
<code that SHOULD trigger the rule>

# ok: <rule-id>
<code that should NOT trigger the rule>
```

Include at minimum:
- 2-3 true positive cases (different variations of the bad pattern)
- 2-3 true negative cases (similar but correct code)
- Edge cases (framework exceptions, standard library usage)

### 6. Validate

Run validation and tests:
```bash
# Validate rule syntax
semgrep --validate --config <rule-file>

# Run test
semgrep --test --config <rule-file> <test-file>
```

Both must pass. If validation fails, fix the rule syntax. If tests fail,
adjust the pattern or test annotations.

### 7. Verify Against Codebase

Run the new rule against the target codebase to check for false positives:
```bash
semgrep --config <rule-file> <target_paths>
```

If excessive false positives appear, refine the pattern with `pattern-not`
or `pattern-not-inside` exclusions.

### 8. Commit

```bash
git add .semgrep/<category>/<rule-file> .semgrep/tests/<category>/
git commit -m "guardrail(<category>): add <rule-name> rule

Distilled from review finding: <description>"
```

## Batch Distillation

When processing review-results.tsv for multiple findings:

1. Group kept fixes by category
2. Within each category, identify recurring patterns
3. Distill one rule per distinct pattern (not per finding)
4. Run all new rules together to check for conflicts

## Additional Resources

### Reference Files

- **`references/rule-templates.md`** — Complete Semgrep rule templates
  for each pattern technique, with examples for Go, Python, and TypeScript
