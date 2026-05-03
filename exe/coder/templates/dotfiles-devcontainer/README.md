# Coder template — dotfiles-devcontainer (interactive prebuilt-image workspace)

This template spawns a long-lived, interactive Coder workspace whose
container image is the **dotfiles dev container** declared by
`.devcontainer/devcontainer.json` (debian-12 + devcontainer features),
prebuilt by GitHub Actions on each main merge and pulled from
Artifact Registry. The same image is used by:

- the operator's local IDE (VS Code / Cursor / JetBrains via Dev
  Containers extension), and
- the CI sandbox in `.github/workflows/`,

so all three environments stay byte-identical.

ADR: [`../../../../docs/adr/0002-coder-prebuilt-image.md`](../../../../docs/adr/0002-coder-prebuilt-image.md)

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

## Lifecycle

Unlike the sibling `dotfiles-job` template (which is one-shot), this
template is meant for **long-lived interactive use**. There is no
TTL set in the `.tf` source. To set one, the operator runs:

```bash
cdr templates edit exe-dotfiles-devcontainer --default-ttl 8h
```

Workspaces auto-stop after the TTL elapses; the boot disk is retained
(`auto_delete = false` in `main.tf`) so a subsequent `cdr start` boots
back into the same `/home/<user>` state.

To delete a workspace explicitly:

```bash
cdr stop my-ws --yes
cdr delete my-ws --yes
```

## Smoke

```bash
cdr workspaces list                # status: starting -> running (~30-60s)
cdr ssh my-ws.dev -- just --list   # workspace recipes available
cdr ssh my-ws.dev -- '
  for cli in codex gemini claude copilot pi; do
    printf "%s: " "$cli"; "$cli" --version 2>&1 | head -1
  done'
```

## Differences from the sibling job template

| Aspect | `dotfiles-devcontainer` (this) | `dotfiles-job` |
|---|---|---|
| Use case | Long-lived interactive IDE / SSH | One-shot headless command |
| Interactive params | `instance_type`, `dotfiles_uri` | none |
| Lifecycle | `default-ttl` via `cdr templates edit` | wrapper-trap (`cdr-job` `coder delete -y` on EXIT/INT/TERM) |
| Hostname suffix | `-ws` | `-job` |
| `coder dotfiles` install | yes (operator's repo on top of the prebuilt image) | no |

## Related docs

- [`../../../docs/architecture.md`](../../../docs/architecture.md) — full exe.hironow.dev architecture
- [`../../../docs/runbook.md`](../../../docs/runbook.md) — operator workflow
- [`../../../../docs/adr/0002-coder-prebuilt-image.md`](../../../../docs/adr/0002-coder-prebuilt-image.md) — why prebuilt image
- [`../../../../docs/adr/`](../../../../docs/adr/) — full ADR list
