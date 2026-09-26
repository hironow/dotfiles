# The GKE cluster and its single node pool.
#
# =====================================================================
# WHO OWNS THE NODE COUNT — the one documented exception to the IaC
# drift policy (docs/agents/iac-drift-policy.md).
#
# This stack does NOT own how many nodes run. The lease-based auto-sleep
# does: `exe-reaper wake` sets it to 1, and L1 / L2 / L3 set it back to 0.
# Encoding a count here would mean the next `tofu apply` silently wakes a
# cluster nobody asked for, or shrinks one mid-task and — on Substrate
# v0.1.0 — kills every awake actor within about 60 seconds, terminally.
#
# So: no `node_count` attribute at all, `initial_node_count` is a constant,
# and the runtime size is ignored. A `tofu plan` that wants to resize the
# pool is a bug in this file, not drift to accept.
# =====================================================================

resource "google_container_cluster" "exe" {
  project = var.gcp_project_id
  name    = local.cluster_name

  # Zonal, not regional: a zonal Standard cluster is in GKE's free management
  # tier, and a one-node cluster has no availability story to protect.
  location       = local.zone
  node_locations = [local.zone]

  # Rapid is not a preference: 1.37 exists only there, and 1.37 is what turns
  # on the beta APIs Substrate needs by default — without it, missing them at
  # creation time means rebuilding the cluster rather than fixing a flag.
  release_channel {
    channel = "RAPID"
  }

  # Minor floor from the single pin source. Drift is ignored because GKE owns
  # the patch inside a minor and will move it on its own schedule; a diff here
  # would be noise every time it does.
  min_master_version = local.pins.gke.cluster_minor

  # Phase 7 has to be able to destroy this. Left at the provider default
  # (true), a teardown fails halfway and leaves the expensive half standing.
  deletion_protection = false

  network    = google_compute_network.exe.id
  subnetwork = google_compute_subnetwork.nodes.id

  # The default pool is replaced by the managed one below. initial_node_count
  # is required here and is consumed by that replacement, not by anything that
  # survives the apply.
  remove_default_node_pool = true
  initial_node_count       = 1

  ip_allocation_policy {
    cluster_secondary_range_name  = "${local.prefix}-pods"
    services_secondary_range_name = "${local.prefix}-services"
  }

  private_cluster_config {
    # Forced by org policy: external IPs are allowlist-only, so nodes cannot
    # have one. This is what makes Cloud NAT load-bearing.
    enable_private_nodes    = true
    enable_private_endpoint = true
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # Public exposure is zero by construction, not by firewall rule: the IP-based
  # control-plane endpoint does not exist, and the DNS endpoint requires Google
  # IAM on every request. `allow_external_traffic` lets the operator's laptop
  # reach that IAM-guarded endpoint from outside the VPC — it is not a public
  # cluster; there is nothing to reach without a token.
  control_plane_endpoints_config {
    dns_endpoint_config {
      allow_external_traffic = true
    }
    ip_endpoints_config {
      enabled = false
    }
  }

  workload_identity_config {
    workload_pool = "${var.gcp_project_id}.svc.id.goog"
  }

  # Dataplane V2 (eBPF): required for the NetworkPolicy enforcement the cluster
  # stack relies on, and it replaces kube-proxy rather than adding to it.
  datapath_provider = "ADVANCED_DATAPATH"

  addons_config {
    # No HTTP load balancer: an Ingress controller here would create a
    # continuously-billed forwarding rule, and nothing is meant to be reachable.
    http_load_balancing {
      disabled = true
    }
    horizontal_pod_autoscaling {
      disabled = false
    }
    # Needed for the Postgres and Redis PVCs the cluster stack creates.
    gce_persistent_disk_csi_driver_config {
      enabled = true
    }
  }

  # System logs only for monitoring, and Managed Service for Prometheus off.
  # The node-uptime alert deliberately reads a Compute Engine metric instead, so
  # the money stop does not depend on the cluster's own monitoring being healthy
  # — or on a metrics bill that scales with workloads.
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = false
    }
  }

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  maintenance_policy {
    # 04:00-08:00 JST: after L3's daily stop, so maintenance lands on a cluster
    # that is already meant to be cold.
    recurring_window {
      start_time = local.maintenance_window_start
      end_time   = local.maintenance_window_end
      recurrence = "FREQ=DAILY"
    }

    # One node means an upgrade is a full outage, and on Substrate v0.1.0
    # replacing a worker pod kills awake actors terminally. Upgrades are held
    # off for the life of the minor and re-dated deliberately.
    maintenance_exclusion {
      exclusion_name = "${local.prefix}-hold-minor-and-node-upgrades"
      start_time     = local.upgrade_exclusion_start
      end_time       = local.upgrade_exclusion_end
      exclusion_options {
        scope = "NO_MINOR_OR_NODE_UPGRADES"
      }
    }
  }

  resource_labels = local.common_labels

  lifecycle {
    # GKE moves the patch version inside the pinned minor on its own schedule.
    ignore_changes = [min_master_version]
  }

  depends_on = [google_project_service.enabled]
}

