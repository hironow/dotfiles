// -*- mode: quint -*-
//
// retention.qnt -- what exe deletes on its own schedule: tasks past their TTL,
// and task images nothing protects (Phase 6 plan D10).
//
// WHY THIS FILE EXISTS
//
// Two things delete here with nobody watching:
//   - L1 deletes an AX task whose actor has sat SUSPENDED for task_ttl_days,
//     unless the operator kept it (keep.json);
//   - Artifact Registry's cleanup policy deletes a task-image version older
//     than ar_delete_days unless it carries an `inuse-` tag.
// Both "delete on their own" (docs/agents/formal-methods.md). What goes wrong
// is a DELETE that lands on something still wanted: a task deleted before its
// time, or the image a live task needs at its next resume. Every wake is a
// fresh node, so a resume pulls the image again, and a collected image is a
// task that can never run again.
//
// THE MECHANISMS, AS DECIDED
//
//   TTL     L1 deletes a task whose actor is SUSPENDED and whose record in the
//           Substrate store has not changed for task_ttl_days. The store moves
//           an actor's update_time on every write, so a resume and a
//           re-suspend both move it, whether or not L1 ticked in between. L1
//           runs only while a node is up, so this is "deleted at the first
//           wake after task_ttl_days".
//   tags    L1 tags every digest a live task references with its own
//           `inuse-<sha12>`, and releases that tag once the digest has been
//           unreferenced for tag_release_days, counted in tasks.json from the
//           first tick that saw it so.
//   ax-job  tags the image BEFORE it applies the task, with a tag of its own
//           whose name carries its creation time, `inuse-<sha12>-<unix>`. L1
//           releases one of those once its name says it is tag_release_days
//           old, and never by a record.
//   AR      deletes any untagged version older than ar_delete_days, at any
//           moment. The real policy also keeps the 2 most recent versions; the
//           model does not rely on that, so it collects at least as much as AR.
//
// LIVENESS
//
// Safety alone is satisfied by a TTL that never fires, and a TTL that never
// fires is unbounded storage. So a task SUSPENDED and untouched for
// task_ttl_days, and not kept, must be deleted by the first L1 tick after
// that: `TtlNeverMissed`. The model's time is bounded, so this is checked as
// a bounded response -- every tick at or past a task's TTL deletes it -- rather
// than as a temporal formula, which `quint run` cannot check.
//
// It rests on one assumption about the store, checked against the pinned
// Substrate source (exe/spec/README.md lists the paths): nothing writes a
// SUSPENDED actor's row in the background, so its update_time only moves when
// someone suspends, resumes, pauses or deletes it.
//
// REJECTED DESIGNS (each kept as a failing named run, at the bottom)
//
//   sharedJobTag     ax-job tags the shared `inuse-<sha12>`. L1's
//                    unreferencedSince for that digest can be weeks old, so a
//                    tick between ax-job's tag and its apply releases the tag,
//                    and AR collects the image of a task ax-job has just
//                    created.
//   ttlByFirstSight  the TTL counts from the first tick L1 saw the task
//                    suspended. A resume and a re-suspend between two ticks
//                    are invisible to it, and a task used yesterday is deleted
//                    as a month old.
//   backgroundWriteRefreshes
//                    the store's assumption broken: something rewrites a
//                    SUSPENDED actor's row now and then. update_time never
//                    gets old, and the TTL never fires.
//
// TIME
//
// One clock in whole days, and everything else interleaves freely inside a
// day: L1's ticks, AR's cleanup, the operator's commands. That is deliberately
// coarser than reality (L1 ticks every minute): any order of events the real
// system can produce inside one day, the model can produce too.
//
// OUTSIDE THE MODEL
//
//   - A raw `ax apply` of an untagged image older than ar_delete_days, with
//     AR's cleanup landing before L1's next tick tags it. ax-job is the
//     supported path; the evidence below only counts tasks that are protected
//     (created by ax-job, or seen by an L1 tick).
//   - keep.json edits racing L1's read of it inside one tick.
//   - Platform images (exe-platform): the same tag mechanism over a different
//     set of references, with a 30-day DELETE.
//   - Snapshot objects in GCS (the operator-run snapshot GC, plan D11).

