# What this file pins: the shape of the GKE cluster itself.
#
# Every assertion here guards a property that can only be chosen at CREATION
# time, or one whose loss costs money quietly rather than loudly. That is the
# selection rule: a flag you can flip later on a running cluster does not need a
# test, a flag that forces a rebuild — or that bills while looking healthy —
# does.
#
#   - zonal + one node location, Rapid channel, and the minor from the single
#     pin document: none of the three can be changed on an existing cluster, and
#     1.37 exists only in Rapid. Getting any of them wrong means deleting the
#     cluster and starting again, after the cluster stack has already installed
#     into it.
#   - Workload Identity, Dataplane V2: same story. The workload pool name is
#     built from the project ID (while the IAM members in iam.tf address the
#     pool by project NUMBER); swapping the two yields bindings that apply to
#     nothing and a 403 at first use rather than an error at apply time.
#   - private nodes, no IP control-plane endpoint, DNS endpoint on: this is the
#     entire exposure story of the cluster. It is not enforced by a firewall
#     rule that could be relaxed — the public endpoint does not exist. A test is
#     the only thing standing between "no IP endpoint" and someone enabling one
#     to debug a connection problem and leaving it on.
#   - HTTP load balancing addon off, Managed Service for Prometheus off: both
#     bill continuously and neither is used. An Ingress controller would create
#     a forwarding rule that is charged whether or not a node exists, which on a
#     cluster meant to sit at zero nodes is the entire monthly bill.
#   - deletion_protection off, remove_default_node_pool on: Phase 7 has to be
#     able to destroy this stack. Left at the provider's default, a teardown
#     fails halfway through and leaves the expensive half standing.
#   - the maintenance window and the upgrade exclusion: one node means an
#     upgrade is a full outage, and on Substrate v0.1.0 replacing a worker pod
#     kills every awake actor terminally. The window is placed after L3's daily
#     stop so maintenance lands on a cluster that is already meant to be cold.
#
# command = plan + mock_provider keeps this offline: no GCP credentials, no API
# calls, nothing created. Every value asserted comes from configuration, not
# from a provider response, so the mock's generated values are never read.

mock_provider "google" {}

# Synthetic inputs. The real identifiers live only in terraform.tfvars
# (gitignored) — this repo is public. Each value is chosen to satisfy the
# validation block on its variable, so a plan failure here means a real
# regression and not a rejected placeholder.
variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "cluster_is_zonal_and_pinned_to_one_zone" {
  command = plan

  # A region ("asia-northeast1") has no zone letter; a zone always ends in one.
  # Zonal is deliberate: a zonal Standard cluster sits inside GKE's free
  # management tier, and a regional control plane is billed per hour.
  assert {
    condition     = endswith(google_container_cluster.exe.location, "-a")
    error_message = "cluster location must be a ZONE (ending in a zone letter), not a region: a regional cluster leaves GKE's free management tier and bills per control-plane hour, and it cannot be converted to zonal afterwards."
  }

  # node_locations wider than the control-plane zone would silently multiply the
  # node count — the pool's size is per zone.
  assert {
    condition     = google_container_cluster.exe.node_locations == toset([google_container_cluster.exe.location])
    error_message = "node_locations must be exactly the cluster's own zone: the node pool's size is applied PER zone, so a second entry doubles every wake into two billed nodes while `exe-status` still reports a pool size of 1."
  }
}

run "cluster_tracks_the_single_pin_document" {
  command = plan

  # Read from exe/versions.json exactly as locals.tf does, and for the same
  # reason: a literal here would be a second opinion that nothing reconciles.
  # The path is relative to the stack (path.module), not to this tests/
  # directory.
  assert {
    condition     = google_container_cluster.exe.min_master_version == jsondecode(file("${path.module}/../../exe/versions.json")).gke.cluster_minor
    error_message = "min_master_version must equal gke.cluster_minor from exe/versions.json. A cluster's minor is fixed at creation, so a stack that disagrees with the pin document cannot be corrected by an apply — it has to be rebuilt after the cluster stack has already installed into it."
  }

  assert {
    condition     = google_container_cluster.exe.release_channel[0].channel == "RAPID"
    error_message = "release_channel must be RAPID: the pinned minor exists only there, and it is Rapid that turns on by default the beta APIs Substrate needs. A channel is not changeable downwards on a live cluster."
  }

  # The stack writes "RAPID" literally while exe/versions.json also declares
  # gke.release_channel. Nothing else reconciles those two, so this assertion
  # does: change the pin document and this fails until gke.tf agrees.
  assert {
    condition     = google_container_cluster.exe.release_channel[0].channel == jsondecode(file("${path.module}/../../exe/versions.json")).gke.release_channel
    error_message = "the cluster's release channel and gke.release_channel in exe/versions.json have diverged. The pin document is the single source of truth for both the channel and the minor; a stack on a different channel than the document claims cannot host the pinned minor."
  }
}

run "workload_identity_and_dataplane_v2_are_on" {
  command = plan

  assert {
    condition     = length(google_container_cluster.exe.workload_identity_config) == 1
    error_message = "workload_identity_config must be present: without it no KSA token is ever exchanged and every principal:// binding in iam.tf is inert. It cannot be added to a cluster without recreating the metadata server configuration on every node."
  }

  # Named by project ID, while the IAM members are addressed by project NUMBER.
  # Interchanging the two produces bindings that match nothing.
  assert {
    condition     = google_container_cluster.exe.workload_identity_config[0].workload_pool == "${var.gcp_project_id}.svc.id.goog"
    error_message = "workload_pool must be <project ID>.svc.id.goog. The pool is NAMED by project id and ADDRESSED by project number (locals.wi_pool); using the number here yields a pool no binding resolves to, which surfaces only as a 403 the first time an actor suspends."
  }

  assert {
    condition     = google_container_cluster.exe.datapath_provider == "ADVANCED_DATAPATH"
    error_message = "datapath_provider must be ADVANCED_DATAPATH (Dataplane V2): the cluster stack's NetworkPolicy enforcement depends on it, and the datapath cannot be switched on an existing cluster."
  }
}

