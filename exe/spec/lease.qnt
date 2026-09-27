// -*- mode: quint -*-
//
// lease.qnt -- the lease-based auto-sleep of the `exe` GKE cluster.
//
// WHY THIS FILE EXISTS
//
// The `exe` cluster is a single-node pool that must be asleep by default and is
// woken only with an expiry attached. Three independent things are allowed to
// take that node away on their own, and four more things are allowed to wake an
// actor without asking anyone: the atenet router on a connection, the
// ax-controller executing a raw `ax resume`, Substrate's own golden-template
// reconciler, and the operator through the wrappers. "Deletes or releases on
// its own" is exactly the trigger in docs/agents/formal-methods.md, so the
// design carries a model and the Go reaper carries a seeded simulation of the
// same state machine. This is the model half.
//
// The thing that actually goes wrong here is never "the node did not stop". It
// is ORDER: the pool shrinks while an actor is still awake, and the actor is
// CRASHED instead of SUSPENDED -- state lost, snapshot never taken, and the
// operator's next `ax resume` finds nothing. The second thing is SILENCE: a
// crash that happened during a drain must never be reported as a graceful
// stop. The third is MONEY: a stop decision is not a stopped node; the node
// bills until it is actually gone. Every invariant below is a statement about
// order, silence or a bound, never about liveness alone.
//
// LAYERS -> ACTIONS
//
//   L0  lease (operator, on the Mac)      wake / extend / sleep
//                                         (+ rogueLeaseWrite: the second
//                                          writer the design forbids)
//   L1  graceful drain (in-cluster        l1Tick / l1Crash
//       CronJob, every minute)            -> l1NoOp, l1Reopen, l1Cancel,
//                                            l1Begin, l1Lost, l1Finish,
//                                            l1GiveUp, l1Resuspend,
//                                            l1Suspend, l1Stall,
//                                            l1Quiesce, l1Wait, l1Settled
//   L2  deadline enforcement (Cloud Run   l2Tick
//       job, every 10 min)                -> the table in plan section 3.2,
//                                            plus the idle stop and the
//                                            stop-latency detector
//   L3  daily stop (Cloud Scheduler ->    l3Tick   (no logic at all, on purpose)
//       GKE setSize(0), 04:00 local)
//   L4  detection (Monitoring + budget)   NOT MODELLED -- it observes, it does
//                                         not decide. See "outside" below.
//
//   GKE                                   nodeGoneTick (the node actually
//                                         leaves, stop_latency after setSize)
//   environment                           nodeLoss, leaseReadBreaks,
//                                         leaseReadHeals, autoResume,
//                                         rawResume, operatorResume,
//                                         templateCreated, goldenResume,
//                                         goldenSettles, checkpointDone,
//                                         crashDetected, podsTerminate,
//                                         deleteTask
//
// ONE WRITER PER OBJECT
//
// The three GCS objects are three state variables, and each is written by
// exactly one action family -- that is the design rule, and here it is a
// structural property of the model rather than a comment: `lease` is only ever
// assigned a new value by the L0 actions, `drain` only by l1Tick, `enforce`
// only by l2Tick. Everything else frames them with `x' = x`. A reviewer can
// check the rule by grepping for `lease' = {`, `drain' = {`, `enforce' = {`.
// The replica counts of atenet-router and ax-controller have one owner too,
// L1: only l1Tick assigns routerReplicas or controllerReplicas.
//
// THE CLOCK IS ABSTRACT
//
// `clock.now` is minutes since the start of the modelled window -- not a real
// timestamp, no dates, no time zone. The window ends at HORIZON. The clock only
// ever moves inside a tick action, and a tick may only fire when it is the
// EARLIEST scheduled event. The node actually leaving is one of those
// scheduled events: stop_latency minutes after the pool's target went to zero.
// That single rule is what lets a bounded-time claim about BILLING be written
// as a safety property (see NodesEventuallyZero).
//
// OUTSIDE THE MODEL'S GUARANTEE (do not read an invariant as covering these)
//
//   * Real time. One global clock: no skew between the Mac, the in-cluster
//     CronJob and the Cloud Run job, and no scheduler jitter beyond "a tick
//     happens no later than its period".
//   * GCS semantics. Reads are strongly consistent and a generation-precondition
//     write either lands or fails; the only failure modelled is "cannot read".
//   * How soon a crash is DETECTED. When a worker pod goes away, the store keeps
//     saying RUNNING until a workflow or the worker syncer notices (the source
//     has no bound on that). The model lets detection happen at any moment,
//     never, or late, and no property relies on it.
//   * The stop latency itself. stop_latency_minutes is an ASSUMPTION, measured
//     on the real stack (setSize(0) -> no node: 3m29s, 3m31s, 3m32s with the
//     full stack after the budget fix). NodesEventuallyZero holds only under
//     it; the pdbHoldsTheDrain instance shows that it breaks when a
//     disruption budget holds the drain, and L2's stop-latency detector is
//     the control that notices. A forced stop with an actor awake whose guest
//     ignores SIGTERM can also exceed it (the ateom's workload grace is 30
//     min); that is detected by the same detector, not prevented.
//   * Direct callers of Substrate's Control API. It authenticates but does not
//     authorize, so any pod that can mint a token for its audience could resume
//     an actor. The model assumes only the system components modelled here
//     do; the e2e probes that a task cannot.
//   * Pagination. Every observation L1 makes is a snapshot. The Go side reads
//     lists page by page while they change, and compensates by counting a row
//     missing from the baseline as lost (the conservative direction).
//   * L4. Alerting and the JPY budget are detection, not control flow. A trace
//     that leaves normalOperation is a trace where L4 is the only remaining
//     control, and the model says nothing about whether the human reacts.
//   * Money. The model bounds the billing window in minutes; yen never appear.
//   * Snapshot correctness -- that a SUSPENDED actor can actually be resumed.
//   * Task TTL and image-tag GC (plan section 3.3). Same reaper, different job,
//     their own model: exe/spec/retention.qnt.
//   * IAM, Workload Identity, and who is allowed to call what.
//   * Two actors, not N. The WorkerPool runs 2 replicas (plan Q17), so the
//     model has 2; a symmetry argument is not attempted. Golden actors are
//     one flag, not a set.
//   * `quint run` samples traces. It is a bug finder, not a proof. Apalache
//     (`quint verify`) may be pointed at this file by hand and is deliberately
//     NOT part of `just check`.
//
// CONSTANTS
//
// Every number below is mirrored from exe/lease-constants.json, which is the
// only place they live. tests/unit/test_lease_constants_lockstep.py holds the
// mirror equal and re-derives the cap formula. Do not edit a number here.

module leaseCore {
  // --------------------------------------------------------------------------
  // Design-variant switches.
  //
  // Instantiated `false` (and the stop latency the design assumes) by the
  // `lease` module at the bottom of this file -- the design as decided. Each
  // other instantiation is one of the designs that was considered and
  // rejected, kept as a named run that FAILS, so the reason for the rejection
  // stays executable instead of becoming folklore.
  // --------------------------------------------------------------------------

  /// lease.json has a second writer that does not hold the generation
  /// precondition (`twoWriterLease`).
  const two_writer_lease: bool

  /// L1 shrinks the node pool as the first step of the drain, before anything
  /// is suspended (`naiveShrinkFirst`).
  const naive_shrink_first: bool

  /// L1 leaves the atenet router serving while it drains, so a connection can
  /// auto-resume an actor behind the drain's back (`routerLeftOpen`).
  const router_left_open: bool

  /// L1 leaves the ax-controller running when it writes `drained`, so a raw
  /// `ax resume` is still executed (`controllerLeftUp`).
  const controller_left_up: bool

  /// L1 takes a replica count of 0 as proof that the pod is gone, instead of
  /// waiting until no pod is left (`scaleIsNotABarrier`).
  const scale_is_barrier: bool

  /// L1 ignores Substrate's golden-template reconciler, which resumes golden
  /// actors on its own (`goldenIgnored`).
  const golden_ignored: bool

  /// How long the node really takes to leave after setSize(0). The decided
  /// design runs with the measured stop_latency_minutes; `pdbHoldsTheDrain`
  /// runs with a disruption budget holding the drain for an hour.
  const stop_latency_actual: int

  // --------------------------------------------------------------------------
  // Constants -- mirrored from exe/lease-constants.json. Snake_case on purpose:
  // the names ARE the JSON keys, and the lockstep test parses them out of this
  // text.
  // --------------------------------------------------------------------------

  pure val default_lease_minutes = 60
  pure val max_lease_minutes = 480
  pure val l1_tick_minutes = 1
  pure val drain_ceiling_minutes = 30
  pure val l2_tick_minutes = 10
  pure val slack_minutes = 19
  pure val l3_daily_stop_local_hour = 4
  pure val nightly_cap_local_hour = 3
  pure val force_grace_minutes = 45
  pure val heartbeat_stale_ticks = 2
  pure val idle_zero_running_minutes = 30
  pure val lease_read_failure_threshold = 3
  pure val stop_latency_minutes = 5
  pure val wedge_clear_minutes = 10

  pure val minutes_per_hour = 60

  // --------------------------------------------------------------------------
  // Derived constants. These are the whole point of keeping the numbers in one
  // file: each is recomputed here, never restated.
  // --------------------------------------------------------------------------

  /// The worst-case time from "the lease expired" to "the pool is at zero":
  /// L1 notices within one tick, the graceful drain is allowed its ceiling, L2
  /// acts within one of its own ticks, and the rest is deliberate slack. The
  /// slack also covers the stop latency: L3 needs no actor to be AWAKE when it
  /// fires, not the node to be gone.
  pure val cap_gap_minutes =
    l1_tick_minutes + drain_ceiling_minutes + l2_tick_minutes + slack_minutes

  /// The nightly cap hour, RE-DERIVED. Nothing downstream reads
  /// nightly_cap_local_hour except the invariant that compares the two.
  pure val nightly_cap_from_formula =
    l3_daily_stop_local_hour - cap_gap_minutes / minutes_per_hour

  /// "The heartbeat is stale" in wall-clock minutes: heartbeat_stale_ticks is
  /// counted in L2 ticks, and L2's tick is l2_tick_minutes long.
  pure val heartbeat_stale_minutes = heartbeat_stale_ticks * l2_tick_minutes

  /// The plan's bound (section 3.2, "期限 + 45 分 + L2 の周期 10 分"), plus the
  /// time the node takes to actually leave once the pool's target is zero
  /// (inbox M18, layer 2: bounds are measured in billing, not in decisions).
  /// force_grace_minutes is when L2 stops waiting for anything at all, one
  /// l2_tick_minutes covers the scheduler's phase, and stop_latency_minutes is
  /// the measured drain of the node. It holds while L2 can READ the lease.
  pure val awake_bound_minutes =
    force_grace_minutes + l2_tick_minutes + stop_latency_minutes

  /// The same bound when L2 cannot read the lease. The three-strike rule
  /// forbids forcing on the first lease_read_failure_threshold - 1 misses
  /// however late they come, so the first tick past the grace can be followed
  /// by that many more before the blind stop.
  pure val blind_awake_bound_minutes =
    awake_bound_minutes + l2_tick_minutes * (lease_read_failure_threshold - 1)

  /// End of the modelled window. One local day is more than enough: the latest
  /// L3 offset below is 10 hours.
  pure val HORIZON = 24 * minutes_per_hour

  /// "This layer has nothing scheduled." Bigger than any reachable clock value.
  pure val NEVER = 100 * HORIZON

  /// The task actors that can exist at once = the WorkerPool replica count
  /// (plan Q17), one actor per worker (Substrate internal/ateomcapacity:
  /// actorsPerAteom = 1).
  pure val ACTORS = Set(1, 2)

  /// How far the daily 04:00 stop is from the start of the modelled window --
  /// i.e. what local time the window starts at. Four choices, so the nightly
  /// cap binds differently in each:
  ///   cap_gap_minutes                          03:00 -- the cap has just gone
  ///   2 * cap_gap_minutes                      02:00 -- it clamps a short lease
  ///   l3_daily_stop_local_hour * 60            00:00 -- it clamps the max lease
  ///   10 * 60                                  18:00 -- only the max lease is clamped
  pure val L3_OFFSETS = Set(
    cap_gap_minutes,
    2 * cap_gap_minutes,
    l3_daily_stop_local_hour * minutes_per_hour,
    10 * minutes_per_hour,
  )

  /// Lease lengths the operator can ask for. The last one is over the maximum
  /// and must be refused -- that is what keeps the `max_lease_minutes` guard
  /// from being dead code.
  pure val LEASE_REQUESTS = Set(
    0,
    l2_tick_minutes,
    default_lease_minutes,
    max_lease_minutes,
    max_lease_minutes + l2_tick_minutes,
  )

  // --------------------------------------------------------------------------
  // State
  // --------------------------------------------------------------------------

  /// L1's record in drain.json. `DrainNone` is "no drain in flight".
  type DrainState =
    | DrainNone
    | Draining
    | Drained
    | DrainFailed

  /// Why L1 began the drain it records. Only an idle drain may stop the pool
  /// before the lease's deadline (L2's idle row).
  type DrainReason =
    | NoReason
    | DeadlinePassed
    | IdleZeroRunning
    | LeaseUnreadable

  /// L2's last decision, recorded in enforce.json so `exe-status` can show what
  /// the enforcer did without a cluster credential.
  type Decision =
    | NoDecision
    | AlreadyStopped
    | LeaseLive
    | WaitedForDrain
    | WaitedOnReadFailure
    | StoppedOnDrained
    | StoppedOnIdleDrained
    | StoppedForced
    | StoppedOnReadFailures

  /// What took the pool's target to zero. Only `GracefulStop` promises an
  /// empty cluster; the rest are allowed to crash an actor, and say so.
  type Shrink =
    | NoShrink
    | GracefulStop
    | ForcedStop
    | DailyStop
    | NodeGone

  /// lease.json. `granted` is what the operator was told they have; in the
  /// decided design it is always equal to `deadline`, and the two only come
  /// apart when a second writer exists. `gen` is the GCS generation the
  /// precondition writes turn on. `wokenAt` is written by `wake` and copied by
  /// every other L0 write: it is what restarts L1's idle clock on a new node
  /// and on nothing else.
  type Lease = {
    deadline: int,
    gen: int,
    granted: int,
    readable: bool,
    wokenAt: int,
  }

  /// drain.json. `leaseGen` is the lease generation this record is ABOUT, which
  /// is how a reader tells a fresh `drained` from one that predates an extend.
  /// `idleSince` is the first L1 tick that saw nothing awake (-1: something
  /// is), carried here because L1 is a CronJob with no memory between runs.
  /// `baselineCrashed` is the actors that were already CRASHED when the drain
  /// began: any other crash before `drained` is a loss. `wedgeSeen` maps each
  /// actor stuck in DELETING to the tick L1 first saw it so.
  type Drain = {
    state: DrainState,
    heartbeat: int,
    startedAt: int,
    leaseGen: int,
    reason: DrainReason,
    idleSince: int,
    baselineCrashed: Set[int],
    wedgeSeen: int -> int,
  }

  /// enforce.json, plus L2's consecutive-read-failure counter and the
  /// stop-latency detector's memory: the first tick that saw the pool's
  /// target at zero with the node still there (-1: none).
  type Enforce = {
    last: Decision,
    gen: int,
    notified: bool,
    leaseReadFailures: int,
    stoppingSince: int,
    stopLatencyAlarm: bool,
  }

