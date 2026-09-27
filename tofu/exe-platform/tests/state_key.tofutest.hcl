# What this file pins: the KMS key that encrypts tofu/exe-cluster's state.
#
# That stack's state carries secrets -- the Postgres password inside the
# Substrate DSN, the Redis requirepass, later the Gemini key -- so it is
# encrypted with OpenTofu state encryption, and the key lives here, in the
# platform that outlives any one install. Four things are pinned:
#
#   - the key is for symmetric encryption, which is what the gcp_kms key
#     provider wraps its data key with;
#   - it sits in the stack's own region, next to the state bucket, not in the
#     "global" location that any neighbour's key ring shares;
#   - its name and ring name are exe-scoped, on a project shared with two
#     unrelated stacks;
#   - it is software-protected, the cheapest level (an HSM key costs orders of
#     magnitude more per version and buys nothing for a state file).
#
# prevent_destroy is on both resources and cannot be asserted from a plan; the
# comment on them in kms.tf says why it is there. KMS itself refuses to delete
# a key ring, and a destroyed key version makes every state it encrypted
# unreadable -- the one irreversible mistake in this stack.
#
# command = plan + mock_provider: offline, no credentials, nothing created.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "the_state_key_encrypts_symmetrically_in_the_stacks_region" {
  command = plan

  assert {
    condition     = google_kms_crypto_key.state.purpose == "ENCRYPT_DECRYPT"
    error_message = "the exe-cluster state key must be a symmetric ENCRYPT_DECRYPT key: OpenTofu's gcp_kms key provider wraps its data key with encrypt/decrypt, and any other purpose cannot."
  }

  assert {
    condition     = google_kms_crypto_key.state.version_template[0].protection_level == "SOFTWARE"
    error_message = "the exe-cluster state key must be SOFTWARE-protected: an HSM key costs far more per version per month and adds nothing for a state file."
  }

  assert {
    condition     = google_kms_crypto_key.state.version_template[0].algorithm == "GOOGLE_SYMMETRIC_ENCRYPTION"
    error_message = "the exe-cluster state key must use GOOGLE_SYMMETRIC_ENCRYPTION, the algorithm the gcp_kms key provider expects."
  }

  assert {
    condition     = google_kms_key_ring.state.location == "asia-northeast1"
    error_message = "the state key ring must be regional (asia-northeast1), next to the state bucket: the global location is shared with every neighbour's key rings."
  }

  assert {
    condition     = google_kms_crypto_key.state.key_ring == google_kms_key_ring.state.id
    error_message = "the exe-cluster state key must live in this stack's own key ring."
  }
}

run "the_state_key_and_ring_are_exe_scoped" {
  command = plan

  assert {
    condition     = startswith(google_kms_key_ring.state.name, "exe-")
    error_message = "the state key ring must be exe-scoped: key rings cannot be deleted, so a name that collides with a neighbour's is permanent."
  }

  assert {
    condition     = google_kms_crypto_key.state.name == "exe-cluster-state"
    error_message = "the state key must be named for the one state it encrypts, exe-cluster-state; a second stack that needs encrypted state gets its own key."
  }

  assert {
    condition     = google_kms_key_ring.state.project == "zz-synthetic-project"
    error_message = "the state key ring must be created in the private project, from the variable."
  }
}

run "the_state_key_rotates_never_on_a_timer" {
  command = plan

  # Every rotation adds a key version that bills monthly and can never be
  # removed while any state it encrypted might still be read. A state file is
  # re-encrypted with the current version on every write, so rotation is a
  # deliberate operator act, not a schedule.
  assert {
    condition     = google_kms_crypto_key.state.rotation_period == null
    error_message = "the state key must not rotate on a timer: each rotation adds a version that bills every month and cannot be deleted while old state may need it. Rotate by hand when there is a reason."
  }
}
