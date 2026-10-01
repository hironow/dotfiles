# GCP cost guardrails — bounds on what accumulates, brakes on what runs alone

Two principles, and everything below is an instance of one of them:

1. **Anything that accumulates gets an explicit upper bound.**
2. **Anything that runs unattended gets something that stops it by itself.**

A personal project's bill is not a spike, it is a drip. Nothing fails, no alert
fires: images and objects keep landing and the total grows a little every month.
This repo has the receipt — a dev container repository reached 20+ versions and
~21 GiB because its only DELETE policy targeted UNTAGGED versions while every
publish tagged its image (ADR 0034). The policy looked like a bound and was not.

Two gates exist, and they see different things:

- `scripts/check_storage_bounds.py` (in `just check`) reads the repo's OpenTofu
  and refuses to let a sink be DECLARED without a bound.
- `just gcp-cost-audit <project>` asks a LIVE project, so it also sees what was
  made by hand, left behind by a deleted VM, or never put in tofu at all.

Fix what either finds **through IaC**, never by hand: the next `tofu apply`
would undo a manual change, silently.

## Artifact Registry: three traps that read as protection

- **KEEP beats DELETE.** When both policies match a version, the version
  survives. A KEEP written to protect one rolling tag widens into "protect
  everything" the moment its condition is broader than intended.
- **`most_recent_versions` is a floor, not a cap.** It means "never delete the
  newest N", not "keep at most N". A repository whose only policy is a
  `most_recent_versions` KEEP therefore deletes **nothing, forever**.
- **One policy block carries a `condition` OR a `most_recent_versions`, never
  both.** The rejection comes from the API at apply time; `tofu plan` is
  perfectly happy. Ten policies per repository is the hard limit, so the
  pressure to merge two KEEPs into one mixed block is real, and that is exactly
  how the error gets written.

Also: `cleanup_policy_dry_run = false`, or the policies report and delete
nothing. Policies are evaluated with a lag of roughly a day, so read actual size
rather than inferring it from the config, and pair `tag_state` with
`tag_prefixes` when a tag is what marks "in use".

A working shape, from `tofu/exe-platform`: KEEP what is tagged in-use, KEEP the
newest few, DELETE older than N days — three policies, dry run off.

## Buckets: a bound, except where a bound is the bug

- Every bucket needs a delete lifecycle rule or a generation cap.
- **A snapshot bucket must have NO delete lifecycle.** A lifecycle rule cannot
  tell a referenced snapshot from an abandoned one, and deleting a referenced one
  makes a suspended workload impossible to resume. Bound it by the lifetime of
  the thing that refers to it, and collect orphans with a dry-run-by-default
  tool a human starts.
- **Cloud Build's default source bucket (`<project>_cloudbuild`) keeps every
  upload forever** and is created behind your back on the first build. Point
  builds at a bucket with a 7-day lifecycle and send logs to
  `CLOUD_LOGGING_ONLY`.
- `soft_delete_policy` defaults to keeping every deleted object for 7 days as
  billed storage. Nobody asks for it and nobody sees it.
- State buckets: cap old generations (10 is plenty). Ops buckets that carry
  leases and flags: fewer (5).

## What bills while idle

"Stopped" reads as "free" and is not:

| thing | charged when |
|---|---|
| persistent disk | always, attached or not |
| static IP | reserved and **unused** is the charged case |
| Cloud SQL instance | STOPPED still pays for its data disk and its backups |
| GKE cluster | per-hour management fee while it exists (a free zonal tier may absorb it — confirm, do not assume) |
| GKE nodes | only while up; this is the number worth watching |
| snapshots / images | always |

## Brakes on unattended compute

A lease is the shape that works: something writes an expiry, and a separate
thing stops the workload when now is past it.

- **One writer.** Two things extending the same lease is how a lease never
  expires.
- **The expiry is a formula, not a countdown**, so a crash cannot leave it
  pending forever.
- **A heartbeat needs a ceiling.** "Extend while work continues" with no cap is
  an unbounded lease wearing a seatbelt.
- **A last resort with no judgement in it.** The final stop must not reason
  about whether stopping is a good idea; it must only check the clock. Then
  alert when IT fires, because that firing means every earlier layer failed.
- **A scheduler job is usually the only thing that turns something off.** Its
  failure is silent by construction, so audit its last attempt and alert on a
  paused one. `just gcp-cost-audit` warns on both.
- **A budget is the only thing that notices a drip nobody is looking at.** Set
  it with alert thresholds before the first expensive thing runs, not after.

## Auditing

```sh
just gcp-cost-audit <project>                               # read-only
just gcp-cost-audit <project> --billing-account <id>        # also checks budgets
just gcp-cost-audit <project> > ~/audit-$(date +%F).txt     # keep it LOCAL
```

Exit 1 means something has no bound. Every probe is a `gcloud … list`, so it is
safe to run against a live project with no change window.

**The report stays local.** It names the project, every bucket and every
instance; in a public repo that is exactly the content that must not be
committed. The same goes for the billing account id — it is an argument, never a
tracked value.

Rolling this out to another project: `docs/plan/gcp-cost-guardrails-rollout.md`.
