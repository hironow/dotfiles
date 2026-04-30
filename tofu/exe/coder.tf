# GCE workspace VM that hosts the Coder server (added in a later commit)
# and the dev container (built from tests/docker/JustSandbox.Dockerfile).
#
# Network model:
#   - The VM has a public IP only so cloudflared can phone home; no
#     ingress is opened in the firewall (Tailscale handles inbound).
#   - All inbound traffic to dev workloads flows through Tailscale
#     (Pattern A) — no firewall rule for 22/80/443/3000-3999.
#
# Boot model:
#   - cos-stable image keeps the host minimal and auto-updating.
#   - Startup-script:
#       1. Install Tailscale (apt-less; cos uses cloud-init's pull).
#       2. Pull the workspace VM auth key from Secret Manager.
#       3. tailscale up --auth-key=$KEY --hostname=exe-coder.
#   - Coder server install is its own commit (feat(exe/coder): ...).

# ----- service account -------------------------------------------------
#
# A dedicated service account with the minimum roles needed by the VM
# at boot time. Add Coder-specific roles in the Coder install commit.

resource "google_service_account" "exe_coder" {
  account_id   = "${local.prefix}-coder"
  display_name = "exe.hironow.dev workspace VM"
  description  = "Service account for the exe-coder GCE VM (managed by tofu)."
}

resource "google_secret_manager_secret_iam_member" "exe_coder_authkey_reader" {
  secret_id = google_secret_manager_secret.exe_coder_authkey.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.exe_coder.email}"
}

# Logs/metrics so a preempted VM still leaves a trail.
resource "google_project_iam_member" "exe_coder_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.exe_coder.email}"
}

resource "google_project_iam_member" "exe_coder_metric_writer" {
  project = var.gcp_project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.exe_coder.email}"
}

# ----- network --------------------------------------------------------
#
# A small dedicated VPC + subnet keeps the workspace blast radius
# contained. The VPC has no firewall rules allowing ingress; Tailscale
# is the only path in.

resource "google_compute_network" "exe" {
  name                            = "${local.prefix}-vpc"
  auto_create_subnetworks         = false
  delete_default_routes_on_create = false
  routing_mode                    = "REGIONAL"
}

resource "google_compute_subnetwork" "exe" {
  name                     = "${local.prefix}-subnet"
  region                   = var.gcp_region
  network                  = google_compute_network.exe.id
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true
}

# Egress is allowed by default. Explicitly DENY all ingress (defense in
# depth — there should be no public-facing port on this VM).
resource "google_compute_firewall" "deny_all_ingress" {
  name      = "${local.prefix}-deny-all-ingress"
  network   = google_compute_network.exe.name
  direction = "INGRESS"
  priority  = 65000
  deny {
    protocol = "all"
  }
  source_ranges = ["0.0.0.0/0"]
}

# ----- VM -------------------------------------------------------------

