# exe.hironow.dev workspace template — dotfiles devcontainer.
#
# Adapted from coder/coder examples/templates/gcp-devcontainer.
# Differences from upstream:
#   - default repo_url    = https://github.com/hironow/dotfiles.git
#                           (this stack's reason for existing — see
#                            docs/intent.md "Coder workspace whose
#                            container image IS the dotfiles Dev Container")
#   - default project_id  = gen-ai-hironow
#   - default region      = asia (us+europe upstream)
#   - default instance    = e2-small (e2-micro upstream — too small
#                            for an envbuilder build, OOMs)
#   - browser IDE module the upstream gcp-devcontainer template ships
#                          with `registry.coder.com/coder/<browser-ide>/coder`
#                          as a sibling resource; we drop it because
#                          alpine+musl trips its install script (binary
#                          drops into ~/.local/bin then refuses to start
#                          on 127.0.0.1:13337). Terminal-first is the
#                          stated workflow; reintroduce a musl-friendly
#                          browser IDE in a follow-up if the need arises.
#   - dotfiles_uri param  added so workspaces auto-clone & install
#                           hironow's personal dotfiles on top of the
#                           devcontainer base.
#
# Push:
#   cdr templates push exe-dotfiles-devcontainer \
#     -d exe/coder/templates/dotfiles-devcontainer \
#     --variable project_id=gen-ai-hironow
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
    envbuilder = {
      source = "coder/envbuilder"
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
# HTML instead of the binary. See coder/coder
# provisioner/terraform/provision.go provisionEnv() for the
# server-side rendering path.
provider "coder" {
  url = var.coder_internal_url
}

# Provider-level zone is fixed to the stack's home zone so the
# template-push preview plan can resolve a non-empty string. The
# 'gcp_region' Coder parameter still drives the *workspace* zone,
# but per-resource (see google_compute_instance.vm.zone). Without
# this fallback, push fails with 'expected a non-empty string' on
# the provider block because the parameter default does not
# propagate at preview time.
provider "google" {
  region  = "asia-northeast1"
  zone    = "asia-northeast1-a"
  project = var.project_id
}

data "google_compute_default_service_account" "default" {}

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
authkey secret. Operator stack exports it as 'exe_workspace_sa_email'.
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

variable "cache_repo" {
  default     = ""
  description = "(Optional) Container registry to cache devcontainer builds. Example: host.tld/path/to/repo."
  type        = string
}

variable "cache_repo_docker_config_path" {
  default     = ""
  description = "(Optional) Path to a docker config.json containing credentials to the cache repo."
  sensitive   = true
  type        = string
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

data "coder_parameter" "fallback_image" {
  default      = "codercom/enterprise-base:ubuntu"
  description  = "Image used if the devcontainer build fails (envbuilder fallback)."
  display_name = "Fallback Image"
  mutable      = true
  name         = "fallback_image"
  order        = 3
}

data "coder_parameter" "devcontainer_builder" {
  description  = <<-EOF
Image that builds the devcontainer (envbuilder). Pin a digest in
production; :latest is convenient for personal stacks.
EOF
  display_name = "Devcontainer Builder"
  mutable      = true
  name         = "devcontainer_builder"
  default      = "ghcr.io/coder/envbuilder:latest"
  order        = 4
}

data "coder_parameter" "repo_url" {
  name         = "repo_url"
  display_name = "Repository URL"
  default      = "https://github.com/hironow/dotfiles.git"
  description  = "Git repo with .devcontainer/ — defaults to the dotfiles dev container the stack was designed around."
  mutable      = true
  order        = 1
}

data "coder_parameter" "git_branch" {
  name         = "git_branch"
  display_name = "Git Branch"
  description  = <<-EOF
Branch to clone from repo_url. Leave blank for the repo's default
(usually main). Set to e.g. 'feat/exe-hironow-dev' to test changes
before they are merged into main.
EOF
  default      = ""
  mutable      = true
  order        = 6
}

data "coder_parameter" "dotfiles_uri" {
  name         = "dotfiles_uri"
  display_name = "Dotfiles URI"
  description  = <<-EOF
Personal dotfiles repo cloned + installed on top of the
devcontainer base (Coder runs `dotfiles install` after the agent
starts). Leave blank to skip.
EOF
  default      = "https://github.com/hironow/dotfiles.git"
  mutable      = true
  order        = 5
}

data "local_sensitive_file" "cache_repo_dockerconfigjson" {
  count    = var.cache_repo_docker_config_path == "" ? 0 : 1
  filename = var.cache_repo_docker_config_path
}

# Be careful when modifying the locals — they wire the agent token
# and init script into envbuilder's environment.
locals {
  linux_user                 = lower(substr(data.coder_workspace_owner.me.name, 0, 32))
  container_name             = "coder-${data.coder_workspace_owner.me.name}-${lower(data.coder_workspace.me.name)}"
  devcontainer_builder_image = data.coder_parameter.devcontainer_builder.value
  docker_config_json_base64  = try(data.local_sensitive_file.cache_repo_dockerconfigjson[0].content_base64, "")

  envbuilder_env = {
    "ENVBUILDER_GIT_URL" : data.coder_parameter.repo_url.value,
    # Empty value = envbuilder honours the repo's default branch.
    # Set this to e.g. 'feat/exe-hironow-dev' to test pre-merge
    # changes (libc6-compat in Dockerfile, new tests, etc.) without
    # waiting for a merge to main. Once merged, leave it blank.
    "ENVBUILDER_GIT_BRANCH" : data.coder_parameter.git_branch.value,
    "CODER_AGENT_TOKEN" : try(coder_agent.dev[0].token, ""),
    "CODER_AGENT_URL" : data.coder_workspace.me.access_url,
    "ENVBUILDER_INIT_SCRIPT" : "echo ${base64encode(try(coder_agent.dev[0].init_script, ""))} | base64 -d | sh",
    "ENVBUILDER_DOCKER_CONFIG_BASE64" : try(data.local_sensitive_file.cache_repo_dockerconfigjson[0].content_base64, ""),
    "ENVBUILDER_FALLBACK_IMAGE" : data.coder_parameter.fallback_image.value,
    "ENVBUILDER_CACHE_REPO" : var.cache_repo,
    "ENVBUILDER_PUSH_IMAGE" : var.cache_repo == "" ? "" : "true",
  }

  docker_env_input       = try(envbuilder_cached_image.cached[0].env_map, local.envbuilder_env)
  docker_env_list_base64 = base64encode(join("\n", [for k, v in local.docker_env_input : "${k}=${v}"]))
  builder_image          = try(envbuilder_cached_image.cached[0].image, data.coder_parameter.devcontainer_builder.value)

  startup_script = <<-META
    #!/usr/bin/env sh
    set -eux

    # Workspace user.
    if ! id -u "${local.linux_user}" >/dev/null 2>&1; then
      useradd -m -s /bin/bash "${local.linux_user}"
      echo "${local.linux_user} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/coder-user
    fi

    # ---- Tailscale --------------------------------------------------
    # Workspace VMs talk to the Coder control-plane VM
    # (exe-coder:7080) over the tailnet. Without this step, the agent
    # binary download from the bootstrap script falls back to the
    # public CODER_ACCESS_URL which sits behind Cloudflare Access and
    # returns OIDC interstitial HTML for unauthenticated requests —
    # which the bootstrap script then 'chmod +x'es and tries to exec,
    # producing 'syntax error: unexpected newline' and a workspace
    # that never connects. See docs/handover.md for the full
    # post-mortem. This is base image debian-12 (see google_compute_disk
    # boot image), so apt is the install path.
    if ! command -v tailscale >/dev/null 2>&1; then
      install -m 0755 -d /usr/share/keyrings
      curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg \
        > /usr/share/keyrings/tailscale-archive-keyring.gpg
      curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list \
        > /etc/apt/sources.list.d/tailscale.list
      apt-get update -y
      apt-get install -y --no-install-recommends tailscale
    fi
    systemctl enable --now tailscaled

    # Need gcloud to fetch the auth-key from Secret Manager. The base
    # image does not ship it.
    if ! command -v gcloud >/dev/null 2>&1; then
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | gpg --dearmor -o /etc/apt/keyrings/cloud.google.gpg
      echo 'deb [signed-by=/etc/apt/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main' \
        > /etc/apt/sources.list.d/google-cloud-sdk.list
      apt-get update -y
      apt-get install -y --no-install-recommends google-cloud-cli
    fi

    AUTH_KEY="$(gcloud --quiet --project='${var.project_id}' \
      secrets versions access latest --secret='${var.workspace_authkey_secret_id}')"
    # tailscale up is idempotent: a no-op if already authenticated under
    # the same hostname + tags.
    tailscale up \
      --auth-key="$AUTH_KEY" \
      --hostname='${lower(data.coder_workspace.me.name)}-ws' \
      --accept-routes=false \
      --advertise-tags='tag:exe-workspace'
    unset AUTH_KEY

    # Docker (host-side; envbuilder uses the host daemon).
    if ! command -v docker >/dev/null 2>&1; then
      curl -fsSL https://get.docker.com -o get-docker.sh
      sudo sh get-docker.sh >/dev/null 2>&1
      sudo usermod -aG docker ${local.linux_user}
      newgrp docker
    fi

    # Cache-repo docker config, if any.
    if [ -n "${local.docker_config_json_base64}" ]; then
      mkdir -p "/home/${local.linux_user}/.docker"
      printf "%s" "${local.docker_config_json_base64}" | base64 -d | tee "/home/${local.linux_user}/.docker/config.json"
      chown -R ${local.linux_user}:${local.linux_user} "/home/${local.linux_user}/.docker"
    fi

    # Container env (passed to envbuilder via --env-file).
    printf "%s" "${local.docker_env_list_base64}" | base64 -d | tee "/home/${local.linux_user}/env.txt"

    # Fire envbuilder.
    docker run \
      --rm \
      --net=host \
      -h ${lower(data.coder_workspace.me.name)} \
      -v /home/${local.linux_user}/envbuilder:/workspaces \
      -v /var/run/docker.sock:/var/run/docker.sock \
      --env-file /home/${local.linux_user}/env.txt \
      ${local.builder_image}
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

resource "envbuilder_cached_image" "cached" {
  count         = var.cache_repo == "" ? 0 : data.coder_workspace.me.start_count
  builder_image = local.devcontainer_builder_image
  git_url       = data.coder_parameter.repo_url.value
  cache_repo    = var.cache_repo
  extra_env     = local.envbuilder_env
}

resource "google_compute_instance" "vm" {
  name         = "coder-${lower(data.coder_workspace_owner.me.name)}-${lower(data.coder_workspace.me.name)}-root"
  machine_type = data.coder_parameter.instance_type.value
  # Honour the operator's region pick at workspace creation. Falls
  # back to the provider-level default ('asia-northeast1-a') only
  # during the template-push preview when the parameter has no value.
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
  dir                = "/workspaces/${trimsuffix(basename(data.coder_parameter.repo_url.value), ".git")}"
  connection_timeout = 0

  # Personalisation: pull and install the operator's dotfiles on top
  # of whatever the devcontainer base image gives us.
  #
  # The dotfiles install.sh tries to install Homebrew + Google Cloud
  # SDK + replay brew/gcloud bundle dumps — none of which work on
  # alpine + musl (linuxbrew is glibc-only, gcloud SDK install path
  # likewise; alpine's apk repo has no google-cloud-cli). install.sh
  # honours three env vars to skip those segments; with all three
  # set, the script still runs `just clean` + `just deploy` which
  # produces the actually-valuable bits (~/.zshrc symlink, sheldon
  # lock, starship config, fzf-tab clone, ...). Without them the
  # script aborts at homebrew install via `set -eu` and the agent
  # logs '[exe] dotfiles install failed; continuing' on every boot.
  startup_script = data.coder_parameter.dotfiles_uri.value == "" ? "" : <<-EOT
    set -eu
    export INSTALL_SKIP_HOMEBREW=1
    export INSTALL_SKIP_GCLOUD=1
    export INSTALL_SKIP_ADD_UPDATE=1
    if command -v coder >/dev/null 2>&1; then
      coder dotfiles -y "${data.coder_parameter.dotfiles_uri.value}" || \
        echo "[exe] dotfiles install failed; continuing"
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
    key   = "repo"
    value = data.coder_parameter.repo_url.value
  }
}

resource "coder_metadata" "home_info" {
  resource_id = google_compute_disk.root.id

  item {
    key   = "size"
    value = "${google_compute_disk.root.size} GiB"
  }
}
