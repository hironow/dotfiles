# exe/spec/

Formal models of what the `exe` cluster stops or deletes on its own: the
lease-based auto-sleep (`lease.qnt`), and task retention with the image tags
that protect a live task's image (`retention.qnt`, at the end of this file).

`lease.qnt` is the design half of what
[`docs/agents/formal-methods.md`](../../ROOT_AGENTS_docs_agents_formal-methods.md)
requires for anything that stops or deletes on its own. The implementation half
— a seeded, replayable simulation of the Go reaper, and a replay of the model's
own decisions through the Go code — lives with the Go code in
`tools/exe-reaper/`, not here.

The design it models is plan section 3.2 (`docs/plan/exe-google-ax.md`). All of
its numbers come from [`../lease-constants.json`](../lease-constants.json),
which is the only place they live.

## What the model covers

| Layer | Action(s) | Property it buys |
|---|---|---|
| L0 lease (operator, Mac) | `wakeFor` / `extendFor` / `sleep` | every wake carries an expiry; the nightly cap clamps it; a successful extend beats a stale `drained`; only a wake restarts the idle clock (`wokenAt`) |
| L1 graceful drain (in-cluster CronJob, 1 min) | `l1Tick` → `l1NoOp`, `l1Reopen`, `l1Cancel`, `l1Begin`, `l1Lost`, `l1Finish`, `l1GiveUp`, `l1Resuspend`, `l1Suspend`, `l1Stall`, `l1Quiesce`, `l1Wait`, `l1Settled`; `l1Crash` | every resume path is closed before `drained`; a crash during a drain is never reported as graceful; the only pod L1 deletes hosts an actor already being deleted; the pool is never touched by L1 |
| L2 deadline enforcement (Cloud Run, 10 min) | `l2Tick` → plan section 3.2's L2 table, row for row the same as `DecideL2`, plus the idle stop and the stop-latency detector | the node stops even when the cluster is broken; one or two read failures do nothing; past deadline + 45 min nothing waits; an idle drain stops billing; a node that outlives its stop is paged |
| L3 daily stop (Cloud Scheduler → `setSize(0)`) | `l3Tick` | no logic at all, and the cap arithmetic makes that safe |
| GKE | `nodeGoneTick` | the node leaves `stop_latency_minutes` after its target went to zero, and bills until then |
| environment | `autoResume`, `rawResume`, `operatorResume`, `templateCreated`, `goldenResume`, `goldenSettles`, `checkpointDone`, `crashDetected`, `podsTerminate`, `deleteTask`, `workerPodLost`, `nodeLoss`, `leaseReadBreaks`, `leaseReadHeals` | four things wake actors, three of them without asking; checkpoints take time; pods terminate late; crashes are detected whenever they are; nodes vanish; GCS stops answering |

The three GCS objects are three state variables with exactly one writer each —
`lease` by L0, `drain` by L1, `enforce` by L2 — so "one writer per object" is a
structural property of the model, checkable by grepping for `lease' = {`,
`drain' = {` and `enforce' = {`. The router's and the controller's replica
counts have one owner too, L1.

### The drain, and why it has every step it has

1. **Begin**: the baseline of what is already CRASHED, `draining`, and the
   router to 0 replicas. Every later tick of the drain holds the router at 0
   again, because the real scale-down can fail after `draining` is written,
   and the next tick is a new process that knows only what it observes.
2. **Suspend**: AX suspends every awake task; a checkpoint takes as long as it
   takes.
3. **Quiesce**: nothing awake, so the ax-controller goes to 0 replicas. A raw
   `ax resume` bypasses the wrappers and is executed by the controller.
4. **Wait**: until both replica counts read 0 and no router or controller pod
   is left, because a pod whose count is already 0 still serves until it has
   terminated, and a count that still reads 1 brings a pod back. Also until no
   ActorTemplate is in flight, because Substrate's own reconciler, inside
   ate-api-server, resumes golden actors without asking anyone.
5. **Finish**: `drained`.

A crash since the baseline is `lost` (never `drained`), and the ceiling is
`drain-failed`. Each step that looks skippable is a rejected design below with
a run that fails.

### Invariants

`Safety` carries the six mandatory properties and nothing else:

- **`NoCrashOnGracefulSleep`**: a stop that claims to be graceful never finds
  anything awake, task actor or golden actor. This is why L1 exists.
