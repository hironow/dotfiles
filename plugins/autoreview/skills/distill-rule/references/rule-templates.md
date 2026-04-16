# Semgrep Rule Templates

Quick-reference templates for each major pattern technique. All examples
follow the guardrails convention: `[WHY]` + `[HOW]` in message, category
prefix in id.

## Simple Pattern

Match a single code structure.

```yaml
rules:
  - id: naming.example-violation-python
    languages: [python]
    severity: WARNING
    message: >-
      [WHY] Explanation of the problem.
      [HOW] Concrete fix instructions.
    pattern: |
      class $NAME(...):
          ...
    metavariable-regex:
      metavariable: $NAME
      regex: ^.*BadSuffix$
    metadata:
      category: naming
      rule-origin: autoreview/distill-rule
```

## Pattern-Either (OR)

Match any of several variant patterns.

```yaml
rules:
  - id: immutability.destructive-mutation-python
    languages: [python]
    severity: WARNING
    message: >-
      [WHY] Destructive mutation breaks immutability guarantees.
      [HOW] Return a new collection instead of mutating in place.
    pattern-either:
      - pattern: $LIST.append($X)
      - pattern: $LIST.extend($X)
      - pattern: $LIST.insert($IDX, $X)
      - pattern: $DICT[$KEY] = $VAL
    metadata:
      category: immutability
      rule-origin: autoreview/distill-rule
```

## Patterns (AND)

Combine multiple conditions that must all be true.

```yaml
rules:
  - id: layer-dependency.domain-imports-infra-python
    languages: [python]
    severity: WARNING
    message: >-
      [WHY] Domain layer must not depend on infrastructure.
      [HOW] Define a repository interface in domain and implement in infra.
    patterns:
      - pattern: import $MOD
      - metavariable-regex:
          metavariable: $MOD
          regex: ^(sqlalchemy|boto3|redis|requests)
      - pattern-inside: |
          # In a domain module
          ...
    paths:
      include:
        - "**/domain/**"
    metadata:
      category: layer-dependency
      rule-origin: autoreview/distill-rule
```

## Pattern with Exclusion

Match a pattern but exclude known-good variants.

```yaml
rules:
  - id: error-handling.broad-catch-python
    languages: [python]
    severity: WARNING
    message: >-
      [WHY] Catching bare Exception hides bugs.
      [HOW] Catch specific exception types.
    patterns:
      - pattern: |
          try:
              ...
          except Exception as $E:
              ...
      - pattern-not: |
          try:
              ...
          except Exception as $E:
              logger.exception(...)
              raise
    metadata:
      category: error-handling
      rule-origin: autoreview/distill-rule
```

## Pattern-Regex

Match string patterns (naming conventions, secrets, etc.).

```yaml
rules:
  - id: security.hardcoded-token-typescript
    languages: [typescript]
    severity: ERROR
    message: >-
      [WHY] Hardcoded tokens in source code risk credential exposure.
      [HOW] Use environment variables or a secret manager.
    pattern-regex: "(?i)(api_key|secret|token|password)\\s*[:=]\\s*['\"][^'\"]{8,}['\"]"
    paths:
      exclude:
        - "**/*.test.*"
        - "**/__tests__/**"
    metadata:
      category: security
      rule-origin: autoreview/distill-rule
```

## Pattern-Inside (Scoping)

Restrict matches to a specific context.

```yaml
rules:
  - id: encapsulation.getter-in-domain-go
    languages: [go]
    severity: WARNING
    message: >-
      [WHY] Getters in domain types break encapsulation.
      [HOW] Add a behavior method that operates on the data internally.
    pattern: |
      func ($RECV $TYPE) Get$FIELD() $RET {
          return $RECV.$FIELD
      }
    pattern-inside: |
      package domain
      ...
    metadata:
      category: encapsulation
      rule-origin: autoreview/distill-rule
```

## Test File Conventions

### Python (`_test.py`)

```python
# ruleid: category.rule-name-python
bad_code_example_1()

# ruleid: category.rule-name-python
bad_code_example_2()

# ok: category.rule-name-python
good_code_example_1()

# ok: category.rule-name-python
good_code_example_2()
```

### TypeScript (`_test.ts`)

```typescript
// ruleid: category.rule-name-typescript
const bad = badCodeExample1();

// ok: category.rule-name-typescript
const good = goodCodeExample1();
```

### Go (`_test.go`)

```go
// ruleid: category.rule-name-go
func badExample() { badCode() }

// ok: category.rule-name-go
func goodExample() { goodCode() }
```

## Severity Guidelines

| Severity | When to Use |
|----------|-------------|
| `ERROR` | Security vulnerabilities, data loss risks |
| `WARNING` | Architecture violations, code quality issues |
| `INFO` | Style preferences, minor suggestions |

Default to `WARNING` for most guardrails rules. Use `ERROR` only for
security category rules.