  /// The cluster.
  ///
  /// `nodes` is the number of BILLING instances, 0 or 1. `stopping` means the
  /// pool's target is zero but the node has not left yet: it still bills, and
  /// nothing on it runs any more.
  ///
  /// Task actors, as Substrate's store sees them, partition ACTORS:
  ///   awake          RUNNING (or RESUMING, PAUSING, PAUSED -- anything with
  ///                  a live sandbox)
  ///   checkpointing  SUSPENDING: a suspend is in progress, and slow
  ///   doomed         the worker pod is gone but the store still says RUNNING
  ///                  or SUSPENDING, until a crash is detected
  ///   crashed        CRASHED: state lost
  ///   deleting       DELETING and stuck, still holding a worker (the Phase 4
  ///                  wedge: TerminateWorkload failing forever)
  ///   gone           deleted
  ///   (the rest)     SUSPENDED
  ///
  /// `goldenAwake` is a golden actor in ate-golden with a live sandbox, and
  /// `templatePending` an ActorTemplate whose golden snapshot is neither
  /// written nor failed: Substrate's reconciler resumes golden actors for it.
  ///
  /// `routerReplicas` / `controllerReplicas` are what L1 set (they outlive the
  /// node); `routerPod` / `controllerPod` say whether a pod is actually
  /// running (a scale-down takes effect only when podsTerminate happens).
  type Cluster = {
    nodes: int,
    stopping: bool,
    awake: Set[int],
    checkpointing: Set[int],
    doomed: Set[int],
    crashed: Set[int],
    deleting: Set[int],
    gone: Set[int],
    goldenAwake: bool,
    templatePending: bool,
    routerReplicas: int,
    controllerReplicas: int,
    routerPod: bool,
    controllerPod: bool,
    reaperAlive: bool,
  }

  /// The discrete-event clock. `l1Due` / `l2Due` are the next scheduled tick of
  /// each layer; `l3At` is the single daily stop; `nodeGoneDue` is when the
  /// stopping node leaves.
  type Clock = {
    now: int,
    l1Due: int,
    l2Due: int,
    l3At: int,
    l3Fired: bool,
    nodeGoneDue: int,
  }

  /// Ghost state. Nothing reads it; it exists so the invariants can be written
  /// about events rather than about the current instant, and every flag is
  /// monotone so a later action cannot mask an earlier violation.
  type Evidence = {
    lastShrink: Shrink,
    gracefulCrash: bool,
    silentLoss: bool,
    l3HitAwakeActor: bool,
    stoppedDespiteLiveLease: bool,
    drainEverFailed: bool,
    leaseEverUnreadable: bool,
    clearedLiveActor: bool,
  }

  /// Ghost: the branch the last L1 tick took, and how many ticks there have
  /// been. Nothing reads it; the L1 replay does.
  type L1Ghost = { branch: str, ticks: int }

  var lease: Lease
  var drain: Drain
  var enforce: Enforce
  var cluster: Cluster
  var clock: Clock
  var evidence: Evidence
  var l1Last: L1Ghost

  // --------------------------------------------------------------------------
  // Helpers
  // --------------------------------------------------------------------------

  pure def minInt(a: int, b: int): int = if (a < b) a else b
  pure def maxInt(a: int, b: int): int = if (a > b) a else b

  /// The lowest-numbered element of `s`, or 0 for the empty set. The actors are
  /// symmetric, so "which one" carries no information: a total, deterministic
  /// pick beats a `oneOf` that has to be guarded against an empty set at every
  /// call site, and it keeps the scripted incident replays reproducible. Actor
  /// ids are positive, so 0 is an unambiguous "none".
  pure def pickOne(s: Set[int]): int =
    s.fold(0, (acc, x) => if (acc == 0 or x < acc) x else acc)

  /// Actors that are SUSPENDED: in none of the other states.
  def suspendedIn(c: Cluster): Set[int] =
    ACTORS
      .exclude(c.awake).exclude(c.checkpointing).exclude(c.doomed)
      .exclude(c.crashed).exclude(c.deleting).exclude(c.gone)

  val suspendedActors = suspendedIn(cluster)

  /// What Substrate's store reports as not at rest: every task actor L1 has to
  /// see SUSPENDED before it may write `drained`. Doomed actors are in it,
  /// because the store cannot tell them from live ones.
  def storeAwakeIn(c: Cluster): Set[int] = c.awake.union(c.checkpointing).union(c.doomed)

  val storeAwake = storeAwakeIn(cluster)

  /// The node is up and not being stopped: pods can run on it.
  def liveIn(c: Cluster): bool = c.nodes == 1 and not(c.stopping)

  val nodeLive = liveIn(cluster)

  /// The two resume paths that need a pod.
  val routerServing = nodeLive and cluster.routerPod
  val controllerServing = nodeLive and cluster.controllerPod

  /// The pool's target goes to zero. Everything on the node is evicted: the
  /// reaper, the router and controller pods, and every worker pod -- so every
  /// actor with a live sandbox, or mid-checkpoint, becomes doomed. The node
  /// itself keeps billing until nodeGoneTick.
  pure def stopRequested(c: Cluster): Cluster = {
    ...c,
    stopping: c.nodes == 1,
    awake: Set(),
    checkpointing: Set(),
    doomed: c.doomed.union(c.awake).union(c.checkpointing),
    goldenAwake: false,
    routerPod: false,
    controllerPod: false,
    reaperAlive: false,
  }

  /// When a stop requested now makes the node leave.
  val nodeGoneAfterStop = clock.now + stop_latency_actual

  /// The latest instant a lease may expire at: exactly cap_gap_minutes before
  /// the daily stop. With the JSON's numbers and a window starting at local
  /// midnight this is 03:00 against L3's 04:00.
  val capAt = clock.l3At - cap_gap_minutes

  /// The deadline a request for `d` more minutes actually gets. Two clamps and
  /// a floor: never more than the maximum lease, never past the nightly cap,
  /// never in the past.
  def cappedDeadline(d: int): int =
    maxInt(minInt(clock.now + minInt(d, max_lease_minutes), capAt), clock.now)

  /// L1 is an in-cluster CronJob: it only ticks while the node is live and the
  /// job is actually running.
  val l1Scheduled = nodeLive and cluster.reaperAlive

  val l1NextDue = if (l1Scheduled) clock.l1Due else NEVER
  val l2NextDue = clock.l2Due
  val l3NextDue = if (clock.l3Fired) NEVER else clock.l3At
  val nodeGoneNextDue = if (cluster.stopping) clock.nodeGoneDue else NEVER

  /// Does drain.json hold a record in state `s` about THIS lease generation? A
  /// record about an older generation says nothing about this lease -- that is
  /// how a successful extend invalidates an earlier `drained`.
  def drainIs(s: DrainState): bool = drain.state == s and drain.leaseGen == lease.gen

  /// A terminal record L1 must not settle on: it is about an older lease
  /// generation, so the lease it described is gone. Only decidable when the
  /// lease can be read.
  val staleTerminal = and {
    drain.state == Drained or drain.state == DrainFailed,
    lease.readable,
    drain.leaseGen != lease.gen,
  }

  // Frame helpers. "This action does not write that object."
  action leaseUnchanged = lease' = lease
  action drainUnchanged = drain' = drain
  action enforceUnchanged = enforce' = enforce
  action clusterUnchanged = cluster' = cluster
  action clockUnchanged = clock' = clock
  action evidenceUnchanged = evidence' = evidence
  action l1LastUnchanged = l1Last' = l1Last

  // --------------------------------------------------------------------------
  // L0 -- the operator, on the Mac. The only writer of lease.json.
  // --------------------------------------------------------------------------