resource "google_container_node_pool" "main" {
  project  = var.gcp_project_id
  name     = local.node_pool_name
  cluster  = google_container_cluster.exe.name
  location = local.zone

  # Read the banner at the top of this file before touching this line. This is
  # a creation-time constant, not a desired state, and there is deliberately no
  # `node_count` attribute and no autoscaling block anywhere in this resource.
  initial_node_count = var.node_pool_initial_count

  # The provider's purpose-built escape hatch for exactly this ownership split:
  # it tells the provider that the RUNNING size is somebody else's, so a pool
  # woken to 1 does not read as drift to be corrected back down. Without it,
  # every `tofu plan` while a task is running proposes to kill that task.
  #
  # It pairs with the lifecycle block at the bottom of this resource, which
  # covers the other direction: a change to the CONFIGURED constant must not
  # force a resize of a pool that is already running.
  ignore_node_count_changes = true

  management {
    # Auto-repair recreates a node it considers unhealthy. On Substrate v0.1.0
    # that is indistinguishable from deleting every awake actor, and a node
    # that is unhealthy while the cluster is meant to be asleep should stay
    # dead, not be resurrected.
    auto_repair = false
    # Upgrades are the maintenance exclusion's job, not a surprise.
    auto_upgrade = false
  }

  # One node at a time, no surge: surging would mean two billed nodes.
  upgrade_settings {
    max_surge       = 0
    max_unavailable = 1
  }

  network_config {
    enable_private_nodes = true
  }

  node_config {
    machine_type = var.node_machine_type
    disk_size_gb = var.node_disk_size_gb
    disk_type    = "pd-balanced"

    # On-demand, explicitly (decision Q2). A spot node can be reclaimed at any
    # moment, which on Substrate v0.1.0 destroys awake actors with no recovery
    # path — the saving is not worth a class of unfixable data loss.
    spot        = false
    preemptible = false

    service_account = google_service_account.node.email
    # cloud-platform plus per-resource IAM is Google's recommended shape: the
    # scope stops being the access-control boundary and the SA's bindings become
    # it, which is what makes the narrow grants in iam.tf actually bind.
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]

    # The version label Substrate's node selector matches on, taken from the
    # single pin source. A literal here is how you get nodes the selector
    # quietly declines to schedule onto.
    labels = {
      (local.pins.substrate.version_label_key) = local.pins.substrate.version_label_value
    }

    # Required for Workload Identity: without GKE_METADATA a pod's KSA token is
    # never exchanged and every principal:// binding in iam.tf is inert.
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    metadata = {
      disable-legacy-endpoints = "true"
    }

    resource_labels = local.common_labels
  }

  lifecycle {
    # The auto-sleep owns the running size; see the banner. initial_node_count
    # is ignored so that a pool currently at 1 (woken) does not read as drift
    # to be "corrected" back to 0 mid-task.
    ignore_changes = [initial_node_count]
  }
}
