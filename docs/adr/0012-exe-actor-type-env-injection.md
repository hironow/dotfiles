# 0012. exe-coder workspace VM RUNOPS_ACTOR_TYPE env injection (per caller path)

**Date:** 2026-05-09
**Status:** Accepted

## Context

The runops-gateway `0011 architectural pin` (= AI agent cannot approve another AI agent's 4-eyes approval) is complete on the gateway side: ADR 0035 (architectural pin), ADR 0036 (Phase 4a effective_requester_actor_type rule), and ADR 0037 (4-axes producer-side classification) are all main-merged.

The producer-side rollout is also complete on the 4 producer tools that emit D-Mails (sightjack / paintress / amadeus / dominator — phonewave is relay-only and out of scope per phonewave ADR 0005). Each producer reads `RUNOPS_ACTOR_TYPE` env via the canonical `internal/platform/actortype/` helper and injects `metadata.requester_actor_type` (+ optional `metadata.initiating_actor_type` when actor=workspace-daemon) into D-Mail frontmatter. Invalid env values (= not one of the 4 canonical values: `human-operator` / `gateway-service` / `ai-agent` / `workspace-daemon`) cause the emit to fail with no filesystem side effect — silent escalation guard per gateway ADR 0037 §Producer-side validation.

What is missing is the **delivery path** for `RUNOPS_ACTOR_TYPE` itself. The producer helpers read the env, but if the env is not set when the producer runs, two failure modes happen:

1. **HIGH severity 4-eyes approval path**: gateway ADR 0036 fails closed at the 4-layer gate. Every HIGH approval stops working until the env is delivered.
2. **Non-HIGH severity path (dispatch / canary)**: the gateway-side migration window applies a `CallerHumanOperator` fallback, which means **the audit trail records every AI-driven dispatch as `human-operator`**. This is a silent classification failure that survives until the eventual fail-closed flip (gateway ADR 0038 candidate).

The challenge is that the producer tools run in **multiple caller contexts** on the workspace VM, and each context has a different injection layer:

- `dmail-receiver` and `dmail-emitter` daemons run inside Docker containers spawned by host-OS systemd units. systemd `Environment=` lines are merged from the unit + drop-ins, but the `docker run` invocation explicitly allowlists which env vars get propagated into the container. Drop-in alone is insufficient.
- `cdr-job` is a wrapper script, but the actual command runs inside an ephemeral Coder workspace via the agent startup_script and a separate `docker run` for the devcontainer image. Adding `--env` to the wrapper does not propagate into the eventual `job_command` execution process.
- `cdr-exec` is a wrapper that calls `coder ssh -- sh -c "$EXEC_COMMAND"`. The wrapper layer can prefix the command directly with `env RUNOPS_ACTOR_TYPE=...`, and that does propagate.
- AI agent runners launched locally (e.g., `claude-code`) have a fundamentally different concern: a globally-set `RUNOPS_ACTOR_TYPE=human-operator` in `~/.zshenv` would silently misclassify every AI invocation. Context-specific override is required.

Refs `0020-exe-actor-type-env-injection.md` enumerated these mismatches and broke the work into a per-path table. This ADR captures the chosen design contract.

## Decision

`RUNOPS_ACTOR_TYPE` is injected per caller path with **path-specific layer** discipline, not a single global wrapper. There are 4 in-scope paths and 2 explicitly out-of-scope paths.

### Path A — `dmail-receiver` / `dmail-emitter` daemons (workspace-daemon)

Two-layer injection in `exe/coder/templates/dotfiles-devcontainer/main.tf`:

1. systemd unit body adds `Environment=RUNOPS_ACTOR_TYPE=workspace-daemon` next to the existing `Environment=` lines (the dmail-receiver section currently ends at the OTEL block; the same pattern is mirrored in dmail-emitter).
2. The `docker run -e RUNOPS_ACTOR_TYPE` allowlist entry is appended to the `ExecStart=docker run ...` command for both units. This is the layer codex specifically flagged: drop-in / `Environment=` alone does not reach the container because the dotfiles unit declares each propagated env var explicitly via `-e VAR` (value-less form so docker inherits the unit env).

Rationale for hardcoding the value at the systemd layer (not via `fetch-projects-env.sh` drop-in): the env is **constant per workspace VM** (= every dmail daemon on the VM is, by definition, a `workspace-daemon`). It does not vary per project. ADR 0011's drop-in path is reserved for project-scoped multi-mode env (`PHONEWAVE_OUTBOX_DIRS_BY_PROJECT` and friends).

Initiating-actor carry (`RUNOPS_INITIATING_ACTOR_TYPE`) is **not** set at this layer because the daemons currently relay D-Mails (phonewave ADR 0005 invariant) rather than emitting their own. If a future feature has the daemons emit alerts (= phonewave ADR 0005 §2 deferred path), initiating-actor will be added at the same two layers.

### Path B — `cdr-job` (AI agent dispatch via ephemeral workspace)

`dotfiles-job/main.tf` does **not** have a systemd unit body. The runtime layers in the job template are (a) the VM startup script that runs `docker run` to launch the devcontainer image, and (b) the in-container `coder_agent.job.startup_script` that runs `${data.coder_parameter.job_command.value}` after the agent is up. Injection happens at both layers in `exe/coder/templates/dotfiles-job/main.tf`, not in the `cdr-job` wrapper script:

1. The VM startup script `docker run` invocation adds `--env RUNOPS_ACTOR_TYPE=ai-agent` (value form, not value-less `-e RUNOPS_ACTOR_TYPE`). Value-less form would require the VM-side shell to have `RUNOPS_ACTOR_TYPE` exported beforehand, which the cdr-job VM does not.
2. The agent `startup_script` (in-container) adds `export RUNOPS_ACTOR_TYPE=ai-agent` before invoking `${data.coder_parameter.job_command.value}`. Even though the docker run already injected the env into the container, restating it in the agent startup_script makes the contract self-evident and survives any future restructuring that splits the agent into a separate container.

Two layers are needed because the boundary between docker run env propagation and the agent's startup_script execution context is not always identical (e.g., when the agent runs as a separate process group or under a sub-shell that scrubs env). Belt-and-suspenders: both layers carry the value verbatim.

`RUNOPS_INITIATING_ACTOR_TYPE` is not set by default. If a human operator wants to be recorded as the initiator, they pass an explicit `--initiating-actor=human-operator` (or equivalent) flag through `cdr-job`'s parameter chain in a follow-up enhancement. Out of scope for this ADR.

### Path C — `cdr-exec` (long-lived workspace, human operator)

Injection in `exe/scripts/cdr-exec`:

1. The `coder ssh "$WS_NAME" -- sh -c "$EXEC_COMMAND"` invocation is rewritten to prefix the command with `env RUNOPS_ACTOR_TYPE=human-operator` **always**, regardless of any pre-existing `RUNOPS_ACTOR_TYPE` in the operator's parent shell. `cdr-exec` is by contract a human-operator dispatch path; honoring an inherited `ai-agent` value (e.g., from a runner the operator forgot to exit) would silently misclassify the action.

The override is hardcoded at the wrapper level. If a future feature needs `cdr-exec` to forward an alternate caller-type, that requires an explicit flag + canonical value validation (= 4-canonical-value gate inside `cdr-exec` before forwarding), and is out of scope for this ADR.

This path completes inside the wrapper because `cdr-exec`'s contract is "execute one command in an existing workspace and stream output back." There is no template / startup_script layer below it that would otherwise lose the env.

### Path D — Local AI agent runners (e.g., `claude-code`)

`claude-code` and similar AI runners must override `RUNOPS_ACTOR_TYPE=ai-agent` at runner-launch time, regardless of the host shell's value. The override happens in the runner-specific launcher (likely a shell function or wrapper script in dotfiles, scope to be confirmed), not in `~/.zshenv`.

Explicit non-decision: **a global `~/.zshenv` / `.envrc` default of `RUNOPS_ACTOR_TYPE=human-operator` is rejected.** A global default that is "usually right" but silently mis-classifies AI invocations whenever the runner forgets to override it would create the exact audit-laundering risk that gateway ADR 0035 was written to prevent. Documentation in the runbook will instead instruct operators to export `RUNOPS_ACTOR_TYPE=human-operator` explicitly when running the 5 tools directly from the local Mac.

### Path E — phonewave courier daemon (out of scope)

phonewave is relay-only (= phonewave ADR 0005). The 4 producer tools have already injected actor-type metadata into the D-Mail at emit time; phonewave's job is to preserve those bytes during relay, not to inject anything new. No env is needed at this layer today. The deferred case in phonewave ADR 0005 §2 (= daemon-generated emit) re-opens this.

### Path F — gateway-service internal emit (out of scope)

Gateway-internal D-Mail emit paths attest `actor_type=gateway-service` from inside the gateway process, not via env. This ADR does not touch them.

### Migration semantics

- Existing env vars on every path are not modified or unset by this ADR. Only `RUNOPS_ACTOR_TYPE` (and, in Path B's eventual extension, `RUNOPS_INITIATING_ACTOR_TYPE`) are added.
- `RUNOPS_ACTOR_TYPE` is always set explicitly per context. Inheriting whatever the parent shell happened to have is forbidden because actor classification is a security control: silent inheritance produces silent misclassification.
- No ADR for `~/.zshenv` defaults is created. The runbook covers the local-direct case as a documented operator action, not as a system default.
- Until all 4 in-scope paths are deployed, the gateway non-HIGH path's migration-window fallback continues to apply. The eventual fail-closed flip is tracked separately as the gateway ADR 0038 candidate referenced in refs `0018`.

## Enforcement inventory

This ADR pins a system-level invariant (= the actor classification cannot be silently misclassified during boot or dispatch). Per the .claude/CLAUDE.md ADR template requirement:

### Entry points

- `exe/coder/templates/dotfiles-devcontainer/main.tf` — dmail-receiver + dmail-emitter unit bodies + `docker run` allowlists (Path A)
- `exe/coder/templates/dotfiles-job/main.tf` — devcontainer startup_script + `docker run` allowlist (Path B)
- `exe/scripts/cdr-exec` — `coder ssh` command prefix (Path C)
- `exe/scripts/<claude-code-launcher>` — runner-specific override (Path D, location TBD per scope follow-up)

### Persistent / carried data needed at each enforcement point

- `RUNOPS_ACTOR_TYPE` ∈ {`human-operator`, `gateway-service`, `ai-agent`, `workspace-daemon`} (4 canonical values, exact match)
- `RUNOPS_INITIATING_ACTOR_TYPE` (optional, only when actor=workspace-daemon and a human operator initiated the action) — Path B follow-up only

### Bypass candidates

- systemd drop-in alone (ADR 0011 path) without `docker run -e` — Path A first-failure mode, mitigated by two-layer test
- `coder create --env` on `cdr-job` wrapper — does not propagate to job_command process, mitigated by template-side injection in Path B
- inheriting `RUNOPS_ACTOR_TYPE` from parent shell — mitigated by explicit per-context set, never via default
- a forgotten `~/.zshenv` default of `human-operator` masking AI invocations — mitigated by deliberate non-decision (Path D)
- env value typo (e.g., `ai_agent` instead of `ai-agent`) — already mitigated by producer-side `ErrInvalidActorType` in actortype helper (gateway ADR 0037 §Producer-side validation), but operators should treat producer emit-fail as a hard signal, not retry without a fix

### Tests proving coverage

| Test | Layer | Verifies |
|---|---|---|
| `printenv RUNOPS_ACTOR_TYPE` inside dmail-receiver container | Path A integration | container process sees `workspace-daemon` (drop-in + docker run -e both present) |
| `printenv RUNOPS_ACTOR_TYPE` inside dmail-emitter container | Path A integration | container process sees `workspace-daemon` |
| `cdr-job <name> -- printenv RUNOPS_ACTOR_TYPE` | Path B end-to-end | job_command process sees `ai-agent` (template startup_script + docker run -e both present) |
| `cdr-exec <ws> -- printenv RUNOPS_ACTOR_TYPE` | Path C wrapper | command prefix produces `human-operator` |
| Path D launcher integration test (TBD) | Path D | claude-code child process always sees `ai-agent` regardless of parent shell value |

Implementation lands in follow-up PRs (one per path is permissible). This ADR is the design contract; mapping ADR Acceptance to a single rollout PR is intentionally not required — codex review of each follow-up PR will check this ADR's enforcement inventory as the spec.

## Consequences

### Positive

- Each caller path has a verified end-to-end env path, not a partially-wired drop-in.
- Audit-laundering via global `human-operator` default is structurally prevented.
- Producer-side actor-type emit (refs `0018` rollout: sj #205 / pt #207 / am #208 / pw #143 main merged + dom #21 OPEN) becomes operationally complete as soon as the systemd + template layers ship.
- Aligns with ADR 0011's "no `--env-file`, env via `Environment=` + `-e VAR`" pattern.

### Negative

- Touch points span 3 different files (dotfiles-devcontainer/main.tf, dotfiles-job/main.tf, exe/scripts/cdr-exec) plus a future Path D launcher. There is no single place to grep for the env contract; this ADR is the contract.
- A typo in `Environment=` value (e.g., `workspace_daemon` instead of `workspace-daemon`) silently disables the daemon's emit until producer emit-fail telemetry surfaces it. Mitigation: producer-side `ErrInvalidActorType` will fail loudly during the first emit.
- Path D scope (claude-code launcher) is not yet finalized in this ADR. The follow-up may require a separate ADR if the launcher lives in a different repo.

### Neutral

- The dotfiles `~/.zshenv` is intentionally left unchanged; operators running 5 tools directly from the local Mac must `export RUNOPS_ACTOR_TYPE=human-operator` themselves (or wrap the invocation with `env`). This is documented in the runbook, not enforced via shell init.
- Eventual gateway ADR 0038 (= non-HIGH path fail-closed flip) is gated on this ADR's full rollout + observed `requester_actor_type=empty` telemetry hitting zero. The flip itself is gateway-side and not part of this ADR.
- The ADR follows existing dotfiles ADR cadence (Proposed → Accepted via codex review). Implementation PRs reference this ADR by number.