  /// `just exe-wake [d]`. A wake always carries an expiry: there is no request
  /// shape that means "stay up". Two refusals are part of the contract --
  ///   * more than max_lease_minutes is rejected outright by the CLI, and
  ///   * a wake whose capped deadline would not be in the future is rejected
  ///     too. That second one is the 03:00-04:00 window: the cap has already
  ///     passed, so the only lease available is a zero-length one. Granting it
  ///     would start a node and open the router less than cap_gap_minutes
  ///     before L3 fires, which is precisely the situation the cap exists to
  ///     prevent. The model found this; `exe-wake` must fail there and say so.
  ///
  /// `wokenAt` is the one thing a wake writes that an extend does not: it
  /// restarts L1's idle clock, because a new node is a new session.
  action wakeFor(d: int): bool = all {
    clock.now <= HORIZON,
    d <= max_lease_minutes,
    cappedDeadline(d) > clock.now,
    lease' = {
      ...lease,
      deadline: cappedDeadline(d),
      granted: cappedDeadline(d),
      gen: lease.gen + 1,
      wokenAt: clock.now,
    },
    // A wake creates a node when there is none, or when the one there is being
    // stopped (setSize(1) on a pool whose node is still leaving: GKE starts a
    // new one). If the node was already live, a wedged reaper stays wedged --
    // reviving it here would make the model optimistic, which is the one
    // direction that can hide a bug.
    //
    // It does NOT touch a replica count. The router's and the controller's
    // replicas have exactly one owner, L1, and this is where that rule earns
    // its keep: a `wake` that also scaled the router to 1 would reopen it in
    // the middle of a drain, after which L1 writes a `drained` record that an
    // auto-resume immediately falsifies -- and L2's graceful stop then crashes
    // the actor. The model found that in a few dozen steps when this action set
    // the router up. On a new node the pods simply start as the replica counts
    // L1 left say; L1 reopens both on its first tick where the lease is live.
    cluster' =
      if (nodeLive) cluster
      else {
        ...cluster,
        nodes: 1,
        stopping: false,
        routerPod: cluster.routerReplicas == 1,
        controllerPod: cluster.controllerReplicas == 1,
        reaperAlive: true,
      },
    clock' = {
      ...clock,
      l1Due: clock.now + l1_tick_minutes,
      nodeGoneDue: if (nodeLive) clock.nodeGoneDue else NEVER,
    },
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
    l1LastUnchanged,
  }

  action wake = nondet d = oneOf(LEASE_REQUESTS) { wakeFor(d) }

  /// `just exe-extend [d]`. Same two clamps as wake. "Successful" means the new
  /// deadline is genuinely in the future -- an extend inside the cap window
  /// fails rather than silently granting nothing, which is what makes
  /// ExtendBeatsStaleDrained a statement about something that happened.
  ///
  /// Note what this action does NOT do: touch drain.json (L1 owns it) or
  /// wokenAt (an extend is not a new session, so the idle clock keeps running:
  /// extending a lease with nothing running does not keep the node up). The
  /// invalidation of an older `drained` happens two other ways: the deadline
  /// moves into the future, and the lease generation moves, so a `drained`
  /// written about the previous generation is visibly not about this one.
  action extendFor(d: int): bool = all {
    clock.now <= HORIZON,
    cluster.nodes == 1,
    d <= max_lease_minutes,
    cappedDeadline(d) > clock.now,
    lease' = {
      ...lease,
      deadline: cappedDeadline(d),
      granted: cappedDeadline(d),
      gen: lease.gen + 1,
    },
    clusterUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
    l1LastUnchanged,
  }

  action extend = nondet d = oneOf(LEASE_REQUESTS) { extendFor(d) }

  /// `just exe-sleep`. Sets the deadline to now and stops there. It does not
  /// scale anything, does not call the GKE API, does not touch the router --
  /// L1 does the graceful part. That is why a sleep cannot lose an actor: there
  /// is no shrink in this action at all.
  action sleep = all {
    clock.now <= HORIZON,
    lease' = {
      ...lease,
      deadline: clock.now,
      granted: clock.now,
      gen: lease.gen + 1,
    },
    clusterUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
    l1LastUnchanged,
  }

  /// REJECTED DESIGN, reachable only in the `twoWriterLease` instance. A second
  /// writer for lease.json -- a retried `exe-sleep` from another shell, a
  /// leftover process, a reaper subcommand that "helpfully" normalises the
  /// object -- writes the deadline it had in hand.
  ///
  /// It bumps the generation, which is the point: a generation precondition
  /// protects against a LOST update, not against a second writer that reads,
  /// decides, and writes correctly with respect to the protocol and wrongly
  /// with respect to intent. `granted` -- what the operator believes they were
  /// given -- is untouched, and that gap is what the invariant sees.
  action rogueLeaseWrite = all {
    two_writer_lease,
    clock.now <= HORIZON,
    lease' = { ...lease, deadline: clock.now, gen: lease.gen + 1 },
    clusterUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
    l1LastUnchanged,
  }

  // --------------------------------------------------------------------------
  // Waking an actor. Four paths, and only one of them asks permission.
  // --------------------------------------------------------------------------

  /// Everything below changes only the cluster.
  action onlyCluster(c: Cluster): bool = all {
    cluster' = c,
    leaseUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
    l1LastUnchanged,
  }

  def withAwake(a: int): Cluster = { ...cluster, awake: cluster.awake.union(Set(a)) }

  /// `ax-job` / `ax-exec` resume a task through the ax-controller, after
  /// MayStartTask: they refuse an expired lease and a drain record about the
  /// current lease. A record about an OLDER lease does not refuse -- a
  /// successful extend reopens the cluster for work -- which is the same
  /// generation comparison L2 uses.
  action operatorResume = all {
    controllerServing,
    drain.state == DrainNone or (lease.readable and drain.leaseGen != lease.gen),
    lease.readable,
    clock.now < lease.deadline,
    suspendedActors != Set(),
    onlyCluster(withAwake(pickOne(suspendedActors))),
  }

  /// A raw `ax resume`, bypassing the wrappers. ax-server writes the request
  /// into Redis at once; the ax-controller executes it whenever it runs. Look
  /// at what is NOT a precondition: the lease, the drain, anything at all but
  /// a controller pod to execute it. That omission is why L1 takes the
  /// controller down, and waits for its pod to be gone, before `drained`.
  action rawResume = all {
    controllerServing,
    suspendedActors != Set(),
    onlyCluster(withAwake(pickOne(suspendedActors))),
  }

  /// The atenet router resumes a SUSPENDED actor on the next connection,
  /// without the ax-controller being involved. It really does this, and it
  /// does not read lease.json and cannot be made to. That is why L1's first
  /// step takes the router to zero replicas BEFORE it suspends anything, and
  /// it is the entire content of the `routerLeftOpen` variant.
  action autoResume = all {
    routerServing,
    suspendedActors != Set(),
    onlyCluster(withAwake(pickOne(suspendedActors))),
  }

  /// The ax-controller creates an ActorTemplate for a task image it has not
  /// seen: from then on Substrate's reconciler owns a golden flow.
  action templateCreated = all {
    controllerServing,
    not(cluster.templatePending),
    onlyCluster({ ...cluster, templatePending: true }),
  }

  /// Substrate's ActorTemplateReconciler, inside ate-api-server (which L1 does
  /// NOT stop), calls ResumeActor on the golden actor of any template whose
  /// golden snapshot is neither written nor failed. Nobody asks it to.
  action goldenResume = all {
    nodeLive,
    cluster.templatePending,
    not(cluster.goldenAwake),
    onlyCluster({ ...cluster, goldenAwake: true }),
  }

  /// The golden flow ends: the snapshot is written, or the template fails.
  /// Either way the template is terminal and its golden actor is at rest.
  action goldenSettles = all {
    nodeLive,
    cluster.templatePending,
    onlyCluster({ ...cluster, goldenAwake: false, templatePending: false }),
  }

  /// A suspend that was asked for completes -- possibly minutes later: a
  /// checkpoint takes as long as it takes.
  action checkpointDone = all {
    nodeLive,
    cluster.checkpointing != Set(),
    onlyCluster({
      ...cluster,
      checkpointing: cluster.checkpointing.exclude(Set(pickOne(cluster.checkpointing))),
    }),
  }

  /// Substrate notices that a doomed actor's worker pod is gone and marks it
  /// CRASHED. There is no bound on when: a workflow or the worker syncer finds
  /// it, possibly not until the next wake. No property may rely on this ever
  /// happening.
  action crashDetected = all {
    cluster.doomed != Set(),
    onlyCluster({
      ...cluster,
      doomed: cluster.doomed.exclude(Set(pickOne(cluster.doomed))),
      crashed: cluster.crashed.union(Set(pickOne(cluster.doomed))),
    }),
  }

  /// A scale-down takes effect: the old pod finishes terminating. Until this
  /// happens, a pod whose replica count is already 0 still serves -- and can
  /// still execute a resume that is already in flight.
  action podsTerminate = all {
    or {
      cluster.routerReplicas == 0 and cluster.routerPod,
      cluster.controllerReplicas == 0 and cluster.controllerPod,
    },
    onlyCluster({
      ...cluster,
      routerPod: cluster.routerPod and cluster.routerReplicas == 1,
      controllerPod: cluster.controllerPod and cluster.controllerReplicas == 1,
    }),
  }

  /// The operator deletes a task (`ax delete task`). Its actor goes away -- or,
  /// as in Phase 4, the delete wedges: TerminateWorkload fails forever and the
  /// actor sits in DELETING, holding its worker.
  action deleteTaskWith(wedges: bool): bool = {
    val candidates = cluster.awake.union(suspendedActors)
    val a = pickOne(candidates)
    all {
      controllerServing,
      candidates != Set(),
      onlyCluster({
        ...cluster,
        awake: cluster.awake.exclude(Set(a)),
        deleting: if (wedges) cluster.deleting.union(Set(a)) else cluster.deleting,
        gone: if (wedges) cluster.gone else cluster.gone.union(Set(a)),
      }),
    }
  }

  action deleteTask = any { deleteTaskWith(true), deleteTaskWith(false) }

  /// One worker pod dies on its own -- OOM-killed, evicted, its sandbox wedged
  /// and restarted -- while the node stays. The actor on it, awake or
  /// mid-checkpoint, is doomed: the store says RUNNING until a crash is
  /// detected.
  action workerPodLost = {
    val candidates = cluster.awake.union(cluster.checkpointing)
    val a = pickOne(candidates)
    all {
      nodeLive,
      candidates != Set(),
      onlyCluster({
        ...cluster,
        awake: cluster.awake.exclude(Set(a)),
        checkpointing: cluster.checkpointing.exclude(Set(a)),
        doomed: cluster.doomed.union(Set(a)),
      }),
    }
  }

  // --------------------------------------------------------------------------
  // L1 -- the in-cluster reaper, once a minute. The only writer of drain.json,
  // and the only owner of the router's and the controller's replica counts.
  //
  // Every tick first OBSERVES, whatever it then decides: it carries the idle
  // clock (drain.idleSince) and the wedge record (drain.wedgeSeen) forward, and
  // it deletes the worker pod of any actor that has been stuck in DELETING for
  // wedge_clear_minutes -- the only pod L1 ever deletes, and only one hosting
  // an actor that is already being deleted, so nothing live can be lost. Then
  // exactly one branch decides.
  //
  // The drain, in order (plan section 3.2, revised in Phase 6):
  //   begin     the baseline of what is already CRASHED, `draining`, and the
  //             router to 0 replicas
  //   suspend   AX suspends every awake task (needs the controller)
  //   quiesce   nothing awake: the controller to 0 replicas
  //   wait      until no router or controller pod is left, no template is in
  //             flight, and every checkpoint has finished
  //   finish    `drained`
  // with two ways out: `lost` (something crashed since the baseline -- never
  // reported as graceful) and the ceiling (`drain-failed`). L1 never touches
  // the pool.
  // --------------------------------------------------------------------------

  /// L1's idle clock after observing tick `t`: the first tick that saw nothing
  /// awake, or -1 while something is.
  def observedIdleSince(t: int): int =
    if (storeAwake != Set()) -1 else if (drain.idleSince < 0) t else drain.idleSince

  /// The wedge record after observing tick `t`: every actor stuck in DELETING,
  /// with the tick L1 first saw it so.
  def observedWedges(t: int): int -> int =
    cluster.deleting.mapBy(a => if (drain.wedgeSeen.keys().contains(a)) drain.wedgeSeen.get(a) else t)

  /// The wedged actors whose worker pods L1 deletes at tick `t`.
  pure def wedgesToClear(t: int, seen: int -> int): Set[int] =
    seen.keys().filter(a => t - seen.get(a) >= wedge_clear_minutes)

  /// L1's drain trigger at minute `t`, with the idle clock it just observed.
  /// Three reasons, exactly as the plan lists them: the deadline passed,
  /// nothing has been awake for idle_zero_running_minutes since the later of
  /// the first idle tick and the wake, or lease.json could not be read at all.
  def l1TriggerWith(t: int, idleSince: int): bool = or {
    not(lease.readable),
    lease.readable and t >= lease.deadline,
    idleSince >= 0 and t - maxInt(idleSince, lease.wokenAt) >= idle_zero_running_minutes,
  }

  def l1ReasonAt(t: int): DrainReason =
    if (not(lease.readable)) LeaseUnreadable
    else if (t >= lease.deadline) DeadlinePassed
    else IdleZeroRunning

  /// Every stop condition of the barrier holds: nothing awake, no golden work
  /// left, and no pod left that could resume anything. The rejected variants
  /// each skip one clause.
  def drainDoneIn(c: Cluster): bool = and {
    storeAwakeIn(c) == Set(),
    golden_ignored or (not(c.goldenAwake) and not(c.templatePending)),
    controller_left_up or c.controllerReplicas == 0,
    controller_left_up or scale_is_barrier or not(c.controllerPod),
    router_left_open or scale_is_barrier or not(c.routerPod),
  }

  /// Something crashed since the drain began: its state is lost, and the drain
  /// must say so.
  def lostIn(c: Cluster): bool = c.crashed.exclude(drain.baselineCrashed) != Set()

  /// The lease generation a record L1 writes now is about. If the lease cannot
  /// be read, L1 keeps the last generation it saw rather than inventing one.
  val l1Gen = if (lease.readable) lease.gen else drain.leaseGen

  def l1ClockAt(t: int): Clock = { ...clock, now: t, l1Due: t + l1_tick_minutes }

  pure def reopened(c: Cluster): Cluster =
    { ...c, routerReplicas: 1, controllerReplicas: 1, routerPod: true, controllerPod: true }

  /// Nothing to do: no trigger, no drain in flight, both paths open. This is
  /// what almost every one of the 1440 daily ticks does.
  action l1NoOp(t: int, trigger: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    not(trigger),
    drain.state == DrainNone,
    c0.routerReplicas == 1,
    c0.controllerReplicas == 1,
    drain' = d0,
    cluster' = c0,
    evidence' = e0,
    clock' = l1ClockAt(t),
    l1Last' = { branch: "NoOp", ticks: l1Last.ticks + 1 },
  }

  /// The lease is live and a replica count is at zero -- a previous drain took
  /// it there. L1 puts both back. This is a reconcile, not an event handler: it
  /// is what makes L1 the single owner of both counts, so no other action ever
  /// has a reason to scale them.
  action l1Reopen(t: int, trigger: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    not(trigger),
    drain.state == DrainNone,
    c0.routerReplicas == 0 or c0.controllerReplicas == 0,
    drain' = d0,
    cluster' = reopened(c0),
    evidence' = e0,
    clock' = l1ClockAt(t),
    l1Last' = { branch: "Reopen", ticks: l1Last.ticks + 1 },
  }

  /// The lease came back inside its deadline -- a successful `exe-extend`, a
  /// new `exe-wake`, or a read that started working again. Cancel whatever the
  /// record says and reopen both paths. This is L1's half of "a successful
  /// extend invalidates a prior `drained`".
  action l1Cancel(t: int, trigger: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    not(trigger),
    drain.state != DrainNone,
    drain' = {
      ...d0,
      state: DrainNone,
      heartbeat: t,
      startedAt: t,
      leaseGen: lease.gen,
      reason: NoReason,
      baselineCrashed: Set(),
    },
    cluster' = reopened(c0),
    evidence' = e0,
    clock' = l1ClockAt(t),
    l1Last' = { branch: "Cancel", ticks: l1Last.ticks + 1 },
  }

  /// Begin: the baseline of what is ALREADY crashed, then `draining` with a
  /// heartbeat, then the router to zero replicas so nothing can auto-resume
  /// behind the drain's back. A terminal record about an OLDER lease does not
  /// hold L1 back: `exe-sleep` after an idle drain must drain again, not
  /// settle on the old record and leave L2 to force (review note, Phase 3).
  /// The pool is not touched here. Not once, not as an optimisation, not
  /// "since we are about to anyway" -- see naiveShrinkFirst.
  action l1Begin(t: int, trigger: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    trigger,
    drain.state == DrainNone or staleTerminal,
    drain' = {
      ...d0,
      state: Draining,
      heartbeat: t,
      startedAt: t,
      leaseGen: l1Gen,
      reason: l1ReasonAt(t),
      baselineCrashed: c0.crashed,
    },
    cluster' =
      if (naive_shrink_first)
        // REJECTED DESIGN: shrink now, suspend later. There is no "later".
        stopRequested(c0)
      else
        { ...c0, routerReplicas: if (router_left_open) c0.routerReplicas else 0 },
    evidence' =
      if (naive_shrink_first)
        { ...e0,
          lastShrink: GracefulStop,
          gracefulCrash: e0.gracefulCrash or storeAwakeIn(c0) != Set() or c0.goldenAwake }
      else
        e0,
    clock' =
      if (naive_shrink_first) { ...l1ClockAt(t), nodeGoneDue: t + stop_latency_actual }
      else l1ClockAt(t),
    l1Last' = { branch: "Begin", ticks: l1Last.ticks + 1 },
  }

  /// Something crashed since the baseline. Its state is gone, so this drain can
  /// never be graceful: `drain-failed`, and L2 forces and pages. Checked before
  /// anything else, including "done" -- a crashed actor is not awake, so a
  /// drain that only asked "is anything awake?" would call this graceful.
  action l1Lost(t: int, trigger: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    trigger,
    drain.state == Draining,
    lostIn(c0),
    drain' = { ...d0, state: DrainFailed, heartbeat: t, leaseGen: l1Gen },
    cluster' = c0,
    evidence' = { ...e0, drainEverFailed: true },
    clock' = l1ClockAt(t),
    l1Last' = { branch: "Lost", ticks: l1Last.ticks + 1 },
  }

  /// The barrier holds: `drained`.
  action l1Finish(t: int, trigger: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    trigger,
    drain.state == Draining,
    not(lostIn(c0)),
    drainDoneIn(c0),
    drain' = { ...d0, state: Drained, heartbeat: t, leaseGen: l1Gen },
    cluster' = c0,
    evidence' = e0,
    clock' = l1ClockAt(t),
    l1Last' = { branch: "Finish", ticks: l1Last.ticks + 1 },
  }

  /// drain_ceiling_minutes spent without reaching the barrier: `drain-failed`.
  /// L1 still does not shrink the pool. It records the failure and lets L2
  /// force, so the crash that follows is attributed to a FORCED stop and
  /// notified -- never mislabelled as a graceful sleep.
  action l1GiveUp(t: int, trigger: bool, ceilingBlown: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    trigger,
    drain.state == Draining,
    not(lostIn(c0)),
    not(drainDoneIn(c0)),
    ceilingBlown,
    drain' = { ...d0, state: DrainFailed, heartbeat: t, leaseGen: l1Gen },
    cluster' = c0,
    evidence' = { ...e0, drainEverFailed: true },
    clock' = l1ClockAt(t),
    l1Last' = { branch: "GiveUp", ticks: l1Last.ticks + 1 },
  }

  /// Something is awake again after the controller was taken down -- a resume
  /// slipped in before its pod was gone. Suspending goes through AX, so the
  /// controller comes back first, and the drain goes round again.
  action l1Resuspend(t: int, trigger: bool, ceilingBlown: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    trigger,
    drain.state == Draining,
    not(lostIn(c0)),
    not(drainDoneIn(c0)),
    not(ceilingBlown),
    c0.awake.union(c0.doomed) != Set(),
    c0.controllerReplicas == 0,
    drain' = { ...d0, heartbeat: t, leaseGen: l1Gen },
    cluster' = { ...c0, controllerReplicas: 1, controllerPod: true },
    evidence' = e0,
    clock' = l1ClockAt(t),
    l1Last' = { branch: "Resuspend", ticks: l1Last.ticks + 1 },
  }

  /// Ask AX to suspend every task whose actor the store calls awake, and
  /// refresh the heartbeat. Each suspend starts a checkpoint (SUSPENDING) that
  /// finishes when it finishes. An actor that is doomed -- its pod already gone
  /// -- cannot be checkpointed: Substrate crashes it (ReasonWorkerPodGone), and
  /// the next tick sees the loss.
  action l1Suspend(t: int, trigger: bool, ceilingBlown: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    trigger,
    drain.state == Draining,
    not(lostIn(c0)),
    not(drainDoneIn(c0)),
    not(ceilingBlown),
    c0.awake.union(c0.doomed) != Set(),
    c0.controllerReplicas == 1,
    drain' = { ...d0, heartbeat: t, leaseGen: l1Gen },
    cluster' = {
      ...c0,
      awake: Set(),
      checkpointing: c0.checkpointing.union(c0.awake),
      doomed: Set(),
      crashed: c0.crashed.union(c0.doomed),
    },
    evidence' = e0,
    clock' = l1ClockAt(t),
    l1Last' = { branch: "Suspend", ticks: l1Last.ticks + 1 },
  }

  /// A tick during a drain whose suspend requests make no progress: the
  /// controller is not acting, the request errored. The heartbeat is still
  /// written, so L2 keeps waiting. That is the intended behaviour and it is
  /// bounded by the ceiling, not by patience.
  action l1Stall(t: int, trigger: bool, ceilingBlown: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    trigger,
    drain.state == Draining,
    not(lostIn(c0)),
    not(drainDoneIn(c0)),
    not(ceilingBlown),
    c0.awake.union(c0.doomed) != Set(),
    c0.controllerReplicas == 1,
    drain' = { ...d0, heartbeat: t, leaseGen: l1Gen },
    cluster' = c0,
    evidence' = e0,
    clock' = l1ClockAt(t),
    l1Last' = { branch: "Stall", ticks: l1Last.ticks + 1 },
  }

  /// Nothing is awake any more: take the controller to zero replicas, so a
  /// raw `ax resume` can no longer be executed. The pod lingers until
  /// podsTerminate; `drained` waits for that.
  action l1Quiesce(t: int, trigger: bool, ceilingBlown: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    trigger,
    drain.state == Draining,
    not(controller_left_up),
    not(lostIn(c0)),
    not(drainDoneIn(c0)),
    not(ceilingBlown),
    c0.awake.union(c0.doomed) == Set(),
    c0.controllerReplicas == 1,
    drain' = { ...d0, heartbeat: t, leaseGen: l1Gen },
    cluster' = { ...c0, controllerReplicas: 0 },
    evidence' = e0,
    clock' = l1ClockAt(t),
    l1Last' = { branch: "Quiesce", ticks: l1Last.ticks + 1 },
  }

  /// Nothing to ask for, not done yet: checkpoints still writing, a pod still
  /// terminating, a golden flow still in flight. Heartbeat and wait.
  action l1Wait(t: int, trigger: bool, ceilingBlown: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    trigger,
    drain.state == Draining,
    not(lostIn(c0)),
    not(drainDoneIn(c0)),
    not(ceilingBlown),
    c0.awake.union(c0.doomed) == Set(),
    c0.controllerReplicas == 0 or controller_left_up,
    drain' = { ...d0, heartbeat: t, leaseGen: l1Gen },
    cluster' = c0,
    evidence' = e0,
    clock' = l1ClockAt(t),
    l1Last' = { branch: "Wait", ticks: l1Last.ticks + 1 },
  }

  /// The drain already reached a terminal record about this lease and the
  /// trigger still holds: nothing left for L1 to do. Note that it does NOT
  /// keep writing heartbeats here -- a heartbeat means "a drain is in
  /// progress", and L2's staleness test would be worthless if it meant "L1 is
  /// alive".
  action l1Settled(t: int, trigger: bool, c0: Cluster, d0: Drain, e0: Evidence): bool = all {
    trigger,
    drain.state == Drained or drain.state == DrainFailed,
    not(staleTerminal),
    drain' = d0,
    cluster' = c0,
    evidence' = e0,
    clock' = l1ClockAt(t),
    l1Last' = { branch: "Settled", ticks: l1Last.ticks + 1 },
  }

  /// One L1 tick, at minute `l1Due`. `progress` says whether the suspend
  /// requests this tick sends are acted on -- `l1Tick` leaves that open, and
  /// the scripted tests pin it so an incident replay is deterministic.
  action l1TickWith(progress: bool): bool = {
    val t = clock.l1Due
    val idleSince = observedIdleSince(t)
    val seen = observedWedges(t)
    val cleared = wedgesToClear(t, seen)
    val c0 = {
      ...cluster,
      deleting: cluster.deleting.exclude(cleared),
      gone: cluster.gone.union(cleared),
    }
    val d0 = {
      ...drain,
      idleSince: idleSince,
      wedgeSeen: seen.keys().exclude(cleared).mapBy(a => seen.get(a)),
    }
    val e0 = {
      ...evidence,
      clearedLiveActor: evidence.clearedLiveActor or cleared.intersect(storeAwake) != Set(),
    }
    val trigger = l1TriggerWith(t, idleSince)
    val ceilingBlown = t - drain.startedAt >= drain_ceiling_minutes
    all {
      l1Scheduled,
      t <= HORIZON,
      t <= l2NextDue,
      t <= l3NextDue,
      t <= nodeGoneNextDue,
      leaseUnchanged,
      enforceUnchanged,
      // The thirteen branches of one tick. They are exhaustive, so a tick is
      // never a dead end, and disjoint, so a tick is a replay rather than a
      // coin toss.
      any {
        l1NoOp(t, trigger, c0, d0, e0),
        l1Reopen(t, trigger, c0, d0, e0),
        l1Cancel(t, trigger, c0, d0, e0),
        l1Begin(t, trigger, c0, d0, e0),
        l1Lost(t, trigger, c0, d0, e0),
        l1Finish(t, trigger, c0, d0, e0),
        l1GiveUp(t, trigger, ceilingBlown, c0, d0, e0),
        l1Resuspend(t, trigger, ceilingBlown, c0, d0, e0),
        all { progress, l1Suspend(t, trigger, ceilingBlown, c0, d0, e0) },
        all { not(progress), l1Stall(t, trigger, ceilingBlown, c0, d0, e0) },
        l1Quiesce(t, trigger, ceilingBlown, c0, d0, e0),
        l1Wait(t, trigger, ceilingBlown, c0, d0, e0),
        l1Settled(t, trigger, c0, d0, e0),
      },
    }
  }

  action l1Tick = any { l1TickWith(true), l1TickWith(false) }

  /// The reaper stops ticking: the CronJob is wedged, the KSA lost its binding,
  /// the node is NotReady but still counted. Nothing in the cluster changes --
  /// the heartbeat in drain.json simply stops moving. This is the only thing
  /// that gives L2's staleness test any work to do.
  action l1Crash = all {
    nodeLive,
    cluster.reaperAlive,
    onlyCluster({ ...cluster, reaperAlive: false }),
  }

  // --------------------------------------------------------------------------
  // L2 -- the Cloud Run enforcer, every 10 minutes. The only writer of
  // enforce.json. It reads GCS, reads the pool's MIG (target size and the
  // instances still there) and calls nodePools.setSize; it never holds a
  // cluster credential, which is why it still works when the cluster does not.
  //
  // The branches are the rows of plan section 3.2's L2 table, and the SAME
  // table as DecideL2 in tools/exe-reaper/internal/lease/decide.go, in the same
  // order: the pool's target already at zero; read failures (a lease you
  // cannot read tells you nothing about expiry); the lease-is-live exit, except
  // for an idle drain about this lease; then the rule for an expired lease.
  // They are disjoint and exhaustive, so a tick is a replay rather than a coin
  // toss -- which is what lets TestDecideL2AgreesWithTheModel replay the
  // model's own traces through DecideL2 and demand the same branch.
  // --------------------------------------------------------------------------

  /// The pool's target size, which is what L2 reads as the pool's size: it goes
  /// to zero the moment setSize(0) is accepted, while the node itself is still
  /// there and billing.
  val target = if (nodeLive) 1 else 0

  /// L2's run of consecutive lease read failures after this tick: reset while
  /// the target is zero, reset by a readable lease, extended by a miss. The
  /// same rule as NextReadFailures on the Go side.
  val l2ReadFailuresNext =
    if (target == 0 or lease.readable) 0 else enforce.leaseReadFailures + 1

  /// The heartbeat L2 judges L1 by. With no record about this lease it is the
  /// deadline itself: a live L1 writes `draining` within a minute of it, so a
  /// whole heartbeat window of silence after it means L1 is not running.
  val l2Heartbeat = if (drainIs(Draining)) drain.heartbeat else lease.deadline

  /// Past the deadline, the only two ways L2 waits: a drain in progress, or no
  /// record yet -- in both cases inside heartbeat_stale_minutes of the
  /// heartbeat, and NEVER past force_grace_minutes. The grace is unconditional:
  /// it is what bounds every wait.
  def l2MayWait(t: int): bool = and {
    not(drainIs(Drained)),
    not(drainIs(DrainFailed)),
    t <= lease.deadline + force_grace_minutes,
    t - l2Heartbeat <= heartbeat_stale_minutes,
  }

  /// An idle drain about this lease has finished: nothing has been awake for
  /// idle_zero_running_minutes and every actor is suspended. Billing on until
  /// the deadline would buy nothing (review note, Phase 3), so L2 stops the
  /// pool even though the lease is live. An extend moves the generation and
  /// takes this away.
  val idleDrained = drainIs(Drained) and drain.reason == IdleZeroRunning

  /// The enforce.json fields every tick writes the same way.
  def l2Record(d: Decision, t: int): Enforce = {
    ...enforce,
    last: d,
    gen: enforce.gen + 1,
    leaseReadFailures: l2ReadFailuresNext,
    stoppingSince: -1,
  }

  def l2ClockAt(t: int): Clock = { ...clock, now: t, l2Due: t + l2_tick_minutes }

  /// A stop L2 decides: the target goes to zero now, the node leaves
  /// stop_latency later.
  def l2StopClockAt(t: int): Clock = { ...l2ClockAt(t), nodeGoneDue: t + stop_latency_actual }

  /// The pool's target is already zero. Nothing to stop, whatever the lease
  /// says -- and the read-failure run is reset, so a run carried across a stop
  /// cannot turn the first miss after the next wake into a blind stop.
  ///
  /// It also runs the stop-latency detector (inbox M18, layer 3): the target is
  /// zero but the node is still there. The first tick that sees that remembers
  /// when; a later tick that still sees it past stop_latency_minutes raises
  /// the alarm, which pages. That is how a disruption budget holding the drain
  /// -- the Phase 4 incident -- becomes visible instead of silently billing.
  action l2AlreadyStopped(t: int): bool = all {
    target == 0,
    enforce' = {
      ...l2Record(AlreadyStopped, t),
      stoppingSince:
        if (not(cluster.stopping)) -1
        else if (enforce.stoppingSince < 0) t
        else enforce.stoppingSince,
      stopLatencyAlarm: enforce.stopLatencyAlarm or and {
        cluster.stopping,
        enforce.stoppingSince >= 0,
        t - enforce.stoppingSince > stop_latency_minutes,
      },
    },
    cluster' = cluster,
    evidence' = evidence,
    clock' = l2ClockAt(t),
  }

  /// Fewer than lease_read_failure_threshold consecutive read failures: record
  /// the miss and do nothing. L1 is draining on the very same signal, so the
  /// correct move is to let it. One or two misses must never stop the pool.
  action l2ReadFailedBelowThreshold(t: int): bool = all {
    target == 1,
    not(lease.readable),
    l2ReadFailuresNext < lease_read_failure_threshold,
    enforce' = l2Record(WaitedOnReadFailure, t),
    cluster' = cluster,
    evidence' = evidence,
    clock' = l2ClockAt(t),
  }

  /// lease_read_failure_threshold consecutive failures. L2 cannot see the
  /// deadline at all, so it stops the pool blind and notifies.
  ///
  /// This is the one stop that can land on a lease that is genuinely live, and
  /// it is deliberately outside ExtendBeatsStaleDrained -- see that invariant.
  /// The compensating control is the notification plus L1, which has been
  /// draining gracefully on the same signal since its own first tick.
  action l2ReadFailedAtThreshold(t: int): bool = all {
    target == 1,
    not(lease.readable),
    l2ReadFailuresNext >= lease_read_failure_threshold,
    enforce' = { ...l2Record(StoppedOnReadFailures, t), notified: true },
    cluster' = stopRequested(cluster),
    evidence' = { ...evidence, lastShrink: ForcedStop },
    clock' = l2StopClockAt(t),
  }

  /// The lease is live and no idle drain about it has finished. L2 has nothing
  /// to enforce, and still records a decision -- that record is how
  /// `exe-status` proves the enforcer ran at all.
  action l2LeaseLive(t: int): bool = all {
    target == 1,
    lease.readable,
    t < lease.deadline,
    not(idleDrained),
    enforce' = l2Record(LeaseLive, t),
    cluster' = cluster,
    evidence' = evidence,
    clock' = l2ClockAt(t),
  }

  /// A graceful stop's evidence: it may not catch anything awake, and it may
  /// not follow a crash since the drain's baseline.
  def gracefulEvidence(t: int, idleStop: bool): Evidence = {
    ...evidence,
    lastShrink: GracefulStop,
    gracefulCrash: evidence.gracefulCrash or storeAwake != Set() or cluster.goldenAwake,
    silentLoss: evidence.silentLoss or cluster.crashed.exclude(drain.baselineCrashed) != Set(),
    stoppedDespiteLiveLease: evidence.stoppedDespiteLiveLease or (t < lease.granted and not(idleStop)),
  }

  /// The lease is still live, and L1 finished an idle drain about THIS lease:
  /// stop gracefully now. This is the only stop before a deadline that
  /// ExtendBeatsStaleDrained accepts, and only because nothing was awake for
  /// idle_zero_running_minutes and everything is suspended.
  action l2StopOnIdleDrained(t: int): bool = all {
    target == 1,
    lease.readable,
    t < lease.deadline,
    idleDrained,
    enforce' = l2Record(StoppedOnIdleDrained, t),
    cluster' = stopRequested(cluster),
    evidence' = gracefulEvidence(t, true),
    clock' = l2StopClockAt(t),
  }

  /// L1 says `drained`, about THIS lease generation, and the deadline has
  /// passed. The pool can go to zero, at any time past the deadline, and this
  /// is the stop NoCrashOnGracefulSleep and NoSilentLoss judge.
  action l2StopOnDrained(t: int): bool = all {
    target == 1,
    lease.readable,
    t >= lease.deadline,
    drainIs(Drained),
    enforce' = l2Record(StoppedOnDrained, t),
    cluster' = stopRequested(cluster),
    evidence' = gracefulEvidence(t, false),
    clock' = l2StopClockAt(t),
  }

  /// A drain in progress with a fresh heartbeat, or no record yet inside the
  /// heartbeat window after the deadline -- and in both cases inside the grace.
  /// Wait.
  action l2WaitForDrain(t: int): bool = all {
    target == 1,
    lease.readable,
    t >= lease.deadline,
    l2MayWait(t),
    enforce' = l2Record(WaitedForDrain, t),
    cluster' = cluster,
    evidence' = evidence,
    clock' = l2ClockAt(t),
  }

  /// Everything else past the deadline -- `drain-failed` (lost or ceiling), a
  /// stale heartbeat, no record for a whole heartbeat window, or the grace
  /// spent. Force the pool's target to zero and notify. An actor awake here is
  /// CRASHED, and that is accepted: the alternative is a node that never stops.
  action l2Force(t: int): bool = all {
    target == 1,
    lease.readable,
    t >= lease.deadline,
    not(drainIs(Drained)),
    not(l2MayWait(t)),
    enforce' = { ...l2Record(StoppedForced, t), notified: true },
    cluster' = stopRequested(cluster),
    evidence' = {
      ...evidence,
      lastShrink: ForcedStop,
      stoppedDespiteLiveLease: evidence.stoppedDespiteLiveLease or t < lease.granted,
    },
    clock' = l2StopClockAt(t),
  }

  /// One L2 tick, at minute `l2Due`.
  action l2Tick = {
    val t = clock.l2Due
    all {
      t <= HORIZON,
      t <= l1NextDue,
      t <= l3NextDue,
      t <= nodeGoneNextDue,
      leaseUnchanged,
      drainUnchanged,
      l1LastUnchanged,
      any {
        l2AlreadyStopped(t),
        l2ReadFailedBelowThreshold(t),
        l2ReadFailedAtThreshold(t),
        l2LeaseLive(t),
        l2StopOnIdleDrained(t),
        l2StopOnDrained(t),
        l2WaitForDrain(t),
        l2Force(t),
      },
    }
  }

  // --------------------------------------------------------------------------
  // L3 -- Cloud Scheduler calls nodePools.setSize(0) at the daily stop hour.
  // --------------------------------------------------------------------------

  /// No lease read. No drain check. No Kubernetes credential. No logic at all,
  /// on purpose: this is the layer that has to work when every other layer is
  /// broken, so it has nothing that can break. Whatever is awake is lost --
  /// which is what the nightly cap exists to make impossible in normal
  /// operation, and L3NeverHitsAwakeActor is that claim. On a pool whose
  /// target is already zero, setSize(0) changes nothing.
  action l3Tick = all {
    not(clock.l3Fired),
    clock.l3At <= HORIZON,
    clock.l3At <= l1NextDue,
    clock.l3At <= l2NextDue,
    clock.l3At <= nodeGoneNextDue,
    cluster' = if (nodeLive) stopRequested(cluster) else cluster,
    clock' = {
      ...clock,
      now: clock.l3At,
      l3Fired: true,
      nodeGoneDue: if (nodeLive) clock.l3At + stop_latency_actual else clock.nodeGoneDue,
    },
    evidence' =
      if (nodeLive)
        {
          ...evidence,
          lastShrink: DailyStop,
          l3HitAwakeActor: evidence.l3HitAwakeActor or cluster.awake != Set()
            or cluster.checkpointing != Set() or cluster.goldenAwake,
        }
      else evidence,
    leaseUnchanged,
    drainUnchanged,
    enforceUnchanged,
    l1LastUnchanged,
  }

  // --------------------------------------------------------------------------
  // GKE -- the node actually leaves.
  // --------------------------------------------------------------------------

  /// stop_latency after the target went to zero, the node is gone and billing
  /// ends. A scheduled event like the ticks, so the clock cannot pass it: that
  /// is what makes "the node is gone by then" arithmetic.
  action nodeGoneTick = all {
    cluster.stopping,
    clock.nodeGoneDue <= HORIZON,
    clock.nodeGoneDue <= l2NextDue,
    clock.nodeGoneDue <= l3NextDue,
    cluster' = { ...cluster, nodes: 0, stopping: false },
    clock' = { ...clock, now: clock.nodeGoneDue, nodeGoneDue: NEVER },
    leaseUnchanged,
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
    l1LastUnchanged,
  }

  // --------------------------------------------------------------------------
  // Environment
  // --------------------------------------------------------------------------

  /// The node disappears at an arbitrary moment: the underlying VM is repaired,
  /// the kernel panics, the zone hiccups. Nobody decided this, so the crash it
  /// causes is not attributable to any stop decision.
  action nodeLoss = all {
    cluster.nodes == 1,
    cluster' = { ...stopRequested(cluster), nodes: 0, stopping: false },
    clock' = { ...clock, nodeGoneDue: NEVER },
    evidence' = { ...evidence, lastShrink: NodeGone },
    leaseUnchanged,
    drainUnchanged,
    enforceUnchanged,
    l1LastUnchanged,
  }

  /// lease.json cannot be read: the object was deleted, the bucket is 503-ing,
  /// the Workload Identity binding lapsed. Both L1 and L2 see it.
  action leaseReadBreaks = all {
    lease.readable,
    lease' = { ...lease, readable: false },
    evidence' = { ...evidence, leaseEverUnreadable: true },
    clusterUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
    l1LastUnchanged,
  }

  action leaseReadHeals = all {
    not(lease.readable),
    lease' = { ...lease, readable: true },
    clusterUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
    l1LastUnchanged,
  }

  // --------------------------------------------------------------------------
  // init / step
  // --------------------------------------------------------------------------

  pure val emptyDrain: Drain = {
    state: DrainNone,
    heartbeat: 0,
    startedAt: 0,
    leaseGen: 0,
    reason: NoReason,
    idleSince: -1,
    baselineCrashed: Set(),
    wedgeSeen: Map(),
  }

  pure val emptyEnforce: Enforce = {
    last: NoDecision,
    gen: 0,
    notified: false,
    leaseReadFailures: 0,
    stoppingSince: -1,
    stopLatencyAlarm: false,
  }

  pure val asleepCluster: Cluster = {
    nodes: 0,
    stopping: false,
    awake: Set(),
    checkpointing: Set(),
    doomed: Set(),
    crashed: Set(),
    deleting: Set(),
    gone: Set(),
    goldenAwake: false,
    templatePending: false,
    routerReplicas: 1,
    controllerReplicas: 1,
    routerPod: false,
    controllerPod: false,
    reaperAlive: false,
  }

  pure val noEvidence: Evidence = {
    lastShrink: NoShrink,
    gracefulCrash: false,
    silentLoss: false,
    l3HitAwakeActor: false,
    stoppedDespiteLiveLease: false,
    drainEverFailed: false,
    leaseEverUnreadable: false,
    clearedLiveActor: false,
  }

  /// The cluster starts asleep with no lease. `l3At` fixes what local time the
  /// modelled window starts at.
  action initWith(l3Offset: int): bool = all {
    lease' = { deadline: 0, gen: 0, granted: 0, readable: true, wokenAt: 0 },
    drain' = emptyDrain,
    enforce' = emptyEnforce,
    cluster' = asleepCluster,
    clock' = {
      now: 0,
      l1Due: l1_tick_minutes,
      l2Due: l2_tick_minutes,
      l3At: l3Offset,
      l3Fired: false,
      nodeGoneDue: NEVER,
    },
    evidence' = noEvidence,
    l1Last' = { branch: "", ticks: 0 },
  }

  action init = nondet l3Offset = oneOf(L3_OFFSETS) { initWith(l3Offset) }

  /// Every scheduled event, for scripted runs that only need the clock to move.
  action anyTick = any { l1Tick, l2Tick, l3Tick, nodeGoneTick }

  /// Every scheduled event, with the drain's suspends forced to make no
  /// progress.
  action anyTickStalling = any { l1TickWith(false), l2Tick, l3Tick, nodeGoneTick }

  action step = any {
    wake,
    extend,
    sleep,
    rogueLeaseWrite,
    operatorResume,
    rawResume,
    autoResume,
    templateCreated,
    goldenResume,
    goldenSettles,
    checkpointDone,
    crashDetected,
    podsTerminate,
    deleteTask,
    workerPodLost,
    l1Tick,
    l1Crash,
    l2Tick,
    l3Tick,
    nodeGoneTick,
    nodeLoss,
    leaseReadBreaks,
    leaseReadHeals,
  }

  // --------------------------------------------------------------------------
  // The L2 table, one decision at a time.
  //
  // Not part of `step`. A world set up for exactly one L2 decision, so the
  // table can be walked row by row (the l2Table*Test runs in `lease`) and at
  // random: `just spec-check` samples l2WorldStep traces and hands them to
  // TestDecideL2AgreesWithTheModel, which replays every L2 decision in them
  // through the Go DecideL2 and demands the same branch. The offsets sit on
  // both sides of every boundary the rule has, because that is where two
  // encodings of one table disagree.
  // --------------------------------------------------------------------------

  /// The minute the sampled L2 tick lands at: far enough from 0 that every
  /// offset below stays a valid clock value.
  pure val L2_TABLE_NOW = 10 * minutes_per_hour

  /// Deadline offsets from the tick: past the grace and at it, past the
  /// heartbeat window and at it, just past the deadline, exactly at it, and
  /// before it -- plus one well inside each region.
  pure val L2_DEADLINE_OFFSETS = Set(
    -60,
    -(force_grace_minutes + 1),
    -force_grace_minutes,
    -30,
    -(heartbeat_stale_minutes + 1),
    -heartbeat_stale_minutes,
    -10,
    -1,
    0,
    1,
    60,
  )

  /// How old the drain heartbeat is at the tick, around the stale boundary.
  pure val L2_HEARTBEAT_AGES = Set(
    0,
    l2_tick_minutes,
    heartbeat_stale_minutes,
    heartbeat_stale_minutes + 1,
    40,
  )

  /// How long ago the detector first saw the node still there with the target
  /// at zero (-1: it has not), around the stop-latency boundary.
  pure val L2_STOPPING_AGES = Set(-1, 0, stop_latency_minutes, stop_latency_minutes + 1, l2_tick_minutes)

  /// A world whose next event is one L2 tick at minute `t`, with the lease,
  /// drain.json, the carried read-failure run and the pool exactly as given.
  /// `pool` is 0 (no node), 1 (live) or 2 (target zero, node still there).
  /// L1 is not running and L3 has fired, so nothing but L2 can move.
  action l2WorldAt(
    t: int,
    deadline: int,
    gen: int,
    readable: bool,
    failures: int,
    drainState: DrainState,
    reason: DrainReason,
    heartbeat: int,
    drainGen: int,
    pool: int,
    stoppingSince: int,
  ): bool = all {
    lease' = { deadline: deadline, gen: gen, granted: deadline, readable: readable, wokenAt: 0 },
    drain' = {
      ...emptyDrain,
      state: drainState,
      reason: reason,
      heartbeat: heartbeat,
      startedAt: heartbeat,
      leaseGen: drainGen,
    },
    enforce' = { ...emptyEnforce, leaseReadFailures: failures, stoppingSince: stoppingSince },
    cluster' = { ...asleepCluster, nodes: if (pool == 0) 0 else 1, stopping: pool == 2 },
    clock' = {
      now: t - 1,
      l1Due: t + l1_tick_minutes,
      l2Due: t,
      l3At: HORIZON,
      l3Fired: true,
      nodeGoneDue: if (pool == 2) t + l2_tick_minutes + 1 else NEVER,
    },
    evidence' = { ...noEvidence, leaseEverUnreadable: not(readable) },
    l1Last' = { branch: "", ticks: 0 },
  }

  /// One random row of the L2 table.
  action l2World = {
    nondet deadlineOffset = oneOf(L2_DEADLINE_OFFSETS)
    nondet heartbeatAge = oneOf(L2_HEARTBEAT_AGES)
    nondet readable = oneOf(Set(true, false))
    nondet failures = oneOf(0.to(lease_read_failure_threshold))
    nondet drainState = oneOf(Set(DrainNone, Draining, Drained, DrainFailed))
    nondet reason = oneOf(Set(DeadlinePassed, IdleZeroRunning, LeaseUnreadable))
    nondet staleRecord = oneOf(Set(true, false))
    nondet pool = oneOf(Set(0, 1, 2))
    nondet stoppingAge = oneOf(L2_STOPPING_AGES)
    l2WorldAt(
      L2_TABLE_NOW,
      L2_TABLE_NOW + deadlineOffset,
      7,
      readable,
      failures,
      drainState,
      reason,
      L2_TABLE_NOW - heartbeatAge,
      if (staleRecord) 6 else 7,
      pool,
      if (stoppingAge < 0) -1 else L2_TABLE_NOW - stoppingAge,
    )
  }

  /// Re-roll the world or take the tick. Traces of this step are what the Go
  /// replay reads: every l2* branch in them is one row checked twice, and a tick
  /// straight after a tick checks the carried read-failure run as well.
  action l2WorldStep = any { l2World, l2Tick }

  // --------------------------------------------------------------------------
  // L1, one tick at a time.
  //
  // The same idea for L1's thirteen branches: `just spec-check` samples
  // l1WorldStep traces -- a random observation, then the tick that decides it
  // -- and TestDecideL1AgreesWithTheModel replays each tick through the Go
  // DecideL1, which must take the same branch and write the same drain.json,
  // the same replica counts, the same suspends and the same pod deletions.
  // --------------------------------------------------------------------------

  pure val L1_TABLE_NOW = 10 * minutes_per_hour

  /// Where each actor is in the sampled world.
  type Placement =
    | AtRest
    | Awake
    | Checkpointing
    | Doomed
    | Crashed
    | Deleting
    | Gone

  pure def placed(p: int -> Placement, s: Placement): Set[int] = ACTORS.filter(a => p.get(a) == s)

  /// A world whose next event is one L1 tick at minute `t`.
  action l1WorldAt(
    t: int,
    deadline: int,
    readable: bool,
    wokenAt: int,
    drainState: DrainState,
    reason: DrainReason,
    startedAt: int,
    drainGen: int,
    idleSince: int,
    baselineCrashed: Set[int],
    wedgeSeen: int -> int,
    placement: int -> Placement,
    goldenAwake: bool,
    templatePending: bool,
    routerReplicas: int,
    controllerReplicas: int,
    routerPod: bool,
    controllerPod: bool,
  ): bool = all {
    lease' = { deadline: deadline, gen: 7, granted: deadline, readable: readable, wokenAt: wokenAt },
    drain' = {
      state: drainState,
      heartbeat: startedAt,
      startedAt: startedAt,
      leaseGen: drainGen,
      reason: reason,
      idleSince: idleSince,
      baselineCrashed: baselineCrashed,
      wedgeSeen: wedgeSeen,
    },
    enforce' = emptyEnforce,
    cluster' = {
      nodes: 1,
      stopping: false,
      awake: placed(placement, Awake),
      checkpointing: placed(placement, Checkpointing),
      doomed: placed(placement, Doomed),
      crashed: placed(placement, Crashed),
      deleting: placed(placement, Deleting),
      gone: placed(placement, Gone),
      goldenAwake: goldenAwake,
      templatePending: templatePending,
      routerReplicas: routerReplicas,
      controllerReplicas: controllerReplicas,
      routerPod: routerPod or routerReplicas == 1,
      controllerPod: controllerPod or controllerReplicas == 1,
      reaperAlive: true,
    },
    clock' = {
      now: t - 1,
      l1Due: t,
      l2Due: t + l2_tick_minutes,
      l3At: HORIZON,
      l3Fired: true,
      nodeGoneDue: NEVER,
    },
    evidence' = noEvidence,
    l1Last' = { branch: "", ticks: 0 },
  }

  pure val L1_OFFSETS = Set(-61, -31, -30, -29, -10, -1, 0, 1, 30)

  /// One random L1 observation.
  action l1World = {
    val t = L1_TABLE_NOW
    nondet deadlineOffset = oneOf(L1_OFFSETS)
    nondet readable = oneOf(Set(true, false))
    nondet wokenOffset = oneOf(L1_OFFSETS)
    nondet drainState = oneOf(Set(DrainNone, Draining, Drained, DrainFailed))
    nondet reason = oneOf(Set(DeadlinePassed, IdleZeroRunning, LeaseUnreadable))
    nondet startedOffset = oneOf(L1_OFFSETS)
    nondet staleRecord = oneOf(Set(true, false))
    nondet idleOffset = oneOf(Set(-1, -31, -30, -29, -10, 0))
    nondet baseline = oneOf(ACTORS.powerset())
    nondet placement = oneOf(ACTORS.setOfMaps(Set(AtRest, Awake, Checkpointing, Doomed, Crashed, Deleting, Gone)))
    nondet wedgeAge = oneOf(Set(0, wedge_clear_minutes - 1, wedge_clear_minutes))
    nondet goldenAwake = oneOf(Set(true, false))
    nondet templatePending = oneOf(Set(true, false))
    nondet routerReplicas = oneOf(Set(0, 1))
    nondet controllerReplicas = oneOf(Set(0, 1))
    nondet routerPod = oneOf(Set(true, false))
    nondet controllerPod = oneOf(Set(true, false))
    // A third of the worlds are tidied into a barrier that holds -- every
    // actor at rest or already crashed at the baseline, no golden work, both
    // counts and pods at zero -- or `drained` would almost never be sampled.
    nondet tidy = oneOf(Set(0, 1, 2))
    val atRest = ACTORS.mapBy(a => if (baseline.contains(a)) Crashed else AtRest)
    l1WorldAt(
      t,
      t + deadlineOffset,
      readable,
      t + wokenOffset,
      drainState,
      reason,
      t + startedOffset,
      if (staleRecord) 6 else 7,
      if (idleOffset < 0 and idleOffset != -1) t + idleOffset else if (idleOffset == 0) t else -1,
      baseline,
      placed(if (tidy == 0) atRest else placement, Deleting).mapBy(a => t - wedgeAge),
      if (tidy == 0) atRest else placement,
      tidy != 0 and goldenAwake,
      tidy != 0 and templatePending,
      if (tidy == 0) 0 else routerReplicas,
      if (tidy == 0) 0 else controllerReplicas,
      tidy != 0 and routerPod,
      tidy != 0 and controllerPod,
    )
  }

  /// Re-roll the world or take the tick.
  action l1WorldStep = any { l1World, l1Tick }

  // --------------------------------------------------------------------------
  // Invariants
  //
  // `Safety` carries the mandatory properties and nothing else. The model's
  // own frame check lives in `WellFormed` and is checked alongside it by `just
  // spec-check`, because a broken frame is a broken model, not a broken design.
  // --------------------------------------------------------------------------

  /// Every deadline the model ever grants sits at or before the nightly cap.
  /// The second disjunct covers `exe-sleep` and the rejected second writer,
  /// both of which set the deadline to the current instant -- never into the
  /// window the cap protects.
  val leaseRespectsCap = lease.deadline <= capAt or lease.deadline <= clock.now

  /// What the cap formula budgets for, and therefore what "normal operation"
  /// means when L3 fires. A trace that fails one of these has spent a budget
  /// the arithmetic never promised, and L4 -- the alert and the budget -- is
  /// the control there, not the cap.
  val normalOperation = and {
    leaseRespectsCap,
    not(evidence.drainEverFailed),
    not(evidence.leaseEverUnreadable),
  }

  /// MANDATORY 1. A stop that claims to be graceful never finds anything
  /// awake -- task actor or golden actor. This is the whole reason L1 exists:
  /// `exe-sleep` and an expired lease must cost nothing but a resume.
  ///
  /// The flag is monotone, so a later graceful stop over an empty cluster
  /// cannot paper over an earlier one that lost an actor.
  val NoCrashOnGracefulSleep = not(evidence.gracefulCrash)

  /// MANDATORY 2. A stop that claims to be graceful never follows a crash
  /// since its drain began. A crashed actor is not awake, so "nothing awake"
  /// alone would call a drain that lost an actor graceful -- and nobody would
  /// be paged. The baseline in drain.json is what tells the two apart.
  val NoSilentLoss = not(evidence.silentLoss)

  /// MANDATORY 3. L3 has no logic, so nothing in the code keeps it off an
  /// awake actor -- arithmetic does. The cap hour is RE-DERIVED here from
  /// l3_daily_stop_local_hour and the four latency terms; the stored
  /// nightly_cap_local_hour appears exactly once, as the thing being checked.
  /// Trusting the stored 3 would make this invariant a tautology.
  val L3NeverHitsAwakeActor = and {
    // 04:00 - (1 + 30 + 10 + 19) minutes = 03:00
    nightly_cap_from_formula == nightly_cap_local_hour,
    // and the cap instant really is a full worst-case budget before L3
    capAt + l1_tick_minutes + drain_ceiling_minutes + l2_tick_minutes + slack_minutes
      == clock.l3At,
    // therefore, in normal operation, L3 has never fired on an awake actor
    normalOperation implies not(evidence.l3HitAwakeActor),
  }

  /// MANDATORY 4. Bounded BILLING, written as a safety property.
  ///
  /// Quint has no fairness, so "the node eventually leaves" cannot be stated
  /// as a temporal formula: the unfair trace where the schedulers simply never
  /// fire would falsify it. The model instead makes the schedulers -- and the
  /// node's own departure -- the ONLY way the clock moves, and lets an event
  /// fire only when it is the earliest one scheduled. That turns "eventually"
  /// into arithmetic -- if the clock has got past deadline + bound, the event
  /// that had to end the billing has necessarily already happened.
  ///
  /// `cluster.nodes` counts billing instances, so this is about money, not
  /// decisions (inbox M18): the bound includes stop_latency_minutes, and holds
  /// only while the real stop latency is within it. awake_bound_minutes holds
  /// whenever L2's last read of the lease succeeded; blind_awake_bound_minutes
  /// holds regardless.
  val NodesEventuallyZero = and {
    (clock.now > lease.deadline + awake_bound_minutes and enforce.leaseReadFailures == 0)
      implies cluster.nodes == 0,
    clock.now > lease.deadline + blind_awake_bound_minutes implies cluster.nodes == 0,
  }

  /// MANDATORY 5. A lease the operator was granted is honoured: no stop taken
  /// from a lease L2 could actually READ ever lands before the granted
  /// deadline -- except L2's idle stop about the current generation, which is
  /// the plan's own rule (nothing awake for idle_zero_running_minutes, every
  /// actor suspended; an extend takes it away). The stale-`drained` race is
  /// the case that matters -- L1 wrote `drained`, the operator extended, and
  /// L2 must not act on the old record -- and it is blocked twice over: the
  /// deadline has moved into the future, and the drain record names an older
  /// lease generation.
  ///
  /// Deliberately NOT covered: l2ReadFailedAtThreshold. That branch stops the
  /// pool precisely because it cannot read the lease, so it cannot know whether
  /// the lease is live; the compensating control is the notification and L1's
  /// own drain on the same signal.
  val ExtendBeatsStaleDrained = not(evidence.stoppedDespiteLiveLease)

  /// MANDATORY 6. The only pod L1 ever deletes on its own -- a wedged actor's
  /// worker -- never hosts anything awake or mid-checkpoint. Elapsed time alone
  /// cannot tell a wedge from a slow checkpoint, so L1 only clears an actor
  /// that is already being deleted.
  val ClearingNeverLosesState = not(evidence.clearedLiveActor)

  val Safety = and {
    NoCrashOnGracefulSleep,
    NoSilentLoss,
    L3NeverHitsAwakeActor,
    NodesEventuallyZero,
    ExtendBeatsStaleDrained,
    ClearingNeverLosesState,
  }

  /// The lemma NoCrashOnGracefulSleep rests on, checked separately so that a
  /// regression points at the cause instead of at the symptom: while a
  /// `drained` record exists, nothing can wake an actor, and nothing is awake.
  ///
  /// It holds because every way an actor wakes needs a pod or a template that
  /// the barrier has already removed: autoResume needs a router pod,
  /// rawResume and operatorResume a controller pod, goldenResume a pending
  /// template (and only the controller creates templates). Break the barrier
  /// -- leave the router open, the controller up, count a scale patch as a
  /// terminated pod, or forget Substrate's own reconciler -- and this lemma
  /// fails first, followed by NoCrashOnGracefulSleep.
  val DrainedRecordStaysTrue = drain.state == Drained implies and {
    not(cluster.routerPod),
    not(cluster.controllerPod),
    storeAwake == Set(),
    not(cluster.goldenAwake),
    not(cluster.templatePending),
  }

  /// Not a stated property of the design but of its DETECTION: a node that
  /// keeps billing with the pool's target at zero is noticed within two L2
  /// ticks. Holds vacuously in the decided design, where the node leaves in
  /// stop_latency_minutes; pdbHoldsTheDrain is where it earns its keep.
  val SlowStopIsPaged =
    (cluster.stopping and clock.now > clock.nodeGoneDue - stop_latency_actual + 2 * l2_tick_minutes)
      implies enforce.stopLatencyAlarm

  /// Not a design property -- a check that the model is not lying. The actor
  /// states partition ACTORS, nothing is awake without a live node, and the
  /// clock never runs backwards past a due time.
  val WellFormed = and {
    cluster.nodes == 0 implies and {
      not(cluster.stopping),
      cluster.awake == Set(),
      cluster.checkpointing == Set(),
      not(cluster.routerPod),
      not(cluster.controllerPod),
      not(cluster.goldenAwake),
    },
    cluster.stopping implies and {
      cluster.nodes == 1,
      cluster.awake == Set(),
      cluster.checkpointing == Set(),
      not(cluster.routerPod),
      not(cluster.controllerPod),
      not(cluster.goldenAwake),
    },
    cluster.awake.size() + cluster.checkpointing.size() + cluster.doomed.size()
      + cluster.crashed.size() + cluster.deleting.size() + cluster.gone.size()
      == cluster.awake.union(cluster.checkpointing).union(cluster.doomed)
           .union(cluster.crashed).union(cluster.deleting).union(cluster.gone).size(),
    cluster.awake.union(cluster.checkpointing).union(cluster.doomed)
      .union(cluster.crashed).union(cluster.deleting).union(cluster.gone).subseteq(ACTORS),
    clock.now <= clock.l2Due,
    lease.deadline >= 0,
    enforce.leaseReadFailures >= 0,
  }
}

