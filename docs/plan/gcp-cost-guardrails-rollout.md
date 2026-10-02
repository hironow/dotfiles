# Rolling the GCP cost guardrails out to the personal account's projects

The guardrails were built for one project. This is how they reach the others.
The method is deliberately boring: **audit, then bound through IaC, then
re-audit**, one project at a time, with nothing destructive in the loop.

Prerequisite knowledge is one spoke: [`docs/agents/gcp-cost-guardrails.md`](../agents/gcp-cost-guardrails.md).
Reading it plus running the audit should be enough to do this without having
been there, which is the point of writing it down.

## Scope and order

Every project on the personal billing account, oldest and least-touched first:
those are the ones carrying a disk from a VM deleted two years ago. The project
with active work goes LAST, so the earlier ones teach the shape and a mistake
costs nothing in progress.

Out of scope here: the private project, whose guardrails are already in its own
OpenTofu, and anything on a work account.

## Per project

### 1. Audit, read-only

```sh
OUT=~/gcp-audit/<project>-$(date +%F).txt
just gcp-cost-audit <project> --location <region> --billing-account <id> > "$OUT"
```

Pass both flags. Without `--location` the scheduler leg never runs and without
`--billing-account` the budget leg never runs; each is then reported as `WARN …
not verified`, so a flagless run cannot exit 0 and must not be read as one.
Find the billing account read-only with
`gcloud billing projects describe <project> --format='value(billingAccountName)'`.

Read-only, so no change window and no announcement. **Keep the output local**:
it names the project, every bucket and every instance.

Exit 0 means every check ran and every sink has a bound — record that and move
to the next project.

### 2. Triage what it found

Sort the findings into three piles, because they have different answers.

| pile | examples | the answer |
|---|---|---|
| **delete** | a disk attached to nothing, a reserved address nobody routes, a SQL instance for a dead project | delete it, after taking the one backup you would want; nothing to codify afterwards |
| **bound** | an Artifact Registry repository with no DELETE policy, a bucket with no lifecycle, Cloud Build's default bucket | a bound, expressed in IaC (step 3) |
| **brake** | no budget, a scheduler job that stopped stopping things, nodes left up | a budget and an alert, plus whatever stops the thing (step 4) |

For the delete pile, confirm each one by hand before removing it. An unattached
disk is usually garbage and occasionally the only copy of something.

### 3. Put the bound in IaC, never by hand

A console change is undone by the next `tofu apply`, silently, and nothing
reports that it happened.

If the project has no OpenTofu yet, that is the first piece of work: import the
sinks the audit found (`tofu import`, or an `import` block), so the state
describes what exists before anything changes it. A project nobody has codified
is also a project where a hand-made bound will quietly disappear.

Then write the bounds, using the shapes the spoke gives:

- Artifact Registry: KEEP in-use, KEEP the newest few, DELETE older than N days,
  `cleanup_policy_dry_run = false`;
- buckets: a delete lifecycle or a generation cap — except a snapshot bucket,
  which must have neither;
- Cloud Build: its own source bucket with a 7-day lifecycle, logs to
  `CLOUD_LOGGING_ONLY`;
- `soft_delete_policy` set deliberately rather than left at its 7-day default.

`just check` runs `scripts/check_storage_bounds.py` over every stack in this
repo, so a sink added here without a bound fails the gate rather than the bill.

### 4. Brakes before the next expensive thing

- A **budget** with alert thresholds on the billing account, set before anything
  expensive runs rather than after.
- For anything unattended, the lease shape from the spoke: one writer, an expiry
  that is a formula, a capped heartbeat, and a last resort with no judgement in
  it that alerts when it fires.
- Alert on a **paused or failing scheduler job**, because that is usually the
  only thing that turns the expensive thing off, and its failure is silent.

### 5. Re-audit, and keep the receipt

```sh
just gcp-cost-audit <project> --location <region> --billing-account <id>
# expect exit 0 — which both flags are required for
```

Record the before and after totals locally. The audit is cheap, so put it on a
monthly rhythm rather than trusting that the bound stayed.

## Done, for the account as a whole

- every project audited at least once, with its report kept locally;
- every finding either deleted, bounded in IaC, or written down as a deliberate
  exception with the reason (a snapshot bucket is the canonical exception);
- a budget with alerts on the billing account;
- `just gcp-cost-audit` with both flags exits 0 for every project, or the
  exceptions are listed;
- a monthly re-audit on the calendar, because a bound that was true once is not
  a bound that stays true.

## What this plan deliberately does not do

- It does not delete anything automatically. Every removal is a human's call on
  a named resource; a tool that deletes on a heuristic is how the one copy of
  something goes.
- It does not touch work accounts.
- It does not put any project id, billing account id or audit report in this
  repo. Those are arguments and local files.
