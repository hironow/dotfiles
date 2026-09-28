# What this file pins: the exact set of Google APIs this stack enables, and the
# fact that tearing the stack down never disables any of them.
#
# Two failure modes, opposite in shape, are what make this worth a test.
#
# An API enabled BY HAND is drift no plan can see: `google_project_service` only
# ever adds, so a resource that works today because somebody clicked "Enable" in
# the console keeps working until the project is rebuilt from this stack in a
# fresh project, where it fails as an opaque 403 several resources into the
# apply. Enumerating the set here — and asserting the enumeration — is what makes
# the stack a complete description of what the project needs.
#
# An API REMOVED from the list is the same failure with a delay: nothing breaks
# until the next apply against a clean project. So the assertions are written to
# fail in both directions: a length check plus one presence check per key, so an
# addition fails the length and a removal fails its own key, and each message
# says who needs that API. A deliberate change means editing apis.tf AND this
# list, which is exactly the review conversation that should happen.
#
# disable_on_destroy = false is the other half. The project is SHARED with two
# unrelated OpenTofu stacks: disabling compute or storage while tearing this
# stack down would break them, and enablement costs nothing when unused. The
# safe asymmetry — enable here, never disable — is only safe if it cannot be
# quietly dropped, so it is asserted for every service in the map at once.
#
# command = plan + mock_provider: offline, no credentials, nothing enabled.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "the_enabled_api_set_is_exactly_the_nineteen_declared_here" {
  command = plan

  assert {
    condition     = length(google_project_service.enabled) == 19
    error_message = "this stack must enable exactly 19 services. A 20th means an API was added to apis.tf without being explained here; an 18th means one was dropped and the resource that needed it will fail as an opaque 403 on the next apply into a clean project."
  }

  # The explicit list. Anything enabled by apis.tf but absent here is either a
  # new dependency that needs recording, or an API nobody needs turned on.
  assert {
    condition = length(setsubtract(toset(keys(google_project_service.enabled)), toset([
      "cloudresourcemanager.googleapis.com",
      "serviceusage.googleapis.com",
      "iam.googleapis.com",
      "iamcredentials.googleapis.com",
      "sts.googleapis.com",
      "compute.googleapis.com",
      "container.googleapis.com",
      "networkconnectivity.googleapis.com",
      "storage.googleapis.com",
      "artifactregistry.googleapis.com",
      "cloudbuild.googleapis.com",
      "secretmanager.googleapis.com",
      "run.googleapis.com",
      "cloudscheduler.googleapis.com",
      "monitoring.googleapis.com",
      "logging.googleapis.com",
      "cloudtrace.googleapis.com",
      "billingbudgets.googleapis.com",
      "cloudkms.googleapis.com",
    ]))) == 0
    error_message = "apis.tf enables a service this test does not list: ${join(", ", setsubtract(toset(keys(google_project_service.enabled)), toset(["cloudresourcemanager.googleapis.com", "serviceusage.googleapis.com", "iam.googleapis.com", "iamcredentials.googleapis.com", "sts.googleapis.com", "compute.googleapis.com", "container.googleapis.com", "networkconnectivity.googleapis.com", "storage.googleapis.com", "artifactregistry.googleapis.com", "cloudbuild.googleapis.com", "secretmanager.googleapis.com", "run.googleapis.com", "cloudscheduler.googleapis.com", "monitoring.googleapis.com", "logging.googleapis.com", "cloudtrace.googleapis.com", "billingbudgets.googleapis.com", "cloudkms.googleapis.com"])))}. On a shared project an unexplained enablement widens the blast radius of this stack; add it here with a note saying who needs it, or take it out of apis.tf."
  }
}