// ============================================================================
// REJECTED DESIGN 1 -- two writers for lease.json
//
// Scope: lease.json is written by `wake`, `extend` and `sleep`, all of which
//   run from the operator's Mac. The rejected alternative let a second process
//   write it too -- the shape that keeps suggesting itself is the reaper
//   "normalising" the object from inside the cluster, or a retried CLI
//   invocation from a second shell.
// Accepted by: the operator, plan section 3.2 ("1 つのオブジェクトの書き手は
//   1 つだけ" -- one writer per object) and the sub-table that names the writer
//   of each of the three objects.
// Compensating control: none is possible, which is why the design is a rule
//   rather than a mitigation. The generation precondition does NOT substitute:
//   the run below has the second writer follow the protocol correctly and still
//   destroy the operator's lease, because a precondition stops a lost update,
//   not a second author of intent. The controls are that `exe-reaper` has no
//   subcommand that writes lease.json outside wake/extend/sleep, reviews keep
//   it that way, and IAM grants the reaper and the enforcer write access to
//   their own object only.
// ============================================================================
module twoWriterLease {
  import leaseCore(
    two_writer_lease = true,
    naive_shrink_first = false,
    router_left_open = false,
    controller_left_up = false,
    scale_is_barrier = false,
    golden_ignored = false,
    stop_latency_actual = 5,
  ).*

