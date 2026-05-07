# 0011. exe-coder workspace VM multi-project systemd env delivery

**Date:** 2026-05-07
**Status:** Accepted

## Context

The runops-gateway side of multiplex Phase α is complete (issues
0009 / 0011 / 0008 / 0006 / 0007 / 0012 all merged on develop): the
gateway has a project registry, Slack `/agent --project=<id>` flag,
multi-mode dmail-receiver / dmail-emitter routing, and an HTTP admin
endpoint for production registry CRUD. What remains is the
workspace-VM side — the consumer of `PHONEWAVE_OUTBOX_DIRS_BY_PROJECT`
and friends.

Two issues track the workspace work:

- exe-coder issue 0006 — pin a `~/projects/<project_id>/.phonewave/{outbox,archive}`
  directory layout so daemons and tools share the same filesystem
  grammar.
- exe-coder issue 0010 — deliver multi-mode env vars to the dmail
  systemd units on every workspace boot, replacing the legacy
  single-`/outbox` / single-`/archive` design.

The challenge is that the gateway registry is the source of truth, the
workspace VM is the consumer, and the two run on different hosts. We
need a delivery path that:

1. Picks up new projects without a Coder template push.
2. Survives gateway outages without bricking workspace boots.
3. Cannot be manipulated into hostile filesystem operations by a
   compromised registry response.
4. Stays compatible with the existing `Environment=PHONEWAVE_OUTBOX_DIR`
   wiring so legacy single-project deployments keep working byte-for-
   byte.

## Decision

A new script (`exe/scripts/fetch-projects-env.sh`) runs on every
workspace VM boot. It is idempotent (re-running it is a no-op when no
project list has changed) and fail-soft (no exit path blocks the
workspace from starting).

The script:

1. Reads `RUNOPS_GATEWAY_URL` and `RUNOPS_ADMIN_TOKEN` from the
   environment. If either is empty, it writes empty drop-in files
   (single-mode fallback) and exits 0.
2. `curl --max-time 15` against `${RUNOPS_GATEWAY_URL}/admin/projects?status=active`
   with `Authorization: Bearer ${RUNOPS_ADMIN_TOKEN}`. Any non-success
   path (network failure, missing `jq`, parse failure, empty list)
   results in fallback drop-ins.
3. Validates every `project_id` returned by the gateway against
   `^[a-zA-Z0-9_-]+$` and a 64-char limit — the same regex the gateway
   enforces in `domain.ValidateProjectID`. This is a defence-in-depth
   layer: a misbehaving gateway, a man-in-the-middle, or a tampered
   response cannot inject `,` / newlines / `../` into systemd
   Environment lines or path-traversal sequences into `mkdir`.
4. For each surviving id, `mkdir -p ~/projects/<id>/.phonewave/{outbox,archive}`
   (chmod 0777 to match the existing `/var/lib/phonewave` policy).
5. Writes a `[Service]` + `Environment=PHONEWAVE_OUTBOX_DIRS_BY_PROJECT=...`
   drop-in to `/etc/systemd/system/dmail-receiver.service.d/env.conf`
   and the archive variant to the emitter's drop-in. systemd's
   standard drop-in auto-merge mechanism (man systemd.unit) picks
   them up; no `EnvironmentFile=` directive is needed in the main
   unit body.
6. `systemctl daemon-reload` + `systemctl try-restart` so the daemons
   pick up the new env on workspace boot. The boot path tolerates
   restart failures (legacy `Restart=on-failure` keeps the units
   running on placeholder images).

### Single-mode fallback

The fallback branch writes drop-in files containing only `[Service]`
plus a comment, so systemd merges nothing dynamic. The main unit's
`Environment=PHONEWAVE_OUTBOX_DIR=/outbox` (and the emitter's
`PHONEWAVE_ARCHIVE_DIRS=/archive`) stays effective; the daemons fall
back to `SingleOutboxRouter` / `SingleArchiveRouter` from gateway
issues 0006 and 0007. This is byte-for-byte identical to the
pre-issue-0010 deployment, so workspaces that have never opted into
multi-mode are unaffected by the new code path.

### docker --env-file is not used

Earlier drafts considered piping `env.conf` through `docker run
--env-file ...`, but `docker --env-file` requires `KEY=VALUE` form
which conflicts with systemd's `[Service]` + `Environment=` drop-in
fragment. We instead inject env via systemd's `Environment=` and
`ExecStart=docker run ... -e VAR ...` (variable name only) so docker
inherits the unit's environment. There is one source of truth
(systemd) and one syntax to keep right.

