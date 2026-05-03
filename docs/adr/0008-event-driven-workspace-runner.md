# 0008. Event-driven Coder workspace runner (GHA-style without GHA)

**Date:** 2026-05-03
**Status:** Proposed

## Context

Up to ADR 0007 the only consumer of the Coder workspace
template at `exe/coder/templates/dotfiles-devcontainer/` was an
**operator** opening a long-lived dev workspace via `cdr create`,
SSH-ing in, working interactively, then `cdr stop`-ing it later.

The operator now wants a **second consumption mode**: short-lived
ephemeral workspaces that:

- spin up on a trigger (operator running a shell command, or a
  scheduled job),
- run a single workload (an AI agent task, or a CI-style command
  such as `tofu plan`, `just lint`, a migration script),
- emit a result (log + optional artifact pushed to GCS / git),
- self-tear-down (autostop / dormancy expiry).

GitHub Actions is **explicitly out of scope** as a trigger or
runner — the goal is to keep the entire orchestration inside the
existing `exe.hironow.dev` Coder + Tailscale + Cloudflare stack
without paying GitHub-hosted runner minutes or piping secrets
through GitHub Actions.

## Constraints surfaced during research (2026-05)

1. **`coder exp task ...` is experimental.** Coder Tasks (the
   first-party "agent task in ephemeral workspace" feature) lives
   under `/api/experimental/tasks/` as of v2.27. Endpoints and
   the `coder exp task` CLI namespace are documented to change
   before GA. Building the runner on top of Tasks today would
   accept a known breaking-change window.
2. **Coder has no native cron that creates new workspaces.** The
   schedule fields on templates / presets only manage *existing*
   workspaces' autostart / autostop / dormancy. Anything that
   needs "create a new ephemeral workspace at HH:MM" has to live
   outside Coder's data model.
3. **No builtin task-completion webhook.** Result delivery is the
   caller's responsibility (poll `coder ... logs`, or have the
   workload push a PR comment / GCS artifact itself).