module retentionCore {
  // --------------------------------------------------------------------------
  // Design-variant switches: `false` in the decided design (module retention
  // at the bottom), `true` in the rejected one each names.
  // --------------------------------------------------------------------------

  /// ax-job tags the shared `inuse-<sha12>` instead of a dated tag of its own
  /// (`sharedJobTag`).
  const shared_job_tag: bool

  /// The TTL counts from the first tick L1 saw the task suspended, instead of
  /// the store's update_time (`ttlByFirstSight`).
  const ttl_by_first_sight: bool

  /// Something in the background rewrites a SUSPENDED actor's row, moving its
  /// update_time (`backgroundWriteRefreshes`). The pinned Substrate has no
  /// such writer; this is what the TTL would do if one appeared.
  const background_writes: bool

  // --------------------------------------------------------------------------
  // Constants. task_ttl_days and task_ttl_warning_days mirror
  // exe/lease-constants.json (tests/unit/test_lease_constants_lockstep.py);
  // so does tag_release_days. ar_delete_days is exe-task's cleanup policy
  // (tofu/exe-platform/artifact_registry.tf); no invariant depends on its
  // value, only how soon an unprotected image goes.
  // --------------------------------------------------------------------------

  pure val task_ttl_days = 30
  pure val task_ttl_warning_days = 7
  pure val tag_release_days = 7
  pure val ar_delete_days = 14

  /// End of the modelled window: long enough for a TTL, a release and a
  /// collection to follow one another.
  pure val HORIZON = 70

  /// Tasks and image versions. Two tasks can share a digest, and a digest can
  /// outlive every task that used it.
  pure val TASKS = Set(1, 2)
  pure val DIGESTS = Set(1, 2, 3)

  pure val NONE = -1

  type Task = {
    alive: bool,
    suspended: bool,
    digest: int,
    // Protected from AR by construction: created through ax-job (tagged
    // first), or seen alive by an L1 tick (which tags its digest).
    protected: bool,
    // The store's update_time for the task's actor: every state change.
    changedAt: int,
    // Ground truth: when it was last suspended. Evidence only.
    suspendedAt: int,
    // L1's first sight of it suspended (the rejected TTL's clock).
    firstSeenSuspended: int,
  }

  type Version = { pushedAt: int, collected: bool }

  var clock: int
  var awake: bool
  var tasks: int -> Task
  var versions: int -> Version
  /// L1's own `inuse-<sha12>` tags.
  var l1Tags: Set[int]
  /// ax-job's dated tags: (digest, the day in the tag's name).
  var jobTags: Set[(int, int)]
  /// An ax-job between its tag and its apply: task -> digest.
  var axJobPending: int -> int
  var keep: Set[int]
  /// tasks.json: for each digest L1 tagged and no live task references, the
  /// first tick that saw it so.
  var unreferencedSince: int -> int

  // evidence, raised at the step that breaks a property
  var deletedEarly: bool
  var liveImageCollected: bool
  var ttlMissed: bool

  // --------------------------------------------------------------------------
  // Helpers
  // --------------------------------------------------------------------------

  val liveTasks: Set[int] = tasks.keys().filter(t => tasks.get(t).alive)

  def tagged(d: int): bool = l1Tags.contains(d) or jobTags.exists(jt => jt._1 == d)

  def pushed(d: int): bool = versions.get(d).pushedAt != NONE

  def available(d: int): bool = pushed(d) and not(versions.get(d).collected)

  /// The TTL test L1 applies to one task on one tick.
  def ttlExpired(t: int): bool = {
    val task = tasks.get(t)
    val since = if (ttl_by_first_sight) task.firstSeenSuspended else task.changedAt
    and {
      task.suspended,
      not(keep.contains(t)),
      since != NONE,
      clock - since >= task_ttl_days,
    }
  }

