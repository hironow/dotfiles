# exe.hironow.dev workspace template — dotfiles devcontainer (prebuilt image).
#
# Adapted from coder/coder examples/templates/gcp-vm-container.
# Differences from upstream:
#   - default project_id   = gen-ai-hironow
#   - default region       = asia (us+europe upstream)
#   - workspace VM is debian-12 (not COS) so apt-installed tailscaled
#                            can run on the host and the workspace
#                            container can reach exe-coder over the
#                            tailnet — see B-plan in
#                            docs/handover.md / docs/adr/0001.
#   - prebuilt container image pulled from Artifact Registry; built
#                            and pushed by the publish-devcontainer
#                            workflow on each main merge. envbuilder
#                            is no longer in the path
#                            (docs/adr/0002-coder-prebuilt-image.md).
#   - dotfiles_uri parameter retained — `coder dotfiles` still runs
#                            the operator's personalisation on top
#                            of the baked-in image.
#
# Push:
#   cdr templates push exe-dotfiles-devcontainer \
#     -d exe/coder/templates/dotfiles-devcontainer \
#     --variable project_id=gen-ai-hironow \
#     --variable workspace_sa_email=$(just exe-output -raw exe_workspace_sa_email) \
#     --variable coder_internal_url=$(just exe-output -raw coder_internal_url) \
#     --variable image=$(just exe-output -raw artifact_registry_repo)/devcontainer:main
#
# Create a workspace:
#   cdr create my-ws --template exe-dotfiles-devcontainer

terraform {
  required_providers {
    coder = {
      source = "coder/coder"
    }
    google = {
      source = "hashicorp/google"
    }
  }
}

# url overrides the deployment-wide CODER_ACCESS_URL on the workspace
# side: every interpolation of `${ACCESS_URL}` in the bootstrap shell
# script (most importantly the BINARY_URL the workspace VM uses to
# fetch `/bin/coder-linux-amd64`) is rendered from this value, not
# from the public URL. Pointed at the tailnet-internal endpoint so
# the download bypasses the public CF Access edge — workspaces have
# no service token and would otherwise receive the OIDC interstitial
# HTML instead of the binary.
provider "coder" {
  url = var.coder_internal_url
}

# Provider-level zone is fixed to the stack's home zone so the
# template-push preview plan can resolve a non-empty string. The
# 'gcp_region' Coder parameter still drives the *workspace* zone
# per-resource (see google_compute_instance.vm.zone).
provider "google" {
  region  = "asia-northeast1"
  zone    = "asia-northeast1-a"
  project = var.project_id
}

data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

variable "project_id" {
  description = "GCP project hosting the workspace VMs. Stack default."
  type        = string
  default     = "gen-ai-hironow"
}

variable "coder_internal_url" {
  description = <<-EOF
URL workspaces use to reach the Coder server (agent binary download +
agent-server protocol). Resolved over MagicDNS on the tailnet so this
is typically 'http://exe-coder:7080'. Operator stack exports it as
the 'coder_internal_url' tofu output; pass via:
  cdr templates push --variable coder_internal_url=$(just exe-output coder_internal_url)
EOF
  type        = string
  default     = "http://exe-coder:7080"
}

variable "workspace_sa_email" {
  description = <<-EOF
Service account email stamped on every workspace VM. Must have
roles/secretmanager.secretAccessor on the tag:exe-workspace tailnet
authkey secret AND roles/artifactregistry.reader on the dotfiles
Artifact Registry repo. Operator stack exports it as
'exe_workspace_sa_email'.
EOF
  type        = string
}

variable "workspace_authkey_secret_id" {
  description = <<-EOF
Bare Secret Manager secret_id (no project prefix) holding the
tag:exe-workspace tailnet authkey. The startup-script reads it via
'gcloud secrets versions access latest --secret=...'. Operator stack
exports it as 'tailscale_secret_workspace_id'.
EOF
  type        = string
  default     = "exe-tailscale-workspace-authkey"
}