run "every_declared_api_is_present_by_key" {
  command = plan

  assert {
    condition     = contains(keys(google_project_service.enabled), "cloudresourcemanager.googleapis.com")
    error_message = "cloudresourcemanager.googleapis.com must be enabled: without it every IAM binding and project metadata read in iam.tf fails, and it is the API the others are enabled THROUGH."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "serviceusage.googleapis.com")
    error_message = "serviceusage.googleapis.com must be enabled: it is what enables the rest of this list, so losing it makes every other entry unreachable rather than merely missing."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "iam.googleapis.com")
    error_message = "iam.googleapis.com must be enabled: the five dedicated service accounts and the custom node-pool-resizer role cannot be created without it, and the resizer role is the only power L3 has."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "iamcredentials.googleapis.com")
    error_message = "iamcredentials.googleapis.com must be enabled: it mints the short-lived tokens Cloud Scheduler's OAuth target uses. Without it L3 cannot authenticate, so the daily forced stop fails silently every night."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "sts.googleapis.com")
    error_message = "sts.googleapis.com must be enabled: it performs the Workload Identity token exchange. Without it every principal:// binding in iam.tf is inert and the first actor snapshot 403s."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "compute.googleapis.com")
    error_message = "compute.googleapis.com must be enabled: the VPC, subnet, Cloud Router, Cloud NAT and the node VMs themselves all live behind it — and so does the instance/uptime_total metric the node-uptime money-stop alert reads."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "container.googleapis.com")
    error_message = "container.googleapis.com must be enabled: it serves both the GKE cluster and the nodePools.setSize call L3 POSTs to. Losing it disables the last automatic money stop as well as the cluster."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "networkconnectivity.googleapis.com")
    error_message = "networkconnectivity.googleapis.com must be enabled: it carries the Private Service Connect plumbing GKE creates behind a private cluster, and a private cluster is not optional here (the org policy forbids external node IPs)."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "storage.googleapis.com")
    error_message = "storage.googleapis.com must be enabled: it holds the OpenTofu state, the actor snapshots, the lease/drain/enforce objects the auto-sleep coordinates through, and the Cloud Build sources."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "artifactregistry.googleapis.com")
    error_message = "artifactregistry.googleapis.com must be enabled: both image repositories (exe-platform, exe-task) and every image pull the node or atelet makes depend on it."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "cloudbuild.googleapis.com")
    error_message = "cloudbuild.googleapis.com must be enabled: the task image is built inside the private project, not on a laptop, so there is no other path from source to a pullable image."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "secretmanager.googleapis.com")
    error_message = "secretmanager.googleapis.com must be enabled: it holds the agent credential the task runner is handed at run time. No key material is meant to exist anywhere else."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "run.googleapis.com")
    error_message = "run.googleapis.com must be enabled: L2 (the out-of-cluster lease enforcer) is a Cloud Run job. It is enabled a phase ahead of the job itself on purpose, so the money stop is never blocked on an API enablement."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "cloudscheduler.googleapis.com")
    error_message = "cloudscheduler.googleapis.com must be enabled: it runs L3's daily forced stop and, next phase, L2's tick. It is the API the entire automatic-stop story currently rests on."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "monitoring.googleapis.com")
    error_message = "monitoring.googleapis.com must be enabled: the L4 alert policies and the email notification channel are what notice when the money stops did not work. Without them a failed stop is invisible until the bill."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "logging.googleapis.com")
    error_message = "logging.googleapis.com must be enabled: it carries the cluster's system logs and the log-based metric the Scheduler-failure alert counts, i.e. the only signal that a silently dead L3 produces."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "cloudtrace.googleapis.com")
    error_message = "cloudtrace.googleapis.com must be enabled: Substrate emits traces unconditionally, and an export to a disabled API is an error on every span rather than a quiet no-op. The API itself costs nothing."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "billingbudgets.googleapis.com")
    error_message = "billingbudgets.googleapis.com must be enabled: the JPY budget is the last-resort money stop that catches everything the uptime and Scheduler alerts missed."
  }

  assert {
    condition     = contains(keys(google_project_service.enabled), "cloudkms.googleapis.com")
    error_message = "cloudkms.googleapis.com must be enabled: it holds the key that encrypts tofu/exe-cluster's state, which carries the Postgres and Redis passwords. Without it that stack cannot read its own state."
  }
}

run "tearing_this_stack_down_never_disables_a_shared_projects_apis" {
  command = plan

  assert {
    condition     = alltrue([for svc in google_project_service.enabled : svc.disable_on_destroy == false])
    error_message = "every google_project_service must set disable_on_destroy = false. The project is shared with two unrelated OpenTofu stacks, so a destroy that switches compute or storage off takes the neighbours down with it — and enablement is close to idempotent and costs nothing while unused, which makes 'enable here, never disable' the only safe asymmetry."
  }

  assert {
    condition     = alltrue([for svc in google_project_service.enabled : svc.disable_dependent_services == false])
    error_message = "every google_project_service must set disable_dependent_services = false: the same shared-project hazard, one level further out — a cascade that disables a neighbour's dependency is a neighbour's outage caused by this stack's teardown."
  }
}