  /// What the property means, from the ground truth.
  def ttlExpiredForReal(t: int): bool = {
    val task = tasks.get(t)
    and {
      task.suspended,
      not(keep.contains(t)),
      clock - task.suspendedAt >= task_ttl_days,
    }
  }

  // --------------------------------------------------------------------------
  // The operator, AX and Artifact Registry
  // --------------------------------------------------------------------------

  action unchangedEvidence = all {
    deletedEarly' = deletedEarly,
    liveImageCollected' = liveImageCollected,
    ttlMissed' = ttlMissed,
  }

  /// A new task image is pushed (Cloud Build).
  action push(d: int): bool = all {
    not(pushed(d)),
    versions' = versions.set(d, { pushedAt: clock, collected: false }),
    clock' = clock, awake' = awake, tasks' = tasks, l1Tags' = l1Tags, jobTags' = jobTags,
    axJobPending' = axJobPending, keep' = keep, unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  /// ax-job, step 1: tag the image, after checking it exists. Only with a
  /// node up: ax-job starts with may-start.
  action axJobTag(t: int, d: int): bool = all {
    awake,
    not(tasks.keys().contains(t)),
    not(axJobPending.keys().contains(t)),
    available(d),
    l1Tags' = if (shared_job_tag) l1Tags.union(Set(d)) else l1Tags,
    jobTags' = if (shared_job_tag) jobTags else jobTags.union(Set((d, clock))),
    axJobPending' = axJobPending.put(t, d),
    clock' = clock, awake' = awake, tasks' = tasks, versions' = versions,
    keep' = keep, unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  /// ax-job, step 2: apply the task, the same day. It fails, creating
  /// nothing, if the image is gone by then.
  action axJobApply(t: int): bool = all {
    awake,
    axJobPending.keys().contains(t),
    val d = axJobPending.get(t)
    all {
      available(d),
      tasks' = tasks.put(t, {
        alive: true, suspended: false, digest: d, protected: true,
        changedAt: clock, suspendedAt: NONE, firstSeenSuspended: NONE,
      }),
      axJobPending' = axJobPending.keys().exclude(Set(t)).mapBy(k => axJobPending.get(k)),
    },
    clock' = clock, awake' = awake, versions' = versions, l1Tags' = l1Tags,
    jobTags' = jobTags, keep' = keep, unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  /// A raw `ax apply`, bypassing ax-job: no tag. Outside the guarantee until
  /// an L1 tick sees it.
  action rawApply(t: int, d: int): bool = all {
    awake,
    not(tasks.keys().contains(t)),
    not(axJobPending.keys().contains(t)),
    available(d),
    tasks' = tasks.put(t, {
      alive: true, suspended: false, digest: d, protected: false,
      changedAt: clock, suspendedAt: NONE, firstSeenSuspended: NONE,
    }),
    clock' = clock, awake' = awake, versions' = versions, l1Tags' = l1Tags,
    jobTags' = jobTags, axJobPending' = axJobPending, keep' = keep,
    unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  /// `ax suspend`, or a drain: the actor checkpoints and its record moves.
  action suspendTask(t: int): bool = all {
    awake,
    liveTasks.contains(t),
    not(tasks.get(t).suspended),
    tasks' = tasks.set(t, { ...tasks.get(t), suspended: true, changedAt: clock, suspendedAt: clock }),
    clock' = clock, awake' = awake, versions' = versions, l1Tags' = l1Tags,
    jobTags' = jobTags, axJobPending' = axJobPending, keep' = keep,
    unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  /// `ax resume` (or ax-exec): the actor comes back, which needs its image.
  action resumeTask(t: int): bool = all {
    awake,
    liveTasks.contains(t),
    tasks.get(t).suspended,
    available(tasks.get(t).digest),
    tasks' = tasks.set(t, { ...tasks.get(t), suspended: false, changedAt: clock }),
    clock' = clock, awake' = awake, versions' = versions, l1Tags' = l1Tags,
    jobTags' = jobTags, axJobPending' = axJobPending, keep' = keep,
    unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  /// `ax delete task` by the operator.
  action operatorDelete(t: int): bool = all {
    awake,
    liveTasks.contains(t),
    tasks' = tasks.set(t, { ...tasks.get(t), alive: false }),
    clock' = clock, awake' = awake, versions' = versions, l1Tags' = l1Tags,
    jobTags' = jobTags, axJobPending' = axJobPending, keep' = keep,
    unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  /// A background write to a SUSPENDED actor's row: its update_time moves,
  /// and nothing else. Enabled only in `backgroundWriteRefreshes`.
  action backgroundWrite(t: int): bool = all {
    background_writes,
    awake,
    liveTasks.contains(t),
    tasks.get(t).suspended,
    tasks' = tasks.set(t, { ...tasks.get(t), changedAt: clock }),
    clock' = clock, awake' = awake, versions' = versions, l1Tags' = l1Tags,
    jobTags' = jobTags, axJobPending' = axJobPending, keep' = keep,
    unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  /// `just exe-keep add|rm`, on the operator's Mac: any time.
  action keepTask(t: int, kept: bool): bool = all {
    keep.contains(t) != kept,
    keep' = if (kept) keep.union(Set(t)) else keep.exclude(Set(t)),
    clock' = clock, awake' = awake, tasks' = tasks, versions' = versions,
    l1Tags' = l1Tags, jobTags' = jobTags, axJobPending' = axJobPending,
    unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  action wake: bool = all {
    not(awake),
    awake' = true,
    clock' = clock, tasks' = tasks, versions' = versions, l1Tags' = l1Tags,
    jobTags' = jobTags, axJobPending' = axJobPending, keep' = keep,
    unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  /// The drain suspends every live task, and the node goes. An ax-job caught
  /// between its tag and its apply is abandoned.
  action sleep: bool = all {
    awake,
    awake' = false,
    tasks' = tasks.keys().mapBy(t => {
      val task = tasks.get(t)
      if (task.alive and not(task.suspended))
        { ...task, suspended: true, changedAt: clock, suspendedAt: clock }
      else task
    }),
    axJobPending' = Map(),
    clock' = clock, versions' = versions, l1Tags' = l1Tags, jobTags' = jobTags,
    keep' = keep, unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  action dayPasses: bool = all {
    clock < HORIZON,
    clock' = clock + 1,
    // ax-job applies within minutes of its tag, never on a later day.
    axJobPending' = Map(),
    awake' = awake, tasks' = tasks, versions' = versions, l1Tags' = l1Tags,
    jobTags' = jobTags, keep' = keep, unreferencedSince' = unreferencedSince,
    unchangedEvidence,
  }

  /// What Artifact Registry's cleanup would take now: every untagged version
  /// older than ar_delete_days.
  val collectable: Set[int] = DIGESTS.filter(d => and {
    available(d),
    not(tagged(d)),
    clock - versions.get(d).pushedAt >= ar_delete_days,
  })

  /// Artifact Registry's cleanup, at any moment.
  action arCleanup: bool = {
    val doomed = collectable
    all {
      doomed != Set(),
      versions' = versions.keys().mapBy(d =>
        if (doomed.contains(d)) { ...versions.get(d), collected: true } else versions.get(d)),
      // Parenthesised: `x' = a or b` would read as `(x' = a) or b`.
      liveImageCollected' = (liveImageCollected or liveTasks.exists(t =>
        tasks.get(t).protected and doomed.contains(tasks.get(t).digest))),
      deletedEarly' = deletedEarly,
      ttlMissed' = ttlMissed,
      clock' = clock, awake' = awake, tasks' = tasks, l1Tags' = l1Tags,
      jobTags' = jobTags, axJobPending' = axJobPending, keep' = keep,
      unreferencedSince' = unreferencedSince,
    }
  }

  // --------------------------------------------------------------------------
  // L1's retention tick (only with a node up)
  // --------------------------------------------------------------------------

  action l1RetentionTick: bool = {
    val expired = liveTasks.filter(t => ttlExpired(t))
    val remaining = liveTasks.exclude(expired)
    val referenced = remaining.map(t => tasks.get(t).digest)
    val allL1 = l1Tags.union(referenced)
    val unreferenced = allL1.exclude(referenced)
    val since = unreferenced.mapBy(d =>
      if (unreferencedSince.keys().contains(d)) unreferencedSince.get(d) else clock)
    val releasedL1 = unreferenced.filter(d => clock - since.get(d) >= tag_release_days)
    val releasedJob = jobTags.filter(jt => clock - jt._2 >= tag_release_days)
    all {
      awake,
      tasks' = tasks.keys().mapBy(t => {
        val task = tasks.get(t)
        if (expired.contains(t)) { ...task, alive: false }
        else if (remaining.contains(t))
          { ...task,
            protected: true,
            firstSeenSuspended:
              if (not(task.suspended)) NONE
              else if (task.firstSeenSuspended != NONE) task.firstSeenSuspended
              else clock }
        else task
      }),
      l1Tags' = allL1.exclude(releasedL1),
      jobTags' = jobTags.exclude(releasedJob),
      unreferencedSince' = unreferenced.exclude(releasedL1).mapBy(d => since.get(d)),
      // Parenthesised: `x' = a or b` would read as `(x' = a) or b`.
      deletedEarly' = (deletedEarly or expired.exists(t => not(ttlExpiredForReal(t)))),
      // The liveness half: a task whose TTL has really run out and that this
      // tick leaves alive is a TTL that did not fire.
      ttlMissed' = (ttlMissed or remaining.exists(t => ttlExpiredForReal(t))),
      liveImageCollected' = liveImageCollected,
      clock' = clock, awake' = awake, versions' = versions,
      axJobPending' = axJobPending, keep' = keep,
    }
  }

  // --------------------------------------------------------------------------
  // Init and step
  // --------------------------------------------------------------------------

  action init: bool = all {
    clock' = 0,
    awake' = false,
    tasks' = Map(),
    versions' = DIGESTS.mapBy(_ => { pushedAt: NONE, collected: false }),
    l1Tags' = Set(),
    jobTags' = Set(),
    axJobPending' = Map(),
    keep' = Set(),
    unreferencedSince' = Map(),
    deletedEarly' = false,
    liveImageCollected' = false,
    ttlMissed' = false,
  }

  action step: bool = any {
    nondet d = oneOf(DIGESTS)
    nondet t = oneOf(TASKS)
    nondet kept = oneOf(Set(true, false))
    any {
      push(d),
      axJobTag(t, d),
      axJobApply(t),
      rawApply(t, d),
      suspendTask(t),
      resumeTask(t),
      operatorDelete(t),
      keepTask(t, kept),
      backgroundWrite(t),
    },
    wake,
    sleep,
    dayPasses,
    arCleanup,
    l1RetentionTick,
  }

  // --------------------------------------------------------------------------
  // Invariants
  // --------------------------------------------------------------------------

  /// AR never collects the image of a live task that is protected: created
  /// through ax-job, or seen by an L1 tick.
  val NoLiveImageCollected = not(liveImageCollected)

  /// A task L1 deletes has really been SUSPENDED for task_ttl_days, and is
  /// not kept.
  val TtlDeletesOnlyTheExpired = not(deletedEarly)

  /// Every protected live task's image carries a tag right now: the state
  /// form of "a tag is released only when nothing live needs it".
  val ProtectedImagesAreTagged = liveTasks.forall(t =>
    tasks.get(t).protected implies tagged(tasks.get(t).digest))

  /// The liveness half, as a bounded response: every L1 tick at or past a
  /// task's TTL -- SUSPENDED and untouched for task_ttl_days, and not kept --
  /// deletes it.
  val TtlNeverMissed = not(ttlMissed)

  val Retention = and {
    NoLiveImageCollected,
    TtlDeletesOnlyTheExpired,
    ProtectedImagesAreTagged,
    TtlNeverMissed,
  }
}

