# VPC, subnet, Cloud Router and Cloud NAT.
#
# A dedicated VPC rather than the project's default: the project is shared, and
# nodes here must be private. The org policy allows external IPs only by
# allowlist, so private nodes are not a hardening choice, they are the only
# option — which makes Cloud NAT mandatory for image pulls and API egress.
#
# No load balancer, no reserved static IP, no VPC peering. NAT bills per
# gateway-hour plus per assigned IP only while it has one, and it is the only
# continuously-billed network object here.

resource "google_compute_network" "exe" {
  project = var.gcp_project_id
  name    = local.network_name

  # Explicit subnets only: an auto-mode VPC creates one subnet in every region,
  # which is 30-odd ranges nobody declared.
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
  description             = "exe: ax / Agent Substrate cluster network"

  depends_on = [google_project_service.enabled]
}

resource "google_compute_subnetwork" "nodes" {
  project       = var.gcp_project_id
  name          = local.subnet_name
  region        = local.region
  network       = google_compute_network.exe.id
  ip_cidr_range = "10.30.0.0/20"

  # Nodes have no external IP, so every Google API call leaves through Private
  # Google Access rather than the NAT. Cheaper and it keeps API traffic off the
  # NAT's connection budget.
  private_ip_google_access = true

  # VPC-native (alias IP) ranges. Named, because the cluster references them by
  # name and an unnamed secondary range cannot be addressed.
  secondary_ip_range {
    range_name    = "${local.prefix}-pods"
    ip_cidr_range = "10.31.0.0/16"
  }

  secondary_ip_range {
    range_name    = "${local.prefix}-services"
    ip_cidr_range = "10.32.0.0/20"
  }
}

resource "google_compute_router" "exe" {
  project = var.gcp_project_id
  name    = local.router_name
  region  = local.region
  network = google_compute_network.exe.id
}

resource "google_compute_router_nat" "exe" {
  project = var.gcp_project_id
  name    = local.nat_name
  router  = google_compute_router.exe.name
  region  = local.region

  # Auto-allocated: a reserved static IP bills whether or not a node exists,
  # and nothing here needs a stable egress address.
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    # Errors only. Logging every translation on a NAT that serves image pulls is
    # a log-ingestion bill for data nobody reads.
    filter = "ERRORS_ONLY"
  }
}
