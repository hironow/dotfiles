# Coder template — dotfiles devcontainer

This template spawns a Coder workspace whose container image is the
**dotfiles dev container** (`tests/docker/JustSandbox.Dockerfile` via
`.devcontainer/devcontainer.json`). It is the realisation of the
core `docs/intent.md` line item:

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

After the Coder server is up and `cdr` is configured (see
`exe/scripts/cdr` and `exe/docs/runbook.md`):

```bash
cdr templates push exe-dotfiles-devcontainer \
  -d exe/coder/templates/dotfiles-devcontainer
```

The first push prompts for the input variables:

| Variable | Default | Notes |
|---|---|---|
| `project_id` | `gen-ai-hironow` | GCP project for the workspace VMs (separate from the Coder server VM) |
| `cache_repo` | `""` | Optional; pre-built devcontainer image cache |
| `cache_repo_docker_config_path` | `""` | Optional; only if cache_repo is private |

## Create a workspace

```bash
cdr create my-ws --template exe-dotfiles-devcontainer
cdr ssh my-ws        # SSH in
cdr open my-ws       # browser IDE (code-server)
```

Workspace parameters (interactive prompt the first time, then
locked unless `mutable = true`):

| Parameter | Default | Notes |
|---|---|---|
| `repo_url` | `https://github.com/hironow/dotfiles.git` | repo containing the `.devcontainer/` |
| `instance_type` | `e2-small` | GCE machine type — `e2-micro` OOMs envbuilder |
| `fallback_image` | `codercom/enterprise-base:ubuntu` | used if the devcontainer build fails |
| `devcontainer_builder` | `ghcr.io/coder/envbuilder:latest` | pin a digest in production |
| `dotfiles_uri` | `https://github.com/hironow/dotfiles.git` | extra `coder dotfiles install` on top |

## Differences from upstream `coder/coder/examples/templates/gcp-devcontainer`

- `default repo_url` -> `hironow/dotfiles.git`
- `default project_id` -> `gen-ai-hironow`
- `gcp_region.regions` -> `["asia", "us", "europe"]` (asia first)
- `default instance_type` -> `e2-small` (upstream's `e2-micro`
  is 1 GiB RAM and OOMs envbuilder)
- `coder_agent.main` references in code-server / jetbrains modules
  -> `coder_agent.dev[0]` (upstream's `.main` is undeclared — likely
  copy/paste rot)
- `dotfiles_uri` parameter added; agent `startup_script` runs
  `coder dotfiles ${uri}` if non-empty

## Smoke

After `cdr create my-ws`:

```bash
cdr workspaces list                     # status: starting -> running
cdr ssh my-ws -- just --list            # JustSandbox recipes available
cdr ssh my-ws -- mise --version         # mise installed via the Dockerfile
cdr ssh my-ws -- ls -la .devcontainer   # devcontainer file present
```
