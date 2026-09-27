# What this file pins: the Substrate store is our own small Postgres, never
# upstream's bundled one, and nothing but ate-api-server can reach it.
#
# Upstream's bundled store requests 2 CPUs and claims 500Gi, a cost trap on our
# one small node; a store anyone on the pod network can dial is a store any
# task can rewrite. Both are properties of values, so both are asserted.

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

run "the_store_is_upstreams_postgres_image_on_a_small_standard_disk" {
  command = plan

  assert {
    condition     = kubernetes_stateful_set_v1.postgres.spec[0].template[0].spec[0].container[0].image == "postgres:18-alpine@sha256:9a8afca54e7861fd90fab5fdf4c42477a6b1cb7d293595148e674e0a3181de15"
    error_message = "the store must run the exact image upstream's bundled store uses at the pinned Substrate commit, by digest: the one combination upstream runs its store on."
  }

  assert {
    condition     = kubernetes_stateful_set_v1.postgres.spec[0].volume_claim_template[0].spec[0].storage_class_name == "standard"
    error_message = "the store's volume must be pd-standard (GKE's `standard` class): cost first (manager-loop inbox M20 T2). A 10Gi disk bills around the clock whether a node runs or not, and pd-balanced costs 2.5x pd-standard; S7 measures that Postgres still turns Ready within 60 s on it."
  }

  # Renamed from "data" when the store moved off pd-balanced: a claim template
  # of the old name would have re-bound the old pd-balanced claim instead of
  # creating a pd-standard one.
  assert {
    condition     = kubernetes_stateful_set_v1.postgres.spec[0].volume_claim_template[0].metadata[0].name == "store" && kubernetes_stateful_set_v1.postgres.spec[0].template[0].spec[0].container[0].volume_mount[0].name == "store"
    error_message = "the store's claim template must be named \"store\" and mounted by that name: the old \"data\" name re-binds the old pd-balanced claim (data-postgres-0), so the move to pd-standard would silently not happen."
  }

  assert {
    condition     = kubernetes_stateful_set_v1.postgres.spec[0].volume_claim_template[0].spec[0].resources[0].requests.storage == "10Gi"
    error_message = "the store's volume must be 10Gi: upstream's bundled 500Gi claim is the cost trap this store exists to avoid, and every GiB of PD bills around the clock."
  }

  assert {
    condition     = kubernetes_stateful_set_v1.postgres.spec[0].replicas == "1"
    error_message = "the store runs one replica: it is a single-node cluster, and a second replica is a second PD billing for nothing."
  }

  assert {
    condition     = kubernetes_stateful_set_v1.postgres.spec[0].template[0].spec[0].container[0].resources[0].limits.memory == "1Gi"
    error_message = "the store must carry a memory limit, so a runaway query is killed instead of taking the node's memory from the workers."
  }
}

run "the_store_password_is_generated_and_kept_out_of_the_installers_configmap" {
  command = plan

  assert {
    condition     = kubernetes_secret_v1.postgres.data.POSTGRES_PASSWORD == random_password.postgres.result
    error_message = "the store's password must come from random_password (it then lives only in this stack's encrypted state and in Secrets), never from a literal."
  }

  assert {
    condition     = kubernetes_secret_v1.ate_api_server_env.data.ATE_API_POSTGRES_CONNECTION_STRING == "postgres://ate:${random_password.postgres.result}@postgres.exe-store.svc.cluster.local:5432/ate?sslmode=disable"
    error_message = "ate-api-server must get the full DSN, password included, from the Secret ate-api-server-secret-envvars, which its manifest reads after the installer's ConfigMap and lets win."
  }

  assert {
    condition     = local.ate_setup_env.ATE_API_POSTGRES_CONNECTION_STRING == "postgres://ate@postgres.exe-store.svc.cluster.local:5432/ate?sslmode=disable"
    error_message = "the DSN handed to ate-setup must be the password-less form: the installer writes it into a plain ConfigMap. It still has to be non-empty, which is what makes the installer skip its bundled 500Gi store."
  }
}

run "only_ate_api_server_reaches_the_store" {
  command = plan

  assert {
    condition     = kubernetes_network_policy_v1.postgres.spec[0].policy_types == tolist(["Ingress"])
    error_message = "the store's NetworkPolicy must govern Ingress: that is the direction every actor, running arbitrary task code on the same pod network, would come from."
  }

  assert {
    condition     = length(kubernetes_network_policy_v1.postgres.spec[0].ingress) == 1 && kubernetes_network_policy_v1.postgres.spec[0].ingress[0].from[0].pod_selector[0].match_labels.app == "ate-api-server" && kubernetes_network_policy_v1.postgres.spec[0].ingress[0].from[0].namespace_selector[0].match_labels["kubernetes.io/metadata.name"] == "ate-system"
    error_message = "the store must admit exactly one peer: pods labelled app=ate-api-server in namespace ate-system. Anything wider lets a task reach Substrate's database."
  }

  assert {
    condition     = kubernetes_network_policy_v1.postgres.spec[0].ingress[0].ports[0].port == "5432"
    error_message = "the store's one allowed port is 5432."
  }

  assert {
    condition     = kubernetes_service_v1.postgres.spec[0].type == "ClusterIP"
    error_message = "the store's Service must be ClusterIP: nothing here is ever exposed outside the cluster."
  }
}
