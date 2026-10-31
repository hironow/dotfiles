# GCP cost guardrails: bound what piles up, brake what runs alone

Two rules. Everything below applies one of them:

1. **Give anything that piles up an explicit upper bound.**
2. **Give anything that runs unattended something that stops it on its own.**

Fix what a gate or audit finds **through IaC**, never by hand. The next
`tofu apply` would silently undo a manual change.

## Artifact Registry: three traps that look like protection

- **KEEP beats DELETE.** When both policies match a version, the version stays.
  A KEEP written to protect one rolling tag turns into "protect everything" as
  soon as its condition is broader than you meant.
- **`most_recent_versions` is a floor, not a cap.** It means "never delete the
  newest N", not "keep at most N". So a repository whose only policy is a
  `most_recent_versions` KEEP deletes **nothing, forever**.
- **One policy block has a `condition` OR a `most_recent_versions`, never
  both.** The API rejects the mix at apply time; `tofu plan` accepts it. A
  repository allows at most ten policies. That limit pushes you to merge two
  KEEPs into one mixed block, and that is exactly how this error gets written.

Also:

- Set `cleanup_policy_dry_run = false`. Otherwise the policies only report and
  delete nothing.
- Policies run about a day late. Read the actual size; do not infer it from the
  config.
- Pair `tag_state` with `tag_prefixes` when a tag is what marks "in use".
- Working shape: KEEP what is tagged in use, KEEP the newest few, DELETE what
  is older than N days (three policies, dry run off).

## Buckets: always a bound, except where a bound is the bug

- Every bucket needs a delete lifecycle rule or a generation cap.
- **A snapshot bucket must have NO delete lifecycle.** A lifecycle rule cannot
  tell a referenced snapshot from an abandoned one. Deleting a referenced one
  makes a suspended workload impossible to resume. Bound the bucket by the
  lifetime of the thing that refers to it. Collect orphans with a tool that a
  human starts and that defaults to dry run.
- **Cloud Build's default source bucket (`<project>_cloudbuild`) keeps every
  upload forever.** Cloud Build creates it silently on the first build. Point
  builds at a bucket with a 7-day lifecycle, and send logs to
  `CLOUD_LOGGING_ONLY`.
- `soft_delete_policy` by default keeps every deleted object for 7 days as
  billed storage.
- State buckets: cap old generations (10 is plenty). Ops buckets that hold
  leases and flags: fewer (5).

## What you pay for while idle

| thing | charged when |
|---|---|
| persistent disk | always, attached or not |
| static IP | reserved and **unused** is the charged case |
| Cloud SQL instance | STOPPED still pays for its data disk and its backups |
| GKE cluster | per-hour management fee while it exists (confirm whether a free zonal tier absorbs it) |
| GKE nodes | only while up; this is the number worth watching |
| snapshots / images | always |

## Brakes on unattended compute

Use a lease: the writer records an expiry time, and a separate component stops
the workload once the current time passes that expiry.

- **One writer.** If two things extend the same lease, it never expires.
- **Compute the expiry from a formula, not a countdown.** Then a crash cannot
  leave it pending forever.
- **Cap the heartbeat.** "Extend while work continues" with no cap is an
  unbounded lease that only looks safe.
- **Make the last resort judgment-free.** The final stop checks the clock and
  nothing else. Alert when IT fires: that means every earlier layer failed.
- **Audit scheduler jobs.** A scheduler job is usually the only thing that turns
  something off, and it fails silently. Audit its last attempt and alert when a
  job is paused.
- **Set a budget** with alert thresholds before the first expensive thing runs.

## Auditing

Two gates in the dotfiles repo check bounds and brakes:

- `scripts/check_storage_bounds.py` (in `just check`) reads OpenTofu and refuses
  a declared sink without a bound.
- `just gcp-cost-audit <project> --location <region> --billing-account <id>`
  queries the live project (`gcloud … list` probes only): sinks, scheduler jobs
  (`--location`), and billing budgets (`--billing-account`).

**A check whose flag is missing reports `WARN … not verified`, never OK**, and
counts toward exit 1. Find the billing account read-only with
`gcloud billing projects describe <project> --format='value(billingAccountName)'`.

**Keep the report and billing account id local.** Never commit project names,
bucket names, instance names, or billing account ids to a public repo.