  /// EXPECTED TO FAIL (ExtendBeatsStaleDrained). The operator is granted an
  /// hour; the second writer puts the deadline back to now; L1 dutifully
  /// drains the lease it can see and writes `drained` against the current
  /// generation; L2 dutifully stops a cluster whose operator was promised 50
  /// more minutes. Every layer behaved. The design did not.
  run twoWritersLoseTheOperatorsLease =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(rogueLeaseWrite)
      .then(l1Tick)                       // 1: expired -> draining, router to 0
      .then(l1Tick)                       // 2: nothing awake -> controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 3: no pod left -> drained
      .then(6.reps(_ => l1Tick))          // 4..9: settled, waiting for L2
      .then(l2Tick)                       // 10: drained -> pool to zero
      .expect(Safety)
}

// ============================================================================
// REJECTED DESIGN 2 -- shrink the pool first, suspend afterwards
//
// Scope: the drain order inside `exe-reaper reap`. The rejected alternative is
//   the one anybody writes first: the lease expired, so scale the pool to zero
//   and let Kubernetes tidy up.
// Accepted by: the operator, plan section 3.2, L1's numbered procedure -- the
//   resume paths close, AX suspends every awake task, every actor is confirmed
//   SUSPENDED, and only then is `drained` written. L2 is what touches the pool.
// Compensating control: none, again by design. Removing the worker pod under an
//   awake actor CRASHES it, which loses the actor's state and its snapshot;
//   nothing downstream can recover that. The structural control is that L1 has
//   no code path to the GKE node-pool API at all -- it holds a KSA scoped to the
//   cluster, not the nodePools.setSize permission. Keep it that way and this
//   variant is unreachable.
// ============================================================================
module naiveShrinkFirst {
  import leaseCore(
    two_writer_lease = false,
    naive_shrink_first = true,
    router_left_open = false,
    controller_left_up = false,
    scale_is_barrier = false,
    golden_ignored = false,
    stop_latency_actual = 5,
  ).*

