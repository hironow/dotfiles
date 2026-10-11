# Converting a hand-rolled TypeScript test harness to bun:test

Read this when you convert a hand-rolled TypeScript test harness to
`bun:test`. docs/agents/testing.md has the general test rules.

Write new TypeScript suites with `bun:test`: `describe` / `test` / `expect`.
Never write a hand-rolled harness such as
`let pass = 0; const ok = (name, cond) => …`. When you migrate an existing
hand-rolled leaf, the conversion must **preserve behaviour**: it exercises the
same inputs and catches the same failures. The rules below come from 7
converted leaves (2026-08-31).

## The naive transform is wrong

```ts
ok("名", 条件, 補足)  →  test("名", () => { expect(条件).toBe(true) })   // ✗
```

Bun's own docs list `expect(users.length === 3).toBe(true)` under **Avoid**.
The condition becomes `true` or `false` before `expect` sees it, so the failure
message says `expected true, got false` and shows neither side. Use the matcher
that carries the values:

```ts
expect(xs.length).toBe(3)            // not expect(xs.length === 3).toBe(true)
expect(() => f(bad)).toThrow("用途")  // not a try/catch + flag
expect(offenders).toEqual([])        // not expect(offenders.length === 0).toBe(true)
```

The most useful shape is `toEqual([])` on a **collected list of offenders**:
the failure prints exactly which items broke. The old `ok()` never did that.

## Loops and shared state

- A `console.log("\n── 節 ──")` section header becomes a `describe`.
- A `const` computed between `ok()` calls stays where it is, inside the
  `describe` body. Move it to `beforeAll` only if it is expensive or mutable.
- **A loop over a small fixed table becomes `test.each`**: one named case per
  row, so a failure names the row.
- **A loop over a large collection does NOT become one test per item.** A loop
  over 1346 words × 2 locales produced 2692 assertions; as separate tests that
  is unreadable and slow. Collapse it into one assertion over the collected
  offenders, and **keep a separate check that the collection is not empty**, so
  an empty collection cannot pass silently:

```ts
test("語を歩けている", () => { expect(WORDS.length).toBeGreaterThanOrEqual(30) })
test("どの語にも両言語が在る", () => {
  const missing = WORDS.flatMap(([p, w]) =>
    LOCALES.filter((lo) => t(w, lo).trim() === "").map((lo) => `${p} の ${lo}`))
  expect(missing).toEqual([])
})
```

- Delete the trailing `console.log(\`${pass} passed\`)` and `process.exit(1)`
  completely. The runner owns the tally and the exit code.

## `test.each` type traps

- **A `readonly` array of primitives fails to type-check.** `readonly Locale[]`
  matches none of bun's three `.each` overloads: the tuple overload accepts
  `readonly` but wants tuples, and the flat overload wants a mutable array. The
  callback argument then becomes `unknown`. Pass a copy instead:
  `test.each([...LOCALES])`. In one leaf this caused 58 type errors and **zero**
  runtime failures, so you only see it when the leaf is inside a type-checked
  program.
- `%s` inserts a positional argument, `%j` a JSON value, and `$prop` a field of
  an object row.

## Proving the conversion is equivalent

The assertion count is **not** the test: it can rightly go up or down. A large
loop collapses into one assertion; a one-line `every()` over 8 bad inputs
expands into 8 named `test.each` rows. Require these instead:

1. The converted leaf is **green**, and you can account for its coverage:
   either the count matches the baseline, or you can name the collapse or
   expansion behind every difference.
2. **Red still works**: break one assertion, confirm the leaf fails, then
   restore it. A conversion that silently stops asserting looks exactly like a
   passing one.
3. The leaf is inside a **type-checked program** (see below). `bun test` alone
   does not catch the `.each` trap above.

## Mechanical conversion does not work

A script that finds `ok(…)` call boundaries by counting parentheses **cannot
parse TypeScript**. A regex literal such as `/^(OL|FI)[\s(（]/` has an
unbalanced `(` inside a character class. That throws the count off, and the
script silently writes a malformed file. Convert by hand, or with small
single-line edits, and run every converted leaf.

## During a dual-runner migration

While both runners exist, **never keep a hand-written list of which leaf runs
on which runner.** If you forget an entry, the old runner skips the leaf ("it
imports `bun:test`") and the new runner never lists it ("not on the list"). The
leaf then runs *nowhere*, and the suite still goes green. Derive the set from
the files themselves (grep for the `bun:test` import) in one script that every
consumer reads: the old runner, the new runner, and the type-config guard.

## Type seat

`@types/bun` replaces the ambient `fetch` with Bun's, which has `preconnect`.
Any `typeof fetch` injection point then fails with TS2741. So bun types usually
cannot go into the shared program, and migrated leaves need a second tsconfig.
With two programs, a leaf can fall out of *both*. Add a guard test that walks
the derived list and asserts that each leaf is excluded from the shared program
and included in the bun one.