variable "image" {
  description = <<-EOF
OCI image reference the workspace runs as its dev container. Built
by .github/workflows/publish-devcontainer.yaml from
.devcontainer/devcontainer.json on each main merge. Operator can
pin to an immutable :<sha> tag for stability or :main for rolling.
EOF
  type        = string
  default     = "asia-northeast1-docker.pkg.dev/gen-ai-hironow/dotfiles/devcontainer:main"
}

# dmail-receiver / dmail-emitter image references for the D-Mail
# Protocol daemons (runops-gateway Issue 0001 + the 2026-05-06
# placement experiment). These run on the workspace VM host OS as
# systemd units that exec `docker run --rm` (auto-cleanup on exit;
# supervision / restart is delegated to systemd Restart=on-failure
# because `--rm` and `--restart` are mutually exclusive at the
# docker-engine layer). They share /var/lib/phonewave/{archive,outbox}
# with the devcontainer so
# the 5pillars (paintress / amadeus / sightjack / dominator /
# phonewave) and the dmail daemons see the same file system. Per-VM
# = singleton — no emitter watch race; receiver multiplexing is
# handled natively by Pub/Sub load-balancing on the same
# subscription. The default points at a placeholder tag because the
# images are built and published by the runops-gateway repo's CI
# (Phase 2 of Issue 0001); operators flip the variable to the real
# tag at template-push time once that pipeline is live.
variable "dmail_receiver_image" {
  description = <<-EOF
OCI image reference for the runops-gateway dmail-receiver daemon.
Pulls from Pub/Sub `dmail-inbound-receiver` and writes `<id>.md`
files atomically into /outbox (bind-mounted to
/var/lib/phonewave/outbox on the host). Built by the
runops-gateway repo's CI; default is a placeholder until that
pipeline lands. Override with:

  cdr templates push --variable dmail_receiver_image=<...>
EOF
  type        = string
  default     = "asia-northeast1-docker.pkg.dev/gen-ai-hironow/runops/dmail-receiver:placeholder"
}

variable "dmail_emitter_image" {
  description = <<-EOF
OCI image reference for the runops-gateway dmail-emitter daemon.
fsnotify-watches /archive (bind-mounted to /var/lib/phonewave/
archive on the host) and publishes new D-Mails to Pub/Sub
`dmail-outbound`. Same lifecycle / publishing pipeline as
dmail_receiver_image.
EOF
  type        = string
  default     = "asia-northeast1-docker.pkg.dev/gen-ai-hironow/runops/dmail-emitter:placeholder"
}

# Service account email for the dmail daemons. Per the runops-
# gateway repo's tofu/iam_pubsub.tf, the SA must already have:
#   - roles/pubsub.subscriber on dmail-inbound-receiver
#   - roles/pubsub.publisher  on dmail-outbound
#   - roles/cloudtrace.agent  (project-level)
# The SA is `exe-coder@gen-ai-hironow.iam.gserviceaccount.com` in
# the default deployment.
variable "dmail_sa_email" {
  description = "Service account email used by the dmail daemons (must already have the IAM bindings the runops-gateway repo applies in tofu/iam_pubsub.tf)."
  type        = string
  default     = "exe-coder@gen-ai-hironow.iam.gserviceaccount.com"
}

# Pub/Sub topology + OTel target for the dmail daemons. Variables
# rather than hard-coded literals so the same template can be
# pushed against a non-production project (e.g. staging) without
# editing main.tf — codex pre-push review #2 (2026-05-06) called
# out the original hardcoded 'gen-ai-hironow' / 'dmail-inbound-
# receiver' / 'telemetry.googleapis.com:443' as a fatal misroute
# risk if the template were ever reused.
variable "pubsub_dmail_inbound_subscription" {
  description = "Pub/Sub Pull subscription the dmail-receiver pulls from. Declared in the runops-gateway repo's tofu/subscriptions.tf (default name 'dmail-inbound-receiver'). Override only when deploying parallel D-Mail topologies in the same GCP project."
  type        = string
  default     = "dmail-inbound-receiver"
}

