# Coder template — dotfiles devcontainer (prebuilt image)

This template spawns a Coder workspace whose container image is the
**dotfiles dev container** declared by `.devcontainer/devcontainer.json`
(debian-12 + devcontainer features), prebuilt by CI and pulled from
Artifact Registry. Same SoT as the local IDE and the CI sandbox, so
all three environments stay aligned. Realises `docs/intent.md`:

> Coder workspace whose container image **is** the dotfiles Dev
> Container.

ADR: `docs/adr/0002-coder-prebuilt-image.md`

## How it works

```
+----------------+   docker pull   +------------------+
| Coder template |---------------->| Artifact Registry|
| (this dir)     |                 |  asia-northeast1 |
+----------------+                 +------------------+
        |                                  ^
        |                                  | docker push
        |                                  |
        v                          +-------+----------+
+--------------+                   | publish-         |
| Coder server |                   | devcontainer.yaml|
+--------------+                   | (GHA, WIF auth)  |
        |                          +------------------+
        v
+--------------+    docker run     +--------------+
| Workspace VM |------------------>| dev container|
| (debian-12)  |                   | (prebuilt)   |
+--------------+                   +--------------+
                                          |
                                          v
                                   +--------------+
                                   |  coder_agent |
                                   +--------------+
```

Legend / 凡例:

- Artifact Registry: GCP \<region\>-docker.pkg.dev/\<project\>/dotfiles
- publish-devcontainer.yaml: GitHub Actions が main merge 時に image build & push
- WIF auth: Workload Identity Federation, no SA keys
- Workspace VM: GCE debian-12 + tailscaled + docker, pulls prebuilt image
- dev container: 起動済みの devcontainer.json image をそのまま走らせる (no envbuilder)
- coder_agent: workspace 内常駐の Coder agent (SSH / IDE)

## Push

```bash
cdr templates push exe-dotfiles-devcontainer \
  -d exe/coder/templates/dotfiles-devcontainer \
  --variable project_id=gen-ai-hironow \
  --variable workspace_sa_email=$(just exe-output -raw exe_workspace_sa_email) \
  --variable coder_internal_url=$(just exe-output -raw coder_internal_url) \
  --variable image=$(just exe-output -raw artifact_registry_repo)/devcontainer:main \
  --yes
```

| Variable | Default | Notes |
|---|---|---|
| `project_id` | `gen-ai-hironow` | GCP project for workspace VMs |
| `workspace_sa_email` | (required) | `just exe-output -raw exe_workspace_sa_email` |
| `coder_internal_url` | `http://exe-coder:7080` | tailnet-internal URL the agent download resolves to |
| `workspace_authkey_secret_id` | `exe-tailscale-workspace-authkey` | Secret Manager id for the tag:exe-workspace key |
| `image` | `asia-northeast1-docker.pkg.dev/gen-ai-hironow/dotfiles/devcontainer:main` | prebuilt image; pin to `:<git-sha>` for reproducible workspaces |

## Create a workspace

```bash
cdr create my-ws --template exe-dotfiles-devcontainer --yes
cdr ssh my-ws.dev
```

Parameters (interactive on first create unless `--parameter` is passed):

| Parameter | Default | Notes |
|---|---|---|
| `instance_type` | `e2-small` | `e2-micro` is now viable (no envbuilder) |
| `dotfiles_uri` | `https://github.com/hironow/dotfiles.git` | runs `coder dotfiles` on top of the prebuilt image |

## What's in the workspace image

The prebuilt image bakes the dev container's `dotfiles-tools`
feature, so a fresh workspace boots with these on PATH:

| Category | Tools |
|---|---|
| Core | `just`, `mise`, `uv`, `sheldon`, `gcloud`, `git`, `docker` (cli-only) |
| Lint / format | `ruff`, `shellcheck`, `markdownlint-cli2`, `prek` |
| Runtime | `node` 24.15.0, `python` 3 (via mise/devcontainer) |
| AI agent CLIs | `codex`, `gemini`, `claude`, `copilot`, `pi` (auth on first use — see [runbook](../../../docs/runbook.md#ai-agent-cli-authentication)) |

Versions are pinned in [`mise.toml`](../../../../mise.toml) per
[ADR 0006](../../../../docs/adr/0006-mise-version-pinning.md).

## Smoke

```bash
cdr workspaces list                # status: starting -> running (~30-60s)
cdr ssh my-ws.dev -- just --list   # JustSandbox recipes available
cdr ssh my-ws.dev -- '
  for cli in codex gemini claude copilot pi; do
    printf "%s: " "$cli"; "$cli" --version 2>&1 | head -1
  done'
```

## Related docs

- [`../../README.md`](../../README.md) — `exe/coder/` overview
- [`../../../README.md`](../../../README.md) — `exe/` overview
- [`../../../docs/architecture.md`](../../../docs/architecture.md)
  — full exe.hironow.dev architecture and trust boundary table
- [`../../../docs/runbook.md`](../../../docs/runbook.md)
  — `cdr templates push` / pre-merge image-tag testing
- [`../../../../README.md`](../../../../README.md) — top-level
  repo README (architecture overview + doc tree)
- [`../../../../docs/adr/0002-coder-prebuilt-image.md`](../../../../docs/adr/0002-coder-prebuilt-image.md)
  — why prebuilt image instead of envbuilder
- [`../../../../docs/adr/0004-workspace-tailnet-routing.md`](../../../../docs/adr/0004-workspace-tailnet-routing.md)
  — why workspace VMs reach Coder over the tailnet (B-plan)
- [`../../../../docs/adr/0005-install-path-rationalization.md`](../../../../docs/adr/0005-install-path-rationalization.md)
  — install.sh OS dispatch + step\_\* helpers
- [`../../../../docs/adr/0006-mise-version-pinning.md`](../../../../docs/adr/0006-mise-version-pinning.md)
  — mise.toml pins + `MISE_DATA_DIR=/opt/mise` relocation
- [`../../../../docs/adr/0007-coder-server-install-hardening.md`](../../../../docs/adr/0007-coder-server-install-hardening.md)
  — Coder server install pinning
