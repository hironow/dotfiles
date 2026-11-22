# ADR 0089 — The dev container tests leave pull requests; unit tests run as shards
- **id**: ADR-0089
- **title**: The dev container tests leave pull requests; unit tests run as shards
- **status**: Proposed
- **date**: 2026-11-22
- **decided-date**: pending
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session)
- **author-contact**: @hironow
- **supersedes**: none
- **superseded-by**: none
- **related**: [0088](0088-ci-speed-standard-for-every-language.md), [0085](0085-slim-prek-hooks-to-check-only-guards.md)
- **consultation-trace**: owner's instruction in Claude Code session on 2026-11-22: "dev container のテストはPRで回すのをやめよう"; this ADR waits for the owner's acceptance

## Plain summary

The dev container test job took about 24 minutes on every pull request. The owner decided it no longer runs on pull requests.
It was also the only pull request job that ran `just check`, the full lint gate. So `just check` now runs in a new job, `check.yaml`, without a container.
The dev container job runs on pushes to main and on demand.
The unit suite runs as three shards, and a gate job proves that the shards together ran every collected test once.

## Decision

- D1. `test-just.yaml` (job "Required disposable Podman devcontainer build/up/exec") triggers on `push` to main and `workflow_dispatch`. It has no `pull_request` trigger.
- D2. `check.yaml` (job "just check (no container)") runs `just check` on ready pull requests and on main. Its tools come from `.devcontainer/ci-bootstrap.sh --tools-only`: the same pinned mise, verified by checksum, and the same frozen tool versions as the container image, without Podman.
- D3. `unit-test.yaml` runs the unit suite in three shards (pytest-split, least-duration, durations in `tests/durations/unit.json`). The job `unit` keeps its name and becomes a gate: it needs every shard and the extras, checks that all shards collected the same list, and runs `ci-audit shards`, which fails when a collected test did not run, ran twice, or a shard was empty or far slower than the mean.
- D4. `shellcheck.yaml` checks every tracked shell script outside `emulator/`, the set `just check` uses.
- D5. `tools/ci-audit` (`just ci-audit`, `just ci-shard-check`) measures where job time goes and proves shard completeness.

## Exception to ADR-0088

ADR-0088 rule 1 says the full suite runs before anything reaches the default branch. The dev container tests now run after the merge. The owner chose this on 2026-11-22.
What stays before the merge: `just check` (all lint legs, Go, JS/TS, Quint), the unit suite, and every other existing job. What moves after it: building the dev container image and the up and exec tests of the sandbox.
A break in the dev container is therefore found on main, and the fix is a follow-up pull request.

## Options considered

- Keep it on pull requests and shard it (planned before the owner's ruling). The sandbox tests need one engine each and the build dominates; it would still cost minutes per shard.
- Remove `just check` from pull requests along with the container job. Rejected: ADR-0088 rule 3 (never check less).
- Run the container job only when container files change. Rejected for now: the owner asked to stop running it on pull requests; a path filter can be added by a later decision.

## Not done, and why

- `bun fmt` for TypeScript: it does not match the formatter we run (`vp fmt`), see ADR-0088.
- Merge queue: unavailable for a user-owned repository; the fallback in ADR-0088 applies.
- Windows unit shards: the Windows job is not split yet. Its share of the wall time is the largest, and sharding it needs a measured split on Windows.
- A required-check registration for the new jobs: the ruleset `protect` requires only "Frontend CI". Registering `unit tests + instruction budget` and `just check (no container)` is the owner's decision.

## Consequences

- Pull request wall time drops from about 24 minutes to the slower of the shards and `just check`.
- The shard gate can fail for a reason in the splitter or in the durations file; refresh the file from the `unit-durations` artifact with a normal pull request.
- `tests/durations/unit.json` leaves out the ids of a secret scanner's own test cases (about 18 of 5156), because their ids hold credential-shaped text that GitHub's push protection and the private-key hook reject. `ci-audit shards --durations-out` drops them the same way, and pytest-split gives a test without a duration the mean of the others.

## Reversal

Add `pull_request` back to `test-just.yaml` and the draft guard to its job; the pinning tests in `tests/unit/test_ci_sandbox_pause.py` and `test_podman_ci_workflows.py` say what must hold. `check.yaml` can stay.
