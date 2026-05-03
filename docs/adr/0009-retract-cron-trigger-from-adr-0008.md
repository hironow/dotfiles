# 0009. Retract the systemd-timer cron trigger from ADR 0008

**Date:** 2026-05-03
**Status:** Accepted (2026-05-04 — cron / systemd-timer infrastructure was reverted in PR #76 and is intentionally absent from the current implementation; operator-pulled `cdr-job` / `cdr-exec` paths in `exe/scripts/` remain the sole job entry points)
**Supersedes:** [0008](./0008-event-driven-workspace-runner.md) (partial — see Decision)

## Context

ADR 0008 (Proposed, 2026-05-03) introduced an "event-driven Coder
workspace runner" composed of three decisions:

1. A `dotfiles-job` headless workspace template that runs one
   command per workspace and exits.
2. Two trigger sources for that template:
   - **Shell** — operator runs `cdr-job <name> -- <cmd>` on the Mac.
   - **Coder-VM systemd timer** — `.timer` units on the control-
     plane VM call the same wrapper at a configured cadence.
3. Workload-pushes-its-own-result: each job emits its artifact
   (PR comment / GCS object / journalctl) itself; the runner is
   stateless.

Decisions 1 and 3 + the shell trigger from 2 were implemented in
PR #70 / #71, including the warm-reuse `cdr-exec` amendment.

The **systemd-timer trigger** from decision 2 was implemented in
PR #72 (heartbeat + `coder-cron-run` helper + admin-token Secret
Manager shell) and PR #74 (`coder-cron-spawn-job` wrapper +
`coder-cron-tofu-plan.{service,timer}` + workspace-side
`cron-tofu-plan.sh` + state-bucket / passphrase IAM + `opentofu`
pin in mise + dev container feature).

After landing, the operator surfaced two concerns that justify
retracting the systemd-timer half:

1. **Cross-layer coupling.** The cron path runs:
   `Coder VM systemd → spawn workspace via Coder API
   (Coder embedded Terraform owns workspace lifecycle) →
   inside that workspace, OpenTofu reads the L1 stack`. This puts
   an L1 OpenTofu cron config "on top of" a workspace instance
   whose lifecycle is owned by Coder's embedded Terraform —
   distinct state files, but conceptually the cron is bypassing
   Coder's workspace-management plane to inject behaviour.

2. **No concrete recurring use case (yet).** ADR 0008 listed
   `tofu plan`, `just lint`, agent task as candidate use cases,
   but none is currently a real recurring need. The boot-tax cost
   (~6 min per nightly fire for the ephemeral pattern) and the
   operational noise (a new `tofu-plan-YYYYMMDD-HHMMSS` workspace
   in the Coder UI every night) are not justified by speculative
   demand.

## Decision

**Retract the systemd-timer trigger from ADR 0008**. The shell
trigger and the workspace template (`dotfiles-job` + `cdr-job` +
`cdr-exec`) survive unchanged — they remain the operator-facing
way to run a one-shot job in an ephemeral or warm-reuse workspace.

What lands in this ADR's commit:

- **Reverted (full).** PR #72 (step 3 scaffolding) and PR #74
  (step 4 nightly `tofu plan`) are reverted as a unit. This
  removes:
    - `coder-cron-{run,spawn-job}` helpers from the VM
    startup_script
    - `coder-cron-heartbeat.{service,timer}` and
    `coder-cron-tofu-plan.{service,timer}` units
    - `/etc/default/coder-cron` env file
    - `exe/scripts/cron-tofu-plan.sh` workspace-side script
    - `google_secret_manager_secret.exe_coder_admin_token` +
    its IAM grant
    - `google_secret_manager_secret.exe_tofu_encryption_passphrase`
        - its IAM grant
    - `google_storage_bucket_iam_member.exe_workspace_state_bucket_admin`
    - `mise.toml` `opentofu` pin
    - `.devcontainer/features/dotfiles-tools/install.sh`
    `opentofu` pin
    - 14 regression tests added by PR #72 + PR #74
    - All runbook + architecture + scripts/README sections
    documenting the cron path

- **Retained (untouched).** PR #70 / PR #71 contributions:
    - `exe/coder/templates/dotfiles-job/` template
    - `exe/scripts/cdr-job` (pure ephemeral)
    - `exe/scripts/cdr-exec` (warm reuse, per ADR 0008 amendment)
    - `cdr-header`, `cdr` wrapper

- **ADR 0008 status updated** to `Superseded by 0009 (partial —
  trigger source 2)` per CLAUDE.md ADR rules.

## Consequences

### Positive

- **No cross-layer coupling.** No OpenTofu cron config sits on
  top of Coder-managed workspace instances.
- **No nightly boot tax.** The Coder UI stays clean of
  cron-spawned workspace history; no SPOT minutes burned on a
  speculative use case.
- **Smaller attack surface.** Two empty Secret Manager shells
  with IAM grants are removed; the Coder VM SA's ability to
  decrypt state and the workspace SA's write access to the
  state bucket are both withdrawn.
- **Simpler operator mental model.** Job execution is always
  operator-pulled (`cdr-job` / `cdr-exec`), never auto-pushed.

### Negative

- **No off-hours automation.** Anyone who wanted "a nightly
  `tofu plan` lands in GCS without manual intervention" has to
  build it themselves or wait for a future ADR. The bar for
  re-introducing cron is now higher: a concrete repeating
  workload, not a speculative slot.
- **Retain-but-unused warm-reuse runner pattern.** ADR 0008's
  amendment described a long-lived `runner` workspace as the
  warm-reuse anchor; it remains a documented operational
  pattern but is unanchored to any auto-trigger.

### Neutral

- **PR #75 (justfile env-var check fix) is unrelated to cron**
  and is unaffected by this revert. Independent of this ADR.
- **PR #71's amendment** (cdr-job polling fix + cdr-exec) is
  retained; it was a fix to the operator-shell-triggered path
  which we keep.

## When (and how) to re-introduce cron

If a real recurring use case appears, prefer **per-job ADRs** over
re-adopting the generic systemd-timer-spawns-workspace pattern:

- **L1 ops cron** (e.g. nightly `tofu plan`, log-rotation,
  backup): run directly on the Coder VM. No workspace involved,
  no cross-layer coupling. Coder VM SA gets only the IAM it
  needs for that one job. Install `tofu` on the VM with the same
  pinned-tag + sha256 hardening as the Coder server (ADR 0007).

- **Agent-task cron** (e.g. nightly `claude` reviews open PRs):
  use the warm-reuse runner pattern from ADR 0008's amendment
  (`cdr-exec runner -- <cmd>`), not pure-ephemeral. The boot tax
  for a fresh agent workspace per fire is the same ~6 min wall-
  clock penalty that prompted the cdr-exec amendment in the
  first place.

Each future cron decision lands in its own ADR with concrete
benchmarks and a defined rollback condition.
