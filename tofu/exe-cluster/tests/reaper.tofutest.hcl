# What this file pins: L1, the in-cluster reaper (Phase 6 plan D1, D2).
#
# exe-reap runs once a minute as a CronJob. It reads every actor through the
# Substrate Control API, reads and writes drain.json in the ops bucket, scales
# the atenet-router and the ax-controller, asks ax-server to suspend tasks, and
# deletes a wedged worker's pod. Each of those is a grant or a path, and each
# is pinned here, because L1's failure mode is a tick that cannot do one of
# them: the drain then never finishes, and L2 forces the stop and pages.
#
#   - Identity. The KSA is exactly the one exe-platform binds to the ops bucket
#     (workload_identity_principals.reaper), read from that stack's state
#     rather than retyped: a KSA under another name holds no grant, and every
#     tick 403s.
#   - Cadence. Every minute, never two at once, a tick that cannot outlive its
#     minute, no retries (the next minute is the retry), and a bounded history.
#   - Image. exe-reap, built from this repo over the same digest-pinned base
#     as AX.
#   - Reach. The Control API exactly as the ax-controller reaches it (a
#     projected token for api.ate-system.svc, the servicedns trust bundle);
#     ax-server through one NetworkPolicy allow rule; and the Kubernetes API
#     through RBAC that names the two Deployments and nothing else.
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
      region               = "asia-northeast1"
      zone                 = "asia-northeast1-a"
      cluster_name         = "exe"
      cluster_dns_endpoint = "gke-zz.asia-northeast1.gke.goog"
      bucket_snapshots     = "zz-synthetic-project-exe-snapshots"
      bucket_ops           = "zz-synthetic-project-exe-ops"
      ar_platform_repo     = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform"
      workload_identity_principals = {
        atelet     = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/ate-system/sa/atelet"
        api_server = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/ate-system/sa/ate-api-server"
        reaper     = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/exe-ops/sa/exe-reaper"
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

run "the_reaper_runs_as_the_ksa_exe_platform_binds" {
  command = plan

  assert {
    condition     = kubernetes_namespace_v1.ops.metadata[0].name == "exe-ops" && kubernetes_service_account_v1.reaper.metadata[0].name == "exe-reaper" && kubernetes_service_account_v1.reaper.metadata[0].namespace == "exe-ops"
    error_message = "the reaper's namespace and KSA must be the ones exe-platform's Workload Identity principal names (ns/exe-ops/sa/exe-reaper): any other KSA holds no grant on the ops bucket, and every tick 403s on the lease."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.reaper.yaml_body).metadata.namespace == kubernetes_namespace_v1.ops.metadata[0].name && yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.serviceAccountName == kubernetes_service_account_v1.reaper.metadata[0].name
    error_message = "the CronJob must run in the reaper's namespace as the reaper's KSA."
  }
}

run "the_reaper_ticks_every_minute_one_at_a_time" {
  command = plan

  assert {
    condition     = yamldecode(kubectl_manifest.reaper.yaml_body).kind == "CronJob" && yamldecode(kubectl_manifest.reaper.yaml_body).spec.schedule == "*/${local.leases.l1_tick_minutes} * * * *"
    error_message = "the reaper must be a CronJob on l1_tick_minutes from exe/lease-constants.json. The drain ceiling, the heartbeat L2 reads and the model's clock all count in L1 ticks; a literal here is a second opinion nothing reconciles."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.reaper.yaml_body).spec.concurrencyPolicy == "Forbid"
    error_message = "concurrencyPolicy must be Forbid. Two reapers at once are two writers of drain.json; the conditional write keeps the record whole, but both would act."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.backoffLimit == 0
    error_message = "a tick gets no retries (backoffLimit 0): the next minute is the retry."
  }

  # While the pool sleeps the tick's pod cannot schedule and stays Pending, and
  # Forbid holds every later tick behind it: one Pending Job for the whole
  # sleep, run the moment a node is up (inbox M28). A Job deadline would fail
  # that Job once its time ran out, and the next minute would create another:
  # a create/fail loop all night. A tick that does run ends itself, on
  # exe-reap's own 45 s deadline.
  assert {
    condition     = !contains(keys(yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec), "activeDeadlineSeconds")
    error_message = "the reaper's Job must set no activeDeadlineSeconds: while the pool sleeps its pod stays Pending, and a deadline turns that one Pending Job into a Job created and failed every minute, all night. exe-reap's own deadline ends a tick that runs."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.reaper.yaml_body).spec.startingDeadlineSeconds <= 60
    error_message = "startingDeadlineSeconds must be at most a minute: a tick that could not start on time is replaced by the next one, not run late beside it."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.reaper.yaml_body).spec.successfulJobsHistoryLimit <= 1 && yamldecode(kubectl_manifest.reaper.yaml_body).spec.failedJobsHistoryLimit <= 3
    error_message = "the CronJob must keep at most one finished and three failed Jobs. At 1,440 runs a day, the default history is Jobs and pods the control plane stores for nothing (plan section 3.3: every sink declares its cap)."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.restartPolicy == "Never"
    error_message = "a tick's pod must not restart in place: a restarted tick is a second tick inside the same minute."
  }
}