variable "pubsub_dmail_outbound_topic" {
  description = "Pub/Sub topic the dmail-emitter publishes to. Declared in the runops-gateway repo's tofu/pubsub.tf (default name 'dmail-outbound')."
  type        = string
  default     = "dmail-outbound"
}

variable "otel_exporter_otlp_endpoint" {
  description = "OTLP endpoint the dmail daemons ship spans to. Production default is the Google Cloud Trace gRPC ingest. Override to 'http://<host>:4317' to point at a local collector."
  type        = string
  default     = "telemetry.googleapis.com:443"
}

variable "otel_traces_sampler_arg" {
  description = "Sample ratio passed to the parent-based traceidratio sampler in the dmail daemons. 1.0 = sample everything (development default); production typically 0.1 or lower."
  type        = string
  default     = "1.0"
}

# Region picker. asia is the home region for this stack; allow
# us/europe as fallbacks for cross-region experimentation.
module "gcp_region" {
  source  = "registry.coder.com/coder/gcp-region/coder"
  version = "~> 1.0"
  regions = ["asia", "us", "europe"]
}

data "coder_parameter" "instance_type" {
  name         = "instance_type"
  display_name = "Instance Type"
  description  = "GCE machine type for this workspace."
  type         = "string"
  mutable      = false
  order        = 2
  default      = "e2-small"
  option {
    name  = "e2-micro (2C, 1G) — minimal"
    value = "e2-micro"
  }
  option {
    name  = "e2-small (2C, 2G) — default"
    value = "e2-small"
  }
  option {
    name  = "e2-medium (2C, 4G)"
    value = "e2-medium"
  }
  option {
    name  = "e2-standard-2 (2C, 8G)"
    value = "e2-standard-2"
  }
  option {
    name  = "e2-standard-4 (4C, 16G)"
    value = "e2-standard-4"
  }
}

data "coder_parameter" "dotfiles_uri" {
  name         = "dotfiles_uri"
  display_name = "Dotfiles URI"
  description  = <<-EOF
Personal dotfiles repo cloned + installed on top of the prebuilt
container image (Coder runs `coder dotfiles` after the agent
starts). Leave blank to skip.
EOF
  default      = "https://github.com/hironow/dotfiles.git"
  mutable      = true
  order        = 1
}

