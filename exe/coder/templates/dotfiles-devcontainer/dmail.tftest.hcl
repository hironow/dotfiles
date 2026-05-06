# Test harness for the dmail-receiver / dmail-emitter related
# variables added to this Coder workspace template (Issue 0001
# Phase 1 + codex review #2).
#
# What this file pins (and the pytest test_dmail_daemon_placement.py
# does NOT pin, by design):
#
#   - all four runtime variables resolve to the right production
#     defaults so a 'cdr templates push' without any --variable flag
#     produces a workspace VM that talks to the production Pub/Sub
#     topology;
#   - both image variables default to a tag pattern that points at
#     Artifact Registry under the runops-gateway repo's CD path
#     (per ADR 0023);
#   - the placeholder default for the image is a safe sentinel — it
#     points at a non-existent tag so a forgotten 'cdr templates
#     push --variable dmail_*_image=...' fails fast at workspace
#     boot rather than silently running a stale tag.
#
# The pytest side (tests/exe/test_dmail_daemon_placement.py) keeps
# the heredoc-content checks (ExecStart= / Restart=on-failure /
# volume mount paths) and the systemd-analyze verify pass because
# those depend on extracting and parsing strings from a multi-page
# HCL heredoc — a problem terraform test was not designed for.
#
# command = plan + mock_provider keeps these tests offline; no GCP
# auth, no Coder server, no docker pull.

mock_provider "google" {}
mock_provider "coder" {}

variables {
  workspace_sa_email = "exe-workspace@test-project.iam.gserviceaccount.com"
  coder_internal_url = "http://exe-coder:7080"
}

run "runtime_variable_defaults_match_production" {
  command = plan

  assert {
    condition     = var.pubsub_dmail_inbound_subscription == "dmail-inbound-receiver"
    error_message = "default subscription must match the runops-gateway repo's tofu/subscriptions.tf 'dmail-inbound-receiver'; otherwise the daemon pulls from the wrong subscription."
  }

  assert {
    condition     = var.pubsub_dmail_outbound_topic == "dmail-outbound"
    error_message = "default outbound topic must match the runops-gateway repo's tofu/pubsub.tf 'dmail-outbound'; otherwise the emitter publishes to a topic the gateway is not subscribed to."
  }

  assert {
    condition     = var.otel_exporter_otlp_endpoint == "telemetry.googleapis.com:443"
    error_message = "default OTLP endpoint must be Google Cloud Trace ingest in production. Override only via --variable for local-collector development."
  }

  assert {
    condition     = var.otel_traces_sampler_arg == "1.0"
    error_message = "default trace sampling ratio must be 1.0 in development. Production should override to 0.1 or lower via --variable."
  }
}

run "image_variable_defaults_point_at_runops_artifact_registry" {
  command = plan

  assert {
    condition = startswith(
      var.dmail_receiver_image,
      "asia-northeast1-docker.pkg.dev/gen-ai-hironow/runops/dmail-receiver:"
    )
    error_message = "default dmail_receiver_image must point at <region>-docker.pkg.dev/<project>/runops/dmail-receiver:* per ADR 0023. Wrong AR path means the workspace VM cannot pull the image at boot."
  }

  assert {
    condition = startswith(
      var.dmail_emitter_image,
      "asia-northeast1-docker.pkg.dev/gen-ai-hironow/runops/dmail-emitter:"
    )
    error_message = "default dmail_emitter_image must point at <region>-docker.pkg.dev/<project>/runops/dmail-emitter:* per ADR 0023."
  }

  # Defaults end with ':placeholder' so a forgotten --variable flag
  # at template-push time produces a 404 on docker pull (visible in
  # the workspace startup log) rather than a silent run of a stale
  # tag. Once Phase 2 publishes real images, operators will flip to
  # ':<sha>' via 'cdr templates push --variable dmail_*_image=...'.
  assert {
    condition     = endswith(var.dmail_receiver_image, ":placeholder")
    error_message = "default dmail_receiver_image must end with :placeholder until Phase 2 lands. A non-placeholder default would imply images are already published, which they are not until the runops-gateway CD path runs against a real GCP project."
  }

  assert {
    condition     = endswith(var.dmail_emitter_image, ":placeholder")
    error_message = "default dmail_emitter_image must end with :placeholder until Phase 2 lands."
  }
}
