# exe/spec/

Formal model of the `exe` cluster's lease-based auto-sleep.

`lease.qnt` is the design half of what
[`docs/agents/formal-methods.md`](../../ROOT_AGENTS_docs_agents_formal-methods.md)
requires for anything that stops or deletes on its own. The implementation half
— a seeded, replayable simulation of the Go reaper — lives with the Go code in
`tools/exe-reaper/`, not here.

The design it models is plan section 3.2 (`docs/plan/exe-google-ax.md`). All of
its numbers come from [`../lease-constants.json`](../lease-constants.json),
which is the only place they live.

## What the model covers

| Layer | Action(s) | Property it buys |
|---|---|---|
| L0 lease (operator, Mac) | `wakeFor` / `extendFor` / `sleep` | every wake carries an expiry; the nightly cap clamps it; a successful extend beats a stale `drained` |
| L1 graceful drain (in-cluster CronJob, 1 min) | `l1Tick` → `l1Begin`, `l1OpenRouter`, `l1Suspend`, `l1Stall`, `l1Finish`, `l1GiveUp`, `l1Cancel`, `l1Settled`, `l1NoOp`; `l1Crash` | the router closes before anything is suspended; the pool is never touched by L1 |
| L2 deadline enforcement (Cloud Run, 10 min) | `l2Tick` → plan section 3.2's L2 table, row for row the same as `DecideL2`: pool already at zero, read failures, lease live, then the rule for an expired lease | the node stops even when the cluster is broken; one or two read failures do nothing; past deadline + 45 min nothing waits |
| L3 daily stop (Cloud Scheduler → `setSize(0)`) | `l3Tick` | no logic at all, and the cap arithmetic makes that safe |
| environment | `autoResume`, `operatorResume`, `nodeLoss`, `leaseReadBreaks`, `leaseReadHeals`, `rogueLeaseWrite` | the router auto-resumes without asking; nodes vanish; GCS stops answering |

The three GCS objects are three state variables with exactly one writer each —
`lease` by L0, `drain` by L1, `enforce` by L2 — so "one writer per object" is a
structural property of the model, checkable by grepping for `lease' = {`,
`drain' = {` and `enforce' = {`.

### Invariants

`Safety` carries the four mandatory properties and nothing else:

- **`NoCrashOnGracefulSleep`** — a stop that claims to be graceful never shrinks
  the pool with an actor Running. This is why L1 exists.
- **`L3NeverHitsAwakeActor`** — the nightly cap hour is **re-derived** from
  `l3_daily_stop_local_hour` and the four latency terms, and the stored
  `nightly_cap_local_hour` appears only as the thing being checked. Scoped to
  `normalOperation` (the lease was readable, the drain never gave up, the
  deadline respected the cap); outside it, L4 alerting is the control, not
  arithmetic.
- **`NodesEventuallyZero`** — bounded-time termination, written as a safety
  property. Quint has no fairness, so "eventually" cannot be stated as a
  temporal formula: the unfair trace where the schedulers never fire would
  falsify it. The model instead makes the tick actions the only thing that moves
  the clock, and lets a tick fire only when it is the earliest scheduled event.
  "Eventually" then becomes arithmetic — if the clock is past the deadline plus
  the bound, the tick that had to stop the pool has already happened — and the
  honest encoding is a statement about the clock. Two bounds, both re-derived
  from the constants: `awake_bound_minutes` is the plan's `deadline + 45 + 10`
  and holds while L2's last read of `lease.json` succeeded;
  `blind_awake_bound_minutes` adds `lease_read_failure_threshold - 1` L2 ticks
  and holds regardless, because the three-strike rule forbids a stop on the
  first misses however late they come. The seeded simulation checks the same
  two numbers, taken from `lease.AwakeBound` and `lease.BlindAwakeBound`.
- **`ExtendBeatsStaleDrained`** — no stop taken from a lease L2 could actually
  read lands before the deadline the operator was granted.

Two more are checked beside `Safety` rather than inside it:

- **`DrainedRecordStaysTrue`** — the lemma `NoCrashOnGracefulSleep` rests on: a
  `drained` record stays true while it exists, because the router is open only
  when no drain is in flight. Checked separately so a regression points at the
  cause instead of the symptom.
- **`WellFormed`** — not a design property. A check that the model is not lying
  (no Running actor without a node, the actor sets partition, the clock does not
  run backwards).

### Rejected designs, kept as failing runs

Three instances of `leaseCore`, each with a header comment recording scope, who
accepted the decision, and the compensating control. Each has one named run that
**fails** — that is the deliverable, not a defect:

| Module | Named run | Invariant the run breaks |
|---|---|---|
| `twoWriterLease` | `twoWritersLoseTheOperatorsLease` | `ExtendBeatsStaleDrained` |
| `naiveShrinkFirst` | `shrinkingFirstCrashesTheRunningActor` | `NoCrashOnGracefulSleep` |
| `routerLeftOpen` | `leftOpenRouterRevivesAnActorAfterDrained` | `NoCrashOnGracefulSleep` |

None of these names end in `Test`, so `quint test` skips them and the gate stays
green. They are run explicitly — see below.

