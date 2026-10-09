# Formal methods (distributed state)

Read this when a component holds **distributed state**: an at-least-once
queue, a lock or lease, a reconciler or janitor, a retention or cleanup policy,
or anything that deletes or releases something on its own. Logic that runs in
one process and is deterministic stays with unit tests.

This applies to **every repo** that matches the trigger above.

## What to produce

- **Design**: `<component>/spec/*.qnt`. It holds the state machine, the
  invariants, every recorded incident as a scripted `*Test`, and design
  variants as instances. `Safety` holds **mandatory** properties only. An
  expected failure stays a named run, and the model header records its scope,
  who accepted it, and the control that compensates for it.
- **Implementation**: a **seeded simulation of the real code that you can
  replay**. Stub the I/O, never the logic. Check the model's invariants at each
  step. On failure, print the seed and the trace. Allow replay of one seed
  through an env var. For each invariant, map the model's action boundary to
  the implementation's I/O boundary and to the test that covers it. Name the
  properties the simulation does **not** reproduce, and state that they are
  outside the guarantee.
- **Deletes or releases that happen on their own**: make the precondition a
  model invariant, make the code's guard mirror it, and keep shared constants
  equal with a lockstep test.

## Gate

The gate is a `just spec-check` recipe that `just check` runs, so CI runs what a
developer runs. Write it in **strict bash** (`set -euo pipefail`). just's
default `sh -cu` hides a failing `for` iteration, and that is how a model
silently stops being checked. Call Quint through one pinned variable, not bare
`quint`, so the gate cannot drift onto whatever version is on PATH.

dotfiles itself no longer has such a recipe: its model left together with the
stack it described. So treat this section as the shape to build, not a recipe to
run here. `quint` stays pinned in the global mise config for exactly that
reason.

Tools: **Quint** (`@informalsystems/quint`) plus the simulation. Apalache
(`quint verify`) is an optional bug finder, never a gate. TLA+ and Lean are not
used.

Start from a small lease example (a lock without a lease, with a lease, with a
fencing token) and grow from there. Whether this applies is a human judgement,
not a grep. A repo out of scope needs nothing in its own tree. Write findings to
`docs/plan/<topic>.md` as what / how found / status.