locals {
  linux_user     = lower(substr(data.coder_workspace_owner.me.name, 0, 32))
  container_name = "coder-${data.coder_workspace_owner.me.name}-${lower(data.coder_workspace.me.name)}"

  # Startup script for the workspace VM. Brings the host onto the
  # tailnet and then `docker run`s the prebuilt dev container image.
  # Order matters: tailscale must come up before docker pull,
  # because the agent binary download (BINARY_URL) is served by
  # exe-coder over MagicDNS.
  startup_script = <<-META
    #!/usr/bin/env sh
    set -eux

    if ! id -u "${local.linux_user}" >/dev/null 2>&1; then
      useradd -m -s /bin/bash "${local.linux_user}"
      echo "${local.linux_user} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/coder-user
    fi

    # Helper: import an apt-repo GPG key only after verifying its
    # fingerprint. Without the pin a TOFU fetch from the same TLS
    # endpoint that distributes the package would let a compromised
    # mirror swap key + package in lock-step. Mirrors the helper at
    # .devcontainer/features/dotfiles-tools/install.sh; positional
    # arguments avoid bash $${var} that would conflict with terraform
    # heredoc interpolation.
    import_apt_key_with_fingerprint() {
      # args: <url> <expected-fingerprint> <output-keyring-path>
      rm -f /tmp/dotfiles-apt-key.armored /tmp/dotfiles-apt-key.gpg
      curl -fsSL -o /tmp/dotfiles-apt-key.armored "$1"
      gpg --no-default-keyring --keyring /tmp/dotfiles-apt-key.gpg \
        --import /tmp/dotfiles-apt-key.armored 2>/dev/null
      actual=$(gpg --no-default-keyring --keyring /tmp/dotfiles-apt-key.gpg \
        --list-keys --with-colons | awk -F: '/^fpr:/ { print $10; exit }')
      if [ "$actual" != "$2" ]; then
        echo "[exe-bootstrap] GPG fingerprint mismatch for $1" >&2
        echo "  expected: $2" >&2
        echo "  actual:   $actual" >&2
        rm -f /tmp/dotfiles-apt-key.armored /tmp/dotfiles-apt-key.gpg
        exit 1
      fi
      install -m 0644 /tmp/dotfiles-apt-key.gpg "$3"
      rm -f /tmp/dotfiles-apt-key.armored /tmp/dotfiles-apt-key.gpg
    }

    # ---- Tailscale --------------------------------------------------
    # Workspace VMs reach the Coder control-plane VM (exe-coder:7080)
    # over the tailnet. Without this step, the agent binary download
    # falls back to the public CF Access URL which returns OIDC
    # interstitial HTML for unauthenticated requests — bootstrap
    # would `chmod +x` it and exec, producing
    # 'syntax error: unexpected newline'.
    # Tailscale apt-key fingerprint pin. Tailscale does not officially
    # publish the fingerprint as of 2026-05 (see
    # github.com/tailscale/tailscale/issues/15221). The value below is
    # observed via dnf/rpm signature verification and was operator-
    # verified against the live bookworm.noarmor.gpg endpoint. The
    # 8-byte suffix matches the NO_PUBKEY 458CA832957F5868 error that
    # apt would otherwise emit for an un-keyed repo (the same suffix
    # is documented in the control-plane VM bootstrap at
    # tofu/exe/coder.tf).
    if ! command -v tailscale >/dev/null 2>&1; then
      install -m 0755 -d /usr/share/keyrings
      import_apt_key_with_fingerprint \
        https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg \
        2596A99EAAB33821893C0A79458CA832957F5868 \
        /usr/share/keyrings/tailscale-archive-keyring.gpg
      curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list \
        > /etc/apt/sources.list.d/tailscale.list
      apt-get update -y
      apt-get install -y --no-install-recommends tailscale
    fi
    systemctl enable --now tailscaled

    # gcloud is needed to fetch the auth key from Secret Manager and
    # to docker-login Artifact Registry below. Fingerprint published
    # by Google at https://cloud.google.com/sdk/docs/install#deb;
    # operator-verified at PR #53 time and reused across all bootstrap
    # paths (feature install.sh, control-plane coder.tf, and here).
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

    AUTH_KEY="$(gcloud --quiet --project='${var.project_id}' \
      secrets versions access latest --secret='${var.workspace_authkey_secret_id}')"
    tailscale up \
      --auth-key="$AUTH_KEY" \
      --hostname='${lower(data.coder_workspace.me.name)}-ws' \
      --accept-routes=false \
      --advertise-tags='tag:exe-workspace'
    unset AUTH_KEY

    # ---- Docker -----------------------------------------------------
    # Install docker via the official apt repository in place of
    # the legacy curl-piped convenience script. The fingerprint is
    # published at https://docs.docker.com/engine/install/debian/
    # (groups of 8: 9DC85822 9FC7DD38 854AE2D8 8D81803C 0EBFCD88).
    # Pinning closes the TOFU window that the convenience script
    # would otherwise leave wide open (RCE on a CDN compromise).
    if ! command -v docker >/dev/null 2>&1; then
      install -m 0755 -d /etc/apt/keyrings
      import_apt_key_with_fingerprint \
        https://download.docker.com/linux/debian/gpg \
        9DC858229FC7DD38854AE2D88D81803C0EBFCD88 \
        /etc/apt/keyrings/docker.gpg
      echo "deb [signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list
      apt-get update -y
      apt-get install -y --no-install-recommends \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
      usermod -aG docker ${local.linux_user}
    fi

    # Configure docker to authenticate against Artifact Registry via
    # the VM's attached service account (must have
    # roles/artifactregistry.reader on the dotfiles repo).
    gcloud --quiet auth configure-docker \
      "$(echo '${var.image}' | cut -d/ -f1)"

    # ---- Pull and run the prebuilt dev container --------------------
    docker pull '${var.image}'

    # The container's PID 1 is `coder agent` via init_script — the
    # agent owns lifecycle, so we run --restart=unless-stopped to
    # survive reboots. Bind /home so dotfiles persist across container
    # restarts within the same VM lifetime.
    install -d -m 0755 /home/${local.linux_user}
    chown ${local.linux_user}:${local.linux_user} /home/${local.linux_user}

    # Phonewave shared state. The 5pillars (paintress / amadeus /
    # sightjack / dominator / phonewave) run inside the devcontainer
    # and emit D-Mail files into /var/lib/phonewave/archive (read by
    # dmail-emitter); they consume D-Mail files written by
    # dmail-receiver into /var/lib/phonewave/outbox. All three
    # processes (devcontainer, dmail-receiver, dmail-emitter) bind-
    # mount the same host dir so they see the same file system.
    # Per-VM = singleton, no emitter watch race; receiver
    # multiplexing on the Pub/Sub subscription is handled natively
    # by Pub/Sub load-balancing. See runops-gateway
    # experiments/2026-05-06_dotfiles-dmail-daemon-placement.md.
    install -d -m 0755 /var/lib/phonewave/archive /var/lib/phonewave/outbox
    chown -R ${local.linux_user}:${local.linux_user} /var/lib/phonewave

    docker rm -f '${local.container_name}' >/dev/null 2>&1 || true
    docker run \
      --detach \
      --name '${local.container_name}' \
      --network host \
      --hostname '${lower(data.coder_workspace.me.name)}' \
      --restart unless-stopped \
      --volume "/home/${local.linux_user}:/root" \
      --volume "/var/run/docker.sock:/var/run/docker.sock" \
      --volume "/var/lib/phonewave:/var/lib/phonewave" \
      --env "CODER_AGENT_TOKEN=${try(coder_agent.dev[0].token, "")}" \
      --env "CODER_AGENT_URL=${var.coder_internal_url}" \
      '${var.image}' \
      sh -c 'echo ${base64encode(try(coder_agent.dev[0].init_script, ""))} | base64 -d | sh'

    # ---- D-Mail Protocol daemons (Issue 0001) -----------------------
    # Two host-OS systemd units that exec `docker run` against
    # operator-pinned receiver / emitter images. The units:
    #
    #   - run as separate containers (one-service-per-container,
    #     unlike supervisord-style multi-process containers);
    #   - share /var/lib/phonewave/{outbox,archive} with the
    #     devcontainer above so the 5pillars see the same files;
    #   - use Restart=on-failure so a daemon crash auto-recovers
    #     instead of silently draining the Pub/Sub backlog.
    #
    # The image variables default to placeholder tags; flip them
    # at template-push time once the runops-gateway repo's CI
    # publishes real images:
    #
    #   cdr templates push exe-dotfiles-devcontainer \
    #     --variable dmail_receiver_image=<...>:<sha> \
    #     --variable dmail_emitter_image=<...>:<sha>
    #
    # ExecStart-time `docker run --rm --name <fixed>` is racy if a
    # previous unit instance is still around; ExecStartPre cleans
    # up first (the `-` prefix lets it succeed on the first boot
    # when no container exists yet).
    docker pull '${var.dmail_receiver_image}' || \
      echo "[exe-bootstrap] dmail-receiver image pull failed; service will retry on first start"
    docker pull '${var.dmail_emitter_image}' || \
      echo "[exe-bootstrap] dmail-emitter image pull failed; service will retry on first start"

    cat > /etc/systemd/system/dmail-receiver.service <<'EOF_DMR'
[Unit]
Description=runops-gateway dmail-receiver (Pub/Sub -> phonewave outbox)
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
Environment=PUBSUB_PROJECT_ID=${var.project_id}
Environment=PUBSUB_DMAIL_INBOUND_SUB=${var.pubsub_dmail_inbound_subscription}
Environment=PHONEWAVE_OUTBOX_DIR=/outbox
Environment=GOOGLE_CLOUD_PROJECT=${var.project_id}
Environment=OTEL_EXPORTER_OTLP_ENDPOINT=${var.otel_exporter_otlp_endpoint}
Environment=OTEL_EXPORTER_OTLP_PROTOCOL=grpc
Environment=OTEL_SERVICE_NAME=dmail-receiver
Environment=OTEL_TRACES_SAMPLER=parentbased_traceidratio
Environment=OTEL_TRACES_SAMPLER_ARG=${var.otel_traces_sampler_arg}
ExecStartPre=-/usr/bin/docker rm -f dmail-receiver
ExecStart=/usr/bin/docker run --rm --name dmail-receiver \
  --network host \
  -v /var/lib/phonewave/outbox:/outbox \
  -e PUBSUB_PROJECT_ID -e PUBSUB_DMAIL_INBOUND_SUB \
  -e PHONEWAVE_OUTBOX_DIR -e GOOGLE_CLOUD_PROJECT \
  -e OTEL_EXPORTER_OTLP_ENDPOINT -e OTEL_EXPORTER_OTLP_PROTOCOL \
  -e OTEL_SERVICE_NAME -e OTEL_TRACES_SAMPLER -e OTEL_TRACES_SAMPLER_ARG \
  ${var.dmail_receiver_image}
ExecStop=/usr/bin/docker stop -t 10 dmail-receiver
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF_DMR

    cat > /etc/systemd/system/dmail-emitter.service <<'EOF_DME'
[Unit]
Description=runops-gateway dmail-emitter (phonewave archive -> Pub/Sub)
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
Environment=PUBSUB_PROJECT_ID=${var.project_id}
Environment=PUBSUB_DMAIL_OUTBOUND_TOPIC=${var.pubsub_dmail_outbound_topic}
Environment=PHONEWAVE_ARCHIVE_DIRS=/archive
Environment=GOOGLE_CLOUD_PROJECT=${var.project_id}
Environment=OTEL_EXPORTER_OTLP_ENDPOINT=${var.otel_exporter_otlp_endpoint}
Environment=OTEL_EXPORTER_OTLP_PROTOCOL=grpc
Environment=OTEL_SERVICE_NAME=dmail-emitter
Environment=OTEL_TRACES_SAMPLER=parentbased_traceidratio
Environment=OTEL_TRACES_SAMPLER_ARG=${var.otel_traces_sampler_arg}
ExecStartPre=-/usr/bin/docker rm -f dmail-emitter
ExecStart=/usr/bin/docker run --rm --name dmail-emitter \
  --network host \
  -v /var/lib/phonewave/archive:/archive:ro \
  -e PUBSUB_PROJECT_ID -e PUBSUB_DMAIL_OUTBOUND_TOPIC \
  -e PHONEWAVE_ARCHIVE_DIRS -e GOOGLE_CLOUD_PROJECT \
  -e OTEL_EXPORTER_OTLP_ENDPOINT -e OTEL_EXPORTER_OTLP_PROTOCOL \
  -e OTEL_SERVICE_NAME -e OTEL_TRACES_SAMPLER -e OTEL_TRACES_SAMPLER_ARG \
  ${var.dmail_emitter_image}
ExecStop=/usr/bin/docker stop -t 10 dmail-emitter
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF_DME

    systemctl daemon-reload
    systemctl enable --now dmail-receiver.service || \
      echo "[exe-bootstrap] dmail-receiver enable failed (placeholder image?); fix dmail_receiver_image and 'systemctl restart dmail-receiver'"
    systemctl enable --now dmail-emitter.service || \
      echo "[exe-bootstrap] dmail-emitter enable failed (placeholder image?); fix dmail_emitter_image and 'systemctl restart dmail-emitter'"
  META
}

