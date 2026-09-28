# What this file pins: the network objects the private cluster cannot work
# without, and the explicit upper bound on every place bytes accumulate
# (section 3.3 of docs/plan/exe-google-ax.md).
#
# NETWORK. Nodes here have no external IP — the org policy allows them only by
# allowlist — so Cloud NAT is not hardening, it is the only path to an image
# registry. It is also the one continuously-billed network object in the stack,
# which is why the allocation option is asserted: AUTO_ONLY bills for an address
# while the gateway holds one, whereas a reserved static IP bills whether or not
# a node exists. And Private Google Access on the subnet keeps API traffic off
# the NAT entirely, which is both cheaper and keeps the NAT's connection budget
# for image pulls.
#
# The subnet's two named secondary ranges are the VPC-native (alias IP) ranges.
# The cluster addresses them BY NAME, and an unnamed or renamed range cannot be
# addressed at all — so the names are asserted to agree with what the cluster
# asks for, rather than each being written twice and hoped about.
#
# STORAGE. Every sink declares a bound, because none of these failures is loud:
# an unbounded bucket produces a slightly larger bill every month and nothing
# else. Uniform bucket-level access plus enforced public access prevention are
# asserted on all three because the alternative — per-object ACLs on a bucket
# holding actor snapshots — is a data-exposure mode no amount of later care
# undoes. Soft delete is zero everywhere on purpose: its 7-day default retention
# is billed storage for objects that are already deleted, which on a lease bucket
# rewritten every minute is pure accumulation.
#
# The snapshot bucket is the INVERTED case, and the most subtle assertion in this
# file: it must have NO lifecycle rule at all. Deleting a snapshot a suspended
# task still references makes that task unresumable, silently, until someone
# tries to resume it — there is no recovery. Substrate garbage-collects
# unreferenced snapshots itself, and the real bound is the task lifetime. So the
# ABSENCE of a delete rule is the invariant, and absence is exactly what a
# well-meaning cleanup commit adds "for consistency".
#
# ARTIFACT REGISTRY. Three provider behaviours make a repository that looks
# managed delete nothing: KEEP beats DELETE when both match; most_recent_versions
# is a FLOOR, not a cap, so on its own it deletes nothing at all; and a
# conditional KEEP cannot share a policy block with a most_recent_versions KEEP.
# The last one is why "keep the in-use tags AND the newest few" is two KEEP
# policies, and it is asserted per policy id below. cleanup_policy_dry_run =
# false is asserted on both repositories because with dry-run on, every policy is
# inert while the configuration still reads as correct.
#
# command = plan + mock_provider: offline, no credentials, nothing created. Note
# that merely REFERENCING these resources pins their existence — a deleted Cloud
# NAT or bucket makes this file fail to evaluate rather than quietly pass.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "cloud_nat_is_the_egress_path_and_reserves_no_address" {
  command = plan

  assert {
    condition     = google_compute_router_nat.exe.nat_ip_allocate_option == "AUTO_ONLY"
    error_message = "Cloud NAT must allocate its address automatically. A reserved static IP is billed whether or not a node exists, and nothing here needs a stable egress address — on a cluster that sits at zero nodes most of the day that reservation would be a permanent charge for an idle cluster."
  }

  assert {
    condition     = google_compute_router_nat.exe.source_subnetwork_ip_ranges_to_nat == "ALL_SUBNETWORKS_ALL_IP_RANGES"
    error_message = "Cloud NAT must translate ALL_SUBNETWORKS_ALL_IP_RANGES. The nodes have no external IP, so a narrower selection that misses the pod alias range leaves pods unable to reach any registry or API — which surfaces as ImagePullBackOff, not as a networking error."
  }

  assert {
    condition     = google_compute_router_nat.exe.router == google_compute_router.exe.name
    error_message = "the NAT must be attached to the Cloud Router this stack creates: a NAT naming a router that does not exist (or a different one) fails at apply, and a NAT on the wrong router silently serves nothing."
  }
}