  /// EXPECTED TO FAIL (NoCrashOnGracefulSleep). An operator types `exe-sleep`
  /// with one task awake. One minute later the pool is going and so is the
  /// task -- and the stop is recorded as graceful, so nothing even alerts.
  run shrinkingFirstCrashesTheRunningActor =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(sleep)
      .then(l1Tick)                       // 1: expired -> "graceful" shrink
      .expect(Safety)
}

// ============================================================================
// REJECTED DESIGN 3 -- leave the router open
//
// Scope: L1's first drain step. The rejected alternative reasoned that
//   suspending through AX is enough, so there is no need to touch atenet-router
//   -- leave the data path alone so `ax ssh` keeps working until the last
//   moment.
// Accepted by: the operator, plan section 3.2 -- "atenet-router を 0 台にする
//   (router 経由の自動 resume と `ax ssh` を止める)", explicitly BEFORE the
//   suspends.
// Compensating control: none available at the controller. The router resumes a
//   SUSPENDED actor on connection without consulting the ax-controller or
//   lease.json, so no guard added to `ax-job` / `ax-exec` can see it coming.
//   Taking the replicas to zero, and waiting for the pod to be gone, is the
//   control.
// ============================================================================
module routerLeftOpen {
  import leaseCore(
    two_writer_lease = false,
    naive_shrink_first = false,
    router_left_open = true,
    controller_left_up = false,
    scale_is_barrier = false,
    golden_ignored = false,
    stop_latency_actual = 5,
  ).*

  /// EXPECTED TO FAIL (NoCrashOnGracefulSleep). The drain completes honestly:
  /// nothing was awake, so `drained` is true when it is written. Then a
  /// connection arrives, the router resumes an actor, and L2 -- reading a
  /// `drained` that was correct a few minutes ago -- performs a graceful stop
  /// on a cluster that is no longer drained.
  run leftOpenRouterRevivesAnActorAfterDrained =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(10.reps(_ => l1Tick))         // 1..9 idle; 10: expiry -> draining,
                                          //    router NOT closed
      .then(l2Tick)                       // 10: draining, heartbeat fresh -> wait
      .then(l1Tick)                       // 11: nothing awake -> controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 12: drained (the router still serves)
      .then(autoResume)                   // a connection resumes an actor
      .then(7.reps(_ => l1Tick))          // 13..19: settled; L1 never revisits `drained`
      .then(l2Tick)                       // 20: "graceful" stop over an awake actor
      .expect(Safety)
}

// ============================================================================
// REJECTED DESIGN 4 -- leave the ax-controller up
//
// Scope: L1's quiesce step (Phase 6). The rejected alternative closes the
//   router and suspends through AX, and stops there: the controller keeps
//   running so AX stays responsive.
// Accepted by: the manager, Phase 6 plan D2 -- the controller executes any
//   ResumeTask, including a raw `ax resume` that bypasses ax-job's lease check,
//   and ax-server writes that request into Redis at once
//   (internal/server/server.go). With the controller up, nothing stands
//   between a raw resume and L2's graceful stop.
// Compensating control: none at the wrappers -- a raw `ax resume` is exactly
//   the path that bypasses them. Taking the controller to zero, and waiting
//   for its pod to be gone, is the control.
// ============================================================================
module controllerLeftUp {
  import leaseCore(
    two_writer_lease = false,
    naive_shrink_first = false,
    router_left_open = false,
    controller_left_up = true,
    scale_is_barrier = false,
    golden_ignored = false,
    stop_latency_actual = 5,
  ).*

  /// EXPECTED TO FAIL (NoCrashOnGracefulSleep). `drained` is written with the
  /// controller still running; the operator types a raw `ax resume`; L2 stops
  /// "gracefully" over the actor it woke.
  run controllerLeftUpLetsARawResumeThrough =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(10.reps(_ => l1Tick))         // 10: expiry -> draining, router to 0
      .then(l2Tick)                       // 10: wait
      .then(podsTerminate)                // the router pod goes
      .then(l1Tick)                       // 11: nothing awake -> drained
      .then(rawResume)                    // the controller executes it
      .then(8.reps(_ => l1Tick))          // 12..19: settled
      .then(l2Tick)                       // 20: "graceful" stop over an awake actor
      .expect(Safety)
}

// ============================================================================
// REJECTED DESIGN 5 -- treat a scale patch as the barrier
//
// Scope: L1's wait after the quiesce (Phase 6). The rejected alternative
//   writes `drained` as soon as both replica counts read zero.
// Accepted by: the manager, Phase 6 plan D2 (codex review, pass 1 #2) -- a
//   replica count of zero does not stop the pod that is running: it keeps
//   serving until it has terminated, and it can still execute a resume that is
//   already in flight.
// Compensating control: none; waiting until the pod list is empty is the
//   control.
// ============================================================================
module scaleIsNotABarrier {
  import leaseCore(
    two_writer_lease = false,
    naive_shrink_first = false,
    router_left_open = false,
    controller_left_up = false,
    scale_is_barrier = true,
    golden_ignored = false,
    stop_latency_actual = 5,
  ).*