run "the_reaper_image_is_exe_reap_over_a_digest_pinned_base" {
  command = plan

  assert {
    condition     = ko_build.exe_reap.importpath == "github.com/hironow/dotfiles/tools/exe-reaper/cmd/exe-reap"
    error_message = "the CronJob must run cmd/exe-reap, L1, and not exe-reaper: that is the binary that shrinks the pool, and it links no gRPC by design."
  }

  assert {
    condition     = endswith(ko_build.exe_reap.working_dir, "/tools/exe-reaper")
    error_message = "exe-reap must build from this repo's tools/exe-reaper module, where its tests and the model's replays run."
  }

  assert {
    condition     = ko_build.exe_reap.base_image == local.ax_base_image && can(regex("@sha256:[0-9a-f]{64}$", ko_build.exe_reap.base_image))
    error_message = "exe-reap must build over the same digest-pinned base as AX: a moving tag is a reaper that changes under a rebuild."
  }

  assert {
    condition     = ko_build.exe_reap.platforms == tolist(["linux/amd64"]) && ko_build.exe_reap.repo == "${local.platform.ar_platform_repo}/exe-reap"
    error_message = "exe-reap builds for linux/amd64, the node's architecture, into its own repository in the platform registry."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.containers[0].image == ko_build.exe_reap.image_ref
    error_message = "the CronJob must run exactly the digest ko_build pushed."
  }
}

run "the_reaper_reaches_substrate_as_the_controller_does_and_knows_its_bucket" {
  command = plan

  assert {
    condition     = length([for v in yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.volumes : v if try(v.projected.sources[0].serviceAccountToken.audience, "") == "api.ate-system.svc"]) == 1
    error_message = "the reaper must present a projected token for the audience the Control API accepts (api.ate-system.svc); without it every actor read is refused and no drain can start."
  }

  assert {
    condition     = length([for v in yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.volumes : v if try(v.projected.sources[0].clusterTrustBundle.signerName, "") == "servicedns.podcert.ate.dev/identity"]) == 1
    error_message = "the reaper must verify the Control API against the servicedns trust bundle Substrate publishes, as the ax-controller does."
  }

  assert {
    condition = toset([for m in yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.containers[0].volumeMounts : m.mountPath]) == toset([
      "/var/run/secrets/ateapi", "/run/servicedns-ca",
    ])
    error_message = "the token and the trust bundle must be mounted where exe-reap reads them by default (/var/run/secrets/ateapi/token, /run/servicedns-ca/trust-bundle.pem)."
  }

  assert {
    condition     = one([for e in yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.spec.containers[0].env : e.value if e.name == "EXE_OPS_BUCKET"]) == "zz-synthetic-project-exe-ops"
    error_message = "EXE_OPS_BUCKET must be exe-platform's ops bucket, read from its state: the lease and drain.json live there, and exe-reap exits on every tick without it."
  }
}