run "subnet_is_vpc_native_with_two_named_secondary_ranges" {
  command = plan

  assert {
    condition     = google_compute_subnetwork.nodes.private_ip_google_access == true
    error_message = "the subnet must have Private Google Access on. Nodes have no external IP, so without it every Google API call has to leave through Cloud NAT: more expensive, and it spends the NAT's connection budget on traffic that never needed to leave Google's network."
  }

  assert {
    condition     = length(google_compute_subnetwork.nodes.secondary_ip_range) == 2
    error_message = "the subnet must declare exactly two secondary ranges (pods and services). A VPC-native cluster needs both, and they cannot be added to a subnet a cluster is already using — a missing range means rebuilding the cluster."
  }

  assert {
    condition     = [for range in google_compute_subnetwork.nodes.secondary_ip_range : range.range_name] == ["exe-pods", "exe-services"]
    error_message = "the secondary ranges must be NAMED exe-pods and exe-services: the cluster's ip_allocation_policy addresses them by name, and an unnamed secondary range cannot be addressed at all."
  }

  # The cluster writes these names and the subnet writes them too. If they ever
  # diverge the apply fails with a message about a range that "does not exist",
  # which is a long way from the two lines that disagree.
  assert {
    condition     = contains([for range in google_compute_subnetwork.nodes.secondary_ip_range : range.range_name], google_container_cluster.exe.ip_allocation_policy[0].cluster_secondary_range_name)
    error_message = "the cluster's pod secondary range name must be one the subnet actually declares. The two are written in different files, so a rename in one place fails the apply with a complaint about a nonexistent range rather than pointing at the mismatch."
  }

  assert {
    condition     = contains([for range in google_compute_subnetwork.nodes.secondary_ip_range : range.range_name], google_container_cluster.exe.ip_allocation_policy[0].services_secondary_range_name)
    error_message = "the cluster's services secondary range name must be one the subnet actually declares — same failure mode as the pod range, and equally far from its cause."
  }
}

run "all_three_buckets_are_private_and_keep_no_deleted_bytes" {
  command = plan

  assert {
    condition     = alltrue([for bucket in [google_storage_bucket.snapshots, google_storage_bucket.ops, google_storage_bucket.build] : bucket.uniform_bucket_level_access])
    error_message = "every bucket must have uniform bucket-level access. Offenders: ${join(", ", [for bucket in [google_storage_bucket.snapshots, google_storage_bucket.ops, google_storage_bucket.build] : bucket.name if !bucket.uniform_bucket_level_access])}. Without UBLA, per-object ACLs are live and a single object can be made readable in a way no bucket policy overrides — on a bucket holding actor snapshots that is an exposure nothing later undoes."
  }

  assert {
    condition     = alltrue([for bucket in [google_storage_bucket.snapshots, google_storage_bucket.ops, google_storage_bucket.build] : bucket.public_access_prevention == "enforced"])
    error_message = "every bucket must set public_access_prevention = enforced. Offenders: ${join(", ", [for bucket in [google_storage_bucket.snapshots, google_storage_bucket.ops, google_storage_bucket.build] : bucket.name if bucket.public_access_prevention != "enforced"])}. 'inherited' means an org-policy change elsewhere can make these buckets publicly grantable without touching this stack at all."
  }

  assert {
    condition     = alltrue([for bucket in [google_storage_bucket.snapshots, google_storage_bucket.ops, google_storage_bucket.build] : bucket.soft_delete_policy[0].retention_duration_seconds == 0])
    error_message = "every bucket must disable soft delete (retention 0). Offenders: ${join(", ", [for bucket in [google_storage_bucket.snapshots, google_storage_bucket.ops, google_storage_bucket.build] : bucket.name if bucket.soft_delete_policy[0].retention_duration_seconds != 0])}. The 7-day default is billed storage for objects that are already deleted, and on a lease bucket rewritten every minute while a node is awake it is pure accumulation that no lifecycle rule can reach."
  }
}

run "the_ops_bucket_bounds_its_generation_history" {
  command = plan

  # Versioning here is load-bearing, not a safety net: lease.json, drain.json and
  # enforce.json are written under generation preconditions so exactly one writer
  # wins a race (section 3.2). Generations are what those preconditions compare.
  assert {
    condition     = google_storage_bucket.ops.versioning[0].enabled == true
    error_message = "the exe-ops bucket must have versioning ENABLED: the auto-sleep's lease/drain/enforce writes use generation preconditions to make exactly one writer win a race, and without object versioning there are no generations for those preconditions to compare against."
  }

  assert {
    condition     = length([for rule in google_storage_bucket.ops.lifecycle_rule : rule if one(rule.condition).num_newer_versions == 5 && one(rule.action).type == "Delete"]) == 1
    error_message = "the exe-ops bucket must carry exactly one Delete rule bounded at num_newer_versions = 5. These objects are a few hundred bytes and are rewritten every minute while a node is awake, so unbounded versioning is roughly 1,400 dead objects a day — invisible individually, permanent in aggregate."
  }
}

