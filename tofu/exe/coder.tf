# GCE workspace VM that hosts the Coder server. Coder workspaces
# spawned from this server pick up .devcontainer/devcontainer.json
# from the cloned dotfiles repo via envbuilder, so the workspace
# image stays in sync with what local IDE / CI build.
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

# Service account stamped on Coder workspace VMs (the per-workspace
# google_compute_instance.vm in the dotfiles-devcontainer template).
# Carries the minimum permissions needed at boot:
#   - read tag:exe-workspace tailnet authkey from Secret Manager
# A dedicated SA (rather than reusing the project default compute SA)
# keeps the Secret Manager grant scoped to this stack — the default SA
# is project-wide and would extend the read permission to every other
# workload running under it.
resource "google_service_account" "exe_workspace" {
  account_id   = "${local.prefix}-workspace"
  display_name = "exe Coder workspace VM"
  description  = "Service account for Coder workspace VMs (managed by tofu)."
}

resource "google_secret_manager_secret_iam_member" "exe_workspace_authkey_reader" {
  secret_id = google_secret_manager_secret.exe_workspace_authkey.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.exe_workspace.email}"
}

# Logs/metrics so a preempted workspace VM still leaves a trail.
resource "google_project_iam_member" "exe_workspace_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.exe_workspace.email}"
}

resource "google_project_iam_member" "exe_workspace_metric_writer" {
  project = var.gcp_project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.exe_workspace.email}"
}

resource "google_secret_manager_secret_iam_member" "exe_coder_authkey_reader" {
  secret_id = google_secret_manager_secret.exe_coder_authkey.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.exe_coder.email}"
}

# TF_ENCRYPTION passphrase used by cron jobs that read the exe stack's
# tofu state (e.g. nightly `tofu plan` per ADR 0008 step 4). The
# passphrase value is operator-generated at bootstrap (lives at
# ~/.config/tofu/exe.passphrase on the operator's Mac) and uploaded
# here once after `just exe-apply`:
#
#   gcloud secrets versions add exe-tofu-encryption-passphrase \
#     --project=gen-ai-hironow \
#     --data-file=$HOME/.config/tofu/exe.passphrase
#
# Tofu owns only the secret shell + IAM grant; the value stays
# operator-managed (re-uploading is the rotation path). Without a
# version, the cron job fails closed with a runbook pointer.
resource "google_secret_manager_secret" "exe_tofu_encryption_passphrase" {
  secret_id = "${local.prefix}-tofu-encryption-passphrase"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "exe_tofu_encryption_passphrase_reader" {
  secret_id = google_secret_manager_secret.exe_tofu_encryption_passphrase.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.exe_workspace.email}"
}

# Workspace SA → state bucket. Required so cron jobs that spawn
# ephemeral workspaces can read the encrypted state and ship plan
# artifacts to gs://<project>-tofu-state/jobs/<date>/. The bucket
# itself lives outside tofu (created by exe/scripts/bootstrap.sh),
# so the IAM grant is on the bucket name (resolved from local).
resource "google_storage_bucket_iam_member" "exe_workspace_state_bucket_admin" {
  bucket = local.state_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.exe_workspace.email}"
}

