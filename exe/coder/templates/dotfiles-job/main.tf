# exe.hironow.dev workspace template — dotfiles-job (ephemeral
# headless workspace runner per ADR 0008).
#
# Differences from the sibling dotfiles-devcontainer template:
#   - No interactive parameters. The caller passes the command to
#     run via the `job_command` template parameter at create-time.
#   - Lifecycle is owned entirely by the cdr-job wrapper:
#       * `coder create --yes` blocks until the agent is up,
#         streams the agent startup_script log, then issues
#         `coder delete -y` from an EXIT/INT/TERM trap.
#     This template does NOT set `default_ttl_ms`,
#     `dormancy_threshold_ms`, or any auto-stop on the VM. If the
#     wrapper is killed by SIGKILL or OOM (no trap fires), the
#     job VM will leak — operator must `cdr delete <job-name> -y`
#     manually. See ADR 0008 "Lifecycle and cost protection".
#   - Same dev container image (`devcontainer:main`) so the job
#     sees the same tool set the operator's interactive workspace
#     does (mise pins, AI CLIs, gcloud, just, ...).
#   - Same VM startup_script as dotfiles-devcontainer (apt-key
#     fingerprint pinned tailscale + gcloud + docker, /opt/mise
#     relocation). Duplicated for now; a shared module is a
#     future cleanup if we add a third template.
#
# Push:
#   cdr templates push exe-dotfiles-job \
#     -d exe/coder/templates/dotfiles-job \
#     --variable project_id=gen-ai-hironow \
#     --variable workspace_sa_email=$(just exe-output -raw exe_workspace_sa_email) \
#     --variable coder_internal_url=$(just exe-output -raw coder_internal_url) \
#     --variable image=$(just exe-output -raw artifact_registry_repo)/devcontainer:main \
#     --yes
#
# Create a job (typically via the cdr-job wrapper, not directly):
#   cdr-job <job-name> -- <command...>
#
# That wrapper issues:
#   coder create <job-name> --template exe-dotfiles-job \
#     --parameter job_command="<command...>" --yes

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

provider "coder" {
  url = var.coder_internal_url
}

provider "google" {
  region  = "asia-northeast1"
  zone    = "asia-northeast1-a"
  project = var.project_id
}

data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

variable "project_id" {
  description = "GCP project hosting the job VMs. Stack default."
  type        = string
  default     = "gen-ai-hironow"
}

variable "coder_internal_url" {
  description = <<-EOF
URL the job's coder-agent uses to reach the Coder server. Same
tailnet-internal endpoint the dotfiles-devcontainer template
uses; resolved over MagicDNS so the agent download bypasses CF
Access.
EOF
  type        = string
  default     = "http://exe-coder:7080"
}

variable "workspace_sa_email" {
  description = <<-EOF
Service account email stamped on every job VM. Same SA as the
dotfiles-devcontainer workspace VMs (artifactregistry.reader on
the dotfiles repo + secretmanager.secretAccessor on the workspace
authkey). Per-job IAM additions (e.g. storage.objectAdmin on the
state bucket for tofu-plan jobs) are applied to this same SA.
EOF
  type        = string
}

variable "workspace_authkey_secret_id" {
  description = "Secret Manager secret holding the tag:exe-workspace tailnet authkey."
  type        = string
  default     = "exe-tailscale-workspace-authkey"
}

variable "image" {
  description = "Dev container image for the job. Same image as the interactive template."
  type        = string
  default     = "asia-northeast1-docker.pkg.dev/gen-ai-hironow/dotfiles/devcontainer:main"
}

# Caller-supplied command. The cdr-job wrapper sets this; manual
# `coder create` invocations can override it interactively.
data "coder_parameter" "job_command" {
  name         = "job_command"
  display_name = "Job command"
  description  = "Single shell command line to execute inside the workspace. The job VM tears down once the command exits."
  type         = "string"
  mutable      = false
  default      = "echo 'no job_command supplied; sleeping 60s then exiting'; sleep 60"
}