run "the_reaper_may_scale_two_deployments_and_delete_worker_pods_and_nothing_else" {
  command = plan

  assert {
    condition = alltrue([
      for r in [kubernetes_role_v1.reaper_router, kubernetes_role_v1.reaper_controller] :
      length([for rule in r.rule : rule if contains(rule.resources, "deployments/scale") && toset(rule.verbs) == toset(["get", "patch"])]) == 1
    ])
    error_message = "the reaper's roles must allow get and patch on deployments/scale: that is how L1 owns both replica counts (plan D2)."
  }

  assert {
    condition     = one([for rule in kubernetes_role_v1.reaper_router.rule : rule.resource_names if contains(rule.resources, "deployments/scale")]) == toset(["atenet-router"]) && kubernetes_role_v1.reaper_router.metadata[0].namespace == "ate-system"
    error_message = "the router role must name atenet-router in ate-system and nothing else. Scale on any Deployment there would let L1 take the Control API itself down."
  }

  assert {
    condition     = one([for rule in kubernetes_role_v1.reaper_controller.rule : rule.resource_names if contains(rule.resources, "deployments/scale")]) == toset(["ax-controller"]) && kubernetes_role_v1.reaper_controller.metadata[0].namespace == "ax-system"
    error_message = "the controller role must name ax-controller in ax-system and nothing else. Scale on ax-server or Redis would let a drain take AX's API and store away."
  }

  assert {
    condition = alltrue([
      for r in [kubernetes_role_v1.reaper_router, kubernetes_role_v1.reaper_controller] :
      length([for rule in r.rule : rule if contains(rule.resources, "pods") && toset(rule.verbs) == toset(["list"])]) == 1
    ])
    error_message = "the reaper must be able to list the pods behind each Deployment: a count of 0 does not stop a pod that is still terminating, and `drained` waits for none to be left."
  }

  assert {
    condition     = kubernetes_role_v1.reaper_workers.metadata[0].namespace == "exe" && length(kubernetes_role_v1.reaper_workers.rule) == 1 && kubernetes_role_v1.reaper_workers.rule[0].resources == toset(["pods"]) && kubernetes_role_v1.reaper_workers.rule[0].verbs == toset(["delete"])
    error_message = "in the atespace namespace the reaper may delete pods and do nothing else: it deletes a wedged worker's pod (plan D6), always with the UID the store named."
  }

  assert {
    condition = alltrue([
      for b in [kubernetes_role_binding_v1.reaper_router, kubernetes_role_binding_v1.reaper_controller, kubernetes_role_binding_v1.reaper_workers] :
      b.subject[0].kind == "ServiceAccount" && b.subject[0].name == "exe-reaper" && b.subject[0].namespace == "exe-ops" && length(b.subject) == 1
    ])
    error_message = "each of the reaper's roles must be bound to the reaper's KSA and to nothing else."
  }
}

# S5 still holds for the pod network as a whole: the reaper is the one pod
# allowed in, by namespace AND label, on ax-server's port.
run "only_the_reaper_reaches_ax_server" {
  command = plan

  assert {
    condition     = kubernetes_network_policy_v1.ax_server_from_reaper.metadata[0].namespace == "ax-system" && kubernetes_network_policy_v1.ax_server_from_reaper.spec[0].pod_selector[0].match_labels["app.kubernetes.io/name"] == "ax-server"
    error_message = "the reaper's allow rule must select the ax-server pods in ax-system."
  }

  assert {
    condition     = length(kubernetes_network_policy_v1.ax_server_from_reaper.spec[0].ingress) == 1 && length(kubernetes_network_policy_v1.ax_server_from_reaper.spec[0].ingress[0].from) == 1
    error_message = "the allow rule must have exactly one peer: the reaper."
  }

  assert {
    condition     = kubernetes_network_policy_v1.ax_server_from_reaper.spec[0].ingress[0].from[0].namespace_selector[0].match_labels["kubernetes.io/metadata.name"] == "exe-ops" && kubernetes_network_policy_v1.ax_server_from_reaper.spec[0].ingress[0].from[0].pod_selector[0].match_labels["app.kubernetes.io/name"] == "exe-reap"
    error_message = "the peer must be the reaper's pods by namespace AND label in one peer: a namespace alone admits anything that ever runs in exe-ops, and a label alone admits any pod in any namespace that carries it -- a task's included."
  }

  assert {
    condition     = kubernetes_network_policy_v1.ax_server_from_reaper.spec[0].ingress[0].ports[0].port == "8080" && kubernetes_network_policy_v1.ax_server_from_reaper.spec[0].ingress[0].ports[0].protocol == "TCP"
    error_message = "the rule must open ax-server's gRPC port (TCP 8080) and no other."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.reaper.yaml_body).spec.jobTemplate.spec.template.metadata.labels["app.kubernetes.io/name"] == "exe-reap"
    error_message = "the reaper's pods must carry the label the allow rule admits, or every suspend request is dropped at the network."
  }
}

run "tofu_does_not_own_the_controllers_replica_count" {
  command = plan

  # L1 is the only writer of both replica counts (plan D2). A `replicas` in
  # this manifest is a second writer: every plan would show the controller
  # going back to 1, and an apply mid-drain would reopen the path a raw
  # `ax resume` takes.
  assert {
    condition     = !contains(keys(yamldecode(kubectl_manifest.ax_controller.yaml_body).spec), "replicas")
    error_message = "the ax-controller manifest must not set spec.replicas: L1 owns that count, and tofu setting it reopens the resume path in the middle of a drain."
  }
}