- **`NoSilentLoss`**: a stop that claims to be graceful never follows a crash
  since its drain began. A crashed actor is not awake, so "nothing awake"
  alone would call a drain that lost an actor graceful, and nobody would be
  paged.
- **`L3NeverHitsAwakeActor`**: the nightly cap hour is **re-derived** from
  `l3_daily_stop_local_hour` and the four latency terms, and the stored
  `nightly_cap_local_hour` appears only as the thing being checked. Scoped to
  `normalOperation`: the lease was readable, the drain never failed, and the
  deadline respected the cap. Outside it, L4 alerting is the control, not
  arithmetic.
- **`NodesEventuallyZero`**: bounded **billing**, written as a safety property.
    - Quint has no fairness, so "eventually" cannot be stated as a temporal
      formula. The model makes the scheduled events the only thing that moves
      the clock: the ticks, and the node actually leaving. An event fires only
      when it is the earliest one. "Eventually" then becomes arithmetic about the
      clock.
    - `cluster.nodes` counts billing instances, not the target size (inbox M18).
    - Two bounds, both re-derived from the constants: `awake_bound_minutes` is
      the plan's `deadline + 45 + 10` plus `stop_latency_minutes`, and holds
      while L2's last read of `lease.json` succeeded. `blind_awake_bound_minutes`
      adds `lease_read_failure_threshold - 1` L2 ticks and holds regardless.
    - The seeded simulation checks the same two numbers, taken from
      `lease.AwakeBound` and `lease.BlindAwakeBound`.
- **`ExtendBeatsStaleDrained`**: no stop taken from a lease L2 could read lands
  before the deadline the operator was granted. The only exception is L2's
  idle stop about the current lease, which is the plan's rule.
- **`ClearingNeverLosesState`**: the only pod L1 deletes on its own, a wedged
  actor's worker, never hosts anything awake or mid-checkpoint.

Three more are checked beside `Safety` rather than inside it:

- **`DrainedRecordStaysTrue`**: the lemma `NoCrashOnGracefulSleep` rests on.
  While a `drained` record exists, no router or controller pod is left, no
  template is in flight, and nothing is awake. Checked separately so a
  regression points at the cause instead of the symptom.
- **`SlowStopIsPaged`**: not a design property but one of its detection. A node
  still billing two L2 ticks after its target went to zero has raised the
  alarm. It holds vacuously in the decided design; `pdbHoldsTheDrain` is where
  it is checked.
- **`WellFormed`**: not a design property. It checks that the model is not
  lying: the actor states partition the actors, nothing is awake without a
  live node, and the clock does not run backwards.

### Rejected designs, kept as failing runs

Seven instances of `leaseCore`, each with a header comment recording its
scope, who accepted the decision, and the compensating control. Each has one
named run that **fails**; that is the deliverable, not a defect:

| Module | Named run | Invariant the run breaks |
|---|---|---|
| `twoWriterLease` | `twoWritersLoseTheOperatorsLease` | `ExtendBeatsStaleDrained` |
| `naiveShrinkFirst` | `shrinkingFirstCrashesTheRunningActor` | `NoCrashOnGracefulSleep` |
| `routerLeftOpen` | `leftOpenRouterRevivesAnActorAfterDrained` | `NoCrashOnGracefulSleep` |
| `controllerLeftUp` | `controllerLeftUpLetsARawResumeThrough` | `NoCrashOnGracefulSleep` |
| `scaleIsNotABarrier` | `scaleAloneLetsALingeringControllerResume` | `NoCrashOnGracefulSleep` |
| `goldenIgnored` | `goldenReconcilerResumesAfterDrained` | `NoCrashOnGracefulSleep` |
| `pdbHoldsTheDrain` | `aDisruptionBudgetOutlivesTheBound` | `NodesEventuallyZero` |

Each run breaks exactly that invariant and no other `Safety` clause. That was
checked by rewriting each run's expectation to "this one false, the rest true",
which passes.

None of these names end in `Test`, so `quint test` skips them and the gate stays
green. They are run explicitly; see below. `pdbHoldsTheDrain` also carries a
passing run, `theSlowStopIsPagedTest`: on the same instance, L2's stop-latency
detector raises the alarm before the bound breaks.