4. **CF Access edge gates the public URL.** Anything calling the
   Coder API from outside the tailnet needs the existing CF
   Access service token (the `cdr` wrapper handles this for the
   operator's Mac; new callers reuse the same secret).

## Decision

Adopt a deliberately small surface that avoids the experimental
API and keeps the operator's mental model simple.

### 1. Use **stable workspace API** (not Coder Tasks)

A second template — `exe/coder/templates/dotfiles-job/` —
declares a headless workspace that runs **one command** specified
by the caller and exits. The lifecycle is the standard Coder
workspace API (`coder create` → `coder ssh -- <cmd>` →
`coder delete`); no `coder exp task ...` involvement.

**Why not Tasks**: experimental → breaking-change risk; agent-
prompt-shaped input doesn't fit the CI-style use case (`tofu
plan`, `just lint`); we can adopt Tasks later for the AI-agent
subset once GA, by adding `coder_ai_task` to *this* template
without changing the orchestration surface.

### 2. Trigger sources: shell + Coder-VM systemd timer

Two sources, no others:

- **Shell**: operator runs a `cdr job <name> <args...>` wrapper
  (lives next to `exe/scripts/cdr`). Wraps `coder create` →
  `coder ssh -- <cmd>` → `coder delete`. Same CF Access auth
  chain as `cdr` itself.
- **Coder-VM systemd timer**: a `.timer` unit on the control-
  plane VM (`tofu/exe/coder.tf` startup-script) calls the same
  `cdr job` wrapper from the VM's local shell at the configured
  cadence (e.g., `OnCalendar=*-*-* 09:00:00`). `Persistent=true`
  so a missed run after VM reboot still fires.

**Why VM systemd, not GCP Cloud Scheduler**: the VM is already
provisioned + on the tailnet + has the Coder admin token
mountable from Secret Manager. Cloud Scheduler would add an
extra IAM scope and a public-internet-facing trigger to maintain.

### 3. Result delivery: workload pushes itself

The runner does not collect output. The job script inside the
workspace is responsible for emitting its result somewhere
durable:

- `tofu plan -out=plan.bin && gcloud storage cp plan.bin gs://gen-ai-hironow-tofu-state/jobs/$(date +%F)/plan.bin`
- agent task: `claude` (or whichever) writes a PR comment via
  `gh pr comment` itself
- cron lint: print to stdout, captured by `journalctl -u <unit>`
  on the Coder VM (operator can `journalctl -u <unit>` to read).

This keeps the runner stateless and matches the "agent inside the
workspace pushes its own output" pattern Coder Tasks already
documents.

### 4. Safety bounds (added to the new template)

To prevent runaway VMs / cost leaks if a job hangs or the runner
is killed mid-flight, the `dotfiles-job` template sets:

- `data.coder_workspace.me.start_count` checked → workspace
  declares no resources when `start_count == 0` (clean teardown).
- `coder_metadata` short timeouts on agent metadata so a hung
  workspace surfaces visibly.
- Template-level `default_ttl_ms` short (e.g., 30 minutes) — any
  workspace older than that auto-stops even if `cdr delete` was
  missed.
- `dormancy_threshold_ms` short (e.g., 24 hours) — auto-deletion
  catches anything the autostop missed.
- The runner wrapper always issues `coder delete -y` in a
  `trap` handler so SIGTERM / failure still deletes the
  workspace.

## Out of scope (deliberately)

- **GitHub Actions integration** (`coder/start-workspace-action`,
  `coder/create-task-action`). Avoided per operator request.
- **GitHub webhook receiver.** No PR/issue-driven triggers in
  this iteration. If we want them later, we add a tiny webhook
  endpoint on the Coder VM that calls the same `cdr job` wrapper
  — not a separate runner.
- **Coder Tasks (experimental API).** Re-evaluate after GA. The
  template can grow a `coder_ai_task` resource at that point
  without changing the trigger / teardown surface this ADR pins
  down.
- **Cloud Scheduler / external cron / cron on operator's Mac.**
  All rejected in favour of Coder-VM systemd timer.
- **Result fan-out (Slack / Discord / PR comment via runner).**
  The workload pushes its own output; the runner stays stateless.

## Consequences

### Positive

- **No experimental API dependency.** Stable Coder workspace API
  only; survives Coder version bumps.
- **Reuses existing auth.** Same CF Access service token + Coder
  admin token as the operator's `cdr` wrapper. No new IAM.
- **One mental model.** Operator's Mac and Coder-VM cron both
  invoke the same `cdr job` wrapper.
- **Failure mode is fail-closed.** Trap handler + template TTL +
  dormancy threshold = three independent layers that prevent
  workspace leaks.

### Negative

- **No agent-affordance UI.** Coder Tasks UI (the
  prompt-and-watch pane) is not used; results live in journalctl
  / GCS / wherever the workload pushed them. Operator who wants
  the polished UI will manually invoke `coder exp task` outside
  this runner.
- **systemd timer state is on the Coder VM.** If the VM is
  destroyed (`tofu destroy` of the exe stack), the timers go
  with it. They are re-provisioned on the next `tofu apply`
  because they live in the startup-script.
- **Operator must put the Coder admin token in a new Secret
  Manager secret** (`exe-coder-admin-token`) for the systemd
  timer's shell to fetch. One-time setup; documented in the
  runbook section that lands with the implementation.
- **No PR/issue-driven trigger today.** Adding it later means
  standing up a tiny HTTP receiver on the Coder VM (acceptable
  but a known follow-up).

### Neutral

- The new template duplicates a small amount of HCL with the
  existing `dotfiles-devcontainer` template (image pull, agent
  init, mise + AI CLI bake-in). A shared module can factor that
  later; not worth it for two consumers.
- AI agent jobs (Claude Code, Codex, etc.) use the same job
  wrapper as CI-style jobs; they just call `claude` / `codex`
  inside the workspace instead of `tofu plan`. No code path
  forks for "agent" vs "ci".