locals {
  vm_name = "${local.prefix}-coder"

  # Startup-script runs on every boot. It is idempotent: if Tailscale is
  # already up with the right hostname, it no-ops. The auth key is
  # fetched from Secret Manager via the VM's service account, so the
  # plaintext never lands in the GCE metadata service.
  startup_script = <<-EOT
    #!/usr/bin/env bash
    set -euo pipefail

    HOSTNAME='${local.vm_name}'
    TS_SECRET='${google_secret_manager_secret.exe_coder_authkey.secret_id}'
    CF_SECRET='${google_secret_manager_secret.tunnel_credentials.secret_id}'
    CF_TUNNEL_ID='${cloudflare_zero_trust_tunnel_cloudflared.exe.id}'
    PROJECT='${var.gcp_project_id}'

    # Tailscale on Container-Optimized OS — install via the official
    # static binary tarball into /var (cos has /usr read-only).
    if ! command -v tailscale >/dev/null 2>&1; then
      mkdir -p /var/lib/tailscale /var/run/tailscale
      curl -fsSL https://pkgs.tailscale.com/stable/tailscale_latest_amd64.tgz \
        | tar -xz -C /var/lib/tailscale --strip-components=1
      ln -sf /var/lib/tailscale/tailscale  /usr/local/bin/tailscale
      ln -sf /var/lib/tailscale/tailscaled /usr/local/bin/tailscaled
    fi

    if ! pgrep -x tailscaled >/dev/null 2>&1; then
      /usr/local/bin/tailscaled \
        --state=/var/lib/tailscale/tailscaled.state \
        --socket=/var/run/tailscale/tailscaled.sock \
        --tun=userspace-networking >/var/log/tailscaled.log 2>&1 &
      sleep 2
    fi

    # Fetch the tag:exe-coder auth key (latest version) from Secret Manager.
    AUTH_KEY="$(gcloud --quiet --project="$PROJECT" \
      secrets versions access latest --secret="$TS_SECRET")"

    /usr/local/bin/tailscale up \
      --auth-key="$AUTH_KEY" \
      --hostname="$HOSTNAME" \
      --ssh \
      --accept-routes=false \
      --advertise-tags='${local.tag_exe_coder}'

    # cloudflared — pull credentials JSON from Secret Manager and run as a
    # connector for the named tunnel. config_src = "cloudflare" means the
    # ingress rules live in the Cloudflare dashboard / tofu state, so the
    # daemon only needs --token-less credentials.
    if ! command -v cloudflared >/dev/null 2>&1; then
      mkdir -p /var/lib/cloudflared
      curl -fsSL -o /usr/local/bin/cloudflared \
        https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
      chmod +x /usr/local/bin/cloudflared
    fi

    install -m 0700 -d /etc/cloudflared
    gcloud --quiet --project="$PROJECT" \
      secrets versions access latest --secret="$CF_SECRET" \
      > "/etc/cloudflared/$CF_TUNNEL_ID.json"
    chmod 0600 "/etc/cloudflared/$CF_TUNNEL_ID.json"

    if ! pgrep -x cloudflared >/dev/null 2>&1; then
      /usr/local/bin/cloudflared tunnel \
        --no-autoupdate \
        --credentials-file "/etc/cloudflared/$CF_TUNNEL_ID.json" \
        run "$CF_TUNNEL_ID" >/var/log/cloudflared.log 2>&1 &
    fi
  EOT
}

resource "google_compute_instance" "exe_coder" {
  name         = local.vm_name
  machine_type = var.machine_type
  zone         = var.gcp_zone
  labels       = local.common_labels
  tags         = ["exe-coder"]

  scheduling {
    preemptible                 = var.preemptible
    automatic_restart           = !var.preemptible
    on_host_maintenance         = var.preemptible ? "TERMINATE" : "MIGRATE"
    provisioning_model          = var.preemptible ? "SPOT" : "STANDARD"
    instance_termination_action = var.preemptible ? "STOP" : null
  }

  boot_disk {
    initialize_params {
      image  = var.vm_image
      size   = var.boot_disk_size_gb
      type   = "pd-balanced"
      labels = local.common_labels
    }
    auto_delete = true
  }

  network_interface {
    network    = google_compute_network.exe.id
    subnetwork = google_compute_subnetwork.exe.id
    access_config {
      # Ephemeral public IP — required for cloudflared egress and for
      # initial Tailscale NAT traversal. No ingress is allowed (see
      # google_compute_firewall.deny_all_ingress).
    }
  }

  service_account {
    email  = google_service_account.exe_coder.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    enable-oslogin             = "TRUE"
    block-project-ssh-keys     = "TRUE"
    google-logging-enabled     = "TRUE"
    google-monitoring-enabled  = "TRUE"
    serial-port-logging-enable = "TRUE"
  }

  metadata_startup_script = local.startup_script

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  # Re-create the VM when the startup-script (and therefore the auth
  # key reference) changes. Otherwise running `tofu apply` after a
  # rotation has no effect on already-booted machines.
  lifecycle {
    create_before_destroy = false
  }

  depends_on = [
    google_secret_manager_secret_iam_member.exe_coder_authkey_reader,
    google_secret_manager_secret_iam_member.tunnel_credentials_reader,
    google_compute_firewall.deny_all_ingress,
  ]
}