  /// EXPECTED TO FAIL (NoCrashOnGracefulSleep). Both counts are zero, so
  /// `drained` is written -- and the controller pod, still terminating,
  /// executes a raw resume. L2 stops "gracefully" over it.
  run scaleAloneLetsALingeringControllerResume =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(10.reps(_ => l1Tick))         // 10: expiry -> draining, router to 0
      .then(l2Tick)                       // 10: wait
      .then(l1Tick)                       // 11: nothing awake -> controller to 0
      .then(l1Tick)                       // 12: both counts 0 -> "drained"
      .then(rawResume)                    // the lingering controller pod runs it
      .then(podsTerminate)
      .then(7.reps(_ => l1Tick))          // 13..19: settled
      .then(l2Tick)                       // 20: "graceful" stop over an awake actor
      .expect(Safety)
}

// ============================================================================
// REJECTED DESIGN 6 -- ignore Substrate's golden reconciler
//
// Scope: L1's wait for templates (Phase 6). The rejected alternative checks
//   only the task atespace: AX and the router are down, so nothing can wake
//   an actor.
// Accepted by: the manager, Phase 6 plan D2 (codex review, pass 2 #1) --
//   Substrate's ActorTemplateReconciler runs inside ate-api-server, which the
//   drain does not stop, and calls ResumeActor on the golden actor of every
//   template that is not terminal (template_reconciler.go).
// Compensating control: none; waiting until every template is terminal is the
//   control, and a template still in flight at the ceiling fails the drain.
// ============================================================================
module goldenIgnored {
  import leaseCore(
    two_writer_lease = false,
    naive_shrink_first = false,
    router_left_open = false,
    controller_left_up = false,
    scale_is_barrier = false,
    golden_ignored = true,
    stop_latency_actual = 5,
  ).*

  /// EXPECTED TO FAIL (NoCrashOnGracefulSleep). A task with a new image has
  /// just been created, so a template is in flight; the drain ignores it and
  /// writes `drained`; the reconciler resumes the golden actor; L2 stops
  /// "gracefully" over it.
  run goldenReconcilerResumesAfterDrained =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(templateCreated)
      .then(10.reps(_ => l1Tick))         // 10: expiry -> draining, router to 0
      .then(l2Tick)                       // 10: wait
      .then(l1Tick)                       // 11: nothing awake -> controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 12: "drained"
      .then(goldenResume)                 // Substrate resumes the golden actor
      .then(7.reps(_ => l1Tick))          // 13..19: settled
      .then(l2Tick)                       // 20: "graceful" stop over it
      .expect(Safety)
}

// ============================================================================
// REJECTED ASSUMPTION -- a disruption budget holds the drain
//
// Scope: GKE's side of a stop (inbox M18, layer 2). NodesEventuallyZero bounds
//   BILLING, so it rests on how long the node takes to leave after setSize(0):
//   stop_latency_minutes, measured on the real stack. The Phase 4 incident was
//   a PodDisruptionBudget on ate-api-server holding the drain until the
//   manager patched it -- GKE waits on budgets for up to an hour.
// Accepted by: the manager, inbox M18 / M19 C1 -- nothing may delay a stop
//   unless it protects state, so every budget outside kube-/gke- is opened by
//   the install step, and the install fails on any budget that could still
//   hold a stop.
// Compensating control: that install check, and L2's stop-latency detector,
//   which pages when the node outlives stop_latency_minutes
//   (SlowStopIsPaged, checked on this instance by `just spec-check`).
// ============================================================================
module pdbHoldsTheDrain {
  import leaseCore(
    two_writer_lease = false,
    naive_shrink_first = false,
    router_left_open = false,
    controller_left_up = false,
    scale_is_barrier = false,
    golden_ignored = false,
    stop_latency_actual = 60,
  ).*

  /// EXPECTED TO FAIL (NodesEventuallyZero). A graceful stop, correct in every
  /// decision -- and the node bills for another hour, far past the bound.
  run aDisruptionBudgetOutlivesTheBound =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(10.reps(_ => l1Tick))         // 10: expiry -> draining
      .then(l2Tick)                       // 10: wait
      .then(l1Tick)                       // 11: controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 12: drained
      .then(7.reps(_ => l1Tick))          // 13..19
      .then(l2Tick)                       // 20: graceful stop; the node stays
      .then(6.reps(_ => l2Tick))          // 30..80: past deadline + bound, billing
      .expect(Safety)

  /// ...and the detector does see it: two L2 ticks after the stop, the alarm
  /// is up. A passing run, checked by `just spec-check` beside the failing one.
  run theSlowStopIsPagedTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(10.reps(_ => l1Tick))
      .then(l2Tick)
      .then(l1Tick)
      .then(podsTerminate)
      .then(l1Tick)
      .then(7.reps(_ => l1Tick))
      .then(l2Tick)                       // 20: graceful stop
      .then(l2Tick)                       // 30: the node is still there: remember
      .expect(not(enforce.stopLatencyAlarm) and enforce.stoppingSince == 30)
      .then(l2Tick)                       // 40: still there past the latency: alarm
      .expect(and { enforce.stopLatencyAlarm, SlowStopIsPaged, cluster.nodes == 1 })
}

// ============================================================================
// THE DECIDED DESIGN. This module is `lease`, so it is what `quint run`,
// `quint test` and `quint verify` pick up by default from lease.qnt.
//
// The `*Test` runs below are the recorded behaviours from plan section 3.2,
// the Phase 3 and Phase 6 e2e lists and the review notes, replayed
// deterministically. Every tick count in them is derived from the constants
// and spelled out in the comment beside it; the discrete-event clock makes the
// interleavings forced, so these are replays, not samples.
// ============================================================================
module lease {
  import leaseCore(
    two_writer_lease = false,
    naive_shrink_first = false,
    router_left_open = false,
    controller_left_up = false,
    scale_is_barrier = false,
    golden_ignored = false,
    stop_latency_actual = 5,
  ).*

  // --- L0: the cap ---------------------------------------------------------

  /// The nightly cap clamps the maximum lease. Window starts at local midnight,
  /// so the cap instant is 03:00 and an eight-hour request lands there.
  run capClampsTheMaxLeaseTest =
    initWith(l3_daily_stop_local_hour * minutes_per_hour)
      .then(wakeFor(max_lease_minutes))
      .expect(and {
        lease.deadline == capAt,
        lease.deadline == nightly_cap_local_hour * minutes_per_hour,
        lease.deadline < max_lease_minutes,
      })