// ============================================================================
// The decided design
// ============================================================================
module retention {
  import retentionCore(shared_job_tag = false, ttl_by_first_sight = false, background_writes = false).*

  /// The helper every scripted run starts from: a node up and one image.
  action upWithImage(d: int): bool = init.then(wake).then(push(d))

  /// A task suspended and left alone for task_ttl_days is deleted at the
  /// first tick after that, and not a day before.
  run ttlDeletesOnlyAfterThirtyDaysTest =
    upWithImage(1)
      .then(axJobTag(1, 1)).then(axJobApply(1))
      .then(suspendTask(1))
      .then(sleep)
      .then((task_ttl_days - 1).reps(_ => dayPasses))
      .then(wake)
      .then(l1RetentionTick)
      .expect(tasks.get(1).alive)
      .then(sleep)
      .then(dayPasses)
      .then(wake)
      .then(l1RetentionTick)
      .expect(and { not(tasks.get(1).alive), Retention })

  /// The liveness half: a task suspended by the drain as the node went to
  /// sleep, and not touched again, is deleted by the first tick of the first
  /// wake after its TTL, however long the sleep.
  run theFirstWakeAfterTheTtlDeletesTest =
    upWithImage(1)
      .then(axJobTag(1, 1)).then(axJobApply(1))
      .then(sleep)                                    // the drain suspends it
      .then((task_ttl_days + 20).reps(_ => dayPasses))
      .then(wake)
      .then(l1RetentionTick)
      .expect(and { not(tasks.get(1).alive), Retention })

