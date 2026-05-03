# Coder template — dotfiles-job (ephemeral runner)

Headless workspace template for running a single command and
exiting. Designed per [ADR 0008](../../../../docs/adr/0008-event-driven-workspace-runner.md)
to give the operator a GitHub-Actions-style ephemeral runner
without GitHub Actions in the loop.

Caller passes the command via the `job_command` parameter; the
agent's startup_script runs it then the workspace stops. The
[`cdr-job`](../../../scripts/cdr-job) wrapper handles the
create-run-delete cycle with a `trap` so the workspace is always
torn down.

## Push

```bash
cdr templates push exe-dotfiles-job \
  -d exe/coder/templates/dotfiles-job \
  --variable project_id=gen-ai-hironow \
  --variable workspace_sa_email=$(just exe-output -raw exe_workspace_sa_email) \
  --variable coder_internal_url=$(just exe-output -raw coder_internal_url) \
  --variable image=$(just exe-output -raw artifact_registry_repo)/devcontainer:main \
  --yes
```

## Run a job

```bash
cdr-job hello -- 'echo hello $(hostname); date'
cdr-job tofu-plan -- 'cd /root/dotfiles/tofu/exe && just exe-plan'
```

`cdr-job` polls the workspace agent until the startup_script
exits, streams logs, then deletes the workspace. The trap
handler also deletes on SIGINT / SIGTERM / failure.

## Image and tool set

The job runs inside the same prebuilt dev container image
(`devcontainer:main`) as the interactive `dotfiles-devcontainer`
template, so the same tools are on PATH (just / mise / uv /
gcloud / 5 AI CLIs / node / etc.).

## Related docs

- [`../../../../docs/adr/0008-event-driven-workspace-runner.md`](../../../../docs/adr/0008-event-driven-workspace-runner.md)
- [`../dotfiles-devcontainer/README.md`](../dotfiles-devcontainer/README.md) — sibling interactive template
- [`../../../scripts/cdr-job`](../../../scripts/cdr-job)
- [`../../../docs/runbook.md`](../../../docs/runbook.md)
