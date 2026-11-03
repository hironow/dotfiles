# Performance: measure before you change code for speed

Read this whenever you measure or change code for speed, in any language. The
language guides add their own tools: Go's profiler and benchmarks are in
docs/agents/go-tooling.md ("Measure before you optimise").

Measurements are noisy. The same code on the same machine can vary between
runs by more than the change you are testing, so one run per version proves
nothing.

## Compare one change at a time

- Before you measure, decide the metric, how big a gain matters, and how many
  runs you can afford.
- Change one thing per comparison. Two changes in one measurement cannot be
  told apart.
- Run the old and the new version the same number of times, alternating, under
  the same conditions. Keep the change when the new runs beat the old ones by
  the gain you decided. If you cannot tell, write "effect unconfirmed" and
  revert that experiment.
- Write each comparison down: the environment, the input, the config, the
  numbers, what you observed and what you infer, and the decision.
- Treat a reviewer's suggestion the same way. It is a hypothesis until a
  comparison supports it.

## Read the profile before you guess

The hot spot can be code you added yourself, such as a debug mode that runs the
old and the new path and compares them, or extra logging. Remove temporary
checks and logging before you finish, or put them behind a switch that is off
by default.

## Keep the contract

A speed change must keep what the code accepts and what it rejects.

- Add regression tests for invalid and edge-case input before you change a
  check.
- Narrowing a check on purpose is a change to the spec. Decide it on its own,
  not as part of a speed change.
- "Same results on the inputs we saw" does not prove that two versions are
  equal.