run "the_build_bucket_expires_sources_after_a_week" {
  command = plan

  assert {
    condition     = length([for rule in google_storage_bucket.build.lifecycle_rule : rule if one(rule.condition).age == 7 && one(rule.action).type == "Delete"]) == 1
    error_message = "the exe-build bucket must carry exactly one Delete rule at age = 7 days. This bucket exists precisely so Cloud Build's --gcs-source-staging-dir points somewhere bounded: Cloud Build's own default staging bucket has no expiry at all, which is how a source tarball from two years ago is still billed."
  }
}

run "the_snapshot_bucket_has_no_lifecycle_rule_at_all" {
  command = plan

  # The one inverted case in section 3.3. Read the header before "fixing" this.
  assert {
    condition     = length(google_storage_bucket.snapshots.lifecycle_rule) == 0
    error_message = "the exe-snapshots bucket must have NO lifecycle_rule at all — the ABSENCE is the invariant. Deleting a snapshot that a suspended task still references makes that task permanently unresumable, and the loss is silent until someone tries to resume it. Substrate garbage-collects unreferenced snapshots itself; the real bound is the task lifetime (30 days), enforced by the reaper deleting tasks, not by storage lifecycle."
  }
}

run "both_registries_actually_enforce_their_cleanup_policies" {
  command = plan

  assert {
    condition     = google_artifact_registry_repository.task.cleanup_policy_dry_run == false
    error_message = "exe-task must have cleanup_policy_dry_run = false. With dry-run on, every policy below is inert while the configuration still reads as correct — the repository grows forever and the only evidence is the bill, which is exactly the silent failure the storage-bounds gate exists to refuse."
  }

  assert {
    condition     = google_artifact_registry_repository.platform.cleanup_policy_dry_run == false
    error_message = "exe-platform must have cleanup_policy_dry_run = false — same silent failure as exe-task: policies that look configured, evaluate nothing, and delete nothing."
  }

  # keys() is sorted, so this pins the exact policy set: an added policy or a
  # renamed id fails here rather than in the detail assertions below.
  assert {
    condition     = keys({ for policy in google_artifact_registry_repository.task.cleanup_policies : policy.id => policy }) == ["delete-stale", "keep-inuse", "keep-recent"]
    error_message = "exe-task must carry exactly the three policies keep-inuse, keep-recent and delete-stale. KEEP beats DELETE in Artifact Registry, so adding or renaming one changes which versions survive in a way no other assertion here would notice."
  }

  assert {
    condition     = keys({ for policy in google_artifact_registry_repository.platform.cleanup_policies : policy.id => policy }) == ["delete-stale", "keep-inuse", "keep-recent"]
    error_message = "exe-platform must carry exactly the three policies keep-inuse, keep-recent and delete-stale. Another policy — most plausibly an 'delete untagged immediately' reflex — would pull versions out from under a running install, which references its images BY DIGEST."
  }
}

run "exe_platform_keeps_the_inuse_tag" {
  command = plan

  # L1 tags every image the cluster's own pods run, and L2's enforcer image,
  # `inuse-` (M19 C3, inbox M53 B6): this KEEP is what makes that tag hold
  # here, as keep-inuse does on exe-task.
  assert {
    condition     = one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "keep-inuse"]).action == "KEEP"
    error_message = "exe-platform's keep-inuse policy must be a KEEP: the reaper's inuse- tag on an image the running install pulls by digest protects it only through a KEEP."
  }

  assert {
    condition     = one(one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "keep-inuse"]).condition[0].tag_prefixes) == "inuse-"
    error_message = "exe-platform's keep-inuse policy must match exactly one tag prefix, 'inuse-', the literal prefix the reaper writes: another prefix protects nothing while looking like it protects everything."
  }

  assert {
    condition     = one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "keep-inuse"]).condition[0].tag_state == "TAGGED"
    error_message = "exe-platform's keep-inuse policy must select TAGGED versions, like exe-task's: the tag prefix is what it keys on."
  }
}

