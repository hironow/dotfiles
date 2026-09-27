# What this file pins: the atespace, its WorkerPool and the pool's guard, and
# the gated Gemini Secret.

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
      ar_platform_repo     = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform"
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

run "without_a_worker_image_there_is_no_pool" {
  command = plan

  assert {
    condition     = length(kubectl_manifest.worker_pool) == 0 && length(terraform_data.worker_pool_guard) == 0
    error_message = "with no ateom_gvisor_image the WorkerPool and its guard must not be planned: a pool needs a worker image, and the stack must plan without one."
  }
}

run "a_worker_image_must_be_pinned_by_digest" {
  command = plan

  variables {
    ateom_gvisor_image = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/substrate/ateom-gvisor:v0.1.0"
  }

  expect_failures = [var.ateom_gvisor_image]
}

run "the_pool_is_two_gvisor_workers_on_the_versioned_node_with_limits" {
  command = plan

  variables {
    ateom_gvisor_image = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/substrate/ateom-gvisor@sha256:2222222222222222222222222222222222222222222222222222222222222222"
  }

  assert {
    condition     = yamldecode(kubectl_manifest.worker_pool[0].yaml_body).spec.workerImage == "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/substrate/ateom-gvisor@sha256:2222222222222222222222222222222222222222222222222222222222222222"
    error_message = "the pool must run exactly the recorded worker image."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.worker_pool[0].yaml_body).spec.replicas == 2
    error_message = "the pool runs two workers: two tasks awake at once on Substrate v0.1.0 (one actor per worker, plan Q17)."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.worker_pool[0].yaml_body).spec.sandboxClass == "gvisor" && yamldecode(kubectl_manifest.worker_pool[0].yaml_body).metadata.namespace == "exe"
    error_message = "the pool is gVisor (E2 has no nested virtualization, so no microvm), in the atespace's namespace."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.worker_pool[0].yaml_body).spec.template.nodeSelector[jsondecode(file("../../exe/versions.json")).substrate.version_label_key] == jsondecode(file("../../exe/versions.json")).substrate.version_label_value
    error_message = "workers must select the node by the pinned substrate-version label, the one the install stamps."
  }

  assert {
    condition     = alltrue([for k in ["cpu", "memory"] : contains(keys(yamldecode(kubectl_manifest.worker_pool[0].yaml_body).spec.template.resources.limits), k)])
    error_message = "every worker must carry cpu AND memory limits: they are its advertised capacity, and gVisor's default is unlimited, so one actor could take the node."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.worker_pool[0].yaml_body).spec.template.resources.requests.memory == yamldecode(kubectl_manifest.worker_pool[0].yaml_body).spec.template.resources.limits.memory
    error_message = "a worker's memory request must equal its limit: memory is not compressible, and an overcommitted node evicts workers, which CRASHES their actors."
  }
}

run "changing_the_pool_is_guarded_against_awake_actors" {
  command = plan

  variables {
    ateom_gvisor_image = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/substrate/ateom-gvisor@sha256:2222222222222222222222222222222222222222222222222222222222222222"
  }

  assert {
    condition     = terraform_data.worker_pool_guard[0].triggers_replace.pool == sha256(jsonencode(local.worker_pool))
    error_message = "the guard must re-run whenever the pool's manifest changes: editing a serving pool replaces its pods and CRASHES every awake actor on Substrate v0.1.0."
  }

  assert {
    condition     = strcontains(local.worker_pool_functions, "ax get tasks -a \"$ATESPACE\"") && strcontains(local.worker_pool_functions, "exit 1")
    error_message = "the shared check must count Running tasks in the atespace and fail the apply when there are any."
  }

  assert {
    condition     = strcontains(local.worker_pool_guard_script, local.worker_pool_functions) && strcontains(local.worker_pool_guard_script, "refuse_while_tasks_run \"worker pool guard\"")
    error_message = "the guard must embed worker_pool.sh and run its check, so it refuses on exactly what every other step that takes workers away refuses on."
  }
}

run "the_gemini_secret_waits_for_the_operators_key" {
  command = plan

  assert {
    condition     = length(kubernetes_secret_v1.gemini) == 0
    error_message = "with no gemini_api_key the Gemini Secret must not exist: the key comes from the operator, into the gitignored tfvars only."
  }

  assert {
    condition     = toset(kubernetes_role_v1.ax_controller_gemini.rule[0].resource_names) == toset(["gemini-api-secret"]) && toset(kubernetes_role_v1.ax_controller_gemini.rule[0].verbs) == toset(["get"])
    error_message = "ax-controller may GET the one Secret it reads, gemini-api-secret, and nothing else (upstream grants get/list/watch on every Secret in the cluster)."
  }
}

run "a_supplied_gemini_key_lands_where_ax_looks" {
  command = plan

  variables {
    gemini_api_key = "zz-not-a-real-key"
  }

  assert {
    condition     = kubernetes_secret_v1.gemini[0].metadata[0].name == "gemini-api-secret" && kubernetes_secret_v1.gemini[0].metadata[0].namespace == "exe"
    error_message = "AX reads Secret gemini-api-secret in the namespace named after the task's atespace (exe)."
  }

  assert {
    condition     = kubernetes_secret_v1.gemini[0].data.GEMINI_API_KEY == "zz-not-a-real-key"
    error_message = "the key must land under GEMINI_API_KEY, the key AX reads."
  }
}
