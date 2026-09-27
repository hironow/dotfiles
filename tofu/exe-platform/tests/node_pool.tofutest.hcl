# What this file pins: WHO OWNS THE NODE COUNT.
#
# This is the most important invariant in the stack, and the only documented
# exception to the IaC drift policy (docs/agents/iac-drift-policy.md). The
# running size of the pool belongs to the lease-based auto-sleep — `exe-reaper
# wake` sets it to 1, and L1 / L2 / L3 set it back to 0 — and NOT to this stack.
#
# Two things have to hold at once for that split to work, and they fail in
# opposite directions:
#
#   ignore_node_count_changes = true tells the provider that the RUNNING size is
#   somebody else's. Without it, every `tofu plan` issued while a task is awake
#   proposes to shrink the pool back to its configured size — and an operator who
#   accepts that plan kills every awake actor within about 60 seconds, which on
#   Substrate v0.1.0 is terminal and unrecoverable.
#
#   initial_node_count stays a CONSTANT (0), never a value written back by the
#   auto-sleep. If it ever became a knob the wake path sets, the next apply would
#   wake a cluster nobody asked for and bill for it until someone noticed.
#
# The rest of the file guards properties that turn a recoverable incident into an
# unrecoverable one, or that bill silently:
#
#   - on-demand, not Spot/preemptible (decision Q2): a reclaimed node destroys
#     awake actors with no recovery path. The saving does not buy back a class of
#     unfixable data loss.
#   - auto_repair off: repair recreates a node it considers unhealthy, which is
#     indistinguishable from deleting every actor on it; and a node that looks
#     unhealthy while the cluster is meant to be ASLEEP should stay dead.
#   - auto_upgrade ON, because OFF is not available: the cluster is enrolled in
#     a release channel, and GKE refuses a node pool there with auto-upgrade
#     disabled. What decides WHEN a node may be replaced is the cluster's
#     NO_MINOR_OR_NODE_UPGRADES maintenance exclusion and its 04:00-08:00 JST
#     window, both pinned in cluster.tofutest.hcl. With upgrades possible, the
#     surge settings become live behaviour, so they are pinned too.
#   - the substrate version label taken from the pin document: Substrate's node
#     selector matches on this exact key/value. A stale literal does not fail
#     loudly — it produces nodes the selector quietly declines to schedule onto,
#     and the symptom is a task that hangs in Pending forever.
#   - GKE_METADATA: without it a pod's KSA token is never exchanged for a Google
#     credential, and every principal:// binding in iam.tf is inert.
#
# command = plan + mock_provider: offline, no credentials, nothing created.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "the_auto_sleep_owns_the_running_size" {
  command = plan

  assert {
    condition     = google_container_node_pool.main.ignore_node_count_changes == true
    error_message = "ignore_node_count_changes must be true. It is the provider's purpose-built escape hatch for this ownership split: without it, every `tofu plan` run while a task is awake proposes to resize the pool back down, and accepting that plan kills every awake actor within ~60s — terminally, on Substrate v0.1.0."
  }

  # A constant, not a desired state. 0 means the stack creates a cold pool and
  # nothing bills until the first wake.
  assert {
    condition     = google_container_node_pool.main.initial_node_count == 0
    error_message = "initial_node_count must be the constant 0, so `tofu apply` creates a COLD pool and nothing bills until the first lease-driven wake. A non-zero value means every fresh apply starts a billed node that only the next L3 run will stop."
  }

  # Decision Q13 allows exactly two values: 0, or 1 if GKE refuses to create a
  # pool at 0 (in which case L3 must be run by hand straight after the apply).
  # Anything else means the count has started to be treated as a knob.
  assert {
    condition     = contains([0, 1], google_container_node_pool.main.initial_node_count)
    error_message = "initial_node_count must be 0 or 1 (decision Q13) and nothing else. Any other value means the creation-time constant has started to be used as a desired running size, which is precisely the ownership the auto-sleep holds."
  }

  # The variable carries no tfvars value in this test, so this pins the DEFAULT:
  # a stack applied without an explicit override still comes up cold.
  assert {
    condition     = var.node_pool_initial_count == 0
    error_message = "node_pool_initial_count must DEFAULT to 0: an operator who applies this stack without setting it in terraform.tfvars must get a cold pool, not a billed node."
  }

  # ============================================================================
  # NOT EXPRESSIBLE HERE — left to the pytest side deliberately.
  #
  # "the config declares no `node_count` attribute at all" cannot be asserted in
  # an OpenTofu test. `node_count` is Optional+Computed in the provider schema,
  # so a plan reports it as 0 whether the configuration omits it or writes
  # `node_count = 0` explicitly: the two are indistinguishable from inside a run
  # block, which can only see planned values and never the configuration text.
  # An assert of `node_count == 0` would therefore look like it pins the absence
  # while actually permitting the exact edit it is supposed to forbid, so it is
  # not written. The absence is a property of the source file and is checked
  # where source text can be read.
  # ============================================================================
}

