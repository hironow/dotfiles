# The key that encrypts tofu/exe-cluster's state.
#
# That stack's state holds secrets: the Postgres password inside the Substrate
# DSN, the Redis requirepass, and later the Gemini key. OpenTofu state
# encryption (the gcp_kms key provider) wraps a data key with this KMS key, so
# the state bucket only ever holds ciphertext. It lives here, in the platform,
# because the platform outlives any one install of the cluster stack.
#
# Who can use it: the operator, as project Owner (roles/owner carries
# cloudkms.cryptoKeyVersions.useToEncrypt / useToDecrypt), and nobody else. No
# service account needs it: nothing but a human runs tofu against exe-cluster.
#
# prevent_destroy on both, because this is the one irreversible mistake in the
# stack: KMS refuses to delete a key ring anyway, and a key whose versions are
# destroyed turns every state it encrypted into noise. A teardown that really
# means it removes the lifecycle block first, on purpose.

resource "google_kms_key_ring" "state" {
  project  = var.gcp_project_id
  name     = "${local.prefix}-state"
  location = local.region

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.enabled]
}

resource "google_kms_crypto_key" "state" {
  name     = "${local.prefix}-cluster-state"
  key_ring = google_kms_key_ring.state.id
  purpose  = "ENCRYPT_DECRYPT"

  # No rotation_period, on purpose. Each rotation adds a key version that bills
  # every month and has to be kept for as long as any state it encrypted could
  # be read; state is re-encrypted with the current version on every write, so
  # rotating is a deliberate operator act, not a schedule.

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }

  labels = local.common_labels

  lifecycle {
    prevent_destroy = true
  }
}