run "exe_task_keeps_the_inuse_tag_and_the_last_two_and_deletes_at_14_days" {
  command = plan

  assert {
    condition     = one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "keep-inuse"]).action == "KEEP"
    error_message = "exe-task's keep-inuse policy must be a KEEP. It is what makes the reaper's `inuse-` tag mean anything: L1 puts that tag on the image every live task references and removes it when the last one goes away, so a KEEP is the only thing standing between a suspended task and an image that was deleted underneath it."
  }

  assert {
    condition     = one(one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "keep-inuse"]).condition[0].tag_prefixes) == "inuse-"
    error_message = "exe-task's keep-inuse policy must match exactly one tag prefix, 'inuse-' — that is the literal prefix the reaper writes. A different prefix produces a policy that protects nothing while looking like it protects everything, and a second prefix widens the KEEP to images no live task references."
  }

  assert {
    condition     = one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "keep-recent"]).most_recent_versions[0].keep_count == 2
    error_message = "exe-task's keep-recent policy must keep the newest 2 versions. Two is the smallest rollback window that still lets a bad task image be replaced without losing the one before it; it is a separate policy from keep-inuse because Artifact Registry forbids mixing a conditional KEEP with most_recent_versions."
  }

  assert {
    condition     = one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "delete-stale"]).action == "DELETE"
    error_message = "exe-task's delete-stale policy must be a DELETE: without one, the two KEEP policies bound nothing at all — most_recent_versions is a FLOOR, not a cap, and on its own deletes nothing."
  }

  assert {
    condition     = one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "delete-stale"]).condition[0].older_than == "1209600s"
    error_message = "exe-task's delete-stale policy must fire at older_than = 1209600s (14 days), the bound section 3.3 states for task images. A longer window is unbounded growth by another name; a shorter one races the suspended tasks the inuse- KEEP exists to protect."
  }
}

run "exe_platform_keeps_the_last_ten_and_deletes_at_30_days" {
  command = plan

  assert {
    condition     = one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "keep-recent"]).most_recent_versions[0].keep_count == 10
    error_message = "exe-platform's keep-recent policy must keep the newest 10 versions regardless of tags. A running install references its images BY DIGEST, so the usual reflex — deleting untagged versions promptly — pulls the floor out from under a live cluster; keeping 10 is what makes that safe."
  }

  assert {
    condition     = one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "delete-stale"]).condition[0].older_than == "2592000s"
    error_message = "exe-platform's delete-stale policy must fire at older_than = 2592000s (30 days), the bound section 3.3 states for platform images. Without a DELETE at all the keep-recent floor bounds nothing, since most_recent_versions never deletes on its own."
  }
}

run "no_cleanup_policy_mixes_a_condition_with_most_recent_versions" {
  command = plan

  # Artifact Registry rejects a policy block that carries both, and the rejection
  # is at apply time. One assertion per policy id, so the failure names the
  # offender instead of just saying the repository is wrong.
  assert {
    condition     = length(one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "keep-inuse"]).condition) == 0 || length(one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "keep-inuse"]).most_recent_versions) == 0
    error_message = "exe-task/keep-inuse must not carry both a condition and most_recent_versions: Artifact Registry forbids the combination, so merging the tag-prefix KEEP with a 'keep the newest N' KEEP fails at apply — which is why they are two policies."
  }

  assert {
    condition     = length(one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "keep-recent"]).condition) == 0 || length(one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "keep-recent"]).most_recent_versions) == 0
    error_message = "exe-task/keep-recent must not carry both a condition and most_recent_versions — the same rejection, arrived at from the other direction by adding a tag condition to the recent-versions KEEP."
  }

  assert {
    condition     = length(one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "delete-stale"]).condition) == 0 || length(one([for policy in google_artifact_registry_repository.task.cleanup_policies : policy if policy.id == "delete-stale"]).most_recent_versions) == 0
    error_message = "exe-task/delete-stale must not carry both a condition and most_recent_versions: a DELETE bounded by most_recent_versions is not a narrower delete, it is a policy Artifact Registry refuses."
  }

  assert {
    condition     = length(one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "keep-inuse"]).condition) == 0 || length(one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "keep-inuse"]).most_recent_versions) == 0
    error_message = "exe-platform/keep-inuse must not carry both a condition and most_recent_versions: Artifact Registry forbids the combination, which is why keep-inuse and keep-recent are two policies here too."
  }

  assert {
    condition     = length(one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "keep-recent"]).condition) == 0 || length(one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "keep-recent"]).most_recent_versions) == 0
    error_message = "exe-platform/keep-recent must not carry both a condition and most_recent_versions: adding a tag condition here — e.g. to exclude untagged versions — makes the policy invalid rather than narrower."
  }

  assert {
    condition     = length(one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "delete-stale"]).condition) == 0 || length(one([for policy in google_artifact_registry_repository.platform.cleanup_policies : policy if policy.id == "delete-stale"]).most_recent_versions) == 0
    error_message = "exe-platform/delete-stale must not carry both a condition and most_recent_versions — same apply-time rejection as its exe-task counterpart."
  }
}
