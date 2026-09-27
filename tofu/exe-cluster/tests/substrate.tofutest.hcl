# What this file pins: how Agent Substrate is installed, and the SandboxConfig
# its gVisor actors boot from.
#
# The install is upstream's `ate-setup deploy ate-system`, run by a
# terraform_data step. Its inputs decide what runs: the pinned commit and
# version, the registry ko pushes to, a DSN that makes it skip the bundled
# store, and two replaced files in the scratch copy it runs from. The
# SandboxConfig decides which gVisor tarball every actor extracts and which
# pause image it starts from.

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

run "the_install_runs_the_pinned_substrate_in_build_mode" {
  command = plan

  assert {
    condition     = local.ate_setup_env.SUBSTRATE_SHA == jsondecode(file("../../exe/versions.json")).substrate.sha
    error_message = "the install must check its checkout against substrate.sha in exe/versions.json, the one place the pin lives."
  }

  assert {
    condition     = local.ate_setup_env.VERSION == jsondecode(file("../../exe/versions.json")).substrate.version_label_value
    error_message = "VERSION must be the pinned label value: ate-setup stamps it on every node as ate.dev/substrate-version, and the WorkerPool and atelet select nodes by it."
  }

  assert {
    condition     = local.ate_setup_env.KO_DOCKER_REPO == "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/substrate"
    error_message = "ko must push Substrate's images to the exe-platform registry (whose cleanup policy bounds them), under substrate/."
  }

  assert {
    condition     = local.ate_setup_env.KO_DEFAULTPLATFORMS == "linux/amd64"
    error_message = "build for linux/amd64 only: the node is an e2-standard-4, and upstream's default of amd64 plus arm64 doubles every build for images nothing pulls."
  }

  assert {
    condition     = local.ate_setup_env.NO_DEV_ENV == "1" && strcontains(local.ate_setup_script, "--no-dev-env")
    error_message = "the installer must not source a developer's .ate-dev-env.sh: an apply has to depend on this stack's inputs, not on a file in someone's checkout."
  }

  assert {
    condition     = strcontains(local.ate_setup_script, "git -C \"$SUBSTRATE_SRC\" rev-parse HEAD") && strcontains(local.ate_setup_script, "\"$SUBSTRATE_SHA\"")
    error_message = "the install must refuse a checkout that is not at the pinned commit before it builds anything."
  }

  assert {
    condition     = strcontains(local.ate_setup_script, "--dns-endpoint") && strcontains(local.ate_setup_script, "--context \"$context\"")
    error_message = "the install must reach the cluster through a DNS-endpoint kubeconfig and pass --context: without --context, ate-setup runs its own get-credentials, which asks for the IP endpoint this cluster does not have."
  }

  assert {
    condition     = strcontains(local.ate_setup_script, "rollout status statefulset/postgres")
    error_message = "the install must wait for the store first: ate-api-server gives up on its DSN after a minute of retries."
  }

  assert {
    condition     = terraform_data.ate_system.triggers_replace.substrate_sha == jsondecode(file("../../exe/versions.json")).substrate.sha
    error_message = "moving the Substrate pin must re-run the install: the pinned commit is one of its triggers."
  }
}

run "the_install_drops_the_gmp_podmonitoring_and_writes_our_sandboxconfig" {
  command = plan

  assert {
    condition     = strcontains(local.ate_setup_script, "rm \"$work/substrate/manifests/ate-install/atenet-router-monitoring.yaml\"")
    error_message = "the install must drop atenet-router-monitoring.yaml from its scratch copy: it is a GMP PodMonitoring, this cluster runs without Managed Prometheus, and the installer applies that directory strictly, so one unknown kind fails the whole install."
  }

  assert {
    condition     = strcontains(local.ate_setup_script, "> \"$work/substrate/manifests/ate-install/sandboxconfig-gvisor.yaml\"") && local.ate_setup_env.SANDBOX_CONFIG_YAML == local.sandbox_config_yaml
    error_message = "the install must write OUR SandboxConfig over upstream's file, so the installer stays the single writer of gvisor-default and writes our content."
  }

  assert {
    condition     = strcontains(local.ate_setup_script, "rsync -a --exclude .git \"$SUBSTRATE_SRC/\" \"$work/substrate/\"")
    error_message = "the replaced files must go into a scratch copy, never into the pinned checkout itself."
  }
}