### Token / URL delivery

`runops_admin_token_secret_id` is a Coder template variable carrying
the **resource id** of a Google Secret Manager secret (no
`projects/` prefix). The startup script resolves it via `gcloud
secrets versions access latest --secret="$id"`, pipes the bytes
straight into `env RUNOPS_ADMIN_TOKEN=$_admin_token` (never `echo`),
and unsets the local afterward. The bash variable name is
`_admin_token` so it stays out of process tables visible to non-root
callers.

`runops_gateway_url` is a plain template variable. Its validation
block requires either an empty string (single-mode fallback) or an
`https://` URL — admin tokens must never traverse plaintext.

The workspace SA must have `roles/secretmanager.secretAccessor` on
the secret. This is recorded as a runbook precondition; the IAM
binding itself lives in the gateway-side tofu (or the operator's
stack-specific overlay) because the secret pre-exists the workspace
VM.

### Peer-mode handshake

When multi-mode kicks in, the emitter's drop-in includes
`PHONEWAVE_PEER_RECEIVER_MODE=multi`. The receiver does not need a
symmetric env: receiver-side mismatches surface via the DLQ runbook
and the gateway-side `firestore-integration` and `pubsub-integration`
CI tests. The emitter env is enough to fail-fast a single-mode
emitter pointing at a multi-mode receiver, which would otherwise
silently route every message to the DLQ.

## Consequences

### Positive

- Adding a project to the gateway registry surfaces on every
  workspace boot — no Coder template push, no per-project terraform
  apply.
- Workspace boots cannot be bricked by a gateway outage or a tampered
  response; the fallback path is always available.
- Defence in depth: even if a gateway bug returns a hostile id, the
  workspace-side regex validation rejects it before it reaches systemd
  or `mkdir`.
- Single-mode deployments (gateway URL / admin token unset) are
  byte-for-byte identical to pre-issue-0010, so existing workspaces
  are unaffected.

### Negative

- Workspace boots take a fixed 15-second timeout when the gateway is
  fully unreachable. We accept this; the script logs the fallback
  reason so operators can grep startup logs.
- A single shared admin token covers every workspace VM that opts
  in. Per-VM token issuance is deferred to a future ADR (gateway
  issue 0011 AI agent identity is the most likely vehicle).
- `~/projects/<id>/.phonewave/{outbox,archive}` is `chmod 0777` to
  mirror the existing `/var/lib/phonewave` policy. We track the
  permission tightening as a follow-up; both daemons (uid 65532) and
  the devcontainer user (uid ~1000) need write access today.

### Neutral

- The script is byte-for-byte synchronised with the repo source via
  `file()` in main.tf — operators who restart the daemons later run
  the same code that was committed. Drift is impossible without a
  template push.
- jq is required for response parsing; the Coder devcontainer base
  image already ships it.

## Out of scope

- **Per-VM token issuance** — covered by the future AI agent identity
  ADR.
- **gcloud secrets rotation** — Secret Manager versioning is the
  standard mechanism; the workspace boot picks up `latest` so
  rotations apply on the next reboot.
- **Permission policy tightening** for `~/projects/<id>/.phonewave/`
  beyond `chmod 0777` — depends on a future setgid-based shared-group
  redesign that also affects `/var/lib/phonewave`.

shellcheck for the boot hook is **not** out of scope — the existing
repo CI runs `just lint` (which invokes `shellcheck` on every tracked
`*.sh` file) inside the dev container, so both `fetch-projects-env.sh`
and its smoke harness are gated by the standard lint pipeline.

## References

- runops-gateway ADR 0025 — port/adapter dual strategy
- runops-gateway ADR 0026 — Firestore production deploy
- runops-gateway ADR 0027 / 0028 / 0029 — multiplex metadata carry,
  receiver / emitter routing
- runops-gateway ADR 0030 — HTTP admin endpoint authentication
- exe-coder ADR 0008 — event-driven workspace runner
- `refs/docs/issues/0006-exe-project-directory-convention.md`
- `refs/docs/issues/0010-exe-dmail-daemon-multi-project-env.md`
- `exe/scripts/fetch-projects-env.sh`
- `exe/scripts/test-fetch-projects-env.sh`
- `exe/coder/templates/dotfiles-devcontainer/main.tf` — startup script
    - dmail unit definitions
- `exe/coder/templates/dotfiles-devcontainer/dmail.tofutest.hcl` —
  variable validation gate
