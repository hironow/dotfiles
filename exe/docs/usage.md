# Usage — `cdr` commands

Everything an operator can do against `exe.hironow.dev` from their
Mac. All four commands live in `exe/scripts/` and are symlinked
into `~/.local/bin` by `just exe-cdr-install` (one-time setup).

| Command | Purpose | When to use |
|---|---|---|
| [`cdr`](#cdr) | Generic Coder CLI passthrough with CF Access auth baked in | Anything you would normally do with `coder` (login, list, ssh, templates, create, delete, ...) |
| [`cdr-job`](#cdr-job) | Run one command in a **fresh ephemeral workspace**; teardown on exit | One-shot agent task / CI-style command where state isolation matters |
| [`cdr-exec`](#cdr-exec) | Run one command in an **existing long-lived workspace** (warm reuse) | Repeated short jobs where boot tax dominates and isolation is not required |
| [`cdr-header`](#cdr-header) | Emit CF Access headers for VS Code's Coder extension | Configure VS Code's "Coder: Header Command" setting once |

Auth chain: every command first reads the Cloudflare Access service-
token credentials from Secret Manager (`exe-coder-cli-client-id`
and `exe-coder-cli-client-secret`, cached locally for 5 min), then
exports `CODER_HEADER_COMMAND` so the underlying `coder` CLI emits
the right `CF-Access-*` headers.

## First-time setup

```bash
# Authenticate gcloud (used by cdr to fetch the service-token).
gcloud auth login
gcloud config set project gen-ai-hironow

# Symlink all four scripts into ~/.local/bin.
just exe-cdr-install

# First login. cdr handles all CF Access plumbing internally.
cdr login https://exe.hironow.dev
```

## `cdr`

Transparent passthrough — every `coder` argument works.

```bash
# Templates (operator pushes the workspace template).
cdr templates push exe-dotfiles-devcontainer \
  -d exe/coder/templates/dotfiles-devcontainer \
  --variable project_id=gen-ai-hironow \
  --variable workspace_sa_email=$(just exe-output -raw exe_workspace_sa_email) \
  --variable coder_internal_url=$(just exe-output -raw coder_internal_url) \
  --variable image=$(just exe-output -raw artifact_registry_repo)/devcontainer:main \
  --yes

# Workspaces (operator's interactive dev workspace).
cdr create my-ws --template exe-dotfiles-devcontainer --yes
cdr ssh my-ws.dev
cdr stop my-ws
cdr start my-ws
cdr delete my-ws --yes

# Inspection.
cdr list
cdr show my-ws
cdr templates list
```

## `cdr-job`

Pure ephemeral: a fresh workspace VM, runs one command, gets
deleted (trap-handler on exit). Boot tax ~6 minutes per fire.

```bash
# Quick smoke.
cdr-job hello -- 'echo hello $(hostname); date'

# A `tofu plan` style command.
cdr-job tofu-plan-once -- 'cd /root/dotfiles/tofu/exe && just exe-plan'

# Override the wall-clock budget (default 1800s / 30 min).
CDR_JOB_TIMEOUT_SEC=3600 cdr-job long-job -- '...'

# Keep the workspace alive on failure for debugging.
CDR_JOB_KEEP_ON_FAILURE=1 cdr-job risky -- '...'
```

The first positional argument is the workspace name; everything
after `--` is the command. The command runs as the workspace
agent's startup_script — when it exits, the workspace transitions
to `ready` and the wrapper tears it down.

## `cdr-exec`

Warm reuse: target an EXISTING workspace, start it if stopped,
exec the command via SSH. Boot tax ~10-30 seconds (disk + image
cache survive). State is NOT isolated — `/tmp`, env vars, and
processes from previous invocations may persist.

```bash
# One-time: create the long-lived runner workspace.
cdr create runner --template exe-dotfiles-job \
  --parameter job_command='sleep infinity' --yes

# Then call it as many times as you want.
cdr-exec runner -- 'cd /root/dotfiles/tofu/exe && just exe-plan'
cdr-exec runner -- 'cd /root/dotfiles && just lint'
cdr-exec runner -- 'claude --print --output-format json "review PR 123"'

# Stop the runner when done (preserves disk + image cache for next start).
cdr stop runner
```

Pick `cdr-job` over `cdr-exec` when isolation matters (one-shot
agent task, secret-handling command); `cdr-exec` when latency
matters and isolation does not.

## `cdr-header`

Helper for VS Code's Coder extension. After `just exe-cdr-install`
symlinks `cdr-header` into `~/.local/bin`, point the extension at
it:

`Settings → Coder: Header Command → ~/.local/bin/cdr-header`

This makes VS Code emit the same `CF-Access-Client-Id=...` /
`CF-Access-Client-Secret=...` headers `cdr` does, so the extension
can reach `https://exe.hironow.dev` through Cloudflare Access.

## Cron is intentionally not provided

The earlier ADR 0008 systemd-timer cron was retracted in
[ADR 0009](../../docs/adr/0009-retract-cron-trigger-from-adr-0008.md).
Job execution is always operator-pulled (`cdr-job` / `cdr-exec`),
never auto-pushed. To run a job on a schedule today: drive it from
the operator's Mac with `cron` / `launchd` / `at`, calling
`cdr-job` or `cdr-exec`. If a recurring use case becomes load-
bearing, a per-job ADR will reintroduce a narrowly-scoped trigger.

## Related

- [`runbook.md`](./runbook.md) — full operator playbook (apply,
  smoke, rotate keys, push template, bump Coder)
- [`architecture.md`](./architecture.md) — component map + trust
  boundaries
- [`../scripts/README.md`](../scripts/README.md) — script-level
  inventory (cdr internals, CF Access secret cache, ...)
