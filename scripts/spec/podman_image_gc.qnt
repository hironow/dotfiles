// Scoped ADR0067 image GC model, owner-authorized 2026-11-08.
// Shell/PS final inspect -> nonforced rmi --no-prune is the deletion boundary.
// The parent is not independently selected: this models one candidate removal,
// not a promise that an aged parent can never be selected in its own turn.
// No global lock/lease is claimed. Arbitrary third-party post-inspect retag,
// FORCE's explicit foreign-job override, workspace/toolcache and cache GC are
// outside this model. Engine reference refusal compensates for reference races.
// configurationOk abstracts checked clock/duration validation. Mathematical
// integers do NOT execute machine overflow or concrete image-ID representations;
// those are covered by public-script regressions with native-shaped full IDs.
module podman_image_gc {
  pure val RETENTION_SECONDS = 7200
  var phase: str
  var ageSeconds: int
  var foreignJob: bool
  var metadataOk: bool
  var configurationOk: bool
  var keepAlias: bool
  var observedKeep: bool
  var referenced: bool
  var imageExists: bool
  var parentExists: bool
  var removed: bool
  var refused: bool
  var authorized: bool

  action init = all {
    phase' = "firstInspect",
    ageSeconds' = RETENTION_SECONDS + 1,
    foreignJob' = false,
    metadataOk' = true,
    configurationOk' = true,
    keepAlias' = false,
    observedKeep' = false,
    referenced' = false,
    imageExists' = true,
    parentExists' = true,
    removed' = false,
    refused' = false,
    authorized' = false,
  }

  action configure(age: int, busy: bool, valid: bool, keep: bool, used: bool): bool = all {
    phase == "firstInspect",
    configurationOk' = configurationOk,
    ageSeconds' = age,
    foreignJob' = busy,
    metadataOk' = valid,
    keepAlias' = keep,
    referenced' = used,
    phase' = "finalInspect",
    observedKeep' = keep,
    imageExists' = imageExists,
    parentExists' = parentExists,
    removed' = removed,
    refused' = refused,
    authorized' = authorized,
  }

  action invalidateConfiguration = all {
    phase == "firstInspect",
    configurationOk' = false,
    phase' = phase, ageSeconds' = ageSeconds, foreignJob' = foreignJob,
    metadataOk' = metadataOk, keepAlias' = keepAlias, observedKeep' = observedKeep,
    referenced' = referenced, imageExists' = imageExists, parentExists' = parentExists,
    removed' = removed, refused' = refused, authorized' = authorized,
  }

  action environment = {
    nondet age = Set(RETENTION_SECONDS - 1, RETENTION_SECONDS, RETENTION_SECONDS + 1).oneOf()
    nondet busy = Set(false, true).oneOf()
    nondet valid = Set(false, true).oneOf()
    nondet keep = Set(false, true).oneOf()
    nondet used = Set(false, true).oneOf()
    configure(age, busy, valid, keep, used)
  }

  // Changes between the two observations must be seen by the final inspect.
  action beforeFinal(keep: bool, valid: bool, busy: bool): bool = all {
    phase == "finalInspect",
    configurationOk' = configurationOk,
    keepAlias' = keep, metadataOk' = valid, foreignJob' = busy,
    phase' = phase, observedKeep' = observedKeep, referenced' = referenced,
    ageSeconds' = ageSeconds, imageExists' = imageExists, parentExists' = parentExists,
    removed' = removed, refused' = refused, authorized' = authorized,
  }

  action observe = all {
    phase == "finalInspect",
    configurationOk' = configurationOk,
    phase' = "remove",
    observedKeep' = keepAlias,
    ageSeconds' = ageSeconds,
    foreignJob' = foreignJob,
    metadataOk' = metadataOk,
    keepAlias' = keepAlias,
    referenced' = referenced,
    imageExists' = imageExists,
    parentExists' = parentExists,
    removed' = removed,
    refused' = refused,
    authorized' = authorized,
  }

  // Only a reference can change after final inspect in the modeled scope.
  action acquireReference = all {
    phase == "remove", imageExists, not(referenced),
    configurationOk' = configurationOk,
    referenced' = true,
    phase' = phase,
    ageSeconds' = ageSeconds,
    foreignJob' = foreignJob,
    metadataOk' = metadataOk,
    keepAlias' = keepAlias,
    observedKeep' = observedKeep,
    imageExists' = imageExists,
    parentExists' = parentExists,
    removed' = removed,
    refused' = refused,
    authorized' = authorized,
  }