locals {
  linux_user     = lower(data.coder_workspace_owner.me.name)
  container_name = "coder-${data.coder_workspace_owner.me.name}-${lower(data.coder_workspace.me.name)}"

  # Same VM startup_script body as dotfiles-devcontainer (apt-
  # key fingerprint pinned tailscale + gcloud + docker, /opt/mise
  # relocation, docker pull + run). The agent init_script differs
  # — see coder_agent.dev.startup_script below — but the VM-level
  # bootstrap is identical to keep one operational model.
  startup_script = <<-META
    #!/usr/bin/env sh
    set -eux

    if ! id -u "${local.linux_user}" >/dev/null 2>&1; then
      useradd -m -s /bin/bash "${local.linux_user}"
      echo "${local.linux_user} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/coder-user
    fi

    import_apt_key_with_fingerprint() {
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
      --hostname='${lower(data.coder_workspace.me.name)}-job' \
      --accept-routes=false \
      --advertise-tags='tag:exe-workspace'
    unset AUTH_KEY

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

    gcloud --quiet auth configure-docker \
      "$(echo '${var.image}' | cut -d/ -f1)"

    docker pull '${var.image}'

    install -d -m 0755 /home/${local.linux_user}
    chown ${local.linux_user}:${local.linux_user} /home/${local.linux_user}

    docker rm -f '${local.container_name}' >/dev/null 2>&1 || true
    docker run \
      --detach \
      --name '${local.container_name}' \
      --network host \
      --hostname '${lower(data.coder_workspace.me.name)}' \
      --restart unless-stopped \
      --volume "/home/${local.linux_user}:/root" \
      --volume "/var/run/docker.sock:/var/run/docker.sock" \
      --env "CODER_AGENT_TOKEN=${try(coder_agent.job[0].token, "")}" \
      --env "CODER_AGENT_URL=${var.coder_internal_url}" \
      '${var.image}' \
      sh -c 'echo ${base64encode(try(coder_agent.job[0].init_script, ""))} | base64 -d | sh'
  META
}

resource "google_compute_disk" "root" {
  name  = "coder-${data.coder_workspace.me.id}-job-root"
  type  = "pd-ssd"
  image = "debian-cloud/debian-12"
  lifecycle {
    ignore_changes = all
  }
}

resource "google_compute_instance" "vm" {
  name         = "coder-${lower(data.coder_workspace_owner.me.name)}-${lower(data.coder_workspace.me.name)}-job"
  machine_type = "e2-small"
  zone         = "asia-northeast1-a"

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

# Job agent. The init_script runs the caller's job_command then
# requests workspace stop. cdr-job's trap handler issues the
# subsequent `coder delete -y`.
resource "coder_agent" "job" {
  count              = data.coder_workspace.me.start_count
  arch               = "amd64"
  auth               = "token"
  os                 = "linux"
  dir                = "/root"
  connection_timeout = 0

  startup_script = <<-EOT
    set -eu
    export MISE_DATA_DIR=/opt/mise
    cd /root
    echo "[dotfiles-job] starting at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "[dotfiles-job] command: ${data.coder_parameter.job_command.value}"
    sh -c '${data.coder_parameter.job_command.value}' \
      || rc=$? && echo "[dotfiles-job] exited rc=$${rc:-0}"
    echo "[dotfiles-job] finished at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  EOT

  metadata {
    key          = "elapsed"
    display_name = "Elapsed (s)"
    interval     = 5
    timeout      = 5
    script       = "echo $((SECONDS))"
  }
}

resource "coder_metadata" "job_info" {
  count       = data.coder_workspace.me.start_count
  resource_id = google_compute_instance.vm.id

  item {
    key   = "command"
    value = data.coder_parameter.job_command.value
  }
  item {
    key   = "type"
    value = "ephemeral-job"
  }
}
