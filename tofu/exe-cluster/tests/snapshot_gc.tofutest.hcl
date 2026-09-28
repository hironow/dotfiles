# What this file pins: the orphan-snapshot GC's side of the cluster (Phase 6
# plan D11, option B in manager-loop inbox M35).
#
# `just exe-snapshot-gc` makes a one-off Job from the exe-snapshot-gc CronJob,
# which is suspended and never schedules anything itself. The Job runs
# `exe-reap snapshot-gc` (a dry run unless the operator adds -apply) as its own
# KSA, exe-ops/exe-snapshot-gc: the one exe-platform lets list the snapshot
# bucket and delete under two prefixes of it.
#
#   - Identity. The KSA is exactly the one exe-platform's principal names, it
#     carries no Kubernetes API token, and it has no Role
#     (tests/unit/test_exe_snapshot_gc_iam.py fails on a RoleBinding naming it).
#   - Nothing lingers. The Job ends within 15 minutes, and is removed 5 minutes
#     after it does even if the recipe could not delete it.
#   - Reach. The Control API exactly as L1 reaches it (the same token, trust
#     bundle and securityContext, compared rather than retyped, so the two
#     cannot drift), and ax-server through an allow rule of its own.
#
# command = plan + mock providers: offline, no credentials, nothing created. The
# platform's outputs are synthetic stand-ins for exe-platform's state.

mock_provider "google" {}
mock_provider "kubernetes" {}
mock_provider "kubectl" {}
mock_provider "random" {}

mock_provider "ko" {
  mock_resource "ko_build" {
    defaults = {
      image_ref = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/ax/built@sha256:1111111111111111111111111111111111111111111111111111111111111111"
    }
  }
}

override_data {
  target = data.terraform_remote_state.platform
  values = {
    outputs = {
      region                 = "asia-northeast1"
      zone                   = "asia-northeast1-a"
      cluster_name           = "exe"
      cluster_dns_endpoint   = "gke-zz.asia-northeast1.gke.goog"
      bucket_snapshots       = "zz-synthetic-project-exe-snapshots"
      bucket_ops             = "zz-synthetic-project-exe-ops"
      ar_task_repository     = "projects/zz-synthetic-project/locations/asia-northeast1/repositories/exe-task"
      ar_platform_repository = "projects/zz-synthetic-project/locations/asia-northeast1/repositories/exe-platform"
      ar_platform_repo       = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform"
      enforcer_image         = ""
      workload_identity_principals = {
        atelet      = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/ate-system/sa/atelet"
        api_server  = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/ate-system/sa/ate-api-server"
        reaper      = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/exe-ops/sa/exe-reaper"
        snapshot_gc = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/exe-ops/sa/exe-snapshot-gc"
      }
    }
  }
}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  state_kms_key      = "projects/zz-synthetic-project/locations/asia-northeast1/keyRings/exe-state/cryptoKeys/exe-cluster-state"
  exe_src_dir        = "/zz/src"

  # Stated, not left to the defaults: `tofu test` also loads the operator's
  # gitignored terraform.tfvars, which sets both once they exist.
  ateom_gvisor_image = ""
  gemini_api_key     = null
}

run "the_gc_runs_as_its_own_ksa_with_no_api_token" {
  command = plan

  assert {
    condition     = kubernetes_service_account_v1.snapshot_gc.metadata[0].name == "exe-snapshot-gc" && kubernetes_service_account_v1.snapshot_gc.metadata[0].namespace == "exe-ops"
    error_message = "the GC's KSA must be the one exe-platform's principal names (ns/exe-ops/sa/exe-snapshot-gc): any other KSA holds no grant on the snapshot bucket."
  }

  assert {
    condition     = kubernetes_service_account_v1.snapshot_gc.automount_service_account_token == false
    error_message = "the GC's KSA must not mount a Kubernetes API token: the GC calls no Kubernetes API."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.spec.serviceAccountName == "exe-snapshot-gc" && yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.spec.automountServiceAccountToken == false
    error_message = "the Job's pod must run as the GC's KSA, with no Kubernetes API token, and never as L1's exe-reaper."
  }
}

