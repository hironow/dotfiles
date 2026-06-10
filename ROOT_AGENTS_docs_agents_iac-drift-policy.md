# IaC Drift Avoidance

Read this before any `gcloud`, `cdr`, `kubectl`, or console action against
production. Root summary is in AGENTS.md.

Production infra (GCP resources, IAM, Cloud Run revisions, Coder workspace VMs)
is managed **exclusively** through OpenTofu + the standard PR + CD flow. Manual
mutations create drift between live infra and the repo; the next `tofu apply`
either silently reverts your change or fails on unexpected state.

## Prohibited (these mutate state OpenTofu owns)

- `gcloud compute disks resize` / `... instances set-machine-type` against any
  resource declared in `tofu/exe/` or `tofu/`.
- `gcloud iam service-accounts add-iam-policy-binding` /
  `gcloud projects add-iam-policy-binding` for bindings that exist in
  `iam_*.tf` — IAM drift is the top source of "works for me / fails in CI".
- `gcloud secrets versions add` with content the IaC doesn't know about — add
  only secrets for which tofu has reserved a slot.
- `cdr workspaces update` / `... edit` to change parameters that belong as
  `coder_parameter` defaults — push the template, don't patch the running VM.
- Editing live Cloud Run revisions in the console (env vars, traffic split) when
  managed by `google_cloud_run_v2_service` / CD `gcloud run deploy`.

## Allowed exceptions

- One-off **bootstrap** before IaC can manage the resource (e.g. `bootstrap.sh`
  creates the GCS state bucket; the bucket is then not tofu-managed, by design).
- **Read-only debug** (`gcloud compute ssh ... --command 'df -h'`,
  `... get-serial-port-output`, `cdr show`, …).
- **Emergency rollback when CD itself is broken** — open an incident, run the
  manual command, then immediately file a PR re-syncing the IaC.
- **Interactive prompts IaC can't pre-fill** (e.g. `cdr create`'s region
  selector) — choose at create-time; don't edit the workspace afterwards.

## When drift happens — recover same session

1. If a manual change shipped, open a PR **this session** reflecting it in IaC.
   Don't leave live state ahead of the repo overnight.
2. If the IaC PR can't land immediately (waiting on review), record the drift in
   `docs/handover.md` so the next operator doesn't blindly `tofu apply` and
   revert the fix.
3. About to type `gcloud ... update/resize` on a resource mentioned anywhere in
   `tofu/`? **Stop. Open a PR.** 30 minutes of latency beats a drift incident.

## Detecting drift

- `tofu plan` shows changes you didn't write — something was hand-edited.
- CD's apply step fails with "resource already exists" / "permission denied on
  existing resource" — IaC and live state disagree on ownership.
- A VM or Cloud Run revision behaves differently from a same-template-version
  peer — runtime state was poked manually.

## Agent directive

- Default to the IaC PR path. Suggest a manual `gcloud`/`cdr` command only for
  one of the four exceptions above.
- If a manual command is unavoidable to unblock the operator, spell out the IaC
  follow-up in the same message ("this bridges the gap; PR XYZ lands within the
  hour to capture it permanently").
- Refuse to **chain** manual mutations — one emergency mutation is acceptable;
  a sequence means the IaC needs restructuring.

(A PreToolUse hook flags `gcloud … add-iam-policy-binding` / `… update` /
`… resize` and Cloud Run console-equivalent calls for confirmation; see
README-agents-setup.md.)