# Upstream's ate-api-server PodDisruptionBudget (maxUnavailable 1) cannot keep
# an API server up on a one-node cluster whose every stop takes the node away:
# the first evicted pod's replacement is unschedulable on the cordoned node, so
# the budget reads zero and the drain waits on the second pod until GKE's
# one-hour PDB limit -- a stop that bills the node for up to an hour past the
# lease. The install step lets the budget allow a full stop.
run "the_install_lets_the_api_server_budget_allow_a_full_stop" {
  command = plan

  assert {
    condition     = strcontains(local.ate_setup_script, "get poddisruptionbudgets -A") && strcontains(local.ate_setup_script, "{\"spec\":{\"maxUnavailable\":\"100%\",\"minAvailable\":null}}")
    error_message = "the install must open every PodDisruptionBudget outside the kube-/gke- system namespaces to maxUnavailable 100% after the deploy (upstream's ate-api-server budget first among them). With one node, a budget cannot protect anything: every stop removes the node, an evicted pod's replacement cannot schedule, and the drain then waits for up to GKE's one-hour PDB limit while the node bills."
  }

  # And a budget it did not open -- a new upstream one, or a GKE-managed one it
  # must not touch -- fails the install loudly instead of stalling a stop later.
  assert {
    condition     = strcontains(local.ate_setup_script, "$3 != \"100%\"") && strcontains(local.ate_setup_script, "could hold a stop")
    error_message = "after opening the budgets, the install must fail when any PodDisruptionBudget in the cluster still allows less than 100% unavailable, so a future budget stops the install loudly rather than a stop silently."
  }
}

run "gvisor_default_names_our_mirror_and_the_gke_pause_image" {
  command = plan

  assert {
    condition     = yamldecode(local.sandbox_config_yaml).metadata.name == "gvisor-default"
    error_message = "the SandboxConfig must be named gvisor-default: AX v0.3.1 hardcodes that name into every ActorTemplate it creates."
  }

  assert {
    condition     = yamldecode(local.sandbox_config_yaml).spec.assets.amd64.gvisor.url == "gs://zz-synthetic-project-exe-snapshots/mirror/gvisor/nightly/2026-09-02/x86_64/gvisor.tar.zstd"
    error_message = "the gVisor asset must be our mirror in the snapshot bucket (read through atelet's grant there), not upstream's nightly path, which can disappear under a suspended actor."
  }

  assert {
    condition     = can(regex("^[0-9a-f]{64}$", yamldecode(local.sandbox_config_yaml).spec.assets.amd64.gvisor.sha256)) && yamldecode(local.sandbox_config_yaml).spec.assets.amd64.gvisor.sha256 == local.gvisor_mirror_env.GVISOR_SHA256
    error_message = "the asset's sha256 must be the one the mirror step verified: atelet checks every download against it and fails closed on a mismatch."
  }

  assert {
    condition     = keys(yamldecode(local.sandbox_config_yaml).spec.assets) == ["amd64"]
    error_message = "only the amd64 asset is named: the node is amd64, and the validating policy requires every named arch to carry an asset that must then be mirrored too."
  }

  assert {
    condition     = startswith(yamldecode(local.sandbox_config_yaml).spec.pauseImage, "gcr.io/gke-release/pause@sha256:")
    error_message = "the pause image must be the in-project GKE mirror, pinned by digest (the CRD demands one), not registry.k8s.io."
  }
}

run "the_gvisor_mirror_is_verified_on_both_ends" {
  command = plan

  assert {
    condition     = local.gvisor_mirror_env.GVISOR_SOURCE == "gs://gvisor/releases/nightly/2026-09-02/x86_64/gvisor.tar.zstd"
    error_message = "the mirror must copy the exact nightly the pinned Substrate names."
  }

  assert {
    condition     = strcontains(local.gvisor_mirror_script, "verify \"$GVISOR_SOURCE\"") && strcontains(local.gvisor_mirror_script, "verify \"$GVISOR_MIRROR\"") && strcontains(local.gvisor_mirror_script, "shasum -a 256")
    error_message = "the mirror step must check the sha256 of the source before copying and of the copy after: a tarball that differs from the pin is refused, not mirrored."
  }

  assert {
    condition     = terraform_data.gvisor_mirror.triggers_replace.sha256 == local.gvisor_amd64_sha256
    error_message = "a new gVisor pin must re-run the mirror step."
  }
}
