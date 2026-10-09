# GCP cost guardrails: bound what piles up, brake what runs alone

Two rules. Everything below applies one of them:

1. **Give anything that piles up an explicit upper bound.**
2. **Give anything that runs unattended something that stops it on its own.**

A personal project's bill does not spike. It drips. Nothing fails and no alert
fires: images and objects keep arriving, and the total grows a little each
month. This repo has the receipt. A dev container repository reached 20+
versions and ~21 GiB. Its only DELETE policy targeted UNTAGGED versions, but
every publish tagged its image (ADR 0034). The policy looked like a bound. It
was not one.

Two gates exist, and each sees different things:

- `scripts/check_storage_bounds.py` (in `just check`) reads the repo's OpenTofu.
  It refuses a sink that is DECLARED without a bound.
- `just gcp-cost-audit <project>` queries a LIVE project. So it also sees what
  someone made by hand, what a deleted VM left behind, and what never went into
  tofu.

Fix what either gate finds **through IaC**, never by hand. The next
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

A working shape, from a registry that runs it: KEEP what is tagged in use, KEEP
the newest few, DELETE what is older than N days. Three policies, dry run off.

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
  billed storage. Nobody asks for it, and nobody sees it.
- State buckets: cap old generations (10 is plenty). Ops buckets that hold
  leases and flags: fewer (5).

## What you pay for while idle

"Stopped" sounds free. It is not:

| thing | charged when |
|---|---|
| persistent disk | always, attached or not |
| static IP | reserved and **unused** is the charged case |
| Cloud SQL instance | STOPPED still pays for its data disk and its backups |
| GKE cluster | per-hour management fee while it exists (a free zonal tier may absorb it — confirm, do not assume) |
| GKE nodes | only while up; this is the number worth watching |
| snapshots / images | always |

## Brakes on unattended compute

Use a lease. One thing writes an expiry time. A separate thing stops the
workload once the current time is past it.

- **One writer.** If two things extend the same lease, it never expires.
- **Compute the expiry from a formula, not a countdown.** Then a crash cannot
  leave it pending forever.
- **Cap the heartbeat.** "Extend while work continues" with no cap is an
  unbounded lease that only looks safe.
- **Make the last resort judgement-free.** The final stop must not reason about
  whether stopping is a good idea. It checks the clock and nothing else. Alert
  when IT fires: that means every earlier layer failed.
- **A scheduler job is usually the only thing that turns something off.** When
  it fails, it fails silently. So audit its last attempt, and alert when a job
  is paused. `just gcp-cost-audit <project> --location <region>` warns on both;
  without `--location` that check never runs (see Auditing).
- **Only a budget notices a drip nobody is looking at.** Set one, with alert
  thresholds, before the first expensive thing runs, not after.

## Auditing

```sh
just gcp-cost-audit <project>                                # sinks only
just gcp-cost-audit <project> --location <region>            # + scheduler jobs
just gcp-cost-audit <project> --billing-account <id>         # + budgets
just gcp-cost-audit <project> --location <region> --billing-account <id>
just gcp-cost-audit <project> … > ~/audit-$(date +%F).txt    # keep it LOCAL
```

**A check whose flag is missing reports `WARN … not verified`, never OK**, and
it counts toward exit 1. A check that did not run cannot pass. `--location`
exists because `gcloud scheduler jobs list` requires one. `--billing-account`
exists because the budget belongs to the billing account, not the project. So a
run without flags audits the sinks and checks **neither brake**. Only the run
with both flags checks everything.

Find the billing account read-only, without writing it anywhere:

```sh
gcloud billing projects describe <project> --format='value(billingAccountName)'
```

Exit 1 means something has no bound, or a check could not be verified. Every
probe is a `gcloud … list`, so you can run it against a live project without a
change window.

**Keep the report local.** It names the project, every bucket, and every
instance. In a public repo, that is exactly what must not be committed. The
same goes for the billing account id: pass it as an argument, never store it in
a tracked file.

To roll this out to another project: `docs/plan/gcp-cost-guardrails-rollout.md`.