run "the_template_never_runs_by_itself_and_nothing_lingers" {
  command = plan

  assert {
    condition     = yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.suspend == true
    error_message = "the exe-snapshot-gc CronJob must stay suspended: it is only the template `just exe-snapshot-gc` makes its one-off Job from."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.ttlSecondsAfterFinished > 0 && yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.ttlSecondsAfterFinished <= 600
    error_message = "a finished GC Job must be removed within 10 minutes, even when the recipe could not delete it: nothing holding the GC's identity lingers (inbox M35)."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.activeDeadlineSeconds > 0 && yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.activeDeadlineSeconds <= 1800 && yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.backoffLimit == 0
    error_message = "a GC Job must end on a deadline of at most 30 minutes, with no retries: a run that has not finished by then is stuck, and a retry is the operator's call."
  }
}

run "the_gc_is_a_dry_run_of_exe_reap_unless_told_otherwise" {
  command = plan

  assert {
    condition     = yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.spec.containers[0].image == ko_build.exe_reap.image_ref && yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.spec.containers[0].args == ["snapshot-gc"]
    error_message = "the Job must run `exe-reap snapshot-gc` from the same digest as L1, with no -apply in the template: only the operator adds it, per run."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.spec.containers[0].env == [{ name = "EXE_SNAPSHOTS_LOCATION", value = "gs://zz-synthetic-project-exe-snapshots/ax/" }]
    error_message = "EXE_SNAPSHOTS_LOCATION must be the location AX's ActorTemplates use (ax_snapshots_location), and the only env: the GC reaches the Control API and ax-server at exe-reap's defaults."
  }
}

run "the_gc_reaches_substrate_exactly_as_l1_does" {
  command = plan

  assert {
    condition     = yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.spec.volumes == yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.volumes && yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.spec.containers[0].volumeMounts == yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.containers[0].volumeMounts
    error_message = "the GC's token and trust bundle must be L1's, volume for volume: the Control API accepts exactly that audience and chain."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.spec.securityContext == yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.securityContext && yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.spec.containers[0].securityContext == yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.containers[0].securityContext
    error_message = "the GC must run as locked down as L1: non-root, RuntimeDefault seccomp, read-only root, no privilege escalation, no capabilities."
  }

  assert {
    condition     = kubernetes_network_policy_v1.ax_server_from_snapshot_gc.metadata[0].namespace == "ax-system" && kubernetes_network_policy_v1.ax_server_from_snapshot_gc.spec[0].pod_selector[0].match_labels["app.kubernetes.io/name"] == "ax-server"
    error_message = "the GC's allow rule must select ax-server in ax-system."
  }

  assert {
    condition     = length(kubernetes_network_policy_v1.ax_server_from_snapshot_gc.spec[0].ingress) == 1 && length(kubernetes_network_policy_v1.ax_server_from_snapshot_gc.spec[0].ingress[0].from) == 1 && kubernetes_network_policy_v1.ax_server_from_snapshot_gc.spec[0].ingress[0].from[0].namespace_selector[0].match_labels["kubernetes.io/metadata.name"] == "exe-ops" && kubernetes_network_policy_v1.ax_server_from_snapshot_gc.spec[0].ingress[0].from[0].pod_selector[0].match_labels["app.kubernetes.io/name"] == yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.metadata.labels["app.kubernetes.io/name"]
    error_message = "ax-server must admit exactly the GC's own pods (exe-ops, its own label), and nothing else through this rule."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.snapshot_gc.yaml_body).spec.jobTemplate.spec.template.metadata.labels["app.kubernetes.io/name"] == "exe-snapshot-gc"
    error_message = "the GC's pods must carry their own name label, not L1's exe-reap: each allow rule admits one identity."
  }
}