run "nodes_are_on_demand_and_never_reclaimed" {
  command = plan

  assert {
    condition     = google_container_node_pool.main.node_config[0].machine_type == "e2-highmem-2"
    error_message = "machine type must be e2-highmem-2 (M20 T3, sized by S7's measurement on 2026-09-27): the stack plus two workers requests 1745m CPU and 10.2 GiB, which fits its ~1.93 vCPU / ~13 GiB allocatable, at about 68% of e2-standard-4's hourly rate. The memory is what two 4Gi workers need; a larger type silently multiplies every awake hour, a smaller one cannot schedule both workers."
  }

  assert {
    condition     = google_container_node_pool.main.node_config[0].spot == false
    error_message = "nodes must NOT be Spot. A Spot node can be reclaimed at any moment with 30s notice, and on Substrate v0.1.0 that destroys every awake actor with no recovery path — the ~70% saving does not buy back a class of unfixable data loss (decision Q2)."
  }

  assert {
    condition     = google_container_node_pool.main.node_config[0].preemptible == false
    error_message = "nodes must NOT be preemptible (the legacy form of the same reclaim risk as Spot): a 24h hard cap plus arbitrary preemption is the same unrecoverable actor loss, arrived at by a different flag."
  }
}

run "gke_never_resurrects_a_node_and_upgrades_only_as_the_channel_allows" {
  command = plan

  assert {
    condition     = google_container_node_pool.main.management[0].auto_repair == false
    error_message = "auto_repair must be false. Repair RECREATES a node GKE considers unhealthy, which is indistinguishable from deleting every actor awake on it; and a node that looks unhealthy while the cluster is meant to be asleep should stay dead rather than be resurrected into a billed node."
  }

  # TRUE, and not by preference: it is the only value a release-channel cluster
  # accepts. GKE documents node auto-upgrade as on by default for clusters
  # enrolled in a release channel, and names a cluster maintenance exclusion
  # with the "No minor or node upgrades" scope as the way to hold upgrades off:
  #   https://docs.cloud.google.com/kubernetes-engine/docs/concepts/release-channels
  #   https://docs.cloud.google.com/kubernetes-engine/docs/how-to/node-auto-upgrades
  # The API rejects false at node-pool creation ("Auto_upgrade must be true
  # when release_channel <CHANNEL> is set"), i.e. AFTER the cluster exists, so
  # an offline test is the only place this can fail cheaply. The control over
  # WHEN a node is replaced lives on the cluster: see the maintenance run in
  # cluster.tofutest.hcl.
  assert {
    condition     = google_container_node_pool.main.management[0].auto_upgrade == true
    error_message = "auto_upgrade must be true. The cluster is enrolled in a release channel, and GKE refuses a node pool there with auto-upgrade off (API: 'Auto_upgrade must be true when release_channel <CHANNEL> is set'): false does not hold upgrades off, it fails the apply after the cluster already exists. Upgrades are held by the cluster's NO_MINOR_OR_NODE_UPGRADES maintenance exclusion and placed by its 04:00-08:00 JST window (cluster.tofutest.hcl)."
  }

  # Upgrades CAN happen now, so how they happen is live behaviour rather than
  # dead configuration. Surge 0 / unavailable 1 replaces the node in place
  # instead of booting a second billed node beside it.
  assert {
    condition     = google_container_node_pool.main.upgrade_settings[0].max_surge == 0 && google_container_node_pool.main.upgrade_settings[0].max_unavailable == 1
    error_message = "upgrade_settings must be max_surge = 0 and max_unavailable = 1. Auto-upgrade is on (the release channel requires it), so a surge above 0 means every upgrade boots a SECOND billed node beside the first, and a pool that only ever holds one node has nothing to gain from it."
  }
}

run "node_labels_and_metadata_come_from_the_pin_document" {
  command = plan

  # Read from exe/versions.json the same way locals.tf does — never a literal.
  # Both the KEY and the VALUE are pins: the key is the label Substrate's node
  # selector matches on, the value is the VERSION argument handed to ate-setup.
  assert {
    condition     = lookup(google_container_node_pool.main.node_config[0].labels, jsondecode(file("${path.module}/../../exe/versions.json")).substrate.version_label_key, "") == jsondecode(file("${path.module}/../../exe/versions.json")).substrate.version_label_value
    error_message = "the node label named by substrate.version_label_key in exe/versions.json must carry substrate.version_label_value from the same file. Substrate's node selector matches on that exact pair: a stale or missing value does not error, it produces nodes the selector declines to schedule onto, and the only symptom is a task stuck Pending forever."
  }

  assert {
    condition     = google_container_node_pool.main.node_config[0].workload_metadata_config[0].mode == "GKE_METADATA"
    error_message = "workload_metadata_config mode must be GKE_METADATA. Without it the GKE metadata server never exchanges a pod's KSA token for a Google credential, so every principal:// binding in iam.tf is inert — and the failure appears as a 403 at the first snapshot write, far from its cause."
  }
}