run "cluster_has_no_public_surface" {
  command = plan

  assert {
    condition     = google_container_cluster.exe.private_cluster_config[0].enable_private_nodes == true
    error_message = "enable_private_nodes must be true: the org policy allows external IPs by allowlist only, so a node with a public IP is refused at creation — and it is private nodes that make Cloud NAT load-bearing for image pulls."
  }

  # The IP-based control-plane endpoint is the one that can be reached without
  # Google IAM. It is not firewalled off here; it does not exist.
  assert {
    condition     = google_container_cluster.exe.control_plane_endpoints_config[0].ip_endpoints_config[0].enabled == false
    error_message = "the IP control-plane endpoint must be disabled. It is the only endpoint reachable without a Google IAM identity; turning it on to debug a connection problem is how a private cluster quietly becomes an internet-reachable one."
  }

  assert {
    condition     = length(google_container_cluster.exe.control_plane_endpoints_config[0].dns_endpoint_config) == 1
    error_message = "the DNS control-plane endpoint block must be present: with no IP endpoint it is the ONLY way in, so losing it locks every operator and every CI job out of the cluster."
  }

  # Not a public cluster: this endpoint authenticates every request with Google
  # IAM. It is what lets the operator's laptop reach the control plane from
  # outside the VPC without a bastion or a VPN.
  assert {
    condition     = google_container_cluster.exe.control_plane_endpoints_config[0].dns_endpoint_config[0].allow_external_traffic == true
    error_message = "the DNS endpoint must allow external traffic: every request to it is IAM-authenticated, so this is not public exposure — but without it `just exe-ctx` cannot reach the control plane from outside the VPC at all."
  }
}

run "no_continuously_billed_addons" {
  command = plan

  assert {
    condition     = google_container_cluster.exe.addons_config[0].http_load_balancing[0].disabled == true
    error_message = "the HTTP load balancing addon must stay disabled: an Ingress controller here would create a forwarding rule billed per hour whether or not a node exists, which on a cluster designed to sit at zero nodes would be the whole monthly bill."
  }

  # Deliberately off, and the node-uptime alert reads a Compute Engine metric
  # instead, so the money stop does not depend on the cluster's own monitoring.
  assert {
    condition     = google_container_cluster.exe.monitoring_config[0].managed_prometheus[0].enabled == false
    error_message = "Managed Service for Prometheus must stay disabled: it bills per sample ingested and therefore scales with workloads, and nothing here reads it — the node-uptime alert deliberately uses a Compute Engine metric so it survives the cluster's monitoring being broken."
  }
}

run "cluster_can_be_destroyed_in_phase_7" {
  command = plan

  assert {
    condition     = google_container_cluster.exe.deletion_protection == false
    error_message = "deletion_protection must be false. The provider defaults it to TRUE, so leaving it out makes `tofu destroy` fail at the cluster after the cheap resources are already gone — the teardown stops with the expensive half still standing and still billing."
  }

  assert {
    condition     = google_container_cluster.exe.remove_default_node_pool == true
    error_message = "remove_default_node_pool must be true: otherwise the cluster keeps an unmanaged default pool alongside the managed one, and that pool's nodes are outside everything the auto-sleep can resize — they would run, and bill, forever."
  }
}

run "maintenance_lands_on_a_cold_cluster_and_upgrades_are_held" {
  command = plan

  # 19:00-23:00 UTC = 04:00-08:00 JST, i.e. immediately after L3's 04:00 JST
  # forced stop. Asserting the UTC time-of-day (not the anchor date) is the
  # point: the date only anchors the recurrence.
  assert {
    condition     = endswith(google_container_cluster.exe.maintenance_policy[0].recurring_window[0].start_time, "T19:00:00Z")
    error_message = "the maintenance window must start at 19:00 UTC (04:00 JST), right after L3's daily stop, so GKE does its work on a cluster that is already meant to be cold. A window during working hours means maintenance interrupts a running task, which on Substrate v0.1.0 kills its actors terminally."
  }

  assert {
    condition     = endswith(google_container_cluster.exe.maintenance_policy[0].recurring_window[0].end_time, "T23:00:00Z")
    error_message = "the maintenance window must end at 23:00 UTC (08:00 JST): a 4-hour window is what GKE asks for, and stretching it into the working day reintroduces exactly the mid-task interruption the window placement exists to avoid."
  }

  assert {
    condition     = google_container_cluster.exe.maintenance_policy[0].recurring_window[0].recurrence == "FREQ=DAILY"
    error_message = "recurrence must be FREQ=DAILY. The start/end timestamps are a fixed anchor date; without the daily recurrence the window applies once, in the past, and GKE is then free to maintain the cluster at any hour."
  }

  # maintenance_exclusion is a SET in the provider schema, so it is read with
  # one() rather than by index — which also asserts that there is exactly one.
  assert {
    condition     = one(google_container_cluster.exe.maintenance_policy[0].maintenance_exclusion).exclusion_options[0].scope == "NO_MINOR_OR_NODE_UPGRADES"
    error_message = "the maintenance exclusion must use scope NO_MINOR_OR_NODE_UPGRADES. A weaker scope still lets GKE replace nodes inside the window; with one node that is a full outage, and on Substrate v0.1.0 a replaced worker pod destroys every awake actor with no recovery path."
  }
}
