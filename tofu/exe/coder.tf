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
    PROJECT='${var.gcp_project_id}'
    CODER_ACCESS_URL='https://${local.coder_host}'
    CODER_WILDCARD='${local.sandbox_host}'
    TS_TAG='${local.tag_exe_coder}'
    CSAP_VERSION='${var.cloud_sql_proxy_version}'
    CSAP_SHA256='${var.cloud_sql_proxy_sha256}'
    CSAP_URL='${local.cloud_sql_proxy_url}'
    PG_CONNECTION_NAME='${local.cloud_sql_connection_name}'
    PG_IAM_DB_USER='${local.cloud_sql_iam_db_user}'
    PG_OPERATOR_DB_USER='${local.cloud_sql_operator_db_user}'
    PG_PRIVATE_IP='${local.cloud_sql_private_ip}'
    PG_ADMIN_SECRET='${google_secret_manager_secret.postgres_admin.secret_id}'

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

      # Extract via temp dir + install. The Coder release tarball stores
      # all members with a leading "./" prefix (./coder, ./LICENSE, ...).
      # GNU tar (Ubuntu 24.04 host) treats `tar -x ... coder` as an exact
      # member-name match and fails with "Not found in archive" because
      # the actual member is `./coder`. BSD tar normalizes the leading
      # `./` so this only surfaces on the live VM, not on dev macs.
      # Extracting to a temp dir + `install` is robust against future
      # tarball layout changes (sub-directory, prefix tweaks) without
      # tracking the specific member name.
      coder_extract_dir="/tmp/coder-extract"
      rm -rf "$${coder_extract_dir}"
      mkdir -p "$${coder_extract_dir}"
      tar -xz -C "$${coder_extract_dir}" -f /tmp/$${coder_tarball}
      install -m 0755 "$${coder_extract_dir}/coder" /usr/local/bin/coder
      rm -rf "$${coder_extract_dir}" /tmp/$${coder_tarball}
    fi

    # ---- Cloud SQL Auth Proxy v2 (ADR 0010) ----------------------------
    # The Coder server reaches the managed Postgres via CSAP listening
    # on 127.0.0.1:5432. CSAP authenticates to Cloud SQL using the VM
    # SA's roles/cloudsql.client. Pinned by version + sha256 mirror of
    # the ADR 0007 hardening pattern.
    if [[ ! -x /usr/local/bin/cloud-sql-proxy ]]; then
      curl -fsSL --proto '=https' --tlsv1.2 \
        -o /tmp/cloud-sql-proxy "$CSAP_URL"
      echo "$CSAP_SHA256  /tmp/cloud-sql-proxy" | sha256sum -c -
      install -m 0755 /tmp/cloud-sql-proxy /usr/local/bin/cloud-sql-proxy
      rm -f /tmp/cloud-sql-proxy
    fi

    cat > /etc/systemd/system/cloud-sql-proxy.service <<UNIT
    [Unit]
    Description=Cloud SQL Auth Proxy (Coder data plane, ADR 0010)
    After=network-online.target
    Wants=network-online.target
    Before=coder.service

    [Service]
    Type=simple
    User=coder
    Group=coder
    Environment=HOME=/var/lib/coder
    # --auto-iam-authn=true: CSAP fetches a short-lived OAuth access
    # token from the VM metadata server and injects it as the
    # Postgres password at every connection. The "password" Coder
    # sends in its connection URL is ignored (and is set to a
    # placeholder; see /etc/default/coder).
    # --private-ip: the Cloud SQL instance has ipv4_enabled=false
    # (private IP only). Without this flag CSAP tries the public
    # IP path first and fails with `instance does not have IP of
    # type "PUBLIC"`.
    # --structured-logs: emit JSON lines instead of free text. journald
    # + Cloud Logging can then key on severity/error/message fields
    # for alerting rather than substring matching the message body.
    # --health-check + --http-address=127.0.0.1: expose
    # /startup, /readiness, /liveness on loopback :9090 so an
    # external watchdog (or ExecStartPre on coder.service) can probe
    # actual proxy readiness instead of just the systemd main-PID
    # state. Loopback-only so the endpoints are not reachable from
    # the tailnet IP.
    ExecStart=/usr/local/bin/cloud-sql-proxy \
      --address 127.0.0.1 --port 5432 \
      --auto-iam-authn \
      --private-ip \
      --structured-logs \
      --health-check \
      --http-address=127.0.0.1 \
      $PG_CONNECTION_NAME
    Restart=on-failure
    RestartSec=5
    NoNewPrivileges=true
    ProtectSystem=full
    ProtectHome=true
    PrivateTmp=true

    [Install]
    WantedBy=multi-user.target
    UNIT
    systemctl daemon-reload
    systemctl enable --now cloud-sql-proxy.service

    # Initial admin password — generated on first boot, persisted on the
    # boot disk (which auto-deletes on tofu destroy). Change it via the
    # Coder UI after first login.
    if [[ ! -f /var/lib/coder/.admin_password ]]; then
      head -c 24 /dev/urandom | base64 | tr -d '+/=' > /var/lib/coder/.admin_password
      chmod 0600 /var/lib/coder/.admin_password
    fi

    # ---- One-time IAM user privilege bootstrap ------------------------
    # Postgres 15+ locks down the public schema by default — newly-
    # created IAM SA users cannot CREATE TABLE there until a
    # cloudsqlsuperuser-privileged role grants USAGE + CREATE on
    # public. Coder's first migration fails closed without this,
    # looping at "permission denied for schema public".
    #
    # Cloud SQL's `postgres` BUILT_IN superuser does the grant once.
    # Connection goes via the Cloud SQL private IP directly (10.x.x.x)
    # rather than through CSAP, because CSAP runs with
    # --auto-iam-authn and would substitute an OAuth token for the
    # postgres password. sslmode=require encrypts the connection
    # without strict cert verification (sufficient inside the
    # peered VPC).
    #
    # Idempotent: the GRANTs are no-ops on repeat. We always re-run
    # so a future variable bump that re-applies the grants stays
    # truthful — there is no marker file to inspect.
    if ! command -v psql >/dev/null 2>&1; then
      apt-get install -y --no-install-recommends postgresql-client
    fi

    PG_ADMIN_PASSWORD="$(gcloud --quiet --project="$PROJECT" \
      secrets versions access latest --secret="$PG_ADMIN_SECRET")"

    # Wait up to 60s for Cloud SQL to accept connections (in case the
    # VM came up before the DB engine finished its own bootstrap).
    for i in $(seq 1 30); do
      if PGPASSWORD="$PG_ADMIN_PASSWORD" psql \
            "host=$PG_PRIVATE_IP port=5432 user=postgres dbname=coder sslmode=require connect_timeout=5" \
            -c '\q' 2>/dev/null; then
        break
      fi
      sleep 2
    done

    # Run the privilege bootstrap. ON_ERROR_STOP=1 makes psql exit
    # non-zero if any GRANT fails; we capture the rc but do not
    # abort the script — coder.service will surface the symptom on
    # its own next start if the bootstrap was insufficient.
    PGPASSWORD="$PG_ADMIN_PASSWORD" psql \
      "host=$PG_PRIVATE_IP port=5432 user=postgres dbname=coder sslmode=require" \
      --set ON_ERROR_STOP=1 <<SQL
    GRANT CONNECT ON DATABASE coder TO "$PG_IAM_DB_USER";
    GRANT USAGE, CREATE ON SCHEMA public TO "$PG_IAM_DB_USER";
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "$PG_IAM_DB_USER";
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "$PG_IAM_DB_USER";
    -- Operator IAM DB user — read-only audit via Cloud SQL Studio.
    --
    -- Why pg_read_all_data instead of table-level GRANTs: the script
    -- runs as the postgres BUILT_IN user (Cloud SQL's
    -- cloudsqlsuperuser). cloudsqlsuperuser is NOT a Postgres
    -- superuser and therefore cannot GRANT SELECT on tables owned by
    -- another role. Coder's migrations create every table as
    -- $PG_IAM_DB_USER, so a 'GRANT SELECT ON ALL TABLES IN SCHEMA
    -- public TO operator' issued from postgres errors out with
    -- 'permission denied for table schema_migrations' — and with
    -- ON_ERROR_STOP=1, that aborts the rest of startup_script,
    -- breaking the subsequent /etc/default/coder + coder.service
    -- writes (real prod outage 2026-05-04).
    --
    -- The fix: grant the predefined role pg_read_all_data
    -- (Postgres 14+, available on Cloud SQL Postgres 16). It
    -- automatically confers SELECT and USAGE on every relation
    -- regardless of owner, no per-table maintenance, and crucially
    -- it can be granted by cloudsqlsuperuser via role membership
    -- (which it CAN do, unlike per-table GRANT).
    --
    -- Posture remains the same: read-only. pg_read_all_data has no
    -- write privilege built in; CONNECT is granted separately so
    -- the operator can open the database in the first place.
    GRANT CONNECT ON DATABASE coder TO "$PG_OPERATOR_DB_USER";
    GRANT pg_read_all_data TO "$PG_OPERATOR_DB_USER";
    SQL
    unset PG_ADMIN_PASSWORD

    # /etc/default/coder — holds CODER_PG_CONNECTION_URL. The "password"
    # is a literal placeholder string: with --auto-iam-authn the proxy
    # ignores whatever Coder sends and substitutes a fresh OAuth access
    # token from the VM metadata server. The username is the IAM SA
    # user provisioned in cloudsql.tf, URL-encoded so the '@' in the
    # email does not collide with the URL grammar.
    #
    # File mode is 0640 root:coder for consistency with the rest of the
    # systemd ecosystem (logs, state) — the URL itself contains no
    # secret material here. The Coder UI still reads the URL via
    # `coder.service`'s EnvironmentFile=.
    PG_IAM_DB_USER_ENC="$(printf '%s' "$PG_IAM_DB_USER" | sed 's/@/%40/g')"
    install -m 0640 -o root -g coder /dev/null /etc/default/coder
    cat > /etc/default/coder <<DEFAULTS
    CODER_PG_CONNECTION_URL=postgres://$PG_IAM_DB_USER_ENC:placeholder@127.0.0.1:5432/coder?sslmode=disable
    DEFAULTS
    chmod 0640 /etc/default/coder
    chown root:coder /etc/default/coder

    chown -R coder:coder /var/lib/coder

    # Resolve the Coder binary location at runtime — install.sh drops
    # it at /usr/bin/coder on Debian/Ubuntu, but the fallback path is
    # /usr/local/bin/coder. Pin to whichever exists so the unit
    # cannot drift.
    CODER_BIN="$(command -v coder)"
    cat > /etc/systemd/system/coder.service <<UNIT
    [Unit]
    Description=Coder OSS server (exe.hironow.dev)
    After=network-online.target cloud-sql-proxy.service
    Wants=network-online.target
    Requires=cloud-sql-proxy.service

    [Service]
    Type=simple
    User=coder
    Group=coder
    # /etc/default/coder holds CODER_PG_CONNECTION_URL with the live
    # Postgres password (mode 0640, root:coder). Sourced FIRST so any
    # Environment= line below can override individual values for
    # debugging. The leading dash makes the file optional so
    # systemd-analyze verify on a clean container does not warn.
    EnvironmentFile=-/etc/default/coder
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
    # CODER_PG_CONNECTION_URL is set via EnvironmentFile=/etc/default/coder
    # (ADR 0010). Keeping no Environment= line here so EnvironmentFile is
    # the unambiguous source of the value.
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
    # ADR 0010: VM startup_script connects to Cloud SQL via CSAP using
    # IAM database authentication. Force ordering so the IAM DB user +
    # SA roles + DB are all ready before the VM tries to bootstrap.
    google_project_iam_member.exe_coder_cloudsql_client,
    google_project_iam_member.exe_coder_cloudsql_instance_user,
    google_sql_user.coder_iam,
    google_sql_user.operator_iam,
    google_sql_database.coder,
    # The privilege-bootstrap path needs the postgres BUILT_IN user
    # password + Secret Manager grant in place before the VM boots
    # (script fetches the password from the secret and uses psql to
    # grant the IAM user CREATE on public schema).
    google_sql_user.postgres,
    google_secret_manager_secret_version.postgres_admin,
    google_secret_manager_secret_iam_member.postgres_admin_reader,
  ]
}
