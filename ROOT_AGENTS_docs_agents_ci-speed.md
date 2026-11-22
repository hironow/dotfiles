# CI speed: a result in under a minute, without lying

Read this when you write, change, or speed up CI, or the `just` recipes it
runs, in any language. docs/agents/frontend-ci.md has the TypeScript part.

The target: a pull request gets its required result in under 1 minute at the
median (p50) and under 2 minutes at the 95th percentile (p95), counted from the
push. Measure real runs before and after every change, and give both numbers
in the PR.

## Three rules outrank speed

1. **The full suite runs before anything reaches the default branch.**
   Selection (below) only narrows the feedback a pull request gets.
2. **Never hide a failure.** Add no retries, no wider timeouts, and no skipped
   tests. A check that needs a retry has a bug: reproduce it with a fixed seed
   (`--seed`, `-shuffle=<seed>`, `--rerun-each`) and fix the cause.
3. **Never check less.** Lint rules and required checks only stay or grow.
   Deleting a test is a change to the spec: see "Fewer tests".

## Audit first

Before you change anything, measure the last 150 runs of each required
workflow, per job, at p50 and p95. Use the REST jobs endpoint
(`GET /repos/{owner}/{repo}/actions/runs/{id}/jobs`):

| Bucket  | How to measure |
| ------- | -------------- |
| waiting | the job's `started_at` minus its `created_at`. A job with `needs` is created when its needs finish, so their run time is not counted as waiting |
| setup   | the steps before the step that runs the job's recipe |
| running | the step that runs the recipe |

Read each `run_attempt` on its own. Keep the audit as a root `just` recipe, and
check it against a job that has `needs`. Fix the biggest bucket first.

## Budgets

| Stage | Budget |
| ----- | ------ |
| Waiting for a runner | under 5 seconds |
| Setup (toolchain, install, cache restore) | under 15 seconds |
| Slowest job | under 35 seconds. No required job that does work waits for another; the one last job that gathers their results does (docs/agents/frontend-ci.md, rule 5) |
| Lint | under 1 second |
| Format check | under 1 second |
| Type check | under 5 seconds |
| Tests | under 30 seconds per shard |
| Local hooks | under 9 seconds |

A budget judges a stage over many runs, at p50 and at p95. Also give each job
a limit for a single run (`timeout-minutes` and a step that compares the job's
time with its budget), set from the spread you measured, so that an ordinary
slow run stays green and a real regression turns red. Do not use the p95 itself
as the limit: about 1 run in 20 would fail. Fail any job that goes over its
limit. When a tool cannot meet the table, write down its measured p50 and p95
as its budget. Never raise a budget or a limit to turn a red run green.

## Waiting and setup

- **Waiting.** Run jobs on warm runners (a runner that is already up), and
  cancel a branch's in-progress run when a new commit lands (`concurrency` with
  `cancel-in-progress`). A faster runner service, such as Blacksmith, needs an
  account and a bill: do it last, and bring it to the human in the list
  described under "How to work".
- **Setup.** Put the toolchain in the runner image. A pull request restores
  caches from its own branch, its base branch, and the default branch, never
  from another pull request, so seed the caches from the default branch: save
  them in a job that runs on pushes to the default branch and in the merge
  queue. Cache the dependency folder itself (`node_modules`, the Go build and
  test cache, `target/`, `.lake/`, the uv cache), keyed by the lockfile. A
  repository holds 10 GB of cache, and entries unread for 7 days are removed.
  Clone with `fetch-depth: 0` and `filter: blob:none` (full history, so
  `git merge-base` works; file contents come on demand).

## Shape

- Run lint, type check, build, and tests as parallel jobs. None of them
  `needs` another, so the slowest sets the time (docs/agents/frontend-ci.md,
  rule 5, has the last job that gathers them).
- Fold the small checks (actionlint, shellcheck, markdown, YAML) into one job.
  Its recipe runs every checker to the end and lists every failure, instead of
  stopping at the first.

## Shards

- Buy cores before shards: a larger runner before another shard, and one worker
  per core.
- Give each shard its own throwaway database.
- Split any test file that takes over 20 seconds.
- Balance the shards from file times that every full run of the default branch
  records.
- Prove that the shards together ran every test they were given, at the unit
  the splitter uses (a file for `bun test`, a test for pytest-split and
  nextest, a package for Go). Collect the expected IDs (`pytest --collect-only
  -q`, `cargo nextest list`, `go list`, the list of test files) and the
  executed IDs from the result report. Fail on a missing ID, an unexpected
  duplicate, or a shard that never ran. In a full run the expected IDs are all
  the tests; in a selected run they are the IDs the selection step chose,
  computed on their own, so a test that selection left out on purpose is not
  "missing". Check the job by dropping one case from one shard and seeing it
  fail.

