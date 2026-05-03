# Coder template — dotfiles-job (ephemeral headless runner)

Headless workspace template for running a single shell command in a
fresh GCE VM and tearing the VM down once the command exits. The
operator's [`cdr-job`](../../../scripts/cdr-job) wrapper drives the
create-poll-stream-delete cycle.

This template ships **no interactive parameters** and **no template-
level TTL**. The caller passes the command via the `job_command`
template parameter at create-time; lifecycle is owned by the wrapper's
`trap` handler. See *Lifecycle and cost protection* below.

ADR: [`../../../../docs/adr/0008-event-driven-workspace-runner.md`](../../../../docs/adr/0008-event-driven-workspace-runner.md)
(status: Superseded by 0009 partial — cron trigger source retracted,
operator-pulled job runner retained)

## Push the template

```bash
cdr templates push exe-dotfiles-job \
  -d exe/coder/templates/dotfiles-job \
  --variable project_id=gen-ai-hironow \
  --variable workspace_sa_email=$(just exe-output -raw exe_workspace_sa_email) \
  --variable coder_internal_url=$(just exe-output -raw coder_internal_url) \
  --variable image=$(just exe-output -raw artifact_registry_repo)/devcontainer:main \
  --yes
```

| Variable | Default | Notes |
|---|---|---|
| `project_id` | `gen-ai-hironow` | GCP project hosting the job VMs |
| `workspace_sa_email` | (required) | `just exe-output -raw exe_workspace_sa_email` — same SA as the interactive devcontainer template |
| `coder_internal_url` | `http://exe-coder:7080` | tailnet-internal MagicDNS endpoint the job's coder-agent uses to reach the Coder server (bypasses CF Access) |
| `workspace_authkey_secret_id` | `exe-tailscale-workspace-authkey` | Secret Manager secret holding the `tag:exe-workspace` tailnet authkey |
| `image` | `asia-northeast1-docker.pkg.dev/gen-ai-hironow/dotfiles/devcontainer:main` | prebuilt dev container image; pin to `:<git-sha>` for reproducible runs |

## Run a job

The intended entry point is the [`cdr-job`](../../../scripts/cdr-job)
wrapper:

```bash
cdr-job hello -- 'echo hello $(hostname); date'
cdr-job tofu-plan -- 'cd /root/dotfiles/tofu/exe && just exe-plan'
```

`cdr-job` issues:

```bash
coder create <job-name> --template exe-dotfiles-job \
  --parameter "job_command=<command...>" --yes
```

then polls the workspace agent until the agent's startup_script exits,
streams the agent log to stdout, and finally `coder delete -y`s the
workspace from a `trap` handler.

You *can* also `cdr create ... --template exe-dotfiles-job` manually —
but you become responsible for the delete step. The wrapper exists
exactly to make that hard to forget.

## Lifecycle and cost protection

This template **does not** set `default_ttl_ms`, `dormancy_threshold_ms`,
or any other auto-stop policy. The protection chain is:

1. **Happy path** — the agent's startup_script runs the
   `job_command`, exits, and `cdr-job`'s post-stream `coder delete -y`
   tears the VM down (~30s).
2. **SIGINT / SIGTERM** — `cdr-job`'s `trap '... coder delete -y' EXIT
   INT TERM` fires and the VM is torn down.
3. **Wrapper crash (SIGKILL, OOM, kernel panic on operator host)** —
   no trap fires; the VM **leaks**. Operator must:

   ```bash
   cdr workspaces list                   # find the orphan
   cdr delete <job-name> --yes
   ```

   Cost exposure of one leak is bounded by GCE preemption (~24h on
   `e2-small` in `asia-northeast1`); a leaked VM stops itself by the
   next maintenance event but is not deleted automatically. See ADR
   0008 *"Lifecycle and cost protection"* for why we accept this
   tradeoff over template-level TTL (TTL would race with long-running
   jobs like `tofu-plan` and surface as silent failures).
4. **`just exe-teardown vm`** — operator escape hatch that destroys
   every workspace VM in the project regardless of state.

## What's in the job VM

The job VM is a debian-12 GCE `e2-small` (zone `asia-northeast1-a`)
that:

1. Joins the tailnet with `tag:exe-workspace` (Secret-Manager-backed
   authkey).
2. `docker pull`s the prebuilt dev container image from Artifact
   Registry.
3. `docker run`s the image with `--network host`, mounting
   `/home/<user>:/root` and `/var/run/docker.sock`.
4. The container's PID 1 is `coder agent`, which runs the
   `job_command` as its `startup_script`.

Tools available inside the container (from the prebuilt image):

| Category | Tools |
|---|---|
| Core | `just`, `mise`, `uv`, `gcloud`, `git`, `docker` (cli-only) |
| Lint / format | `ruff`, `shellcheck`, `markdownlint-cli2`, `prek` |
| Runtime | `node` 24.15.0, `python` 3 (mise-pinned) |
| AI agent CLIs | `codex`, `gemini`, `claude`, `copilot`, `pi` |

Versions are pinned in [`mise.toml`](../../../../mise.toml) per
[ADR 0006](../../../../docs/adr/0006-mise-version-pinning.md).
The mise data dir is `/opt/mise`, baked into the image at build time
and reachable with `MISE_OFFLINE=1`.

## Smoke

```bash
# minimal: spin up, run hostname, tear down (~60s end-to-end)
cdr-job smoke -- 'echo hello $(hostname); date'

# verify the same tool set as the interactive workspace
cdr-job smoke-tools -- '
  for cli in just mise uv gcloud codex gemini claude copilot pi; do
    printf "%s: " "$cli"
    "$cli" --version 2>&1 | head -1
  done'
```

## Differences from the sibling devcontainer template

| Aspect | `dotfiles-job` (this) | `dotfiles-devcontainer` |
|---|---|---|
| Interactive params | none | `instance_type`, `dotfiles_uri` |
| Lifecycle | wrapper-trap (this README §Lifecycle) | TTL via `coder templates edit` |
| Hostname | `<ws>-job` | `<ws>-ws` |
| `coder dotfiles` install | no | yes (operator's repo cloned over the prebuilt image) |
| Default machine type | `e2-small` (fixed) | `e2-small` (operator-overridable) |

## Related docs

- [`../../../scripts/cdr-job`](../../../scripts/cdr-job) — wrapper
  source (read this for the trap semantics)
- [`../dotfiles-devcontainer/README.md`](../dotfiles-devcontainer/README.md) —
  sibling interactive template
- [`../../../docs/runbook.md`](../../../docs/runbook.md) — operator
  workflow including job-leak recovery
- [`../../../../docs/adr/0008-event-driven-workspace-runner.md`](../../../../docs/adr/0008-event-driven-workspace-runner.md)
- [`../../../../docs/adr/0009-retract-cron-trigger-from-adr-0008.md`](../../../../docs/adr/0009-retract-cron-trigger-from-adr-0008.md) —
  why this template no longer has a cron trigger