  /// A kept task is never deleted by the TTL.
  run aKeptTaskOutlivesTheTtlTest =
    upWithImage(1)
      .then(axJobTag(1, 1)).then(axJobApply(1))
      .then(keepTask(1, true))
      .then(sleep)
      .then((task_ttl_days + 5).reps(_ => dayPasses))
      .then(wake)
      .then(l1RetentionTick)
      .expect(and { tasks.get(1).alive, Retention })

  /// A resume restarts the TTL: the store's update_time moves.
  run aResumeRestartsTheTtlTest =
    upWithImage(1)
      .then(axJobTag(1, 1)).then(axJobApply(1))
      .then(suspendTask(1))
      .then(l1RetentionTick)
      .then((task_ttl_days - 1).reps(_ => dayPasses))
      .then(resumeTask(1))
      .then(suspendTask(1))
      .then(dayPasses)
      .then(l1RetentionTick)
      .expect(and { tasks.get(1).alive, Retention })

  /// The case the shared tag loses: a digest whose last task went long ago is
  /// used again through ax-job, and an L1 tick lands between the tag and the
  /// apply. The dated tag keeps the image through the tick and past AR's
  /// cleanup.
  run anAxJobImageSurvivesAStaleRecordTest =
    upWithImage(1)
      .then(axJobTag(1, 1)).then(axJobApply(1))
      .then(l1RetentionTick)
      .then(operatorDelete(1))
      .then(l1RetentionTick)                          // digest 1 unreferenced since day 0
      .then((ar_delete_days + 1).reps(_ => dayPasses))
      .then(axJobTag(2, 1))
      .then(l1RetentionTick)                          // releases L1's stale tag, not ax-job's
      .then(axJobApply(2))
      .expect(and { collectable == Set(), Retention })  // nothing for AR to take

