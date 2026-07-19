# 0034. exe stack mothball mode (`stack_mode`) + AR retention bound

**Date:** 2026-07-20
**Status:** Accepted

## Context

Measured idle run-rate of the exe stack (2026-07, JPY catalog prices,
control-plane VM already destroyed via `just exe-down`) was ~JPY
3,530/mo: Cloud SQL `db-f1-micro` running 24/7 (JPY ~2,000 incl.
disk), a leftover Coder-workspace boot disk (JPY ~1,070), and the AR
`dotfiles` repo at ~21 GiB (JPY ~340). Three structural problems sat
under that number:

1. **Mothballing was not representable in config.** `just exe-down`
   is a targeted destroy, so config and state diverge permanently: a
   full `tofu apply` would silently resurrect the VM. The actual
   "stopped" posture lived nowhere except the operator's memory.
2. **AR retention never fired.** ADR 0002 capped history with a KEEP
   most-recent-10 plus DELETE-untagged-after-7d. Every publish tags
   the image (`main` + `<sha>`), so the UNTAGGED condition never
   matched, and KEEP policies by themselves delete nothing —
   `keep_count` is a floor, not a cap. 20+ tagged versions (~21 GiB)
   accumulated since 2026-05.
3. **Cloud SQL had no declarative off-switch**, and the uptime check +
   alert page the operator forever while the control plane is
   deliberately down.

## Decision

### `stack_mode` variable

A required, no-default `stack_mode ∈ {"active", "mothballed"}`
(operator states intent in gitignored `terraform.tfvars`) gates:

- `google_compute_instance.exe_coder` — `count = active ? 1 : 0`
- `google_monitoring_uptime_check_config` / `_alert_policy` — same gate
- Cloud SQL `settings.activation_policy` — `active ? "ALWAYS" : "NEVER"`

Outputs that read counted resources use null-safe forms:
`one(resource[*].attr)`, and for interpolations the URL is built
*inside* a comprehension (`one([for i in … : "http://${i.name}:7080"])`)
— interpolating `one(...)` directly errors the whole plan at count=0
("Cannot include a null value in a string template", verified on
OpenTofu 1.12.3).

Transitions run through dedicated justfile recipes.
`exe-plan-mothball` / `exe-apply-mothball` cover the 4-resource
google-provider-only slice (SQL, AR, uptime, alert) via a saved plan
file, so no Cloudflare/Tailscale tokens are needed; `exe-apply-wake`
starts Cloud SQL alone before a full apply, because **a full refresh
against a stopped instance can 400 on `google_sql_user` reads** —
while mothballed, drift-check with `tofu plan -refresh=false` or wake
first. A mothball-state full plan is therefore explicitly *not* a
supported operation; convergence is guaranteed for the transition
plans, not steady-state refreshes.

### AR retention (partially supersedes ADR 0002)

ADR 0002's "cap to 10 most-recent" mitigation is replaced by:
KEEP most-recent-3 + explicit KEEP on the `main` tag + DELETE
anything older than 30 days (any tag state). The `main` KEEP exists
because workspaces pull `:main`; without it a >30-day publish gap
would delete the rolling tag (recovery: `workflow_dispatch` on
publish-devcontainer). Steady state is max(3, builds in the last 30
days) plus the `main` version — ~3–4 GiB when idle.

### Enforcement

`tofu validate` does not evaluate values and cannot catch the
null-template class. A config-evaluation gate via `tofu test` +
`mock_provider` was spiked and is blocked upstream: OpenTofu 1.12.3
panics in `providerForTest.ImportResourceState` on configs containing
an `import` block (iam.tf has one). Until that is fixed, the static
invariants live in `tests/unit/test_exe_stack_mode.py` (mode gates,
null-safe output forms, AR policy shape, recipe wiring), which runs
in `just ci`.

### Exception decommission (2026-07)

The leftover workspace VM `coder-hironow-test-ws-001-root` + its
30 GiB pd-ssd (Coder-template-managed, state inside the Coder DB) was
deleted with gcloud instead of `cdr delete`: the control plane was
already destroyed and recreating it requires Cloudflare/Tailscale
tokens not available to the executing session — restoring a control
plane to delete one disk was judged disproportionate. Coder supports
this posture explicitly (`cdr delete <ws> --orphan`); the wake
procedure in the runbook performs that cleanup before any workspace
starts.

## Consequences

### Positive

- Idle run-rate drops to ~JPY 550/mo (SQL storage + backups + AR +
  secrets); nothing pages while intentionally down.
- The mothballed posture is config, not tribal knowledge: losing
  `terraform.tfvars` can no longer silently resurrect paid infra,
  because `stack_mode` has no default and must be restated.
- `exe-down` (targeted destroy, divergent) is retired as the parking
  mechanism in favour of a plannable mode.

### Negative

- Operators must set `stack_mode` in tfvars before any plan (one-time
  friction, by design).
- While mothballed there is no runnable full plan (stopped-instance
  refresh 400s); drift checking degrades to `-refresh=false`.
- The on-demand pre-stop backup is never auto-deleted and bills
  (~JPY 17/GiB-mo) until removed manually.
- AR deletions are irreversible; an image needed for rollback older
  than 30 days must be rebuilt from its commit.
