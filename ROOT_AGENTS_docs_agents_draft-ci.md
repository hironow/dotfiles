# Draft PRs run no Actions

Read this when writing or changing a GitHub Actions workflow that can fire on
`pull_request`.

A draft PR is a declaration that the change is not ready to spend CI. Skip
every job until the author marks it ready. Open PRs **ready**, not draft — a
draft now exempts itself from the gates that would have reviewed it.

## What every caller carries

- Every job reachable from `pull_request` has `github.event.pull_request.draft == false`,
  or is skipped because something it `needs` does.
- `always()` / `!cancelled()` / `failure()` jobs run anyway and **repeat** the
  draft gate themselves.
- The workflow declares `ready_for_review` in `pull_request.types`. Without it
  the skipped run never comes back when the PR leaves draft, and the PR cannot
  merge (or merges untested).
- The fork gate is a separate protection, checked independently — one does not
  imply the other.

Reusable `workflow_call` callees inherit the caller's job gate. Workflows that
never see `pull_request` (push-only, schedule, `labeled`-only CodeQL) need no
draft gate.

Enforce the gate in CI so a missing `draft == false` or a missing
`ready_for_review` type fails the workflow lint, not a later review.
