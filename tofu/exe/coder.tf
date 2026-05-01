# GCE workspace VM that hosts the Coder server and the dev container
# (built from tests/docker/JustSandbox.Dockerfile).
#
# Network model:
#   - The VM has a public IP only so cloudflared can phone home; no
#     ingress is opened in the firewall (Tailscale handles inbound).
#   - All inbound traffic to dev workloads flows through Tailscale
#     (Pattern A) — no firewall rule for 22/80/443/3000-3999.
#
# Boot model — Ubuntu 24.04 LTS (noble):
#   - Earlier revisions used cos-stable; codex review flagged two
#     fatal incompatibilities:
#       1. cos mounts /var as noexec (binaries under /var/lib/coder
#          cannot execute).
#       2. cos has no gcloud on the host (it lives only in toolbox).
#     Switching to Ubuntu LTS resolves both — gcloud installs cleanly
#     via apt, /usr/local/bin is writable + executable, systemd is
#     available for proper service supervision.
#   - The startup-script is idempotent on every boot, including
#     post-preemption auto-restarts.
#   - Each daemon (tailscaled, cloudflared, coder) runs as a systemd
#     unit so we get supervision, restart policy, and journald logs
#     for free.

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

  # Startup-script runs on every boot. It is idempotent: if a daemon
  # is already running with the desired config, the systemctl restart
  # / start calls no-op or replay safely. Auth keys and tunnel
  # credentials are fetched from Secret Manager via the VM's service
  # account, so plaintext never lands in the GCE metadata service.
  startup_script = <<-EOT
    #!/usr/bin/env bash
    set -euo pipefail

    HOSTNAME_VM='${local.vm_name}'
    TS_SECRET='${google_secret_manager_secret.exe_coder_authkey.secret_id}'
    CF_SECRET='${google_secret_manager_secret.tunnel_credentials.secret_id}'
    CF_TUNNEL_ID='${cloudflare_zero_trust_tunnel_cloudflared.exe.id}'
    PROJECT='${var.gcp_project_id}'
    CODER_ACCESS_URL='https://${local.coder_host}'
    CODER_WILDCARD='${local.sandbox_host}'
    TS_TAG='${local.tag_exe_coder}'

    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends \
      apt-transport-https ca-certificates curl gnupg lsb-release jq

    # ---- Google Cloud CLI (Ubuntu noble) ------------------------------
    if ! command -v gcloud >/dev/null 2>&1; then
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | gpg --dearmor -o /etc/apt/keyrings/cloud.google.gpg
      echo 'deb [signed-by=/etc/apt/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main' \
        > /etc/apt/sources.list.d/google-cloud-sdk.list
      apt-get update -y
      apt-get install -y --no-install-recommends google-cloud-cli
    fi

    # ---- Tailscale (apt repository) -----------------------------------
    # Tailscale's published noble.tailscale-keyring.list pins
    # signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg, so
    # the keyring MUST be written there. Putting it under
    # /etc/apt/keyrings/tailscale.gpg breaks apt with NO_PUBKEY 458CA832957F5868.
    if ! command -v tailscale >/dev/null 2>&1; then
      install -m 0755 -d /usr/share/keyrings
      curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg \
        > /usr/share/keyrings/tailscale-archive-keyring.gpg
      curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list \
        > /etc/apt/sources.list.d/tailscale.list
      apt-get update -y
      apt-get install -y --no-install-recommends tailscale
    fi

    systemctl enable --now tailscaled

    # Fetch the tag:exe-coder auth key (latest version) from Secret Manager.
    # Idempotent join: tailscale up is a no-op if already authenticated
    # under the same tags + hostname.
    AUTH_KEY="$(gcloud --quiet --project="$PROJECT" \
      secrets versions access latest --secret="$TS_SECRET")"
    # Tailscale SSH (--ssh) is intentionally OFF.
    # - Removes the dependency on a Tailscale-side ssh{} ACL block.
    # - Closes the SSH-over-Tailscale-cert side door; if SSH is needed
    #   it goes through OpenSSH (sshd.service) over the tailnet IP,
    #   authenticated by the operator's public key.
    # - Eliminates the 'Tailscale SSH enabled, but access controls
    #   don't allow anyone to access this device' warning.
    tailscale up \
      --auth-key="$AUTH_KEY" \
      --hostname="$HOSTNAME_VM" \
      --accept-routes=false \
      --advertise-tags="$TS_TAG"
    unset AUTH_KEY

    # ---- cloudflared (cloudflare apt repo) ----------------------------
    if ! command -v cloudflared >/dev/null 2>&1; then
      curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
        > /etc/apt/keyrings/cloudflare-main.gpg
      echo 'deb [signed-by=/etc/apt/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared noble main' \
        > /etc/apt/sources.list.d/cloudflared.list
      apt-get update -y
      apt-get install -y --no-install-recommends cloudflared
    fi

    install -m 0700 -d /etc/cloudflared
    gcloud --quiet --project="$PROJECT" \
      secrets versions access latest --secret="$CF_SECRET" \
      > "/etc/cloudflared/$CF_TUNNEL_ID.json"
    chmod 0600 "/etc/cloudflared/$CF_TUNNEL_ID.json"

    # The cloudflare apt package installs the binary at
    # /usr/bin/cloudflared. Resolve dynamically so a future location
    # change (or a manual /usr/local/bin override) does not silently
    # break the unit.
    CF_BIN="$(command -v cloudflared)"
    cat > /etc/systemd/system/cloudflared-exe.service <<UNIT
    [Unit]
    Description=cloudflared (exe.hironow.dev tunnel)
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    ExecStart=$CF_BIN tunnel --no-autoupdate \
      --credentials-file /etc/cloudflared/$CF_TUNNEL_ID.json \
      run $CF_TUNNEL_ID
    Restart=on-failure
    RestartSec=10
    NoNewPrivileges=true
    ProtectSystem=strict
    ProtectHome=true
    PrivateTmp=true
    ReadWritePaths=/etc/cloudflared

    [Install]
    WantedBy=multi-user.target
    UNIT
    systemctl daemon-reload
    systemctl enable --now cloudflared-exe.service
    systemctl restart cloudflared-exe.service

    # ---- Coder OSS server ---------------------------------------------
    # Coder's embedded PostgreSQL refuses to run as root, so run the
    # whole server under a dedicated system user.
    if ! id coder >/dev/null 2>&1; then
      useradd --system --home-dir /var/lib/coder --shell /usr/sbin/nologin coder
    fi
    install -m 0755 -o coder -g coder -d /var/lib/coder /var/lib/coder/cache
    if [[ ! -x /usr/local/bin/coder && ! -x /usr/bin/coder ]]; then
      # Coder's install.sh references $HOME. The root startup-script
      # process inherits no HOME, so dash exits with
      # 'HOME: parameter not set' — pin one before piping. Run without
      # extra flags ('--terraform-no-pin' is unknown to install.sh and
      # makes it exit 1).
      export HOME=/root
      curl -fsSL https://coder.com/install.sh | sh || true

      # Fallback: pull the official tar.gz release. The asset filename
      # embeds the version, so resolve it via the GitHub API. Either
      # /usr/local/bin/coder or /usr/bin/coder ends up populated.
      if [[ ! -x /usr/local/bin/coder && ! -x /usr/bin/coder ]]; then
        coder_tag="$(curl -fsSL https://api.github.com/repos/coder/coder/releases/latest \
          | jq -r .tag_name)"
        coder_ver="$${coder_tag#v}"
        curl -fsSL -o /tmp/coder.tar.gz \
          "https://github.com/coder/coder/releases/download/$${coder_tag}/coder_$${coder_ver}_linux_amd64.tar.gz"
        tar -xz -C /usr/local/bin -f /tmp/coder.tar.gz coder
        chmod 0755 /usr/local/bin/coder
        rm -f /tmp/coder.tar.gz
      fi
    fi

    # Initial admin password — generated on first boot, persisted on the
    # boot disk (which auto-deletes on tofu destroy). Change it via the
    # Coder UI after first login.
    if [[ ! -f /var/lib/coder/.admin_password ]]; then
      head -c 24 /dev/urandom | base64 | tr -d '+/=' > /var/lib/coder/.admin_password
      chmod 0600 /var/lib/coder/.admin_password
    fi
    chown -R coder:coder /var/lib/coder

    # Resolve the Coder binary location at runtime — install.sh drops
    # it at /usr/bin/coder on Debian/Ubuntu, but the fallback path is
    # /usr/local/bin/coder. Pin to whichever exists so the unit
    # cannot drift.
    CODER_BIN="$(command -v coder)"
    cat > /etc/systemd/system/coder.service <<UNIT
    [Unit]
    Description=Coder OSS server (exe.hironow.dev)
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    User=coder
    Group=coder
    Environment=HOME=/var/lib/coder
    Environment=CODER_ACCESS_URL=$CODER_ACCESS_URL
    Environment=CODER_HTTP_ADDRESS=127.0.0.1:7080
    Environment=CODER_TLS_ENABLE=false
    Environment=CODER_WILDCARD_ACCESS_URL=$CODER_WILDCARD
    Environment=CODER_PG_CONNECTION_URL=
    Environment=CODER_CACHE_DIRECTORY=/var/lib/coder/cache
    # Telemetry is OFF via the `--telemetry` CLI flag on ExecStart.
    # Coder's serpent CLI library emits a 'WARN: CODER_TELEMETRY is
    # deprecated' line whenever it parses an option that carries a
    # deprecated alias (UseInstead), even when the canonical env
    # CODER_TELEMETRY_ENABLE is the only one set. The CLI flag path
    # bypasses the env-alias warning entirely. (See
    # codersdk/deployment.go where Env:'CODER_TELEMETRY' is kept for
    # backwards compatibility with UseInstead pointing at the new
    # name.)
    Environment=CODER_DISABLE_PASSWORD_AUTH=false
    Environment=CODER_SECURE_AUTH_COOKIE=true
    Environment=CODER_STRICT_TRANSPORT_SECURITY=31536000
    Environment=CODER_STRICT_TRANSPORT_SECURITY_OPTIONS=includeSubDomains,preload
    ExecStart=$CODER_BIN server --telemetry=false
    Restart=on-failure
    RestartSec=10
    NoNewPrivileges=true
    ProtectSystem=full
    ProtectHome=false
    PrivateTmp=true
    ReadWritePaths=/var/lib/coder

    [Install]
    WantedBy=multi-user.target
    UNIT
    systemctl daemon-reload
    systemctl enable --now coder.service
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