`routerLeftOpen` is the reason `DrainedRecordStaysTrue` is checked at all.
Random search finds that lemma broken in a fraction of a second, but does **not**
reach the crash itself — `NoCrashOnGracefulSleep` survives 200 steps × 30000
samples on that instance, because the trace needs a specific interleaving (drain
completes, connection arrives, L2's tick lands next). A sampling checker is not
going to find that; the scripted run and the lemma are what do.

### Recorded behaviour, replayed

The `*Test` runs in the `lease` module are the behaviours plan section 3.2 and
the Phase 3 e2e list name, scripted so they replay deterministically rather than
being sampled: the cap clamping an 8-hour request, `exe-wake` refusing inside the
cap window, a graceful `exe-sleep` losing nothing, the 30-minute idle drain, one
and two read failures doing nothing, the third forcing, a stale heartbeat
forcing, the drain ceiling forcing, a stale `drained` record forcing instead of
stopping gracefully, node loss not counting as a graceful stop, and a full night
ending with L3 springing on an empty pool.

The `l2Table*Test` runs walk the L2 table at the boundaries where the model and
`DecideL2` once disagreed, one tick each from a world built by `l2WorldAt`:
past the grace a fresh heartbeat buys nothing, exactly at it it still does; with
no drain record about the lease, L2 waits exactly one heartbeat window after the
deadline and forces a minute later; `drained` is a graceful stop even past the
grace; and a carried read-failure run resets while the pool is at zero.

## What the model deliberately does not cover

Read no invariant as covering any of this:

- **Real time.** One global clock in abstract minutes — no dates, no zone, no
  skew between the Mac, the CronJob and the Cloud Run job, and no scheduler
  jitter beyond "a tick happens no later than its period".
- **GCS semantics.** Reads are strongly consistent and a
  generation-precondition write either lands or fails. The only failure modelled
  is "cannot read".
- **The 60-second pod-removal window.** Collapsed to an instant. Conservative:
  the model can never miss a crash the real system would suffer, but it also
  cannot show an actor escaping through the window.
- **GKE.** Pool recreation after node loss, autoprovisioning, `setSize` being
  throttled or failing, node upgrades.
- **L4.** Monitoring and the JPY budget observe; they do not decide. A trace
  outside `normalOperation` is one where L4 is the only remaining control, and
  the model says nothing about whether a human reacts.
- **Money.** The awake window is bounded in minutes. Yen never appear.
- **Snapshot correctness** — that a SUSPENDED actor can actually be resumed.
- **Task TTL and image-tag GC** (plan section 3.3). Same binary, different job,
  its own retention argument.
- **IAM** and who may call what.
- **N actors.** The WorkerPool runs 2 replicas (plan Q17), so the model has 2.
  No symmetry argument is attempted.
- **Proof.** `quint run` samples traces; it is a bug finder. Apalache
  (`quint verify`) may be pointed at this file by hand and is deliberately not
  part of `just check`.

Two coverage gaps worth naming, because the numbers say so rather than the prose:
under random search the drain-ceiling path (`evidence.drainEverFailed`) is never
reached, and a clean graceful stop appears in well under 1% of traces. Both are
covered deterministically by the scripted `*Test` runs, which is where the real
coverage of `NoCrashOnGracefulSleep` comes from — not from the invariant search.

## How to run it

Quint is pinned in `config/mise/config.toml`
(`"npm:@informalsystems/quint" = "0.32.0"`), so every command goes through mise:

```sh
mise x -- quint parse      exe/spec/lease.qnt
mise x -- quint typecheck  exe/spec/lease.qnt
mise x -- quint test --max-samples=200 exe/spec/lease.qnt
mise x -- quint run exe/spec/lease.qnt \
    --invariants Safety WellFormed DrainedRecordStaysTrue \
    --max-steps=120 --max-samples=5000 --seed=0x1ea5e --verbosity=1
```

The gate runs that search with a fixed seed, so a failure it reports replays;
drop `--seed` to search elsewhere.

`--main` defaults to the module named after the file, so all four pick up
`lease`, the decided design. The rejected designs are addressed by name:

```sh
# each of these MUST fail
mise x -- quint test --main=twoWriterLease \
    --match=twoWritersLoseTheOperatorsLease exe/spec/lease.qnt
mise x -- quint test --main=naiveShrinkFirst \
    --match=shrinkingFirstCrashesTheRunningActor exe/spec/lease.qnt
mise x -- quint test --main=routerLeftOpen \
    --match=leftOpenRouterRevivesAnActorAfterDrained exe/spec/lease.qnt
```

The constants mirror is held by
`tests/unit/test_lease_constants_lockstep.py`:

```sh
uvx pytest -q tests/unit/test_lease_constants_lockstep.py
```

All of the above is wired into `just check` through `just spec-check`.

## Findings the model produced

Recorded here; all three are requirements for the Go side, not observations:

1. **`exe-wake` must refuse between the nightly cap hour and the daily stop.**
   Granting the zero-length lease that the cap leaves in that window starts a
   node and opens the router less than `cap_gap_minutes` before L3 fires, and an
   auto-resume there is crashed by L3. `wakeFor` therefore requires the capped
   deadline to be in the future, and `wakeIsRefusedInsideTheCapWindowTest` pins
   it.
2. **The atenet-router replica count has exactly one owner, L1 — including the
   restore-to-1 path.** With `wake` also scaling the router, a wake landing
   mid-drain reopens it; L1 then writes a `drained` record that an auto-resume
   immediately falsifies, and L2's graceful stop crashes the actor. The model
   found this in a few dozen steps. L1 reconciles the router itself
   (`l1OpenRouter`), and `DrainedRecordStaysTrue` is the guard against the
   regression.
3. **The idle timer is not reset by `extend`.** "Running has been zero for 30
   minutes" is modelled literally, counted from when the count started: a `wake`
   restarts it (new node, new lease), an `extend` does not, so extending a lease
   with nothing running does not keep the node up. Safe either way — re-draining
   costs a resume, never an actor — but the Go side has to match rather than
   guess.