The barrier variants are also why `DrainedRecordStaysTrue` is checked at all.
Random search finds that lemma broken in each of them in under a second, but a
sampling checker seldom reaches the crash itself: the trace needs a specific
interleaving (drain completes, something wakes, L2's tick lands next). The
scripted runs and the lemma are what find it.

### Recorded behaviour, replayed

The `*Test` runs in the `lease` module are the behaviours plan section 3.2,
the Phase 3 and Phase 6 e2e lists, and the review notes name. They are scripted
so they replay deterministically rather than being sampled:

- **L0 and the cap**: the cap clamping an 8-hour request, and `exe-wake`
  refusing inside the cap window.
- **The graceful path**: a graceful `exe-sleep` losing nothing, and a slow
  checkpoint that still drains.
- **Idle**:
    - the idle drain stopping billing before the deadline;
    - `exe-sleep` after an idle drain staying graceful;
    - an extend not restarting the idle clock;
    - a wake after an idle stop reopening both paths.
- **Resume paths**:
    - a raw resume during a drain (suspended again, the 6.9 e2e's first
      boundary);
    - no resume path after `drained` (its second boundary);
    - golden work being waited for.
- **No silent loss**: a pod lost mid-checkpoint paging, and a crash between two
  L1 polls paging.
- **Stale records**: an extend invalidating `drained`, and a stale `drained`
  forcing instead of stopping gracefully.
- **L2's read failures and forced paths**: one and two read failures doing
  nothing, the third forcing, a stale heartbeat forcing, and the drain ceiling
  forcing.
- **L3 and the environment**:
    - L3 springing on an asleep pool;
    - node loss not counting as a graceful stop;
    - a wedged delete being cleared.

The `l2Table*Test` runs walk the L2 table at its boundaries, one tick each from
a world built by `l2WorldAt`:

- past the grace a fresh heartbeat buys nothing, exactly at it it still does;
- with no drain record about the lease, L2 waits exactly one heartbeat window
  after the deadline and forces a minute later;
- `drained` is a graceful stop even past the grace;
- before the deadline only an idle `drained` about this lease stops the pool;
- a carried read-failure run resets while the target is zero;
- the stop-latency detector remembers, then alarms.

### The two decisions, replayed through the Go code

The L2 rule and the L1 tick are each written twice, as the model's branches and
as `DecideL2` / `DecideL1` in `tools/exe-reaper/internal/lease/`. Two encodings
of one design stay equal only if something compares them.

- `l2World` builds a random row of the L2 table, and `l2WorldStep` either
  re-rolls it or takes the tick that decides it. The rows sit on both sides of
  every boundary the rule has: deadline and heartbeat ages, lease readable or
  not, a carried read-failure run, each drain state and reason about this lease
  generation or an older one, and the pool live, stopping or gone.
- `l1World` builds a random L1 observation: every actor in every state, the
  idle clock and the wake around their boundary, a baseline, wedges, golden
  work, and every combination of replica counts and pods. A third of the worlds
  are tidied into a barrier that holds, so `drained` is sampled often.

`just spec-check` samples 200 L2 and 300 L1 traces as ITF into a fresh
directory and runs `TestDecideL2AgreesWithTheModel` and
`TestDecideL1AgreesWithTheModel` (`tools/exe-reaper/internal/lease/model_replay_test.go`).
Every tick is replayed through the Go decision, which must:

- take the branch the model took (the model's `l1Stall` is the same decision
  as `l1Suspend`: whether AX acts is the environment's business);
- for L2, carry the same read-failure run and stop exactly when the model did,
  and its detector must remember and alarm exactly as the model's does;
- for L1, write the same `drain.json`, the same replica counts, the same
  suspends and the same pod deletions.

Each test also fails unless every one of the model's branches was reached. Its
teeth were checked by planting three bugs in `DecideL1` (no pod wait, no loss
check, clearing a checkpointing actor's pod), each of which the replay fails.

Without the directories, a plain `go test` skips both.

## What the model deliberately does not cover

Read no invariant as covering any of this:

- **Real time.** One global clock in abstract minutes: no dates, no zone, no
  skew between the Mac, the CronJob and the Cloud Run job, and no scheduler
  jitter beyond "a tick happens no later than its period".
- **GCS semantics.** Reads are strongly consistent, and a
  generation-precondition write either lands or fails. The only failure
  modelled is "cannot read".
- **How soon a crash is detected.** The store keeps saying RUNNING for an actor
  whose pod is gone until a workflow or the worker syncer notices, and the
  source has no bound on that. `crashDetected` may happen at any moment, late,
  or never, and no property relies on it.
- **The stop latency itself.** `stop_latency_minutes` is an assumption measured
  on the real stack (3m29s, 3m31s and 3m32s with the full stack after the
  budget fix). `NodesEventuallyZero` holds only under it, `pdbHoldsTheDrain`
  shows it breaking, and L2's detector is the control that notices. A forced
  stop with a guest ignoring SIGTERM can also exceed it (the ateom's workload
  grace is 30 min); that is detected, not prevented.
- **Direct callers of Substrate's Control API**, which authenticates but does
  not authorize. The model assumes only the system components modelled here
  resume actors, and the e2e probes that a task cannot reach it.
- **Pagination.** L1's observations are snapshots. The Go side reads lists page
  by page while they change, and compensates by counting a row missing from
  the baseline as lost.
- **GKE** beyond the stop latency: pool recreation after node loss,
  autoprovisioning, `setSize` being throttled or failing, node upgrades.
- **L4.** Monitoring and the JPY budget observe; they do not decide.
- **Money.** The billing window is bounded in minutes. Yen never appear.
- **Snapshot correctness**: that a SUSPENDED actor can actually be resumed.
- **Task TTL and image-tag GC** (plan section 3.3). Same reaper, a different
  job, with its own model: `retention.qnt`, below.
- **IAM** and who may call what.
- **N actors.** The WorkerPool runs 2 replicas (plan Q17), so the model has 2.
  Golden actors are one flag, not a set. No symmetry argument is attempted.
- **Actors sharing a worker.** Each modelled actor has a worker of its own, so
  clearing a wedge can only ever take that one actor. A Substrate worker can
  host several, and deleting its pod takes them all, so the Go side clears a
  worker only when every actor on it is a ripe wedge
  (`TestDecideL1NeverClearsAWorkerThatAlsoHostsALiveActor`).
- **Proof.** `quint run` samples traces; it is a bug finder. Apalache
  (`quint verify`) may be pointed at this file by hand, and it is deliberately
  not part of `just check`.

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
mise x -- quint test --main=controllerLeftUp \
    --match=controllerLeftUpLetsARawResumeThrough exe/spec/lease.qnt
mise x -- quint test --main=scaleIsNotABarrier \
    --match=scaleAloneLetsALingeringControllerResume exe/spec/lease.qnt
mise x -- quint test --main=goldenIgnored \
    --match=goldenReconcilerResumesAfterDrained exe/spec/lease.qnt
mise x -- quint test --main=pdbHoldsTheDrain \
    --match=aDisruptionBudgetOutlivesTheBound exe/spec/lease.qnt
# and this one must pass
mise x -- quint test --main=pdbHoldsTheDrain \
    --match=theSlowStopIsPagedTest exe/spec/lease.qnt
```

The replays by hand, into a fresh directory:

```sh
traces="$(mktemp -d)"
mise x -- quint run exe/spec/lease.qnt --init=l2World --step=l2WorldStep --max-steps=30 \
    --max-samples=200 --n-traces=200 --seed=0x1ea5e --verbosity=0 \
    --out-itf="$traces/l2_{seq}.itf.json"
mkdir "$traces/l1"
mise x -- quint run exe/spec/lease.qnt --init=l1World --step=l1WorldStep --max-steps=6 \
    --max-samples=300 --n-traces=300 --seed=0x1ea5e --verbosity=0 \
    --out-itf="$traces/l1/l1_{seq}.itf.json"
(cd tools/exe-reaper && EXE_REAPER_L2_TRACES="$traces" EXE_REAPER_L1_TRACES="$traces/l1" \
    mise x -- go test ./internal/lease/ -run 'AgreesWithTheModel' -v)
```

The constants mirror is held by
`tests/unit/test_lease_constants_lockstep.py`:

```sh
uvx pytest -q tests/unit/test_lease_constants_lockstep.py
```

Everything above but that pytest runs in `just check`, through
`just spec-check`; the pytest runs with the other unit tests in `just ci`.

## retention.qnt: the task TTL and the image tags

Two things delete here with nobody watching (Phase 6 plan D10): L1 deletes an
AX task that has sat SUSPENDED for `task_ttl_days` unless the operator kept it
(`just exe-keep`), and Artifact Registry deletes a task image older than 14 days
unless it carries an `inuse-` tag. What goes wrong is a delete that lands on
something still wanted: a task before its time, or the image a live task needs
at its next resume. Every wake is a fresh node, so a resume pulls the image
again.

The decided mechanisms:

- **TTL** counts from the Substrate store's `update_time` for the task's actor,
  which every write moves: a resume and a re-suspend move it whether or not an
  L1 tick saw them. L1 runs only with a node up, so a task is "deleted at the
  first wake after 30 days".
- **L1's tags.** L1 tags every digest a live task references `inuse-<sha12>`,
  and releases that tag once the digest has been unreferenced for
  `tag_release_days`, counted in `tasks.json` from the first tick that saw it
  so.
- **ax-job's tag** is its own and dated, `inuse-<sha12>-<unix>`, created before
  the task is applied. L1 releases it once its name says it is
  `tag_release_days` old, never by a record.

Invariants (`Retention`):

- **`NoLiveImageCollected`**: AR never collects the image of a protected live
  task (created through ax-job, or seen by an L1 tick).
- **`TtlDeletesOnlyTheExpired`**: a task L1 deletes has really been SUSPENDED
  for `task_ttl_days`, and is not kept.
- **`ProtectedImagesAreTagged`**: every protected live task's image carries a
  tag right now.
- **`TtlNeverMissed`**, the liveness half: every L1 tick at or past a task's
  TTL (SUSPENDED and untouched for `task_ttl_days`, not kept) deletes it.
  Safety alone is satisfied by a TTL that never fires, which is unbounded
  storage. The model's time is bounded, so this is a bounded response rather
  than a temporal formula `quint run` could not check.

Rejected designs, each a named run that must fail:

| Module | Run | What breaks |
|---|---|---|
| `sharedJobTag` | `sharedTagLetsAFreshTasksImageBeCollected` | ax-job tags the shared `inuse-<sha12>`; a tick between its tag and its apply reads a weeks-old "unreferenced since" and releases the tag, and AR collects the new task's image |
| `ttlByFirstSight` | `firstSightDeletesATaskUsedYesterday` | the TTL counts from L1's first sight of the task suspended; a resume and re-suspend between two ticks are invisible, and a task used yesterday is deleted as a month old |
| `backgroundWriteRefreshes` | `aBackgroundWriteKeepsATaskForever` | not a design: the TTL clock's assumption broken. Something rewrites a SUSPENDED actor's row now and then, update_time never ages, and the TTL never fires (`TtlNeverMissed`) |

The TTL clock rests on that assumption: nothing writes a SUSPENDED actor's row
in the background. At the pinned Substrate (672533541dbf) it holds. Every
actor write goes through `store.UpdateActor`: the one `UPDATE actors` is
`cmd/ateapi/internal/store/atepg/atepg.go:709`, beside the create (`:636`)
and the delete (`:754`). Its callers in `cmd/ateapi/internal/controlapi/`
are:

- `workflow_suspend.go:152` marks SUSPENDING, from RUNNING or PAUSED only, and
  `:425` commits SUSPENDED. A suspend of an actor already SUSPENDED returns at
  `:68` without writing, which matters because the ax-controller calls
  SuspendActor on every reconcile of a suspended task.
- `workflow_resume.go:266`, `:271`, `:533` and `:803` resume. That is a real
  use, and it should restart the TTL.
- `workflow_pause.go:135` and `:274` pause, from RUNNING.
- `workflow_delete.go:293` and `:336` delete: the TTL's own action, or the
  operator's.
- `crash.go:94` (`crashActor`) is reached only from inside the suspend,
  resume and pause workflows: `crash.go:54`, `workflow_pause.go:162` and
  `:172`, `workflow_resume.go:355`, `:365`, `:376`, `:389` and `:407`,
  `workflow_suspend.go:215`, `:225` and `:283`.
- `workflow_worker_delete.go:213` releases actors from a dead worker, and skips
  a SUSPENDED one just above it ("suspended cleanly before the pod went away").
- `actor.go:256` and `:279` are the client-facing UpdateActor. AX v0.3.1 never
  calls it, and its reconciles are event-driven (`internal/controller/worker.go`
  subscribes to task events; there is no periodic resync).

Background loops checked for actor writes, none found:
`cmd/atecontroller/internal/workersync/syncer.go` (DeleteWorker, which goes
to the worker-delete workflow above), `controlapi/template_reconciler.go`
(templates, and golden actors in `ate-golden` only), `store/atepg/outbox.go`,
`cmd/ateapi/internal/workercache`, atelet's `imagegc.go` and
`systeminfovolume.go`, and atenet's router `health.go` and `envoydrain.go`. A
Substrate upgrade re-opens this list. The model's
`backgroundWriteRefreshes` shows what breaks if it grows.

Time is whole days, and L1's ticks, AR's cleanup and the operator's commands
interleave freely inside one: coarser than reality, so any order the real
system can produce, the model can too. Outside it: a raw `ax apply` of an
untagged image older than 14 days with AR's cleanup landing before L1's next
tick (ax-job is the supported path), keep.json edits racing L1's read,
platform images (the same tags over different references), and snapshot
objects (the operator-run snapshot GC, plan D11).

```sh
mise x -- quint test --max-samples=200 exe/spec/retention.qnt
mise x -- quint run exe/spec/retention.qnt --invariants Retention \
    --max-steps=150 --max-samples=3000 --seed=0x1ea5e --verbosity=1
# each of these MUST fail
mise x -- quint test --main=sharedJobTag \
    --match=sharedTagLetsAFreshTasksImageBeCollected exe/spec/retention.qnt
mise x -- quint test --main=ttlByFirstSight \
    --match=firstSightDeletesATaskUsedYesterday exe/spec/retention.qnt
mise x -- quint test --main=backgroundWriteRefreshes \
    --match=aBackgroundWriteKeepsATaskForever exe/spec/retention.qnt
```

The random search finds all three rejected instances' violations within a
second or so on the same seed, and none in the decided one: the search reaches
the states that matter.

The Go half is `DecideRetention` (`tools/exe-reaper/internal/lease/retention.go`).
`TestSimulationRetention*` runs it through this model's environment on 200 fixed
seeds, checks the three invariants on the Go state after every step, and
requires TTL deletions, releases and collections to occur. The same sweep with
ax-job tagging the shared `inuse-<sha12>` must find a violation, and so must
one with a background writer refreshing suspended actors (a missed TTL);
both do.
`EXE_REAPER_RETENTION_SEED=<seed>` replays one seed.

## Findings the model produced

Recorded here. All of them are requirements for the Go side, not observations:

1. **`exe-wake` must refuse between the nightly cap hour and the daily stop.**
   Granting the zero-length lease that the cap leaves in that window starts a
   node and opens the router less than `cap_gap_minutes` before L3 fires, and an
   auto-resume there is crashed by L3. `wakeFor` therefore requires the capped
   deadline to be in the future, and `wakeIsRefusedInsideTheCapWindowTest` pins
   it.
2. **The atenet-router's and ax-controller's replica counts have exactly one
   owner, L1, including the restore-to-1 path.** With `wake` also scaling the
   router, a wake landing mid-drain reopens it. L1 then writes a `drained`
   record that an auto-resume immediately falsifies, and L2's graceful stop
   crashes the actor. The model found this in a few dozen steps. L1 reconciles
   both itself (`l1Reopen`), and `DrainedRecordStaysTrue` is the guard against
   the regression.
3. **The idle clock is restarted by `wake`, not by `extend`.** "Running has
   been zero for 30 minutes" counts from the later of L1's first idle tick and
   the lease's `wokenAt`, which only `wake` writes. Extending a lease with
   nothing running does not keep the node up. It is safe either way:
   re-draining costs a resume, never an actor.
4. **Closing the router is not enough (Phase 6).** A raw `ax resume` and
   Substrate's golden reconciler each wake actors without the router. A replica
   count of 0 does not stop the pod that is still terminating. Each gap is a
   rejected design above, and the drain waits for all of them.
5. **An idle `drained` before the deadline must stop billing, and a stale
   `drained` must be drained again (Phase 3 review notes).** Without the idle
   stop, L2 billed on to the deadline. Without the re-drain, `exe-sleep` after
   an idle drain left L1 settled on the old record and L2 forcing a page.
6. **ax-job's tag must be its own, dated by its name (retention.qnt, Phase 6).**
   The plan had ax-job put the shared `inuse-<sha12>` on the image before it
   applies the task. L1 releases that tag by its own "unreferenced since"
   record, which can be weeks old for an image being reused, so a tick between
   ax-job's tag and its apply released it, and AR collected the new task's
   image. `sharedJobTag` keeps the failing run.
7. **The TTL counts from the store's update_time, not from L1's first sight
   (retention.qnt, Phase 6).** L1 only sees what is there when it ticks; a
   resume and a re-suspend between two ticks would leave a first-sight clock
   running, and a task used yesterday would be deleted as a month old.
   `ttlByFirstSight` keeps the failing run.
