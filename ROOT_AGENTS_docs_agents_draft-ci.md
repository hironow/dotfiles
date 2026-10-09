# Draft PRs run no Actions

Read this when you write or change a GitHub Actions workflow that can run on
`pull_request`.

A draft PR says the change is not ready to spend CI on. Skip every job until
the author marks the PR ready. Open PRs as **ready**, not draft: a draft skips
the gates that would have reviewed it.

## What every workflow must have

- Every job reachable from `pull_request` has
  `github.event.pull_request.draft == false`, or is skipped because a job it
  `needs` is skipped.
- Jobs with `always()`, `!cancelled()`, or `failure()` run anyway, so they
  **repeat** the draft gate themselves.
- The workflow lists `ready_for_review` in `pull_request.types`. Without it,
  the skipped run never comes back when the PR leaves draft, and the PR
  cannot merge (or merges untested).
- The fork gate is a separate protection. Check it on its own: one does not
  imply the other.

A reusable `workflow_call` callee inherits the caller's job gate. Workflows
that never see `pull_request` (push-only, schedule, `labeled`-only CodeQL) need
no draft gate.

Enforce the gate in CI, so a missing `draft == false` or a missing
`ready_for_review` type fails the workflow lint instead of a later review.
