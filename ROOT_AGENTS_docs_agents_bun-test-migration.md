# Converting a hand-rolled TypeScript test harness to bun:test

Read this when you convert a hand-rolled TypeScript test harness to
`bun:test`. docs/agents/testing.md has the general test rules.

Write new TypeScript suites with `bun:test`: `describe` / `test` / `expect`.
Never write a hand-rolled harness such as `let pass = 0; const ok = (name, cond)
=> …`. When you migrate an existing hand-rolled leaf, the conversion must
**preserve behavior**: it exercises the same inputs and catches the same
failures.

## The naive transform is wrong

Do not turn `ok("name", cond, note)` into
`test("name", () => { expect(cond).toBe(true) })`.

The condition becomes `true` or `false` before `expect` sees it, so the failure
message says `expected true, got false` and shows neither side. Use the matcher
that carries the values:

```ts
expect(xs.length).toBe(3)            // not expect(xs.length === 3).toBe(true)
expect(() => f(bad)).toThrow("usage") // not a try/catch + flag
expect(offenders).toEqual([])        // not expect(offenders.length === 0).toBe(true)
```

`toEqual([])` on a **collected list of offenders** prints the exact items that
broke.

## Loops and shared state

- A `console.log("\n── section ──")` section header becomes a `describe`.
- A `const` computed between `ok()` calls stays where it is, inside the
  `describe` body. Move it to `beforeAll` only if it is expensive or mutable.
- **A loop over a small fixed table becomes `test.each`**: one named case per
  row, so a failure names the row.
- **A loop over a large collection does NOT become one test per item.**
  Collapse it into one assertion over the collected offenders, and **keep a
  separate check that the collection is not empty**, so an empty collection
  cannot pass silently.
- Delete the trailing `console.log(\`${pass} passed\`)` and `process.exit(1)`
  completely. The runner owns the tally and the exit code.

## `test.each` type traps

- **A `readonly` array of primitives fails to type-check.** `readonly Locale[]`
  matches none of bun's three `.each` overloads, so the callback argument
  becomes `unknown`. Pass a mutable copy instead: `test.each([...LOCALES])`.
- `%s` inserts a positional argument, `%j` a JSON value, and `$prop` a field of
  an object row.

## Proving the conversion is equivalent

1. The converted leaf is **green**, and you can account for its coverage:
   either the count matches the baseline, or you can name the collapse or
   expansion behind every difference.
2. **Red still works**: break one assertion, confirm the leaf fails, then
   restore it.
3. The leaf is inside a **type-checked program** (`bun test` alone does not
   catch the `.each` type trap above).

## Convert by hand and derive runner lists

- Do not use regex/parenthesis-counting scripts to rewrite `ok(…)` calls; regex
  literals with unbalanced `(` inside character classes corrupt the file.
- During a dual-runner migration, **never keep a hand-written list of which leaf
  runs on which runner.** Derive the set from the files themselves (grep for the
  `bun:test` import) in one script shared by the old runner, the new runner, and
  the tsconfig guard.
- `@types/bun` replaces ambient `fetch` (adding `preconnect`, which breaks
  `typeof fetch` with TS2741). Give migrated leaves a separate tsconfig, and add
  a guard test that asserts each derived leaf is excluded from the shared
  program and included in the bun one.