  /// An image nothing uses any more is released after tag_release_days and
  /// collected by AR once it is old enough.
  run anUnusedImageIsReleasedThenCollectedTest =
    upWithImage(1)
      .then(axJobTag(1, 1)).then(axJobApply(1))
      .then(l1RetentionTick)
      .then(operatorDelete(1))
      .then(l1RetentionTick)
      .then(tag_release_days.reps(_ => dayPasses))
      .then(l1RetentionTick)
      .expect(not(tagged(1)))
      .then((ar_delete_days - tag_release_days).reps(_ => dayPasses))
      .then(arCleanup)
      .expect(and { versions.get(1).collected, Retention })
}

// ============================================================================
// REJECTED DESIGN 1 -- ax-job tags the shared inuse-<sha12>
//
// Scope: how ax-job protects an image before the task exists.
// Accepted by: plan D10 as amended in Phase 6 -- ax-job's own tag,
//   `inuse-<sha12>-<unix>`, dated by its name.
// Why rejected: L1's record of when a digest became unreferenced can be weeks
//   old. A tick between ax-job's tag and its apply sees the shared tag on a
//   digest "unreferenced for weeks" and releases it; the task is then created
//   on an untagged image, and AR's next cleanup collects it.
// ============================================================================
module sharedJobTag {
  import retentionCore(shared_job_tag = true, ttl_by_first_sight = false, background_writes = false).*