  /// A request longer than the maximum lease is refused outright.
  run overlongLeaseIsRefusedTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(max_lease_minutes + l2_tick_minutes).fail())

  /// Inside the cap window -- after 03:00, before L3 at 04:00 -- there is no
  /// lease left to grant, so `exe-wake` fails instead of starting a node with a
  /// zero-length lease and an open router. The model is where this requirement
  /// came from; without the refusal, the router can auto-resume an actor that
  /// L3 then crashes.
  run wakeIsRefusedInsideTheCapWindowTest =
    initWith(cap_gap_minutes)
      .then(wakeFor(default_lease_minutes).fail())

  // --- L1 + L2: the graceful path ------------------------------------------

  /// `exe-sleep` with one task awake: L1 closes the router, suspends the task,
  /// closes the controller, waits for both pods to go, writes `drained`, and L2
  /// stops an empty cluster; the node leaves stop_latency_minutes later.
  /// Nothing crashes, nothing is notified.
  run gracefulSleepLosesNothingTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(sleep)
      .then(l1TickWith(true))             // 1: draining, router to 0
      .then(l1TickWith(true))             // 2: suspend -> checkpointing
      .then(checkpointDone)
      .then(podsTerminate)                // the router pod goes
      .then(l1Tick)                       // 3: nothing awake -> controller to 0
      .then(podsTerminate)                // the controller pod goes
      .then(l1Tick)                       // 4: drained
      .then(5.reps(_ => l1Tick))          // 5..9
      .then(l2Tick)                       // 10: drained -> target to zero
      .expect(and { cluster.stopping, cluster.nodes == 1, clock.nodeGoneDue == 15 })
      .then(nodeGoneTick)                 // 15: the node leaves
      .expect(and {
        cluster.nodes == 0,
        cluster.crashed == Set(),
        cluster.doomed == Set(),
        not(evidence.gracefulCrash),
        not(evidence.silentLoss),
        enforce.last == StoppedOnDrained,
        not(enforce.notified),
        evidence.lastShrink == GracefulStop,
        Safety,
      })

  /// A checkpoint that takes most of the ceiling still ends gracefully: L1
  /// waits for it rather than guessing, and nothing about elapsed time alone
  /// makes it act.
  run slowCheckpointStillDrainsTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(sleep)
      .then(l1TickWith(true))             // 1: draining
      .then(l1TickWith(true))             // 2: suspend -> checkpointing
      .then(l1Tick)                       // 3: nothing awake -> controller to 0
      .then(podsTerminate)                // both pods go
      .then(10.reps(_ => anyTick))        // 4..9 wait, L2 10 waits, 10..12 wait
      .then(checkpointDone)               // the checkpoint lands at minute 12
      .then(l1Tick)                       // 13: drained
      .then(6.reps(_ => l1Tick))          // 14..19
      .then(l2Tick)                       // 20: graceful stop
      .expect(and {
        enforce.last == StoppedOnDrained,
        not(enforce.notified),
        cluster.doomed == Set(),
        Safety,
      })

  /// Nothing has been awake for idle_zero_running_minutes: L1 drains even
  /// though the lease is live, and L2 STOPS the pool rather than billing on
  /// to the deadline (review note, Phase 3: an idle `drained` before the
  /// deadline must actually stop billing).
  ///
  /// Tick arithmetic: the first idle tick is L1's at minute 1, so the idle
  /// clock expires at 1 + 30 = 31. Events strictly before it: L1 at 1..30 (30)
  /// and L2 at 10, 20, 30 (3) = 33.
  run idleDrainStopsBillingTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(33.reps(_ => anyTick))
      .then(l1Tick)                       // 31: idle -> draining, router to 0
      .expect(and { drain.state == Draining, drain.reason == IdleZeroRunning, clock.now < lease.deadline })
      .then(l1Tick)                       // 32: controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 33: drained
      .then(6.reps(_ => l1Tick))          // 34..39
      .then(l2Tick)                       // 40: idle drained, lease live -> stop
      .then(nodeGoneTick)                 // 45: gone, fifteen minutes before the deadline
      .expect(and {
        cluster.nodes == 0,
        clock.now < lease.deadline,
        enforce.last == StoppedOnIdleDrained,
        not(enforce.notified),
        not(evidence.stoppedDespiteLiveLease),
        Safety,
      })

  /// `exe-sleep` after an idle drain: the `drained` record is about the older
  /// lease, so L1 drains again for the new one instead of settling on it --
  /// and the stop is graceful, with no page. Before this rule the old record
  /// stranded L1, and L2 forced the stop a heartbeat window later (review
  /// note, Phase 3).
  run sleepAfterIdleDrainIsGracefulTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(33.reps(_ => anyTick))
      .then(l1Tick)                       // 31: idle -> draining
      .then(l1Tick)                       // 32: controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 33: drained, about generation 1
      .then(sleep)                        // generation 2, deadline now
      .then(l1Tick)                       // 34: the record is stale -> draining again
      .expect(and { drain.state == Draining, drain.leaseGen == lease.gen, drain.reason == DeadlinePassed })
      .then(l1Tick)                       // 35: drained, about generation 2
      .then(4.reps(_ => l1Tick))          // 36..39
      .then(l2Tick)                       // 40
      .expect(and {
        enforce.last == StoppedOnDrained,
        not(enforce.notified),
        Safety,
      })

  /// An extend does not restart the idle clock: with nothing awake the node
  /// drains and stops anyway (Phase 3 finding 3, kept). A new session is a
  /// `wake`, which is the one write that moves wokenAt.
  run extendDoesNotRestartTheIdleClockTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(33.reps(_ => anyTick))
      .then(l1Tick)                       // 31: idle -> draining
      .then(l1Tick)                       // 32
      .then(podsTerminate)
      .then(l1Tick)                       // 33: drained
      .then(extendFor(default_lease_minutes))
      .then(l1Tick)                       // 34: still idle -> draining again
      .then(l1Tick)                       // 35: drained about the extended lease
      .then(4.reps(_ => l1Tick))
      .then(l2Tick)                       // 40: idle stop, the extended lease live
      .expect(and { enforce.last == StoppedOnIdleDrained, Safety })

  /// ...and a wake after an idle stop restarts the idle clock and reopens both
  /// paths on L1's first tick.
  run wakeAfterIdleStopReopensTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(33.reps(_ => anyTick))
      .then(l1Tick)                       // 31
      .then(l1Tick)                       // 32
      .then(podsTerminate)
      .then(l1Tick)                       // 33: drained
      .then(6.reps(_ => l1Tick))
      .then(l2Tick)                       // 40: idle stop
      .then(nodeGoneTick)                 // 45
      .then(wakeFor(default_lease_minutes))
      .then(l1Tick)                       // 46: live lease, fresh idle clock -> cancel
      .expect(and {
        drain.state == DrainNone,
        cluster.routerReplicas == 1,
        cluster.controllerReplicas == 1,
        routerServing,
        controllerServing,
        Safety,
      })

  /// The whole night, end to end: a ten-minute lease, a graceful drain, and
  /// then L3 firing at 04:00 to find an empty pool. L3 springing harmlessly is
  /// the design's normal case, not an exception.
  ///
  /// Window starts at 02:00, so the cap is at 03:00 and L3 at 04:00.
  run fullNightEndsWithL3SpringingTest =
    initWith(2 * cap_gap_minutes)
      .then(wakeFor(l2_tick_minutes))
      .then(10.reps(_ => l1Tick))         // 1..10; the tick at 10 sees expiry
      .then(l2Tick)                       // 10: draining, heartbeat fresh -> wait
      .then(l1Tick)                       // 11: nothing awake -> controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 12: drained
      .then(7.reps(_ => l1Tick))          // 13..19
      .then(l2Tick)                       // 20: drained -> target to zero
      .then(nodeGoneTick)                 // 25
      .then(9.reps(_ => l2Tick))          // 30..110: nothing to enforce
      .then(l3Tick)                       // 120 = 04:00
      .expect(and {
        clock.l3Fired,
        clock.now == 2 * cap_gap_minutes,
        cluster.nodes == 0,
        cluster.crashed == Set(),
        not(evidence.l3HitAwakeActor),
        Safety,
      })

  // --- L1: every resume path, closed ------------------------------------------

  /// A raw `ax resume` lands while the controller pod is still terminating
  /// after the quiesce: the actor wakes, L1 sees it, brings the controller
  /// back, suspends it again, and only then writes `drained` (the 6.9 e2e,
  /// first boundary).
  run rawResumeDuringDrainIsSuspendedAgainTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(sleep)
      .then(l1TickWith(true))             // 1: draining, router to 0
      .then(l1TickWith(true))             // 2: suspend
      .then(checkpointDone)
      .then(l1Tick)                       // 3: controller to 0; its pod lingers
      .then(rawResume)                    // ...and executes a raw resume
      .then(podsTerminate)                // then both pods go
      .then(l1Tick)                       // 4: awake again -> controller back
      .expect(and { cluster.controllerReplicas == 1, drain.state == Draining })
      .then(l1TickWith(true))             // 5: suspend again
      .then(checkpointDone)
      .then(l1Tick)                       // 6: controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 7: drained
      .then(2.reps(_ => l1Tick))          // 8, 9
      .then(l2Tick)                       // 10: graceful stop over nothing
      .expect(and { enforce.last == StoppedOnDrained, cluster.doomed == Set(), Safety })

  /// After `drained` no resume path is left: the raw resume that bypasses the
  /// wrappers cannot even be taken, because no controller pod is there to
  /// execute it (the 6.9 e2e, second boundary). Neither is the router's.
  run noResumeAfterDrainedTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(sleep)
      .then(l1Tick)                       // 1: draining
      .then(l1Tick)                       // 2: controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 3: drained
      .expect(and { drain.state == Drained, not(controllerServing), not(routerServing), DrainedRecordStaysTrue })
      .then(rawResume.fail())

  /// A task with a new image arrives just before the drain: Substrate's
  /// reconciler is still driving its golden actor. L1 does not write `drained`
  /// until the template is terminal.
  run goldenFlowDuringDrainIsWaitedForTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(templateCreated)
      .then(goldenResume)
      .then(sleep)
      .then(l1Tick)                       // 1: draining
      .then(l1Tick)                       // 2: controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 3: golden work in flight -> wait
      .expect(and { drain.state == Draining, cluster.goldenAwake })
      .then(goldenSettles)                // the golden snapshot is written
      .then(l1Tick)                       // 4: drained
      .then(5.reps(_ => l1Tick))
      .then(l2Tick)                       // 10
      .expect(and { enforce.last == StoppedOnDrained, Safety })

  // --- L1: no silent loss ------------------------------------------------------

  /// The worker pod dies mid-checkpoint. The actor is lost, and the drain says
  /// so: `drain-failed`, and L2 forces and PAGES instead of calling it a
  /// graceful stop.
  run podLossDuringDrainPagesTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(sleep)
      .then(l1TickWith(true))             // 1: draining, baseline: nothing crashed
      .then(l1TickWith(true))             // 2: suspend -> checkpointing
      .then(workerPodLost)                // the pod dies mid-checkpoint
      .then(crashDetected)
      .then(l1Tick)                       // 3: a crash since the baseline -> lost
      .expect(and { drain.state == DrainFailed, evidence.drainEverFailed })
      .then(6.reps(_ => l1Tick))          // 4..9: settled
      .then(l2Tick)                       // 10: drain-failed -> forced, paged
      .expect(and {
        enforce.last == StoppedForced,
        enforce.notified,
        not(evidence.silentLoss),
        Safety,
      })

  /// An actor that was SUSPENDED when the drain began is resumed by a raw
  /// `ax resume`, and crashes -- all between two L1 ticks, so L1 never saw it
  /// awake. The baseline still catches it.
  run crashBetweenPollsPagesTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(sleep)
      .then(l1Tick)                       // 1: draining; nothing awake, nothing crashed
      .then(rawResume)                    // the controller is still up
      .then(workerPodLost)
      .then(crashDetected)
      .then(l1Tick)                       // 2: lost
      .expect(and { drain.state == DrainFailed, Safety })

  // --- L0 + L2: the stale-`drained` race -----------------------------------

  /// A successful extend invalidates a prior `drained`. L1 is alive, so it
  /// cancels the drain on its next tick and reopens both paths, and L2 finds a
  /// live lease -- the pool stays up, which is the entire point of typing
  /// `exe-extend`.
  run extendInvalidatesAPriorDrainedTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(sleep)
      .then(l1Tick)                       // 1: draining
      .then(l1Tick)                       // 2: controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 3: drained
      .then(extendFor(default_lease_minutes))
      .then(6.reps(_ => l1Tick))          // 4: a live lease -> cancel; 5..9
      .then(l2Tick)                       // 10
      .expect(and {
        cluster.nodes == 1,
        drain.state == DrainNone,
        routerServing,
        controllerServing,
        enforce.last == LeaseLive,
        not(evidence.stoppedDespiteLiveLease),
      })

  /// Same race with L1 dead, so nothing cancels the stale record. The lease
  /// generation is what saves it: the `drained` in drain.json is about
  /// generation 2, the lease is on generation 3, so L2 refuses to call it a
  /// graceful stop. It reads as NO record about this lease -- a heartbeat that
  /// stopped at the deadline -- so L2 waits out one heartbeat window and then
  /// forces with a notification. Conservative in the right direction -- a
  /// forced stop is loud, a mislabelled graceful one is silent.
  run staleDrainRecordForcesInsteadOfStoppingGracefullyTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(sleep)
      .then(l1Tick)                       // 1: draining
      .then(l1Tick)                       // 2: controller to 0
      .then(podsTerminate)
      .then(l1Tick)                       // 3: drained, about generation 2
      .then(extendFor(l2_tick_minutes))   // generation 3, deadline 13
      .then(l1Crash)
      .then(l2Tick)                       // 10: lease still live
      .then(l2Tick)                       // 20: expired 7 min ago, no record: wait
      .then(l2Tick)                       // 30: 17 min, still inside the window
      .expect(and { cluster.nodes == 1, enforce.last == WaitedForDrain })
      .then(l2Tick)                       // 40: 27 min > heartbeat_stale_minutes
      .expect(and {
        cluster.stopping,
        enforce.last == StoppedForced,
        enforce.notified,
        evidence.lastShrink == ForcedStop,
        not(evidence.stoppedDespiteLiveLease),
      })

  // --- L2: read failures ---------------------------------------------------

  /// One or two consecutive read failures do nothing at all. L1 is already
  /// draining on the same signal; a pool stopped on the first 503 would be a
  /// worse failure than the one it is reacting to.
  run twoReadFailuresDoNothingTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(l1Crash)                      // isolate L2: keep L1 out of the trace
      .then(leaseReadBreaks)
      .then(l2Tick)                       // 10: failure 1
      .then(l2Tick)                       // 20: failure 2
      .expect(and {
        cluster.nodes == 1,
        not(cluster.stopping),
        enforce.leaseReadFailures == lease_read_failure_threshold - 1,
        enforce.last == WaitedOnReadFailure,
        not(enforce.notified),
      })

  /// The threshold-th consecutive failure stops the pool blind and notifies.
  /// An actor is awake here and it is doomed -- accepted, because the
  /// alternative is a node nobody can switch off. The stop is recorded as
  /// forced, so NoCrashOnGracefulSleep is untouched and Safety still holds even
  /// though the lease was live.
  run thirdReadFailureForcesTheStopTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(l1Crash)
      .then(leaseReadBreaks)
      .then(3.reps(_ => l2Tick))          // 10, 20, 30
      .expect(and {
        clock.now == lease_read_failure_threshold * l2_tick_minutes,
        cluster.stopping,
        cluster.doomed == Set(1),
        enforce.last == StoppedOnReadFailures,
        enforce.notified,
        evidence.lastShrink == ForcedStop,
        not(evidence.gracefulCrash),
        clock.now < lease.granted,        // the lease really was still live
        Safety,
      })

  // --- L2: the two force branches -----------------------------------------

  /// The heartbeat stops. L2 waits while it is inside heartbeat_stale_ticks and
  /// forces on the tick after that, without waiting out the grace period --
  /// a reaper that has stopped writing is not going to finish.
  run staleHeartbeatForcesTheStopTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(sleep)
      .then(l1TickWith(false))            // 1: draining, heartbeat at minute 1
      .then(l1Crash)                      // the heartbeat stops here
      .then(l2Tick)                       // 10: 9 minutes stale -> wait
      .then(l2Tick)                       // 20: 19 minutes stale -> wait
      .then(l2Tick)                       // 30: past the stale window -> force
      .expect(and {
        clock.now == (heartbeat_stale_ticks + 1) * l2_tick_minutes,
        cluster.stopping,
        cluster.doomed == Set(1),
        enforce.last == StoppedForced,
        enforce.notified,
        evidence.lastShrink == ForcedStop,
        not(evidence.gracefulCrash),
      })

  /// The actor will not suspend. L1 keeps the heartbeat fresh -- so L2 keeps
  /// waiting -- right up to drain_ceiling_minutes, then writes `drain-failed`
  /// and L2 forces. The ceiling is what stops a live heartbeat from buying
  /// unlimited time.
  ///
  /// Tick arithmetic: the drain starts at minute 1, so the ceiling expires at
  /// minute 1 + drain_ceiling_minutes = 31. Events strictly before it are L1's
  /// ticks at 1..30 (30) plus L2's at 10, 20 and 30 (3) = 33. Afterwards L1
  /// idles at 32..39 (8) before L2's tick at 40 is next.
  run drainCeilingForcesTheStopTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(sleep)
      .then(33.reps(_ => anyTickStalling))
      .then(l1TickWith(false))            // 31: ceiling blown -> drain-failed
      .then(8.reps(_ => anyTickStalling)) // 32..39
      .then(l2Tick)                       // 40: drain-failed -> force
      .expect(and {
        evidence.drainEverFailed,
        cluster.stopping,
        cluster.doomed == Set(1),
        enforce.last == StoppedForced,
        enforce.notified,
        evidence.lastShrink == ForcedStop,
        not(evidence.gracefulCrash),
      })

  // --- L3 -----------------------------------------------------------------

  /// L3 on a cluster that was never woken: the last resort fires, finds zero
  /// nodes, and changes nothing. Window starts at 03:00, so L3 is 60 minutes
  /// away and `exe-wake` is refused for the whole window.
  run l3SpringsOnAnAsleepClusterTest =
    initWith(cap_gap_minutes)
      .then(5.reps(_ => l2Tick))          // 10..50: nothing to stop
      .then(l3Tick)                       // 60 = 04:00
      .expect(and {
        clock.l3Fired,
        cluster.nodes == 0,
        not(evidence.l3HitAwakeActor),
        // A sleeping pool is never "force-stopped" by L2, so nobody is paged
        // for a cluster that was never up.
        enforce.last == AlreadyStopped,
        not(enforce.notified),
        Safety,
      })

  // --- the L2 table, at its boundaries ----------------------------------------
  //
  // One run per row that decide.go's TestDecideL2 pins at a boundary, in model
  // minutes (the Go table uses one second where these use one minute). The
  // rows at random are TestDecideL2AgreesWithTheModel's job; these are the ones
  // the rule was once written wrong at.

  /// A wait world: a readable lease, one live node.
  action l2Row(deadlineOffset: int, drainState: DrainState, heartbeatAge: int): bool =
    l2WorldAt(
      L2_TABLE_NOW, L2_TABLE_NOW + deadlineOffset, 7, true, 0,
      drainState, DeadlinePassed, L2_TABLE_NOW - heartbeatAge, 7, 1, -1,
    )

  /// Past the grace, a heartbeat that is still arriving buys nothing.
  run l2TableGraceBeatsAFreshHeartbeatTest =
    l2Row(-(force_grace_minutes + 1), Draining, 0)
      .then(l2Tick)
      .expect(and { enforce.last == StoppedForced, cluster.stopping })

  /// Exactly at the grace it still does.
  run l2TableAtTheGraceAFreshHeartbeatWaitsTest =
    l2Row(-force_grace_minutes, Draining, 0)
      .then(l2Tick)
      .expect(and { enforce.last == WaitedForDrain, nodeLive })

  /// No record about this lease is a heartbeat that stopped at the deadline:
  /// exactly one window after it, L2 still waits...
  run l2TableNoRecordWaitsOneHeartbeatWindowTest =
    l2Row(-heartbeat_stale_minutes, DrainNone, 0)
      .then(l2Tick)
      .expect(and { enforce.last == WaitedForDrain, nodeLive })

  /// ...and a minute later it forces.
  run l2TableNoRecordForcesAfterTheWindowTest =
    l2Row(-(heartbeat_stale_minutes + 1), DrainNone, 0)
      .then(l2Tick)
      .expect(and { enforce.last == StoppedForced, cluster.stopping, enforce.notified })

  /// `drained` about this lease is a graceful stop at any time past the
  /// deadline, the grace included.
  run l2TableDrainedPastTheGraceIsGracefulTest =
    l2Row(-(force_grace_minutes + 1), Drained, 0)
      .then(l2Tick)
      .expect(and { enforce.last == StoppedOnDrained, not(enforce.notified) })

  /// Before the deadline, only an IDLE `drained` stops the pool...
  run l2TableIdleDrainedBeforeTheDeadlineStopsTest =
    l2WorldAt(L2_TABLE_NOW, L2_TABLE_NOW + 30, 7, true, 0, Drained, IdleZeroRunning, L2_TABLE_NOW, 7, 1, -1)
      .then(l2Tick)
      .expect(and { enforce.last == StoppedOnIdleDrained, not(enforce.notified) })

  /// ...a deadline `drained` about an older lease does not.
  run l2TableStaleIdleDrainedBeforeTheDeadlineWaitsTest =
    l2WorldAt(L2_TABLE_NOW, L2_TABLE_NOW + 30, 7, true, 0, Drained, IdleZeroRunning, L2_TABLE_NOW, 6, 1, -1)
      .then(l2Tick)
      .expect(and { enforce.last == LeaseLive, nodeLive })

  /// While the target is zero, a carried run of read failures is reset.
  run l2TableAtZeroTheReadFailureRunResetsTest =
    l2WorldAt(
      L2_TABLE_NOW, L2_TABLE_NOW - 60, 7, false, lease_read_failure_threshold - 1,
      DrainNone, NoReason, 0, 7, 0, -1,
    )
      .then(l2Tick)
      .expect(and { enforce.last == AlreadyStopped, enforce.leaseReadFailures == 0 })

  /// The detector remembers the first tick that finds the node still there
  /// with the target at zero...
  run l2TableStoppingIsRememberedTest =
    l2WorldAt(L2_TABLE_NOW, L2_TABLE_NOW - 60, 7, true, 0, DrainNone, NoReason, 0, 7, 2, -1)
      .then(l2Tick)
      .expect(and { enforce.stoppingSince == L2_TABLE_NOW, not(enforce.stopLatencyAlarm) })

  /// ...and a later tick past the latency raises the alarm.
  run l2TableStoppingPastTheLatencyAlarmsTest =
    l2WorldAt(
      L2_TABLE_NOW, L2_TABLE_NOW - 60, 7, true, 0, DrainNone, NoReason, 0, 7, 2,
      L2_TABLE_NOW - (stop_latency_minutes + 1),
    )
      .then(l2Tick)
      .expect(enforce.stopLatencyAlarm)

  // --- L1: wedges ---------------------------------------------------------------

  /// A delete that wedges holds a worker forever. After wedge_clear_minutes L1
  /// deletes that worker's pod -- and nothing else: the actor was already
  /// being deleted, so nothing is lost.
  run wedgedDeleteIsClearedTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(deleteTaskWith(true))         // the delete wedges
      .then(l1Tick)                       // 1: first seen
      .expect(and { cluster.deleting == Set(1), drain.wedgeSeen.get(1) == 1 })
      .then(12.reps(_ => anyTick))        // 2..10 and L2 at 10; 11: cleared
      .expect(and {
        cluster.deleting == Set(),
        cluster.gone == Set(1),
        not(evidence.clearedLiveActor),
        Safety,
      })

  // --- environment --------------------------------------------------------

  /// The node vanishes under an awake actor. The actor is lost, but the stop
  /// was nobody's decision, so it is not a graceful-sleep violation -- and the
  /// pool still ends at zero.
  run nodeLossIsNotAGracefulStopTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(nodeLoss)
      .expect(and {
        cluster.nodes == 0,
        cluster.doomed == Set(1),
        evidence.lastShrink == NodeGone,
        not(evidence.gracefulCrash),
        Safety,
      })
}
