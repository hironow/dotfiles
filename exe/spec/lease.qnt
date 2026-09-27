// -*- mode: quint -*-
//
// lease.qnt -- the lease-based auto-sleep of the `exe` GKE cluster.
//
// WHY THIS FILE EXISTS
//
// The `exe` cluster is a single-node pool that must be asleep by default and is
// woken only with an expiry attached. Three independent things are allowed to
// take that node away on their own -- and a fourth, the atenet router, is
// allowed to bring work back without asking anyone. "Deletes or releases on its
// own" is exactly the trigger in docs/agents/formal-methods.md, so the design
// carries a model and the Go reaper carries a seeded simulation of the same
// state machine. This is the model half.
//
// The thing that actually goes wrong here is never "the node did not stop". It
// is ORDER: the pool shrinks while an actor is still Running, and the actor is
// CRASHED instead of SUSPENDED -- state lost, snapshot never taken, and the
// operator's next `ax resume` finds nothing. Every invariant below is a
// statement about order or about a bound, never about liveness alone.
//
// LAYERS -> ACTIONS
//
//   L0  lease (operator, on the Mac)      wake / extend / sleep
//                                         (+ rogueLeaseWrite: the second
//                                          writer the design forbids)
//   L1  graceful drain (in-cluster        l1Tick / l1Crash
//       CronJob, every minute)            -> l1Begin, l1Suspend, l1Stall,
//                                            l1GiveUp, l1Finish, l1Cancel,
//                                            l1Settled, l1NoOp
//   L2  deadline enforcement (Cloud Run   l2Tick
//       job, every 10 min)                -> the three-way rule plus the
//                                            read-failure branch
//   L3  daily stop (Cloud Scheduler ->    l3Tick   (no logic at all, on purpose)
//       GKE setSize(0), 04:00 local)
//   L4  detection (Monitoring + budget)   NOT MODELLED -- it observes, it does
//                                         not decide. See "outside" below.
//
//   environment                           nodeLoss, leaseReadBreaks,
//                                         leaseReadHeals, autoResume,
//                                         operatorResume
//
// ONE WRITER PER OBJECT
//
// The three GCS objects are three state variables, and each is written by
// exactly one action family -- that is the design rule, and here it is a
// structural property of the model rather than a comment: `lease` is only ever
// assigned a new value by the L0 actions, `drain` only by l1Tick, `enforce`
// only by l2Tick. Everything else frames them with `x' = x`. A reviewer can
// check the rule by grepping for `lease' = {`, `drain' = {`, `enforce' = {`.
//
// THE CLOCK IS ABSTRACT
//
// `clock.now` is minutes since the start of the modelled window -- not a real
// timestamp, no dates, no time zone. The window ends at HORIZON. The clock only
// ever moves inside a tick action, and a tick may only fire when it is the
// EARLIEST scheduled event. That single rule is what lets a bounded-time
// termination claim be written as a safety property (see NodesEventuallyZero);
// Quint has no fairness, so there is no other honest way to say "eventually".
//
// OUTSIDE THE MODEL'S GUARANTEE (do not read an invariant as covering these)
//
//   * Real time. One global clock: no skew between the Mac, the in-cluster
//     CronJob and the Cloud Run job, and no scheduler jitter beyond "a tick
//     happens no later than its period".
//   * GCS semantics. Reads are strongly consistent and a generation-precondition
//     write either lands or fails; the only failure modelled is "cannot read".
//   * The 60-second pod-removal -> CRASHED window is collapsed to an instant.
//     That is the conservative direction: the model can never miss a crash the
//     real system would suffer, but it also cannot show an actor escaping
//     through that window.
//   * GKE itself: a pool that gets recreated after node loss, autoprovisioning,
//     `setSize` being throttled or failing, node upgrades.
//   * L4. Alerting and the JPY budget are detection, not control flow. A trace
//     that leaves normalOperation is a trace where L4 is the only remaining
//     control, and the model says nothing about whether the human reacts.
//   * Money. The model bounds the awake window in minutes; yen never appear.
//   * Snapshot correctness -- that a SUSPENDED actor can actually be resumed.
//   * Task TTL and image-tag GC (plan section 3.3). Same reaper binary, a
//     different job, its own retention argument; not modelled here.
//   * IAM, Workload Identity, and who is allowed to call what.
//   * Two actors, not N. The WorkerPool runs 2 replicas (plan Q17), so the
//     model has 2; a symmetry argument is not attempted.
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
  // Instantiated `false` by the `lease` module at the bottom of this file --
  // the design as decided. Each `true` instantiation is one of the designs that
  // was considered and rejected, kept as a named run that FAILS, so the reason
  // for the rejection stays executable instead of becoming folklore.
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

  // --------------------------------------------------------------------------
  // Constants -- mirrored from exe/lease-constants.json. Snake_case on purpose:
  // the names ARE the JSON keys, and the lockstep test parses them out of this
  // text.
  // --------------------------------------------------------------------------

  pure val default_lease_minutes = 120
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

  pure val minutes_per_hour = 60

  // --------------------------------------------------------------------------
  // Derived constants. These are the whole point of keeping the numbers in one
  // file: each is recomputed here, never restated.
  // --------------------------------------------------------------------------

  /// The worst-case time from "the lease expired" to "the pool is at zero":
  /// L1 notices within one tick, the graceful drain is allowed its ceiling, L2
  /// acts within one of its own ticks, and the rest is deliberate slack.
  pure val cap_gap_minutes =
    l1_tick_minutes + drain_ceiling_minutes + l2_tick_minutes + slack_minutes

  /// The nightly cap hour, RE-DERIVED. Nothing downstream reads
  /// nightly_cap_local_hour except the invariant that compares the two.
  pure val nightly_cap_from_formula =
    l3_daily_stop_local_hour - cap_gap_minutes / minutes_per_hour

  /// "The heartbeat is stale" in wall-clock minutes: heartbeat_stale_ticks is
  /// counted in L2 ticks, and L2's tick is l2_tick_minutes long.
  pure val heartbeat_stale_minutes = heartbeat_stale_ticks * l2_tick_minutes

  /// The bound in NodesEventuallyZero. force_grace_minutes is when L2 stops
  /// waiting for anything at all; one l2_tick_minutes covers the scheduler's
  /// phase (the forcing tick lands no later than one period after the grace
  /// runs out); lease_read_failure_threshold more cover the ticks that a lease
  /// L2 cannot READ is allowed to burn before L2 stops the pool blind.
  pure val termination_bound_minutes =
    force_grace_minutes + l2_tick_minutes * (1 + lease_read_failure_threshold)

  /// End of the modelled window. One local day is more than enough: the latest
  /// L3 offset below is 10 hours.
  pure val HORIZON = 24 * minutes_per_hour

  /// "This layer has nothing scheduled." Bigger than any reachable clock value.
  pure val NEVER = 100 * HORIZON

  /// The actors that can be Running at once = the WorkerPool replica count
  /// (plan Q17). v0.1.0 of Substrate is one actor per worker.
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

  /// L1's record in drain.json. `DrainNone` is "no drain in flight"; the JSON
  /// object simply has no drain recorded for the current lease generation.
  type DrainState =
    | DrainNone
    | Draining
    | Drained
    | DrainFailed

  /// L2's last decision, recorded in enforce.json so `exe-status` can show what
  /// the enforcer did without a cluster credential.
  type Decision =
    | NoDecision
    | LeaseLive
    | WaitedForDrain
    | WaitedOnReadFailure
    | StoppedOnDrained
    | StoppedForced
    | StoppedOnReadFailures

  /// What took the pool to zero. Only `GracefulStop` promises an empty cluster;
  /// the rest are allowed to crash an actor, and say so.
  type Shrink =
    | NoShrink
    | GracefulStop
    | ForcedStop
    | DailyStop
    | NodeGone

  /// lease.json. `granted` is what the operator was told they have; in the
  /// decided design it is always equal to `deadline`, and the two only come
  /// apart when a second writer exists. `gen` is the GCS generation the
  /// precondition writes turn on.
  type Lease = {
    deadline: int,
    gen: int,
    granted: int,
    readable: bool,
  }

  /// drain.json. `leaseGen` is the lease generation this record is ABOUT, which
  /// is how a reader tells a fresh `drained` from one that predates an extend.
  type Drain = {
    state: DrainState,
    heartbeat: int,
    startedAt: int,
    leaseGen: int,
  }

  /// enforce.json, plus L2's consecutive-read-failure counter.
  type Enforce = {
    last: Decision,
    gen: int,
    notified: bool,
    leaseReadFailures: int,
  }

  /// The cluster. `nodes` is the node pool size, 0 or 1. `awake` are the actors
  /// Substrate has RUNNING; `crashed` are the ones that lost their pod while
  /// awake and will never come back. `zeroRunningSince` is -1 whenever the
  /// count is not running (an actor is awake, or there is no node).
  type Cluster = {
    nodes: int,
    awake: Set[int],
    crashed: Set[int],
    routerUp: bool,
    reaperAlive: bool,
    zeroRunningSince: int,
  }

  /// The discrete-event clock. `l1Due` / `l2Due` are the next scheduled tick of
  /// each layer; `l3At` is the single daily stop.
  type Clock = {
    now: int,
    l1Due: int,
    l2Due: int,
    l3At: int,
    l3Fired: bool,
  }

  /// Ghost state. Nothing reads it; it exists so the invariants can be written
  /// about events rather than about the current instant, and every flag is
  /// monotone so a later action cannot mask an earlier violation.
  type Evidence = {
    lastShrink: Shrink,
    gracefulCrash: bool,
    l3HitAwakeActor: bool,
    stoppedDespiteLiveLease: bool,
    drainEverFailed: bool,
    leaseEverUnreadable: bool,
  }

  var lease: Lease
  var drain: Drain
  var enforce: Enforce
  var cluster: Cluster
  var clock: Clock
  var evidence: Evidence

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

  /// The pool going to zero. Whatever is still Running is CRASHED; the router
  /// and the in-cluster reaper go with the node.
  pure def shrunk(c: Cluster): Cluster = {
    ...c,
    nodes: 0,
    awake: Set(),
    crashed: c.crashed.union(c.awake),
    routerUp: false,
    reaperAlive: false,
    zeroRunningSince: -1,
  }

  /// The latest instant a lease may expire at: exactly cap_gap_minutes before
  /// the daily stop. With the JSON's numbers and a window starting at local
  /// midnight this is 03:00 against L3's 04:00.
  val capAt = clock.l3At - cap_gap_minutes

  /// Actors that are SUSPENDED: neither running nor lost.
  val suspendedActors = ACTORS.exclude(cluster.awake).exclude(cluster.crashed)

  /// The deadline a request for `d` more minutes actually gets. Two clamps and
  /// a floor: never more than the maximum lease, never past the nightly cap,
  /// never in the past.
  def cappedDeadline(d: int): int =
    maxInt(minInt(clock.now + minInt(d, max_lease_minutes), capAt), clock.now)

  /// L1 is an in-cluster CronJob: it only ticks while there is a node and the
  /// job is actually running.
  val l1Scheduled = cluster.nodes == 1 and cluster.reaperAlive

  val l1NextDue = if (l1Scheduled) clock.l1Due else NEVER
  val l2NextDue = clock.l2Due
  val l3NextDue = if (clock.l3Fired) NEVER else clock.l3At

  /// L1's drain trigger at minute `t`. Three reasons, exactly as the plan lists
  /// them: the deadline passed, Running has been zero for
  /// idle_zero_running_minutes, or lease.json could not be read at all.
  ///
  /// The idle clause is modelled LITERALLY -- "Running has been zero for 30
  /// minutes", counted from whenever the count started, not from the last lease
  /// write. So `wake` restarts the count (new node, new lease) but `extend`
  /// does not: extending a lease with nothing running does not keep the node
  /// up, and L1 will drain it again on the next tick past the 30 minutes. That
  /// is safe either way -- re-draining costs a resume, never an actor -- but it
  /// is a behaviour the Go side has to match rather than guess at.
  def l1Trigger(t: int): bool = or {
    lease.readable and t >= lease.deadline,
    cluster.zeroRunningSince >= 0
      and t - cluster.zeroRunningSince >= idle_zero_running_minutes,
    not(lease.readable),
  }

  /// The graceful drain has spent its budget: drain_ceiling_minutes since it
  /// started.
  def ceilingBlownAt(t: int): bool = t - drain.startedAt >= drain_ceiling_minutes

  // Frame helpers. "This action does not write that object."
  action leaseUnchanged = lease' = lease
  action drainUnchanged = drain' = drain
  action enforceUnchanged = enforce' = enforce
  action clusterUnchanged = cluster' = cluster
  action clockUnchanged = clock' = clock
  action evidenceUnchanged = evidence' = evidence

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
  action wakeFor(d: int): bool = all {
    clock.now <= HORIZON,
    d <= max_lease_minutes,
    cappedDeadline(d) > clock.now,
    lease' = {
      ...lease,
      deadline: cappedDeadline(d),
      granted: cappedDeadline(d),
      gen: lease.gen + 1,
    },
    // A wake creates the node, and the CronJob comes with it. If the node was
    // already up, a wedged reaper stays wedged -- reviving it here would make
    // the model optimistic, which is the one direction that can hide a bug.
    //
    // It does NOT touch routerUp. The atenet-router's replica count has exactly
    // one owner, L1, and this is where that rule earns its keep: a `wake` that
    // also scaled the router to 1 would reopen it in the middle of a drain,
    // after which L1 writes a `drained` record that an auto-resume immediately
    // falsifies -- and L2's graceful stop then crashes the actor. The model
    // found that in a few dozen steps when this action set routerUp: true.
    // L1 restores the router itself, on the first tick where the lease is live.
    cluster' = {
      ...cluster,
      nodes: 1,
      reaperAlive: cluster.nodes == 0 or cluster.reaperAlive,
      zeroRunningSince: if (cluster.awake == Set()) clock.now else -1,
    },
    clock' = { ...clock, l1Due: clock.now + l1_tick_minutes },
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
  }

  action wake = nondet d = oneOf(LEASE_REQUESTS) { wakeFor(d) }

  /// `just exe-extend [d]`. Same two clamps as wake. "Successful" means the new
  /// deadline is genuinely in the future -- an extend inside the cap window
  /// fails rather than silently granting nothing, which is what makes
  /// ExtendBeatsStaleDrained a statement about something that happened.
  ///
  /// Note what this action does NOT do: touch drain.json. It cannot -- L1 owns
  /// that object. The invalidation of an older `drained` happens two other
  /// ways: the deadline moves into the future (so L2's rule never reaches the
  /// three-way branch), and the lease generation moves (so a `drained` written
  /// about the previous generation is visibly not about this one).
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
  }

  // --------------------------------------------------------------------------
  // Resuming work. Two paths, and only one of them asks permission.
  // --------------------------------------------------------------------------

  /// `ax-job` / `ax-exec` resume a task through the ax-controller. They refuse
  /// once the lease is `draining` or later, and they refuse an expired lease.
  /// Those two refusals are these two preconditions.
  action operatorResume = all {
    cluster.nodes == 1,
    drain.state == DrainNone,
    lease.readable,
    clock.now < lease.deadline,
    suspendedActors != Set(),
    cluster' = {
      ...cluster,
      awake: cluster.awake.union(Set(pickOne(suspendedActors))),
      zeroRunningSince: -1,
    },
    leaseUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
  }

  /// The atenet router resumes a SUSPENDED actor on the next connection,
  /// without the ax-controller being involved. It really does this.
  ///
  /// Look at what is NOT a precondition: the drain state, the deadline, the
  /// lease at all. The router does not read lease.json and cannot be made to.
  /// That omission is why L1's step 2 takes the router to zero replicas BEFORE
  /// it suspends anything, and it is the entire content of the `routerLeftOpen`
  /// variant.
  action autoResume = all {
    cluster.nodes == 1,
    cluster.routerUp,
    suspendedActors != Set(),
    cluster' = {
      ...cluster,
      awake: cluster.awake.union(Set(pickOne(suspendedActors))),
      zeroRunningSince: -1,
    },
    leaseUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
  }

  // --------------------------------------------------------------------------
  // L1 -- the in-cluster reaper, once a minute. The only writer of drain.json.
  //
  // The six sub-actions below are the branches of one tick. Each assigns
  // drain', cluster' and evidence'; l1Tick itself owns lease' (untouched),
  // enforce' (untouched) and clock'.
  // --------------------------------------------------------------------------

  /// Nothing to do: no trigger, no drain in flight, router already serving.
  /// This is what almost every one of the 1440 daily ticks does.
  action l1NoOp(t: int, trigger: bool): bool = all {
    not(trigger),
    drain.state == DrainNone,
    cluster.routerUp,
    drainUnchanged,
    clusterUnchanged,
    evidenceUnchanged,
  }

  /// The lease is live and the router is down -- because a previous drain took
  /// it to zero replicas, or because the node it was running on went away. L1
  /// puts it back. This is a reconcile, not an event handler: it is what makes
  /// L1 the single owner of the router's replica count, so no other action ever
  /// has a reason to scale it. Nothing else may, either -- see wakeFor.
  action l1OpenRouter(t: int, trigger: bool): bool = all {
    not(trigger),
    drain.state == DrainNone,
    not(cluster.routerUp),
    drainUnchanged,
    cluster' = { ...cluster, routerUp: true },
    evidenceUnchanged,
  }

  /// Steps 1 and 2 of the graceful drain: write `draining` with a heartbeat,
  /// then take the atenet router to zero replicas so nothing can auto-resume
  /// behind the drain's back. The pool is not touched here. Not once, not as an
  /// optimisation, not "since we are about to anyway" -- see naiveShrinkFirst.
  action l1Begin(t: int, trigger: bool): bool = all {
    trigger,
    drain.state == DrainNone,
    drain' = {
      state: Draining,
      heartbeat: t,
      startedAt: t,
      // L1 records which lease generation it is draining. If the lease cannot
      // be read it keeps the last generation it saw rather than inventing one.
      leaseGen: if (lease.readable) lease.gen else drain.leaseGen,
    },
    cluster' =
      if (naive_shrink_first)
        // REJECTED DESIGN: shrink now, suspend later. There is no "later".
        shrunk(cluster)
      else
        { ...cluster, routerUp: if (router_left_open) cluster.routerUp else false },
    evidence' =
      if (naive_shrink_first)
        { ...evidence,
          lastShrink: GracefulStop,
          gracefulCrash: evidence.gracefulCrash or cluster.awake != Set() }
      else
        evidence,
  }

  /// Steps 3 and 4: ask AX to suspend one Running task, and refresh the
  /// heartbeat. One actor per tick, because a drain that takes time is the only
  /// kind worth modelling -- the ceiling and the heartbeat exist for no other
  /// reason. A graceful suspend never crashes anything: the pod is left alone
  /// until the actor is SUSPENDED.
  action l1Suspend(t: int, trigger: bool, ceilingBlown: bool): bool = all {
    trigger,
    drain.state == Draining,
    not(ceilingBlown),
    cluster.awake != Set(),
    drain' = {
      ...drain,
      state: if (cluster.awake.exclude(Set(pickOne(cluster.awake))) == Set()) Drained
             else Draining,
      heartbeat: t,
      leaseGen: if (lease.readable) lease.gen else drain.leaseGen,
    },
    cluster' = {
      ...cluster,
      awake: cluster.awake.exclude(Set(pickOne(cluster.awake))),
      zeroRunningSince:
        if (cluster.awake.exclude(Set(pickOne(cluster.awake))) == Set()) t else -1,
    },
    evidenceUnchanged,
  }

  /// A tick during a drain that makes no progress: the actor will not suspend
  /// -- a wedged gVisor sandbox, a guest process ignoring the signal. The
  /// heartbeat is still written, so L2 keeps waiting. That is the intended
  /// behaviour and it is bounded by the ceiling, not by patience.
  action l1Stall(t: int, trigger: bool, ceilingBlown: bool): bool = all {
    trigger,
    drain.state == Draining,
    not(ceilingBlown),
    cluster.awake != Set(),
    drain' = {
      ...drain,
      heartbeat: t,
      leaseGen: if (lease.readable) lease.gen else drain.leaseGen,
    },
    clusterUnchanged,
    evidenceUnchanged,
  }

  /// The last Running task is gone, so the drain is complete: `drained`.
  action l1Finish(t: int, trigger: bool): bool = all {
    trigger,
    drain.state == Draining,
    cluster.awake == Set(),
    drain' = {
      ...drain,
      state: Drained,
      heartbeat: t,
      leaseGen: if (lease.readable) lease.gen else drain.leaseGen,
    },
    clusterUnchanged,
    evidenceUnchanged,
  }

  /// drain_ceiling_minutes spent with actors still Running: `drain-failed`.
  /// L1 still does not shrink the pool. It records the failure and lets L2
  /// force, so the crash that follows is attributed to a FORCED stop and
  /// notified -- never mislabelled as a graceful sleep.
  action l1GiveUp(t: int, trigger: bool, ceilingBlown: bool): bool = all {
    trigger,
    drain.state == Draining,
    ceilingBlown,
    cluster.awake != Set(),
    drain' = {
      ...drain,
      state: DrainFailed,
      heartbeat: t,
      leaseGen: if (lease.readable) lease.gen else drain.leaseGen,
    },
    clusterUnchanged,
    evidence' = { ...evidence, drainEverFailed: true },
  }

  /// The lease came back inside its deadline -- a successful `exe-extend`, or a
  /// read that started working again. Cancel the drain and put the router back
  /// to one replica. This is L1's half of "a successful extend invalidates a
  /// prior `drained`".
  action l1Cancel(t: int, trigger: bool): bool = all {
    not(trigger),
    drain.state != DrainNone,
    drain' = { state: DrainNone, heartbeat: t, startedAt: t, leaseGen: lease.gen },
    cluster' = { ...cluster, routerUp: true },
    evidenceUnchanged,
  }

  /// The drain already reached a terminal record and the trigger still holds:
  /// nothing left for L1 to do. Note that it does NOT keep writing heartbeats
  /// here -- a heartbeat means "a drain is in progress", and L2's staleness
  /// test would be worthless if it meant "L1 is alive".
  action l1Settled(t: int, trigger: bool): bool = all {
    trigger,
    drain.state == Drained or drain.state == DrainFailed,
    drainUnchanged,
    clusterUnchanged,
    evidenceUnchanged,
  }

  /// One L1 tick, at minute `l1Due`. `progress` says whether the actor being
  /// asked to suspend actually does -- `l1Tick` leaves that open, and the
  /// scripted tests pin it so an incident replay is deterministic.
  action l1TickWith(progress: bool): bool = all {
    l1Scheduled,
    clock.l1Due <= HORIZON,
    clock.l1Due <= l2NextDue,
    clock.l1Due <= l3NextDue,
    leaseUnchanged,
    enforceUnchanged,
    clock' = { ...clock, now: clock.l1Due, l1Due: clock.l1Due + l1_tick_minutes },
    // The nine branches of one tick. They are exhaustive over
    // (trigger, drain.state, awake, ceiling, routerUp), so a tick is never a
    // dead end, and disjoint, so a tick is a replay rather than a coin toss.
    any {
      l1NoOp(clock.l1Due, l1Trigger(clock.l1Due)),
      l1OpenRouter(clock.l1Due, l1Trigger(clock.l1Due)),
      l1Begin(clock.l1Due, l1Trigger(clock.l1Due)),
      l1Finish(clock.l1Due, l1Trigger(clock.l1Due)),
      all {
        progress,
        l1Suspend(clock.l1Due, l1Trigger(clock.l1Due), ceilingBlownAt(clock.l1Due)),
      },
      all {
        not(progress),
        l1Stall(clock.l1Due, l1Trigger(clock.l1Due), ceilingBlownAt(clock.l1Due)),
      },
      l1GiveUp(clock.l1Due, l1Trigger(clock.l1Due), ceilingBlownAt(clock.l1Due)),
      l1Cancel(clock.l1Due, l1Trigger(clock.l1Due)),
      l1Settled(clock.l1Due, l1Trigger(clock.l1Due)),
    },
  }

  action l1Tick = any { l1TickWith(true), l1TickWith(false) }

  /// The reaper stops ticking: the CronJob is wedged, the KSA lost its binding,
  /// the node is NotReady but still counted. Nothing in the cluster changes --
  /// the heartbeat in drain.json simply stops moving. This is the only thing
  /// that gives L2's staleness test any work to do.
  action l1Crash = all {
    cluster.nodes == 1,
    cluster.reaperAlive,
    cluster' = { ...cluster, reaperAlive: false },
    leaseUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
  }

  // --------------------------------------------------------------------------
  // L2 -- the Cloud Run enforcer, every 10 minutes. The only writer of
  // enforce.json. It reads GCS and calls nodePools.setSize; it never holds a
  // cluster credential, which is why it still works when the cluster does not.
  //
  // Branch order matters and mirrors the plan: read failures first (a lease you
  // cannot read tells you nothing about expiry), then the lease-is-live exit,
  // then the three-way rule.
  // --------------------------------------------------------------------------

  /// Fewer than lease_read_failure_threshold consecutive read failures: record
  /// the miss and do nothing. L1 is draining on the very same signal, so the
  /// correct move is to let it. One or two misses must never stop the pool.
  action l2ReadFailedBelowThreshold(t: int): bool = all {
    not(lease.readable),
    enforce.leaseReadFailures + 1 < lease_read_failure_threshold,
    enforce' = {
      ...enforce,
      last: WaitedOnReadFailure,
      gen: enforce.gen + 1,
      leaseReadFailures: enforce.leaseReadFailures + 1,
    },
    clusterUnchanged,
    evidenceUnchanged,
  }

  /// lease_read_failure_threshold consecutive failures. L2 cannot see the
  /// deadline at all, so it stops the pool blind and notifies.
  ///
  /// This is the one stop that can land on a lease that is genuinely live, and
  /// it is deliberately outside ExtendBeatsStaleDrained -- see that invariant.
  /// The compensating control is the notification plus L1, which has been
  /// draining gracefully on the same signal since its own first tick.
  action l2ReadFailedAtThreshold(t: int): bool = all {
    not(lease.readable),
    enforce.leaseReadFailures + 1 >= lease_read_failure_threshold,
    enforce' = {
      last: StoppedOnReadFailures,
      gen: enforce.gen + 1,
      notified: true,
      leaseReadFailures: enforce.leaseReadFailures + 1,
    },
    cluster' = shrunk(cluster),
    evidence' = { ...evidence, lastShrink: ForcedStop },
  }

  /// The lease is live. L2 has nothing to enforce, and still records a decision
  /// -- that record is how `exe-status` proves the enforcer ran at all.
  action l2LeaseLive(t: int): bool = all {
    lease.readable,
    t < lease.deadline,
    enforce' = {
      ...enforce,
      last: LeaseLive,
      gen: enforce.gen + 1,
      leaseReadFailures: 0,
    },
    clusterUnchanged,
    evidenceUnchanged,
  }

  /// Three-way rule, branch 1: L1 says `drained`, about THIS lease generation.
  /// The pool can go to zero, and this is the only stop that claims to be
  /// graceful -- so it is the only one NoCrashOnGracefulSleep judges.
  action l2StopOnDrained(t: int): bool = all {
    lease.readable,
    t >= lease.deadline,
    drain.state == Drained,
    drain.leaseGen == lease.gen,
    enforce' = {
      ...enforce,
      last: StoppedOnDrained,
      gen: enforce.gen + 1,
      leaseReadFailures: 0,
    },
    cluster' = shrunk(cluster),
    evidence' = {
      ...evidence,
      lastShrink: GracefulStop,
      gracefulCrash: evidence.gracefulCrash or cluster.awake != Set(),
      stoppedDespiteLiveLease: evidence.stoppedDespiteLiveLease or t < lease.granted,
    },
  }

  /// Branch 2: `draining`, about this generation, with a heartbeat inside
  /// heartbeat_stale_ticks L2 ticks, and the grace period not yet spent. Wait.
  /// The grace clause is what stops a heartbeat that keeps arriving from
  /// buying unlimited time.
  action l2WaitForDrain(t: int): bool = all {
    lease.readable,
    t >= lease.deadline,
    drain.state == Draining,
    drain.leaseGen == lease.gen,
    t - drain.heartbeat <= heartbeat_stale_minutes,
    t < lease.deadline + force_grace_minutes,
    enforce' = {
      ...enforce,
      last: WaitedForDrain,
      gen: enforce.gen + 1,
      leaseReadFailures: 0,
    },
    clusterUnchanged,
    evidenceUnchanged,
  }

  /// Branch 3: everything else past the deadline -- a stale heartbeat, a
  /// `drain-failed`, no drain record at all, a drain record about an older
  /// lease generation, or the grace period spent. Force the pool to zero and
  /// notify. An actor Running here is CRASHED, and that is accepted: the
  /// alternative is a node that never stops.
  action l2Force(t: int): bool = all {
    lease.readable,
    t >= lease.deadline,
    not(drain.state == Drained and drain.leaseGen == lease.gen),
    not(and {
      drain.state == Draining,
      drain.leaseGen == lease.gen,
      t - drain.heartbeat <= heartbeat_stale_minutes,
      t < lease.deadline + force_grace_minutes,
    }),
    enforce' = {
      last: StoppedForced,
      gen: enforce.gen + 1,
      notified: true,
      leaseReadFailures: 0,
    },
    cluster' = shrunk(cluster),
    evidence' = {
      ...evidence,
      lastShrink: ForcedStop,
      stoppedDespiteLiveLease: evidence.stoppedDespiteLiveLease or t < lease.granted,
    },
  }

  /// One L2 tick, at minute `l2Due`.
  action l2Tick = all {
    clock.l2Due <= HORIZON,
    clock.l2Due <= l1NextDue,
    clock.l2Due <= l3NextDue,
    leaseUnchanged,
    drainUnchanged,
    clock' = { ...clock, now: clock.l2Due, l2Due: clock.l2Due + l2_tick_minutes },
    any {
      l2ReadFailedBelowThreshold(clock.l2Due),
      l2ReadFailedAtThreshold(clock.l2Due),
      l2LeaseLive(clock.l2Due),
      l2StopOnDrained(clock.l2Due),
      l2WaitForDrain(clock.l2Due),
      l2Force(clock.l2Due),
    },
  }

  // --------------------------------------------------------------------------
  // L3 -- Cloud Scheduler calls nodePools.setSize(0) at the daily stop hour.
  // --------------------------------------------------------------------------

  /// No lease read. No drain check. No Kubernetes credential. No logic at all,
  /// on purpose: this is the layer that has to work when every other layer is
  /// broken, so it has nothing that can break. Whatever is Running is lost --
  /// which is what the nightly cap exists to make impossible in normal
  /// operation, and L3NeverHitsAwakeActor is that claim.
  action l3Tick = all {
    not(clock.l3Fired),
    clock.l3At <= HORIZON,
    clock.l3At <= l1NextDue,
    clock.l3At <= l2NextDue,
    clock' = { ...clock, now: clock.l3At, l3Fired: true },
    cluster' = shrunk(cluster),
    evidence' = {
      ...evidence,
      lastShrink: DailyStop,
      l3HitAwakeActor: evidence.l3HitAwakeActor or cluster.awake != Set(),
    },
    leaseUnchanged,
    drainUnchanged,
    enforceUnchanged,
  }

  // --------------------------------------------------------------------------
  // Environment
  // --------------------------------------------------------------------------

  /// The node disappears at an arbitrary moment: the underlying VM is repaired,
  /// the kernel panics, the zone hiccups. Nobody decided this, so the crash it
  /// causes is not attributable to any stop decision.
  action nodeLoss = all {
    cluster.nodes == 1,
    cluster' = shrunk(cluster),
    evidence' = { ...evidence, lastShrink: NodeGone },
    leaseUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
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
  }

  action leaseReadHeals = all {
    not(lease.readable),
    lease' = { ...lease, readable: true },
    clusterUnchanged,
    clockUnchanged,
    drainUnchanged,
    enforceUnchanged,
    evidenceUnchanged,
  }

  // --------------------------------------------------------------------------
  // init / step
  // --------------------------------------------------------------------------

  /// The cluster starts asleep with no lease. `l3At` fixes what local time the
  /// modelled window starts at.
  action initWith(l3Offset: int): bool = all {
    lease' = { deadline: 0, gen: 0, granted: 0, readable: true },
    drain' = { state: DrainNone, heartbeat: 0, startedAt: 0, leaseGen: 0 },
    enforce' = { last: NoDecision, gen: 0, notified: false, leaseReadFailures: 0 },
    cluster' = {
      nodes: 0,
      awake: Set(),
      crashed: Set(),
      routerUp: false,
      reaperAlive: false,
      zeroRunningSince: -1,
    },
    clock' = {
      now: 0,
      l1Due: l1_tick_minutes,
      l2Due: l2_tick_minutes,
      l3At: l3Offset,
      l3Fired: false,
    },
    evidence' = {
      lastShrink: NoShrink,
      gracefulCrash: false,
      l3HitAwakeActor: false,
      stoppedDespiteLiveLease: false,
      drainEverFailed: false,
      leaseEverUnreadable: false,
    },
  }

  action init = nondet l3Offset = oneOf(L3_OFFSETS) { initWith(l3Offset) }

  /// Every tick, for scripted runs that only need the clock to move.
  action anyTick = any { l1Tick, l2Tick, l3Tick }

  /// Every tick, with the drain forced to make no progress.
  action anyTickStalling = any { l1TickWith(false), l2Tick, l3Tick }

  action step = any {
    wake,
    extend,
    sleep,
    rogueLeaseWrite,
    operatorResume,
    autoResume,
    l1Tick,
    l1Crash,
    l2Tick,
    l3Tick,
    nodeLoss,
    leaseReadBreaks,
    leaseReadHeals,
  }

  // --------------------------------------------------------------------------
  // Invariants
  //
  // `Safety` carries the four mandatory properties and nothing else. The
  // model's own frame check lives in `WellFormed` and is checked alongside it
  // by `just spec-check`, because a broken frame is a broken model, not a
  // broken design.
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

  /// MANDATORY 1. A stop that claims to be graceful never shrinks the pool with
  /// an actor Running. This is the whole reason L1 exists: `exe-sleep` and an
  /// expired lease must cost nothing but a resume.
  ///
  /// The flag is monotone, so a later graceful stop over an empty cluster
  /// cannot paper over an earlier one that lost an actor.
  val NoCrashOnGracefulSleep = not(evidence.gracefulCrash)

  /// MANDATORY 2. L3 has no logic, so nothing in the code keeps it off a
  /// Running actor -- arithmetic does. The cap hour is RE-DERIVED here from
  /// l3_daily_stop_local_hour and the four latency terms; the stored
  /// nightly_cap_local_hour appears exactly once, as the thing being checked.
  /// Trusting the stored 3 would make this invariant a tautology.
  val L3NeverHitsAwakeActor = and {
    // 04:00 - (1 + 30 + 10 + 19) minutes = 03:00
    nightly_cap_from_formula == nightly_cap_local_hour,
    // and the cap instant really is a full worst-case budget before L3
    capAt + l1_tick_minutes + drain_ceiling_minutes + l2_tick_minutes + slack_minutes
      == clock.l3At,
    // therefore, in normal operation, L3 has never fired on a Running actor
    normalOperation implies not(evidence.l3HitAwakeActor),
  }

  /// MANDATORY 3. Bounded-time termination, written as a safety property.
  ///
  /// Quint has no fairness, so "the pool eventually reaches zero" cannot be
  /// stated as a temporal formula: the unfair trace where the schedulers simply
  /// never fire would falsify it. The model instead makes the schedulers the
  /// ONLY way the clock moves, and lets a tick fire only when it is the
  /// earliest scheduled event. That turns "eventually" into arithmetic -- if
  /// the clock has got past deadline + bound, the tick that had to stop the
  /// pool has necessarily already happened -- so the honest encoding is a
  /// safety property about the clock, and this is it.
  ///
  /// The bound is re-derived in termination_bound_minutes. It is wider than the
  /// plan's "deadline + 45 + 10" because that figure assumes lease.json is
  /// readable; when it is not, L2 is entitled to burn
  /// lease_read_failure_threshold ticks before stopping the pool blind.
  val NodesEventuallyZero =
    clock.now > lease.deadline + termination_bound_minutes implies cluster.nodes == 0

  /// MANDATORY 4. A lease the operator was granted is honoured: no stop taken
  /// from a lease L2 could actually READ ever lands before the granted
  /// deadline. The stale-`drained` race is the case that matters -- L1 wrote
  /// `drained`, the operator extended, and L2 must not act on the old record --
  /// and it is blocked twice over: the deadline has moved into the future, and
  /// the drain record names an older lease generation.
  ///
  /// Deliberately NOT covered: l2ReadFailedAtThreshold. That branch stops the
  /// pool precisely because it cannot read the lease, so it cannot know whether
  /// the lease is live; the compensating control is the notification and L1's
  /// own drain on the same signal. The flag is only ever set by the branches
  /// that did read the lease.
  val ExtendBeatsStaleDrained = not(evidence.stoppedDespiteLiveLease)

  val Safety = and {
    NoCrashOnGracefulSleep,
    L3NeverHitsAwakeActor,
    NodesEventuallyZero,
    ExtendBeatsStaleDrained,
  }

  /// The lemma NoCrashOnGracefulSleep rests on, checked separately so that a
  /// regression points at the cause instead of at the symptom: a `drained`
  /// record stays true for as long as it exists.
  ///
  /// It holds because both ways an actor becomes Running require
  /// drain.state == DrainNone -- operatorResume tests it, and autoResume cannot
  /// test anything, so L1 closes the router instead. That is the whole argument
  /// for giving the router's replica count exactly one owner. Break it (let
  /// `wake` scale the router, say) and the first clause fails within a few
  /// dozen steps, followed immediately by NoCrashOnGracefulSleep.
  val DrainedRecordStaysTrue = and {
    cluster.routerUp implies drain.state == DrainNone,
    drain.state == Drained implies cluster.awake == Set(),
  }

  /// Not a design property -- a check that the model is not lying. An actor
  /// cannot be Running when there is no node to run it on, the three actor
  /// sets partition, and the clock never runs backwards past a due time.
  val WellFormed = and {
    cluster.nodes == 0 implies cluster.awake == Set(),
    cluster.awake.intersect(cluster.crashed) == Set(),
    cluster.awake.union(cluster.crashed).subseteq(ACTORS),
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
//   not a second author of intent. The only control is that `exe-reaper` has no
//   subcommand that writes lease.json outside wake/extend/sleep, and reviews
//   keep it that way.
// ============================================================================
module twoWriterLease {
  import leaseCore(
    two_writer_lease = true,
    naive_shrink_first = false,
    router_left_open = false,
  ).*

  /// EXPECTED TO FAIL (ExtendBeatsStaleDrained). The operator is granted two
  /// hours; the second writer puts the deadline back to now; L1 dutifully
  /// drains the lease it can see and writes `drained` against the current
  /// generation; L2 dutifully stops a cluster whose operator was promised 110
  /// more minutes. Every layer behaved. The design did not.
  run twoWritersLoseTheOperatorsLease =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(rogueLeaseWrite)
      .then(l1Tick)                       // 1: expired -> draining
      .then(l1Tick)                       // 2: nothing Running -> drained
      .then(7.reps(_ => l1Tick))          // 3..9: settled, waiting for L2
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
//   router goes to zero replicas, then AX suspends every Running task, then
//   every actor is confirmed SUSPENDED, and only then is `drained` written. L2
//   is what touches the pool.
// Compensating control: none, again by design. Removing the worker pod under a
//   Running actor CRASHES it after the pod-removal window, which loses the
//   actor's state and its snapshot; nothing downstream can recover that. The
//   structural control is that L1 has no code path to the GKE node-pool API at
//   all -- it holds a KSA scoped to the cluster, not the nodePools.setSize
//   permission. Keep it that way and this variant is unreachable.
// ============================================================================
module naiveShrinkFirst {
  import leaseCore(
    two_writer_lease = false,
    naive_shrink_first = true,
    router_left_open = false,
  ).*

  /// EXPECTED TO FAIL (NoCrashOnGracefulSleep). An operator types `exe-sleep`
  /// with one task Running. One minute later the pool is gone and so is the
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
// REJECTED DESIGN 3 -- stop the controller, leave the router open
//
// Scope: L1's step 2. The rejected alternative reasoned that suspending through
//   AX is enough, so there is no need to touch atenet-router -- stop the
//   ax-controller if anything, and leave the data path alone so `ax ssh` keeps
//   working until the last moment.
// Accepted by: the operator, plan section 3.2 -- "atenet-router を 0 台にする
//   (router 経由の自動 resume と `ax ssh` を止める)", explicitly BEFORE the
//   suspends, and it is step 2 rather than step 4 for exactly the reason below.
// Compensating control: none available at the controller. The router resumes a
//   SUSPENDED actor on connection without consulting the ax-controller or
//   lease.json, so no guard added to `ax-job` / `ax-exec` can see it coming.
//   Taking the replicas to zero is the control. The `drained` record is a
//   promise about the past, and only a closed router makes it a promise about
//   the present too.
// ============================================================================
module routerLeftOpen {
  import leaseCore(
    two_writer_lease = false,
    naive_shrink_first = false,
    router_left_open = true,
  ).*

  /// EXPECTED TO FAIL (NoCrashOnGracefulSleep). The drain completes honestly:
  /// nothing was Running, so `drained` is true when it is written. Then a
  /// connection arrives, the router resumes an actor, and L2 -- reading a
  /// `drained` that was correct four minutes ago -- performs a graceful stop on
  /// a cluster that is no longer drained.
  run leftOpenRouterRevivesAnActorAfterDrained =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(10.reps(_ => l1Tick))         // 1: router opened; 2..9 idle; 10: expiry
                                          //    -> draining, router NOT closed
      .then(l2Tick)                       // 10: draining, heartbeat fresh -> wait
      .then(l1Tick)                       // 11: nothing Running -> drained
      .then(autoResume)                   // the router is still serving
      .then(8.reps(_ => l1Tick))          // 12..19: settled; L1 never revisits `drained`
      .then(l2Tick)                       // 20: "graceful" stop over a Running actor
      .expect(Safety)
}

// ============================================================================
// THE DECIDED DESIGN. This module is `lease`, so it is what `quint run`,
// `quint test` and `quint verify` pick up by default from lease.qnt.
//
// The `*Test` runs below are the recorded behaviours from plan section 3.2 and
// the Phase 3 e2e list, replayed deterministically. Every tick count in them is
// derived from the constants and spelled out in the comment beside it; the
// discrete-event clock makes the interleavings forced, so these are replays,
// not samples.
// ============================================================================
module lease {
  import leaseCore(
    two_writer_lease = false,
    naive_shrink_first = false,
    router_left_open = false,
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

  /// `exe-sleep` with one task Running: L1 suspends it, writes `drained`, and
  /// L2 shrinks an empty cluster. Nothing crashes, nothing is notified.
  ///
  /// Tick arithmetic: L1 at 1 begins the drain, at 2 suspends the last actor
  /// and writes `drained`; L1 then has 7 no-op ticks (3..9) before L2's tick
  /// at l2_tick_minutes is the earliest scheduled event.
  run gracefulSleepLosesNothingTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(sleep)
      .then(l1TickWith(true))             // 1: draining, router closed
      .then(l1TickWith(true))             // 2: actor suspended -> drained
      .then(7.reps(_ => l1Tick))          // 3..9
      .then(l2Tick)                       // 10
      .expect(and {
        cluster.nodes == 0,
        cluster.crashed == Set(),
        not(evidence.gracefulCrash),
        enforce.last == StoppedOnDrained,
        not(enforce.notified),
        evidence.lastShrink == GracefulStop,
      })

  /// Running has been zero for idle_zero_running_minutes, so L1 drains even
  /// though the lease is still live. This is the "forgot to sleep it" case that
  /// costs the most in practice.
  ///
  /// Tick arithmetic: the idle timer starts at the wake (minute 0) and expires
  /// at minute idle_zero_running_minutes = 30. Events strictly before that
  /// minute are L1's ticks at 1..29 (29) plus L2's at 10 and 20 (2) = 31.
  run idleClusterDrainsItselfTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(31.reps(_ => anyTick))
      .then(l1Tick)                       // minute 30: the idle timer expires
      .expect(and {
        clock.now == idle_zero_running_minutes,
        drain.state == Draining,
        not(cluster.routerUp),
        clock.now < lease.deadline,
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
      .then(l1Tick)                       // 11: nothing Running -> drained
      .then(9.reps(_ => l1Tick))          // 12..20
      .then(l2Tick)                       // 20: drained -> pool to zero
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

  // --- L0 + L2: the stale-`drained` race -----------------------------------

  /// A successful extend invalidates a prior `drained`. L1 is alive, so it
  /// cancels the drain on its next tick and L2 finds a live lease -- the pool
  /// stays up, which is the entire point of typing `exe-extend`.
  run extendInvalidatesAPriorDrainedTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(sleep)
      .then(l1Tick)                       // 1: draining
      .then(l1Tick)                       // 2: drained
      .then(extendFor(default_lease_minutes))
      .then(7.reps(_ => l1Tick))          // 3..9: L1 sees a live lease -> cancel
      .then(l2Tick)                       // 10
      .expect(and {
        cluster.nodes == 1,
        drain.state == DrainNone,
        cluster.routerUp,
        enforce.last == LeaseLive,
        not(evidence.stoppedDespiteLiveLease),
      })

  /// Same race with L1 dead, so nothing cancels the stale record. The lease
  /// generation is what saves it: the `drained` in drain.json is about
  /// generation 2, the lease is on generation 3, so L2 refuses to call it a
  /// graceful stop and forces with a notification instead. Conservative in the
  /// right direction -- a forced stop is loud, a mislabelled graceful one is
  /// silent.
  run staleDrainRecordForcesInsteadOfStoppingGracefullyTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(l2_tick_minutes))
      .then(sleep)
      .then(l1Tick)                       // 1: draining
      .then(l1Tick)                       // 2: drained, about generation 2
      .then(extendFor(l2_tick_minutes))   // generation 3, deadline 12
      .then(l1Crash)
      .then(l2Tick)                       // 10: lease still live
      .then(l2Tick)                       // 20: expired, record is generation 2
      .expect(and {
        cluster.nodes == 0,
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
        enforce.leaseReadFailures == lease_read_failure_threshold - 1,
        enforce.last == WaitedOnReadFailure,
        not(enforce.notified),
      })

  /// The threshold-th consecutive failure stops the pool blind and notifies.
  /// An actor is Running here and it is CRASHED -- accepted, because the
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
        cluster.nodes == 0,
        cluster.crashed == Set(1),
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
        cluster.nodes == 0,
        cluster.crashed == Set(1),
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
        cluster.nodes == 0,
        cluster.crashed == Set(1),
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
      .then(5.reps(_ => l2Tick))          // 10..50
      .then(l3Tick)                       // 60 = 04:00
      .expect(and {
        clock.l3Fired,
        cluster.nodes == 0,
        not(evidence.l3HitAwakeActor),
        Safety,
      })

  // --- environment --------------------------------------------------------

  /// The node vanishes under a Running actor. The actor is lost, but the stop
  /// was nobody's decision, so it is not a graceful-sleep violation -- and the
  /// pool still ends at zero.
  run nodeLossIsNotAGracefulStopTest =
    initWith(10 * minutes_per_hour)
      .then(wakeFor(default_lease_minutes))
      .then(operatorResume)
      .then(nodeLoss)
      .expect(and {
        cluster.nodes == 0,
        cluster.crashed == Set(1),
        evidence.lastShrink == NodeGone,
        not(evidence.gracefulCrash),
        Safety,
      })
}