# Coder admin token used by the Coder VM's local cron (systemd timer)
# to call the Coder API on http://127.0.0.1:7080. Tofu creates the
# Secret Manager *shell* only; the operator populates the value AFTER
# the first `tofu apply` via:
#
#   coder login https://exe.hironow.dev   # via cdr / browser
#   coder tokens create --lifetime 720h --name cron \
#     | gcloud secrets versions add exe-coder-admin-token \
#         --project=gen-ai-hironow --data-file=-
#
# Until the operator does this, /usr/local/bin/coder-cron-run exits
# with a clear error (no version → gcloud returns NOT_FOUND). The
# coder-cron-heartbeat.timer that ships with this commit deliberately
# does NOT call coder-cron-run — it only uses /usr/bin/logger so the
# timer mechanism can be smoke-validated before the operator wires up
# any real cron job. See ADR 0008 Step 3 + exe/docs/runbook.md.
resource "google_secret_manager_secret" "exe_coder_admin_token" {
  secret_id = "${local.prefix}-coder-admin-token"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "exe_coder_admin_token_reader" {
  secret_id = google_secret_manager_secret.exe_coder_admin_token.id
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

# Coder server runs templates inside its embedded Terraform; the
# templates create per-workspace GCE VMs and disks under THIS SA.
# Without compute.instanceAdmin the very first 'terraform plan' on
# the dotfiles-devcontainer template fails on the
# 'google_compute_default_service_account' data read with:
#
#   Error 403: Required 'compute.projects.get' permission for
#   'projects/gen-ai-hironow', forbidden
#
# Granting compute.instanceAdmin.v1 lets the SA read project
# metadata and create / start / stop / delete VMs + disks.
# iam.serviceAccountUser lets it assign the default compute SA
# (the workspace runtime identity) to the new VMs.
#
# Trade-off (acknowledged): exe_coder is now a workspace lifecycle
# admin for this project. Acceptable for a single-tenant personal
# stack; in a multi-team Coder, a separate workspace-provisioner SA
# is the right answer.
resource "google_project_iam_member" "exe_coder_instance_admin" {
  project = var.gcp_project_id
  role    = "roles/compute.instanceAdmin.v1"
  member  = "serviceAccount:${google_service_account.exe_coder.email}"
}

resource "google_project_iam_member" "exe_coder_sa_user" {
  project = var.gcp_project_id
  role    = "roles/iam.serviceAccountUser"
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
    ADMIN_TOKEN_SECRET='${google_secret_manager_secret.exe_coder_admin_token.secret_id}'
    PROJECT='${var.gcp_project_id}'
    CODER_ACCESS_URL='https://${local.coder_host}'
    CODER_WILDCARD='${local.sandbox_host}'
    TS_TAG='${local.tag_exe_coder}'

    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends \
      apt-transport-https ca-certificates curl gnupg lsb-release jq

    # Helper: import an apt-repo GPG key only after verifying its
    # fingerprint. Without the pin a TOFU fetch from the same TLS
    # endpoint that distributes the package would let a compromised
    # mirror swap key + package in lock-step. Mirrors the helper at
    # .devcontainer/features/dotfiles-tools/install.sh and the
    # workspace template (post-PR #57). Positional args avoid bash
    # $${var} that would conflict with terraform heredoc interpolation.
    import_apt_key_with_fingerprint() {
      # args: <url> <expected-fingerprint> <output-keyring-path>
      rm -f /tmp/exe-apt-key.armored /tmp/exe-apt-key.gpg
      curl -fsSL -o /tmp/exe-apt-key.armored "$1"
      gpg --no-default-keyring --keyring /tmp/exe-apt-key.gpg \
        --import /tmp/exe-apt-key.armored 2>/dev/null
      actual=$(gpg --no-default-keyring --keyring /tmp/exe-apt-key.gpg \
        --list-keys --with-colons | awk -F: '/^fpr:/ { print $10; exit }')
      if [ "$actual" != "$2" ]; then
        echo "[coder-bootstrap] GPG fingerprint mismatch for $1" >&2
        echo "  expected: $2" >&2
        echo "  actual:   $actual" >&2
        rm -f /tmp/exe-apt-key.armored /tmp/exe-apt-key.gpg
        exit 1
      fi
      install -m 0644 /tmp/exe-apt-key.gpg "$3"
      rm -f /tmp/exe-apt-key.armored /tmp/exe-apt-key.gpg
    }

    # ---- Google Cloud CLI (Ubuntu noble) ------------------------------
    # Fingerprint published by Google at
    # https://cloud.google.com/sdk/docs/install#deb. Operator-verified
    # at PR #53 time and reused here.
    if ! command -v gcloud >/dev/null 2>&1; then
      install -m 0755 -d /etc/apt/keyrings
      import_apt_key_with_fingerprint \
        https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3 \
        /etc/apt/keyrings/cloud.google.gpg
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
    #
    # Fingerprint pin: Tailscale does not officially publish the
    # apt-key fingerprint as of 2026-05 (see github.com/tailscale/tailscale/issues/15221).
    # The value below is observed via dnf/rpm signature verification and
    # was operator-verified against the live noble.noarmor.gpg endpoint.
    # The 8-byte suffix matches the NO_PUBKEY error documented above.
    if ! command -v tailscale >/dev/null 2>&1; then
      install -m 0755 -d /usr/share/keyrings
      import_apt_key_with_fingerprint \
        https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg \
        2596A99EAAB33821893C0A79458CA832957F5868 \
        /usr/share/keyrings/tailscale-archive-keyring.gpg
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
    if [[ ! -x /usr/local/bin/coder ]]; then
      # Per ADR 0007 (Coder server install hardening): pinned-tag
      # tarball install with sha256 verification. The previous
      # piped-shell convenience installer and the GitHub-API
      # latest-resolution fallback have both been removed; any
      # failure in the steps below aborts the startup-script and
      # the VM provisioning fails fast — preferable to coming up
      # with an unverified or absent Coder binary.
      coder_tag='${var.coder_version}'
      coder_ver="$${coder_tag#v}"
      coder_sha256='${var.coder_sha256}'
      coder_tarball="coder_$${coder_ver}_linux_amd64.tar.gz"
      coder_url="https://github.com/coder/coder/releases/download/$${coder_tag}/$${coder_tarball}"

      curl -fsSL --proto '=https' --tlsv1.2 \
        -o /tmp/$${coder_tarball} "$${coder_url}"
      echo "$${coder_sha256}  /tmp/$${coder_tarball}" \
        | sha256sum -c -

      # Defense in depth: if gh is installed and authenticated on
      # the VM, verify the SLSA provenance attestation BEFORE the
      # tarball is consumed. Best-effort — the sha256 pin above is
      # the primary integrity check. Mirrors the pattern used in
      # .devcontainer/features/dotfiles-tools/install.sh for uv.
      if command -v gh >/dev/null 2>&1 && \
         { [ -n "$${GH_TOKEN:-}" ] || [ -n "$${GITHUB_TOKEN:-}" ] || \
           gh auth status >/dev/null 2>&1; }; then
        gh attestation verify "/tmp/$${coder_tarball}" \
          --repo coder/coder >/dev/null 2>&1 || \
          echo "[coder-bootstrap] gh attestation verify failed (sha256 still in force)" >&2
      fi

      tar -xz -C /usr/local/bin -f /tmp/$${coder_tarball} coder
      chmod 0755 /usr/local/bin/coder
      rm -f /tmp/$${coder_tarball}
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
    # Listen on all interfaces, not loopback only. cloudflared still
    # reaches the server on 127.0.0.1:7080 for the public path; the
    # tailnet IP (tun0) is what workspace VMs use to fetch
    # /bin/coder-linux-amd64 and run the agent <-> server protocol
    # without going through the public CF Access edge. The
    # deny-all-ingress firewall keeps the GCE public IP blocked at L3,
    # so the only sources that can dial 0.0.0.0:7080 are localhost
    # (cloudflared) and the tailnet (peers permitted by ACL rule
    # tag:exe-workspace -> tag:exe-coder:7080).
    Environment=CODER_HTTP_ADDRESS=0.0.0.0:7080
    Environment=CODER_TLS_ENABLE=false
    Environment=CODER_WILDCARD_ACCESS_URL=$CODER_WILDCARD
    Environment=CODER_PG_CONNECTION_URL=
    Environment=CODER_CACHE_DIRECTORY=/var/lib/coder/cache
    Environment=CODER_TELEMETRY_ENABLE=false
    Environment=CODER_DISABLE_PASSWORD_AUTH=false
    Environment=CODER_SECURE_AUTH_COOKIE=true
    Environment=CODER_STRICT_TRANSPORT_SECURITY=31536000
    Environment=CODER_STRICT_TRANSPORT_SECURITY_OPTIONS=includeSubDomains,preload
    # Telemetry is OFF via CODER_TELEMETRY_ENABLE=false above.
    # Coder's serpent CLI library still emits 'WARN: CODER_TELEMETRY
    # is deprecated' at boot — that is upstream noise (telemetry is in
    # fact disabled; see the 'telemetry disabled, unable to notify of
    # security issues' journal line). Accept the noise; switching to
    # the --telemetry CLI flag yielded a different deprecation warning
    # and additionally tripped a heredoc-related 'command not found'
    # in Cloud's metadata-script-runner. See runbook.md.
    ExecStart=$CODER_BIN server
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

    # ---- ADR 0008 step 3: systemd timer scaffolding ------------------
    # Two pieces ship together but serve different purposes:
    #
    #   1. /usr/local/bin/coder-cron-run — helper any future systemd
    #      .service unit can invoke to call the local Coder API
    #      (http://127.0.0.1:7080) authenticated with the admin token
    #      from Secret Manager. Operator must populate the secret
    #      version after first apply (see runbook). Until then, calling
    #      the helper exits 65 with a clear pointer to the runbook.
    #
    #   2. coder-cron-heartbeat.service + .timer — pure-logger one-liner
    #      that fires daily and writes to journald. Smoke validation
    #      that the systemd timer mechanism itself works without
    #      depending on the operator-side admin token setup. To inspect
    #      on the VM:    journalctl -u coder-cron-heartbeat --since today
    #
    # Real cron jobs (tofu plan, lint, agent task) land in step 4 as
    # additional .timer + .service units that DO call coder-cron-run.

    # /etc/default/coder-cron — env file consumed by the helper. Keeps
    # the secret name + project out of the helper's source so the
    # helper itself is operator-readable plain bash.
    cat > /etc/default/coder-cron <<DEFAULTS
    CODER_CRON_SECRET_NAME=$ADMIN_TOKEN_SECRET
    CODER_CRON_PROJECT=$PROJECT
    DEFAULTS
    chmod 0644 /etc/default/coder-cron

    # /usr/local/bin/coder-cron-run — quoted heredoc so the inner
    # bash variables (\$#, \$@, \$CODER_CRON_*) stay literal.
    cat > /usr/local/bin/coder-cron-run <<'HELPER'
    #!/usr/bin/env bash
    # coder-cron-run — call the local Coder API from this VM with a
    # short-lived admin token fetched from Secret Manager.
    #
    # Usage:
    #   coder-cron-run <coder-cli-args...>
    #
    # Reads CODER_CRON_SECRET_NAME and CODER_CRON_PROJECT from
    # /etc/default/coder-cron (set by tofu/exe/coder.tf startup_script
    # at VM bootstrap). The admin token itself is created by the
    # operator after first apply with `coder tokens create` and
    # uploaded as a new Secret Manager version. See runbook.
    set -euo pipefail

    if [ "$#" -lt 1 ]; then
      echo "usage: coder-cron-run <coder-cli-args...>" >&2
      exit 64
    fi

    if [ -r /etc/default/coder-cron ]; then
      # shellcheck disable=SC1091
      . /etc/default/coder-cron
    fi
    : "$${CODER_CRON_SECRET_NAME:?CODER_CRON_SECRET_NAME is unset; check /etc/default/coder-cron}"
    : "$${CODER_CRON_PROJECT:?CODER_CRON_PROJECT is unset; check /etc/default/coder-cron}"

    if ! CODER_SESSION_TOKEN="$(gcloud --quiet \
          --project="$CODER_CRON_PROJECT" \
          secrets versions access latest \
          --secret="$CODER_CRON_SECRET_NAME" 2>/dev/null)"; then
      echo "[coder-cron-run] failed to fetch Coder admin token from Secret Manager." >&2
      echo "[coder-cron-run] Operator action: see exe/docs/runbook.md" >&2
      echo "[coder-cron-run] section 'Coder admin token for cron'." >&2
      exit 65
    fi
    export CODER_SESSION_TOKEN
    export CODER_URL='http://127.0.0.1:7080'

    exec coder "$@"
    HELPER
    chmod 0755 /usr/local/bin/coder-cron-run

    # coder-cron-heartbeat.service — one-shot logger; no Coder API
    # call. Proves the timer fires; journald keeps the trail.
    cat > /etc/systemd/system/coder-cron-heartbeat.service <<UNIT
    [Unit]
    Description=coder-cron heartbeat (ADR 0008 step 3 smoke)
    After=network-online.target

    [Service]
    Type=oneshot
    ExecStart=/usr/bin/logger -t coder-cron-heartbeat -- tick
    NoNewPrivileges=true
    ProtectSystem=full
    ProtectHome=true
    PrivateTmp=true
    UNIT

    # coder-cron-heartbeat.timer — daily at 09:17 UTC with up to 5 min
    # of jitter. The off-the-hour minute (17 not 00) avoids cron
    # thundering-herd; Persistent=true means a missed run after VM
    # reboot still fires once on the next boot.
    cat > /etc/systemd/system/coder-cron-heartbeat.timer <<UNIT
    [Unit]
    Description=Run coder-cron-heartbeat daily (ADR 0008 step 3)

    [Timer]
    OnCalendar=*-*-* 09:17:00 UTC
    Persistent=true
    RandomizedDelaySec=300
    Unit=coder-cron-heartbeat.service

    [Install]
    WantedBy=timers.target
    UNIT

    systemctl daemon-reload
    systemctl enable --now coder-cron-heartbeat.timer

    # ---- ADR 0008 step 4: nightly tofu-plan cron --------------------
    # First real cron use case (after the heartbeat smoke). Spawns an
    # ephemeral dotfiles-job workspace whose job_command runs
    # exe/scripts/cron-tofu-plan.sh from the cloned dotfiles repo.
    # Plan artifacts ship to gs://<project>-tofu-state/jobs/<date>/.
    #
    # Three new pieces:
    #   1. /usr/local/bin/coder-cron-spawn-job — VM-side analog of
    #      cdr-job: generates a unique workspace name, calls
    #      coder-cron-run create, polls until the agent reports
    #      ready, then deletes. Trap-handler delete on failure.
    #   2. coder-cron-tofu-plan.service — calls the spawn-job
    #      wrapper with a one-liner that clones dotfiles + execs
    #      the cron-tofu-plan.sh script.
    #   3. coder-cron-tofu-plan.timer — fires daily at 04:23 UTC
    #      (off-the-hour minute, Persistent=true,
    #      RandomizedDelaySec=600) so it runs while the operator is
    #      typically asleep and out of contention with morning use.

    cat > /usr/local/bin/coder-cron-spawn-job <<'SPAWN'
    #!/usr/bin/env bash
    # coder-cron-spawn-job — spawn an ephemeral exe-dotfiles-job
    # workspace from the Coder VM, wait for the agent's startup_script
    # (which IS the job) to finish, then delete the workspace.
    #
    # Usage:
    #   coder-cron-spawn-job <name-prefix> <single-shell-command-string>
    #
    # The command MUST be a single argument (use bash -c '...' or
    # explicit quoting to construct it from systemd ExecStart). The
    # prefix is suffixed with -YYYYMMDD-HHMMSS to keep workspace names
    # unique across runs. Workspace teardown happens in a trap handler
    # so SIGTERM / failure still reaps the VM. Template-level
    # default_ttl_ms + dormancy_threshold_ms remain the secondary +
    # tertiary safety nets per ADR 0008.
    set -euo pipefail

    err() { printf '[coder-cron-spawn-job] ERROR: %s\n' "$*" >&2; exit 1; }
    log() { printf '[coder-cron-spawn-job] %s\n' "$*" >&2; }

    if [ "$#" -ne 2 ]; then
      err "usage: coder-cron-spawn-job <name-prefix> <single-command-string>"
    fi

    SPAWN_TIMEOUT_SEC="$${CODER_CRON_SPAWN_TIMEOUT_SEC:-3600}" # 60 min

    PREFIX="$1"
    JOB_COMMAND="$2"
    if ! [[ "$PREFIX" =~ ^[a-z0-9-]+$ ]]; then
      err "name-prefix must match [a-z0-9-]+ (got: $PREFIX)"
    fi
    NAME="$${PREFIX}-$(date -u +%Y%m%d-%H%M%S)"

    cleanup() {
      local rc=$?
      log "tearing down workspace '$NAME' (rc=$rc)"
      coder-cron-run delete "$NAME" --yes >/dev/null 2>&1 || true
    }
    trap cleanup EXIT

    log "creating workspace '$NAME' from template exe-dotfiles-job"
    coder-cron-run create "$NAME" \
      --template exe-dotfiles-job \
      --parameter "job_command=$${JOB_COMMAND}" \
      --yes

    log "polling agent state (timeout $${SPAWN_TIMEOUT_SEC}s)"
    START_TS=$(date +%s)
    while true; do
      STATUS_JSON="$(coder-cron-run show "$NAME" --output json 2>/dev/null || echo '{}')"
      AGENT_STATE="$(jq -r '.latest_build.resources[]?.agents[]?.lifecycle_state // empty' \
        <<<"$STATUS_JSON" | head -1)"

      case "$AGENT_STATE" in
        ready)
          log "agent state=ready (startup_script finished); tearing down"
          break
          ;;
        starting|created|"") ;;
        start_timeout|start_error|shutdown_timeout|shutdown_error|off)
          log "agent reached terminal state: $AGENT_STATE"
          break
          ;;
      esac

      NOW=$(date +%s)
      if (( NOW - START_TS >= SPAWN_TIMEOUT_SEC )); then
        log "wall-clock budget exceeded ($${SPAWN_TIMEOUT_SEC}s); aborting"
        exit 124
      fi
      sleep 10
    done

    log "job '$NAME' completed; trap will delete the workspace"
    SPAWN
    chmod 0755 /usr/local/bin/coder-cron-spawn-job

    cat > /etc/systemd/system/coder-cron-tofu-plan.service <<'UNIT'
    [Unit]
    Description=Nightly tofu plan via ephemeral Coder workspace (ADR 0008 step 4)
    After=network-online.target coder.service
    Wants=network-online.target

    [Service]
    Type=oneshot
    EnvironmentFile=/etc/default/coder-cron
    # systemd ExecStart does NOT interpret shell metacharacters, so
    # the multi-step job goes through /bin/bash -c. Inside, the
    # second arg to coder-cron-spawn-job is the single shell-string
    # the workspace agent will exec via sh -c '...' once cloned.
    ExecStart=/bin/bash -c '/usr/local/bin/coder-cron-spawn-job tofu-plan "git clone --depth 1 https://github.com/hironow/dotfiles.git /root/dotfiles && bash /root/dotfiles/exe/scripts/cron-tofu-plan.sh"'
    NoNewPrivileges=true
    ProtectSystem=full
    ProtectHome=true
    PrivateTmp=true
    UNIT

    cat > /etc/systemd/system/coder-cron-tofu-plan.timer <<UNIT
    [Unit]
    Description=Run nightly tofu plan (ADR 0008 step 4)

    [Timer]
    OnCalendar=*-*-* 04:23:00 UTC
    Persistent=true
    RandomizedDelaySec=600
    Unit=coder-cron-tofu-plan.service

    [Install]
    WantedBy=timers.target
    UNIT

    systemctl daemon-reload
    # Enabled on every boot; safe because each fire spawns a fresh
    # workspace and the spawn-job wrapper traps teardown.
    systemctl enable --now coder-cron-tofu-plan.timer
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
