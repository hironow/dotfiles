# IaC drift: change production only through OpenTofu

Read this before any `gcloud`, `kubectl`, provisioning-CLI, or console action
against production. The root summary is in AGENTS.md.

Change production infra (GCP resources, IAM, Cloud Run revisions, cloud VMs)
**only** through OpenTofu plus the standard PR and CD flow. A manual change
makes live infra and the repo disagree (drift). The next `tofu apply` then
either silently reverts your change or fails on state it did not expect.

## Prohibited: commands that change state OpenTofu owns

- `gcloud compute disks resize` / `... instances set-machine-type` on any
  resource declared under `tofu/`.
- `gcloud iam service-accounts add-iam-policy-binding` /
  `gcloud projects add-iam-policy-binding` for bindings that exist in
  `iam_*.tf`. IAM drift is the top cause of "works for me, fails in CI".
- `gcloud secrets versions add` with content the IaC does not know about. Add
  only secrets for which tofu has reserved a slot.
- Changing a running instance through the CLI of whatever provisioned it, when
  the parameter belongs in the template or module that created it. Push the
  template; do not patch the instance.
- Editing live Cloud Run revisions in the console (env vars, traffic split)
  when `google_cloud_run_v2_service` or CD `gcloud run deploy` manages them.

## Allowed exceptions

- **Bootstrap**, once, before IaC can manage the resource. Example:
  `bootstrap.sh` creates the GCS state bucket, and by design tofu does not
  manage that bucket afterwards.
- **Read-only debugging**: `gcloud compute ssh ... --command 'df -h'`,
  `... get-serial-port-output`, any `describe` / `show` / `get`, and so on.
- **Emergency rollback when CD itself is broken.** Open an incident, run the
  manual command, then immediately file a PR that brings the IaC back in sync.
- **Interactive prompts that IaC cannot pre-fill**, such as a region selector
  a provisioning CLI asks for at create time. Answer it then; do not edit the
  instance afterwards.

## When drift happens, fix it in the same session

1. If a manual change shipped, open a PR **in this session** that puts it into
   IaC. Do not leave live state ahead of the repo overnight.
2. If the IaC PR cannot land right away (it waits on review), record the drift
   in `docs/handover.md`. Then the next operator will not run `tofu apply`
   blindly and revert the fix.
3. About to type `gcloud ... update/resize` on a resource that appears anywhere
   in `tofu/`? **Stop. Open a PR.** 30 minutes of delay beats a drift incident.

## How to spot drift

- `tofu plan` shows changes you did not write: someone edited by hand.
- CD's apply step fails with "resource already exists" or "permission denied on
  existing resource": IaC and live state disagree about who owns what.
- A VM or Cloud Run revision behaves differently from a peer on the same
  template version: someone changed its runtime state by hand.

## What the agent does

- Default to the IaC PR path. Suggest a manual `gcloud`/`kubectl` command only
  for one of the four exceptions above.
- If a manual command is the only way to unblock the operator, state the IaC
  follow-up in the same message ("this bridges the gap; PR XYZ lands within the
  hour to capture it permanently").
- Refuse to **chain** manual changes. One emergency change is acceptable; a
  sequence means the IaC needs restructuring.

(A PreToolUse hook blocks `gcloud … add-iam-policy-binding` /
`… set-iam-policy` / `… update` / `… resize` / `… deploy` with exit 2 and no
confirmation step; see docs/agents/enforcement.md.)