## Selection on pull requests

- Run only the tests the diff can reach. List the inputs that rerun everything
  (fixtures, snapshots, config, the lockfile, the workflow, build scripts, and
  anything a test reads by path), keep the list in one root recipe, and test
  that recipe.
- Pass the merge base of the pull request and its target branch, never the tip
  of the target branch.
- Prove the selection cannot be fooled: hide a real change from it on purpose
  (break a file that the selection does not follow) and confirm CI goes red.
  When it stays green, the selection lies; fix the list.

## Before the default branch

- Use a merge queue where the repository can have one. Every workflow that
  gives a required check also listens to `merge_group`, the required check runs
  on `pull_request` and on `merge_group`, and the queue runs the full suite in
  shards.
- GitHub offers merge queues for public repositories owned by an organization,
  not for user-owned repositories. Where there is none, run the full suite as a
  required job on the pull request, require branches to be up to date, and let
  selection give early feedback only. Moving the repository to an organization
  is the human's decision: put it in the list under "How to work".

## Fewer tests, on evidence

- For two weeks, label each pull request that fixes a test failure
  `caught-regression` or `change-detector`. The labels only nominate
  candidates.
- Before you delete a test, check each assertion against the requirement it
  serves and name what still protects it. A test that detects the shape of the
  code is rewritten as a test of behavior. Ban the patterns of the tests you
  delete in AGENTS.md.
- Deleting a test is a change to the spec (docs/agents/performance.md): decide
  it on its own, with the human, never inside a speed change.
- Never delete tests for authorization, privacy, migrations, or concurrency.

## Tools

The tools in the language table are defaults. Keep an older tool only with a
measured reason. Before each switch, run the old and the new tool side by side
on the same files, and list what the new one misses or changes in the PR.

## Local hooks

A hook finishes in under 9 seconds. docs/agents/enforcement.md says what a hook
may run. Put what must hold at commit time in a hook, not in a line of an
instruction file: agents skip steps.

## How to work

- Make one small PR per change, with before and after numbers from real runs.
- Do everything you can without the human first. Bring anything that needs an
  account, a secret, or a bigger bill as one list with the expected monthly
  cost.
- End with the total CI time and cost, before and after.

## Each language

| Language | Checks | Cores and shards | Selection and cache |
| -------- | ------ | ---------------- | ------------------- |
| TypeScript | `bun fmt --no-script --check`, `bun lint --no-script` (Bun canary is recommended; a project may stay on stable Bun with `oxlint`), `bun check --no-script` (docs/agents/frontend-ci.md) | `bun test --parallel --shard=<i>/<n>` with `--timings` | `bun test --changed=<merge base>` |
| Python | `ruff format --check`, `ruff check`, `ty` (docs/agents/python-tooling.md) | pytest-xdist for cores (`-n auto`; `--dist loadgroup` keeps a group on one worker); pytest-split for shards (`--store-durations` on full runs, then `--splits <n> --group <i>`; use `--splitting-algorithm least_duration` when you randomize the order) | none built in: run the whole sharded suite unless a selection tool passes the proof above |
| Go | `go vet`, `golangci-lint` per target OS (docs/agents/go-tooling.md) | `go test` runs packages in parallel (`-p`, default `GOMAXPROCS`); shard the output of `go list ./...` | `go test` reuses a cached pass for a package whose test binary and inputs are unchanged. Seed `GOCACHE` from the default branch. Use cached results only when every input the test reads is a file inside its own module or an environment variable Go tracks; a file outside the module root, a generated file, an input of a child process, a service, or a database needs `-count=1`. `-shuffle` and `-count=1` turn the result cache off, so run `-shuffle=on` in the full run. The build cache stays on |
| Rust | `cargo clippy` per target (docs/agents/rust-tooling.md) | `cargo nextest` with `--partition slice:<i>/<n>` (even by count) or `hash:<i>/<n>` (stable when tests change). It balances by test count, not time, so measure the slowest shard against the mean. Build once and reuse the build in the shards (`cargo nextest archive`) | none stated |
| Lean | `lake build` | `lake test` runs the test driver | Lake skips what its trace files say is unchanged: restore the build directory from a cache seeded from the default branch. Its artifact cache (`lake cache get`) is experimental and off by default: measure before you rely on it |
| Quint | `quint typecheck`, `quint test`, `quint run` per spec file (docs/agents/formal-methods.md) | one parallel job per spec, with a fixed `--seed` | `quint verify` (Apalache) is an optional bug finder, never a gate: give it its own job and its own budget |
| Small checks | actionlint, shellcheck, markdownlint, YAML | one folded job (see "Shape") | none |
