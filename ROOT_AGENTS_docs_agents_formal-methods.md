# Formal methods (distributed state)

Read this when the component holds **distributed state**: an at-least-once
queue, a lock or lease, a reconciler or janitor, a retention / cleanup
policy, or anything that deletes or releases something on its own.
Single-process deterministic logic stays unit-test territory.

Applies to **every repo** that matches the trigger above.

## What to produce

- **Design**: `<component>/spec/*.qnt` — state machine, invariants, every
  recorded incident as a scripted `*Test`, design variants as instances.
  `Safety` holds **mandatory** properties only. An expected failure stays a
  named run; the model header records its scope, who accepted it, and the
  compensating control.
- **Implementation**: a **seeded, replayable simulation of the real code**
  (stub I/O, never the logic). Check the model's invariants each step; print
  seed + trace on failure; one-seed replay by env var. Per invariant: model
  action boundary → implementation I/O boundary → covering test. Name the
  properties the simulation does **not** reproduce as outside the guarantee.
- **Autonomous delete / release**: the precondition is a model invariant; the
  code's guard mirrors it; a lockstep test holds shared constants equal.

## Gate

`just spec-check` is a **strict bash** recipe (`set -euo pipefail`; just's
default `sh -cu` hides a failing `for` iteration) calling Quint through one
pinned `QUINT` variable, inside `just check`. CI runs the same recipe.

Tools: **Quint** (`@informalsystems/quint`) + the simulation. Apalache
(`quint verify`) is an optional bug finder, never a gate. TLA+ and Lean are
not used.

Start from a small lease example (a lock without a lease, with a lease,
with a fencing token) and grow from there. Applicability is a human
judgement, not a grep; an out-of-scope repo needs nothing in its own tree.
Findings go to `docs/plan/<topic>.md` as what / how-found / status.