  /// EXPECTED TO FAIL (ProtectedImagesAreTagged, then NoLiveImageCollected).
  run sharedTagLetsAFreshTasksImageBeCollected =
    init.then(wake).then(push(1))
      .then(axJobTag(1, 1)).then(axJobApply(1))
      .then(l1RetentionTick)
      .then(operatorDelete(1))
      .then(l1RetentionTick)                          // digest 1 unreferenced since day 0
      .then((ar_delete_days + 1).reps(_ => dayPasses))
      .then(axJobTag(2, 1))                           // the shared tag, already there
      .then(l1RetentionTick)                          // stale record: released
      .then(axJobApply(2))                            // a task on an untagged image
      .then(arCleanup)
      .expect(Retention)
}

// ============================================================================
// REJECTED DESIGN 2 -- the TTL counts from L1's first sight
//
// Scope: what "suspended for 30 days" is measured from.
// Accepted by: plan D10 as amended in Phase 6 -- the Substrate store's
//   update_time for the task's actor, which every state change moves.
// Why rejected: L1 sees only what is there when it ticks. A resume and a
//   re-suspend between two ticks leave its first-sight record unchanged, and
//   the task is deleted as a month old the day after it was used.
// ============================================================================
module ttlByFirstSight {
  import retentionCore(shared_job_tag = false, ttl_by_first_sight = true, background_writes = false).*

  /// EXPECTED TO FAIL (TtlDeletesOnlyTheExpired).
  run firstSightDeletesATaskUsedYesterday =
    init.then(wake).then(push(1))
      .then(axJobTag(1, 1)).then(axJobApply(1))
      .then(suspendTask(1))
      .then(l1RetentionTick)                          // first sight: day 0
      .then((task_ttl_days - 1).reps(_ => dayPasses))
      .then(resumeTask(1))                            // used on day 29 ...
      .then(suspendTask(1))                           // ... and suspended again, between ticks
      .then(dayPasses)
      .then(l1RetentionTick)                          // day 30 by first sight: deleted
      .expect(Retention)
}

// ============================================================================
// REJECTED DESIGN 3 -- a background writer keeps update_time fresh
//
// Scope: the assumption the TTL clock rests on, not a design anyone chose.
// Accepted by: the Phase 6 amendment of plan D10, on source evidence that the
//   pinned Substrate has no such writer (exe/spec/README.md); the live runs
//   record a suspended actor's update_time across a sleep to confirm it.
// Why it matters: if a Substrate upgrade adds a periodic write to suspended
//   actors, update_time never ages, the TTL never fires, and storage grows
//   without bound. This instance keeps TtlNeverMissed honest: it must FAIL.
// ============================================================================
module backgroundWriteRefreshes {
  import retentionCore(shared_job_tag = false, ttl_by_first_sight = false, background_writes = true).*

  /// EXPECTED TO FAIL (TtlNeverMissed).
  run aBackgroundWriteKeepsATaskForever =
    init.then(wake).then(push(1))
      .then(axJobTag(1, 1)).then(axJobApply(1))
      .then(suspendTask(1))
      .then((task_ttl_days / 2).reps(_ => dayPasses))
      .then(backgroundWrite(1))                       // update_time moves, nobody resumed it
      .then((task_ttl_days / 2 + 1).reps(_ => dayPasses))
      .then(l1RetentionTick)                          // suspended 31 days: must be deleted
      .expect(Retention)
}
