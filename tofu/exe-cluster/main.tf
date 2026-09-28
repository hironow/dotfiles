# exe-cluster — everything that runs inside the exe GKE cluster.
#
# Scope (section 3.1 of docs/plan/exe-google-ax.md): the Substrate store
# (Postgres), Agent Substrate itself (installed by upstream's own `ate-setup`,
# pinned, from a terraform_data step), its gVisor SandboxConfig and asset
# mirror, AX (ax-server, ax-controller, Redis), the WorkerPool the actors run
# on, the NetworkPolicies around the two databases, and the Gemini Secret.
# The GCP foundation under it (cluster, node pool, buckets, registries, IAM,
# the money stops) is tofu/exe-platform's, read here through its state.
#
# The node pool is usually at ZERO. Kubernetes objects apply without a node,
# but upstream's installer waits for its workloads to roll out, so an apply
# that (re)runs the Substrate install needs a node up under a lease
# (`just exe-wake`); see substrate.tf.
#
# STATE IS ENCRYPTED. This stack's state carries the Postgres password (inside
# the Substrate DSN), the Redis requirepass and, once the operator supplies it,
# the Gemini key. OpenTofu state encryption wraps a data key with the KMS key
# exe-platform owns (kms.tf there), and `enforced = true` makes OpenTofu refuse
# to write state or a saved plan in plaintext at all. The key's id embeds the
# project id, so it arrives through the gitignored terraform.tfvars.
#
# CONFIDENTIALITY: the project is private and this repo is public. Every
# identifier comes from terraform.tfvars, backend.hcl (both gitignored) or
# exe-platform's state; see .gitignore.

terraform {
  required_version = ">= 1.12.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.38"
    }
    # Server-side apply for the two custom resources (WorkerPool) whose CRDs
    # only exist after the Substrate install: hashicorp/kubernetes'
    # kubernetes_manifest needs the CRD at PLAN time and cannot plan a fresh
    # cluster.
    kubectl = {
      source  = "alekc/kubectl"
      version = "~> 2.1"
    }
    # 0.x, so dependency class 2 (exe/versions.json): pinned exactly, and only
    # moved after a cooldown and a changelog read.
    ko = {
      source  = "ko-build/ko"
      version = "0.0.21"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }

  # Partial backend config: `tofu init -backend-config=backend.hcl`, the same
  # bucket as exe-platform (its name embeds the project id). The prefix is
  # pinned here so a typo cannot start a second, empty state.
  backend "gcs" {
    prefix = "exe-cluster"
  }

  encryption {
    key_provider "gcp_kms" "state" {
      kms_encryption_key = var.state_kms_key
      key_length         = 32
    }

    method "aes_gcm" "state" {
      keys = key_provider.gcp_kms.state
    }

    # enforced: OpenTofu refuses to write this stack's state, or a saved plan
    # of it, in plaintext. A missing or unusable key is an error, never a
    # quiet downgrade.
    state {
      method   = method.aes_gcm.state
      enforced = true
    }

    plan {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}