  val eligible = configurationOk and not(foreignJob) and metadataOk and
    ageSeconds > RETENTION_SECONDS and not(observedKeep)

  action remove = all {
    phase == "remove",
    configurationOk' = configurationOk,
    phase' = "done",
    authorized' = (eligible and not(referenced)),
    removed' = (eligible and not(referenced)),
    refused' = (eligible and referenced),
    imageExists' = not(eligible and not(referenced)),
    parentExists' = parentExists,
    ageSeconds' = ageSeconds,
    foreignJob' = foreignJob,
    metadataOk' = metadataOk,
    keepAlias' = keepAlias,
    observedKeep' = observedKeep,
    referenced' = referenced,
  }

  action idle = all {
    phase == "done",
    configurationOk' = configurationOk,
    phase' = phase, ageSeconds' = ageSeconds, foreignJob' = foreignJob,
    metadataOk' = metadataOk, keepAlias' = keepAlias, observedKeep' = observedKeep,
    referenced' = referenced, imageExists' = imageExists, parentExists' = parentExists,
    removed' = removed, refused' = refused, authorized' = authorized,
  }
  action step = any {
    invalidateConfiguration, environment, beforeFinal(true, metadataOk, foreignJob),
    beforeFinal(keepAlias, false, foreignJob), beforeFinal(keepAlias, metadataOk, true),
    observe, acquireReference, remove, idle,
  }

  val DeletePrecondition = removed implies authorized
  val ForeignJobProtection = foreignJob implies not(removed)
  val AgeProtection = ageSeconds <= RETENTION_SECONDS implies not(removed)
  val MetadataProtection = not(metadataOk) implies not(removed)
  val ConfigurationProtection = not(configurationOk) implies not(removed)
  val ObservedKeepProtection = observedKeep implies not(removed)
  val ReferenceProtection = referenced implies imageExists
  val ParentProtection = parentExists
  val Safety = DeletePrecondition and ForeignJobProtection and AgeProtection and
    MetadataProtection and ConfigurationProtection and ObservedKeepProtection and ReferenceProtection and ParentProtection

  run invalidConfigurationTest = init.then(invalidateConfiguration)
    .then(configure(7201, false, true, false, false)).then(observe)
    .then(remove).expect(Safety and imageExists and not(removed))

  run concurrentReferenceTest = init
    .then(configure(7201, false, true, false, false)).then(observe)
    .then(acquireReference).then(remove).expect(Safety and imageExists and refused)
  run observedKeepAliasTest = init
    .then(configure(7201, false, true, true, false)).then(observe)
    .then(remove).expect(Safety and imageExists)
  run lateKeepAliasTest = init
    .then(configure(7201, false, true, false, false))
    .then(beforeFinal(true, true, false)).then(observe)
    .then(remove).expect(Safety and imageExists)
  run finalMetadataFailureTest = init
    .then(configure(7201, false, true, false, false))
    .then(beforeFinal(false, false, false)).then(observe)
    .then(remove).expect(Safety and imageExists)
  run ageBoundaryTest = init
    .then(configure(7200, false, true, false, false)).then(observe)
    .then(remove).expect(Safety and imageExists)
  run metadataFailureTest = init
    .then(configure(7201, false, false, false, false)).then(observe)
    .then(remove).expect(Safety and imageExists)
  run foreignJobTest = init
    .then(configure(7201, true, true, false, false)).then(observe)
    .then(remove).expect(Safety and imageExists)
  run eligibleImageTest = init
    .then(configure(7201, false, true, false, false)).then(observe)
    .then(remove).expect(Safety and removed and parentExists)

  // Historical unsafe command semantics: force deletes a referencing container
  // and ordinary rmi without --no-prune can delete a young dangling parent.
  action unsafeForceAndParentPrune = all {
    phase == "remove", referenced,
    configurationOk' = configurationOk,
    phase' = "done", removed' = true, imageExists' = false, parentExists' = false,
    authorized' = false, refused' = false,
    ageSeconds' = ageSeconds, foreignJob' = foreignJob, metadataOk' = metadataOk,
    keepAlias' = keepAlias, observedKeep' = observedKeep, referenced' = referenced,
  }
  run forceParentCounterexampleTest = init
    .then(configure(7201, false, true, false, false)).then(observe)
    .then(acquireReference).then(unsafeForceAndParentPrune).expect(not(Safety))
}
