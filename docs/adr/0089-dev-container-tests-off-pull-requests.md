# ADR 0089 — dotfiles' own CI follows ADR-0088; the dev container tests leave pull requests

- **id**: ADR-0089
- **title**: dotfiles' own CI follows ADR-0088; the dev container tests leave pull requests
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

Before this change, the slowest job of a pull request was the dev container test (about 24 minutes), and the owner ruled that it no longer runs on pull requests.
That job was also the only pull request job that ran `just check`, the full lint gate, so `just check` now runs on pull requests without a container, as three parallel jobs.
The unit suite runs as shards on Linux and on Windows, and a gate proves that the shards together ran every collected test once.
shellcheck, actionlint and the semgrep rule tests run in one small job.
`tools/ci-audit` measures where CI time goes and proves the shards complete.

## Context

- ADR-0088 (Accepted, PR #669) made a CI speed standard for every repository: a pull request gets its result in under 1 minute at p50 and under 2 minutes at p95, and three rules outrank speed (the full suite runs before the default branch; never hide a failure; never check less).
- The audit of dotfiles' own CI (374 runs, 2026-11-22) found the slowest job, the dev container tests, at 1416 s p50 (23.6 minutes), and the Windows unit job at 739 s p50 (12.3 minutes).
- On 2026-11-22 the owner ruled: "dev container のテストはPRで回すのをやめよう" (stop running the dev container tests on pull requests).

## Decision

- D1. `test-just.yaml` (job "Required disposable Podman devcontainer build/up/exec") triggers on `push` to main and `workflow_dispatch`. It has no `pull_request` trigger.
- D2. `check.yaml` runs `just check` on ready pull requests and on main, without a container, as three parallel jobs: `just check-except-go`, `just go-lint`, `just go-test`. `just check` runs the same three in a row. The gate job "just check (no container)" needs all three and fails when any is not a success. The tools come from `.devcontainer/ci-bootstrap.sh --tools-only`: the same pinned mise, verified by checksum, and the same frozen tool versions as the container image, without Podman.
- D3. `unit-test.yaml` runs the unit suite in shards (pytest-split, `least_duration`): three on Linux (`tests/durations/unit.json`) and four on Windows (`tests/durations/unit-windows.json`), and the Windows PowerShell 5.1 tests in a job of their own. The jobs "unit tests + instruction budget" and "Unit tests on Windows, and on Windows PowerShell 5.1" keep their names and become gates: each needs its shards, reads one collected list per shard, and runs `ci-audit shards`, which fails when a collected test did not run, ran twice, was not collected, when a module failed to collect, when the shards collected different lists, when a shard ran nothing, or when the slowest shard is more than 1.5 times the mean. A module that skips itself at collection (POSIX-only modules on Windows) is listed in the output and is not a test.
- D4. `small-checks.yaml` (replacing `shellcheck.yaml`) runs `just small-checks`: shellcheck over every tracked `*.sh` outside `emulator/`, actionlint 1.7.12 (release archive checked against its sha256), and `just semgrep-test`. Each checker runs to the end and the recipe lists every failure. `just semgrep-test` ran on pull requests only inside the dev container job before; it now runs on every pull request.
- D5. `tools/ci-audit` (`just ci-audit`, `just ci-shard-check`): per job, waiting, setup, running and after at p50 and p95 over every attempt of the last completed runs (paged past 100; timed-out runs count); the step counted as running is printed, and `--recipe-step "JOB=STEP"` names it where the longest step is not the recipe; per push, when the pull request had its result and its runner seconds. `--branch` and `--event` fix the sample.

## Exception to ADR-0088

ADR-0088 rule 1 says the full suite runs before anything reaches the default branch. The dev container tests now run after the merge. The owner chose this on 2026-11-22.
What stays before the merge: `just check` (every lint leg, ty per OS, Go per GOOS, JS/TS, Quint, the GC simulation), the semgrep rule tests, the unit suite on Linux and Windows, and every other existing job.
What moves after it: building the dev container image, its features and post-create, and the up and exec tests of the sandbox (`tests/test_just_sandbox.py`, `tests/test_devcontainer.py`).
A break there is found on main, and the fix is a follow-up pull request.

## Measured

Measured with `just ci-audit` on 2026-11-22, from GitHub's REST jobs endpoint. Per push, "result" is from the first run's creation to the end of the last job of the first attempts: when the pull request had its whole result.

| Pull request pushes | n | result p50 / p95 | runner seconds p50 / p95 |
| ------------------- | - | ---------------- | ------------------------ |
| Before: other branches, old layout (last 150 runs of each workflow) | 119 | 1380 s / 1662 s (23.0 / 27.7 min) | 2890 s / 3847 s |
| After: this PR, from the first push without the dev container job | 5 | 395 s / 455 s (6.6 / 7.6 min) | 2028 s / 2310 s |
| After: this PR, the final layout only (pushes b7bf64ae, f381cf38) | 2 | 327 s, 319 s | 2310 s, 2143 s |

The after samples are few; they are the PR's own runs. The table in docs/agents/ci-speed.md asks for p50 under 60 s; this change does not reach it (see "Budgets" and "Not done").

Per job, seconds from start to end (before: p50 / p95 over the audit's runs; after: the final layout's run f381cf38):

| Job | Before | After |
| --- | ------ | ----- |
| Required disposable Podman devcontainer build/up/exec | 1416 / 1751 | not on pull requests |
| Unit tests on Windows (+ PowerShell 5.1), one job | 739 / 892 | 4 shards 93-149, 5.1 tests 125, gate 11 |
| unit tests + instruction budget (ubuntu), one job | 432 / 523 | 3 shards 63-73, extras 123, gate 7 |
| `just check`, one container-free job (this PR's run 45014603116, before the split) | 389 | check-except-go 114, go-lint 295, go-test 109, gate 4 |
| shellcheck (`shellcheck *.sh`, the root scripts only; n=42) | 6 / 11 | small checks (every tracked `*.sh`, actionlint, semgrep rule tests) 21 |
| Test Emulators (unit-integration-e2e) | 261 / 325 | 316 (unchanged) |
| Go tests on Windows (tools/) | 121 / 185 | 94 (unchanged) |
| Go tests (tools/) | 80 / 97 | 78 (unchanged) |

Total CI cost: GitHub-hosted standard runners on a public repository are free, so the money cost is $0 before and after. Runner time per pull request push fell from 2890 s at p50 to 2143 s and 2310 s on the final layout's two pushes.

## Budgets

ADR-0088 asks for a budget per stage, and, where a tool cannot meet the table, the measured p50 and p95 as its budget.
The jobs below cannot meet the 35-second job budget today; their measured times are their budgets until a later change lowers them, and each has a `timeout-minutes` of about twice its time:

| Job | Measured (2026-11-22) | `timeout-minutes` |
| --- | --------------------- | ----------------- |
| unit-integration-e2e (emulators) | 316 s; 261 / 325 s before | unchanged |
| just go-lint (golangci-lint per GOOS) | 287 s, 295 s | 10 |
| Unit tests on Windows, each shard | 93-149 s | 6 |
| Tests on Windows PowerShell 5.1 | 115-125 s | 5 |
| unit extras (Python 3.14 corpora, real Go, instruction budget) | 123-151 s | unchanged |
| just check-except-go | 114 s, 144 s | 5 |
| just go-test | 109 s, 167 s | 6 |
| unit tests, each Linux shard | 59-91 s | unchanged |

Recompute these from main's runs once there are enough of them: `just ci-audit --event push --branch main`.

## Options considered

- Keep the dev container tests on pull requests and shard them (planned before the owner's ruling). The image build and the slowest test bound one shard at about 11 minutes.
- Remove `just check` from pull requests along with the container job. Rejected: ADR-0088 rule 3 (never check less).
- Run the container job only when container files change. Not chosen: the owner asked to stop running it on pull requests; a path filter is a later decision.
- `duration_based_chunks` for the unit shards. Not chosen: under `-n auto --dist loadgroup` neither algorithm keeps an `xdist_group` together across shards, and `least_duration` balances better and never left a shard empty on the real durations.

## Not done, and why

- `bun fmt` for TypeScript: it does not match the formatter we run (`vp fmt`), see ADR-0088.
- Selection on pull requests: pytest has none built in, and the standard asks for a proof that the selection cannot be fooled; that is a change of its own.
- The emulator workflow (about 5 minutes: starting services 1.5 minutes, e2e tests 2 minutes) is now the slowest pull request job and sets the result time: sharding it needs one service stack per shard.
- `go-lint` and `go-test` start with a cold Go build cache in their own jobs (287-295 s and 109-167 s; inside one job go-test reused go-lint's cache). A Go build and golangci-lint cache, saved on main and restored on pull requests, is the next change for them. Test results must not come from that cache where a test reads files outside its module (ADR-0088's Go row), so the test job would keep the build cache only.
- Caches seeded from main and warm runners: setup is a small bucket today (under 35 seconds in every job but one), and waiting is about 2 seconds.
- For the owner to decide, each with its cost:
    - Register the gates ("just check (no container)", "unit tests + instruction budget", "Unit tests on Windows, and on Windows PowerShell 5.1", "small checks (shellcheck, actionlint, semgrep rule tests)") as required checks, and require branches to be up to date (ADR-0088's fallback for a repository without a merge queue). Cost: no money (public repository, standard runners); each merge then waits for a fresh run of a branch that fell behind main.
    - Move the repository to an organization to get a merge queue. Cost: none in money; an account change.
    - Faster or larger runners (for example Blacksmith). Cost: a monthly bill; not needed for the measured buckets.

## Consequences

- A pull request no longer waits for the dev container build; the slowest pull request job is now the Windows unit shards or the parts of `just check`.
- The shard gates can fail on imbalance when the tests change: refresh `tests/durations/unit.json` or `unit-windows.json` from the `unit-durations` or `unit-windows-durations` artifact of a main run with a normal pull request. The gates upload the artifact even when they fail.
- `tests/durations/unit*.json` leave out the ids of a secret scanner's own test cases, because their ids hold credential-shaped text that GitHub push protection and the private-key hook reject. `ci-audit shards --durations-out` drops them the same way, and pytest-split gives a test without a duration the mean of the others.

## Reversal

Add `pull_request` back to `test-just.yaml` and the draft guard to its job; `tests/unit/test_ci_sandbox_pause.py` and `test_podman_ci_workflows.py` say what must hold. The other changes stand on their own.

## Consistency with other decision records

- ADR-0088: follows it, with the one exception above, which the owner ruled.
- ADR-0060 (one source for the frozen image tool versions): `--tools-only` reads the same generated config as the image; it does not add a second list of versions.
- ADR-0085 (hooks only check): no hook changes.