resource "google_compute_disk" "root" {
  name  = "coder-${data.coder_workspace.me.id}-root"
  type  = "pd-ssd"
  image = "debian-cloud/debian-12"
  lifecycle {
    ignore_changes = all
  }
}

resource "google_compute_instance" "vm" {
  name         = "coder-${lower(data.coder_workspace_owner.me.name)}-${lower(data.coder_workspace.me.name)}-root"
  machine_type = data.coder_parameter.instance_type.value
  # Honour the operator's region pick at workspace creation. Falls
  # back to the provider-level default during the template-push
  # preview when the parameter has no value.
  zone = coalesce(module.gcp_region.value, "asia-northeast1-a")

  # data.coder_workspace_owner.me.name == "default" suppresses an
  # error during the first plan when no workspace is being created.
  desired_status = (data.coder_workspace_owner.me.name == "default" || data.coder_workspace.me.start_count == 1) ? "RUNNING" : "TERMINATED"

  network_interface {
    network = "default"
    access_config {}
  }

  boot_disk {
    auto_delete = false
    source      = google_compute_disk.root.name
  }

  service_account {
    email  = var.workspace_sa_email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = local.startup_script
  }
}

# Workspace agent. count = start_count so the agent only exists
# while the workspace is running.
resource "coder_agent" "dev" {
  count              = data.coder_workspace.me.start_count
  arch               = "amd64"
  auth               = "token"
  os                 = "linux"
  dir                = "/root/dotfiles"
  connection_timeout = 0

  # Personalisation + workspace-side mise sync.
  #
  # `coder dotfiles` clones the operator's dotfiles repo into
  # /root/dotfiles and runs install.sh. install.sh's OS dispatch
  # (per ADR 0005) auto-skips the Mac-only steps on Linux; the
  # legacy INSTALL_SKIP_* env vars are kept here as belt-and-
  # suspenders for older images that pre-date the OS dispatch.
  #
  # Then `mise install` runs against the workspace mise.toml so
  # mise's install state tracks what mise.toml asks for. Per ADR
  # 0006 the data dir is /opt/mise (set in the image's profile.d),
  # which sits OUTSIDE the /home/<user>:/root volume mount, so the
  # build-time-baked cache survives. With pinned versions in
  # mise.toml + the cache reachable, MISE_OFFLINE=1 is honoured at
  # workspace runtime — narrowing the trust surface (no per-
  # workspace api.github.com / aqua-registry calls).
  startup_script = data.coder_parameter.dotfiles_uri.value == "" ? "" : <<-EOT
    set -eu
    export INSTALL_SKIP_HOMEBREW=1
    export INSTALL_SKIP_ADD_UPDATE=1
    export MISE_DATA_DIR=/opt/mise
    if command -v coder >/dev/null 2>&1; then
      coder dotfiles -y "${data.coder_parameter.dotfiles_uri.value}" || \
        echo "[exe] dotfiles install failed; continuing"
    fi
    if command -v mise >/dev/null 2>&1 && [ -f /root/dotfiles/mise.toml ]; then
      (
        cd /root/dotfiles
        mise trust mise.toml >/dev/null 2>&1 || true
        MISE_OFFLINE=1 mise install
      ) || echo "[exe] mise install failed; tools fall back to baked-in image versions"
    fi
  EOT

  metadata {
    key          = "cpu"
    display_name = "CPU Usage"
    interval     = 5
    timeout      = 5
    script       = "coder stat cpu"
  }
  metadata {
    key          = "memory"
    display_name = "Memory Usage"
    interval     = 5
    timeout      = 5
    script       = "coder stat mem"
  }
  metadata {
    key          = "disk"
    display_name = "Disk Usage"
    interval     = 5
    timeout      = 5
    script       = "coder stat disk"
  }
}

resource "coder_metadata" "workspace_info" {
  count       = data.coder_workspace.me.start_count
  resource_id = google_compute_instance.vm.id

  item {
    key   = "type"
    value = google_compute_instance.vm.machine_type
  }
  item {
    key   = "zone"
    value = module.gcp_region.value
  }
  item {
    key   = "image"
    value = var.image
  }
}

resource "coder_metadata" "home_info" {
  resource_id = google_compute_disk.root.id

  item {
    key   = "size"
    value = "${google_compute_disk.root.size} GiB"
  }
}
