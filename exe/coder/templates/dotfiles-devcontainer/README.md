# Coder template — dotfiles devcontainer

This template spawns a Coder workspace whose container image is the
**dotfiles dev container** declared by `.devcontainer/devcontainer.json`
(debian-12 + devcontainer features). The same SoT is consumed by the
local IDE and the CI sandbox, so all three environments stay aligned.
It is the realisation of the core `docs/intent.md` line item:

> Coder workspace whose container image **is** the dotfiles Dev
> Container.

## How it works

```
+-------------+   ENVBUILDER_GIT_URL    +--------------+
| Coder server|------------------------>|  envbuilder  |
| (this stack)|                         |  (in a GCE   |
+-------------+                         |   VM, host)  |
                                        +------+-------+
                                               |
                                               v
                                        +------+-------+
                                        | spawn dev    |
                                        | container    |
                                        | from         |
                                        | repo_url's   |
                                        | .devcontainer|
                                        +------+-------+
                                               |
                                               v
                                        +--------------+
                                        | coder_agent  |
                                        | (inside the  |
                                        |  container)  |
                                        +--------------+
```

```
Legend / 凡例:
- ENVBUILDER_GIT_URL: envbuilder が clone する git repo
- envbuilder: Coder 公式 OCI builder (kaniko-style)
- dev container: .devcontainer/devcontainer.json を解釈して立ち上がる
- coder_agent: workspace 内常駐の Coder agent (SSH / IDE)
```

## Push

```bash
cdr templates push exe-dotfiles-devcontainer \
  -d exe/coder/templates/dotfiles-devcontainer \
  --variable project_id=gen-ai-hironow \
  --variable workspace_sa_email=$(just exe-output -raw exe_workspace_sa_email) \
  --variable coder_internal_url=$(just exe-output -raw coder_internal_url) \
  --yes
```

| Variable | Default | Notes |
|---|---|---|
| `project_id` | `gen-ai-hironow` | GCP project for workspace VMs |
| `workspace_sa_email` | (required) | from `just exe-output -raw exe_workspace_sa_email` |
| `coder_internal_url` | `http://exe-coder:7080` | tailnet-internal URL the agent download resolves to |
| `workspace_authkey_secret_id` | `exe-tailscale-workspace-authkey` | Secret Manager id for the tag:exe-workspace key |
| `cache_repo` | `""` | Optional; pre-built devcontainer image cache |

## Create a workspace

```bash
cdr create my-ws --template exe-dotfiles-devcontainer --yes
cdr ssh my-ws.dev
```

Parameters (interactive on first create unless `--parameter` is passed):

| Parameter | Default | Notes |
|---|---|---|
| `repo_url` | `https://github.com/hironow/dotfiles.git` | repo with `.devcontainer/` |
| `git_branch` | `""` (= repo HEAD) | override branch for pre-merge testing |
| `instance_type` | `e2-small` | `e2-micro` OOMs envbuilder |
| `fallback_image` | `codercom/enterprise-base:ubuntu` | used if devcontainer build fails |
| `devcontainer_builder` | `ghcr.io/coder/envbuilder:latest` | pin a digest in production |
| `dotfiles_uri` | `https://github.com/hironow/dotfiles.git` | runs `coder dotfiles` on top of the dev container |

## Smoke

```bash
cdr workspaces list                # status: starting -> running
cdr ssh my-ws.dev -- just --list   # JustSandbox recipes available
```
