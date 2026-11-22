# Frontend CI: TypeScript

Read this when you write or change CI, or the `just` gates it calls, for
TypeScript or other code that runs in a browser page. The rules for every
language (budgets, selection, the merge queue) are in docs/agents/ci-speed.md.
This guide is the TypeScript part.

The target: a pull request gets its result in under one minute at the median
and under two minutes at the 95th percentile (p95). Measure the run before and
after a change, and give both numbers in the PR.

Speed never buys a weaker gate. List the required checks before and after the
change (every lint, type check, build, and test suite), and show that the
pull request still runs the same required checks.

Five rules get you there.

## 1. Type check with `bun check`, not `tsc`

`bun check` reads the same `tsconfig.json` as `tsc`, reports the errors that
`tsc` from TypeScript 7 reports, and uses every CPU core.

| Instead of          | Run                         |
| ------------------- | --------------------------- |
| `tsc --noEmit`      | `bun check --no-script`     |
| `tsc -b`            | `bun check --no-script -b`  |

- Always pass `--no-script`. When `package.json` has a `check` script,
  plain `bun check` runs that script instead of the type checker, and a
  script that only formats exits 0 with the types unchecked.
- `bun check` never writes files. Where `tsc` or `tsc -b` writes output that
  something uses (`.d.ts`, JavaScript, build info), keep that command in the
  build recipe and replace only the type check.
- A project on TypeScript 5 or 6 can get new errors, because `bun check`
  behaves like TypeScript 7. Fix them; do not go back to `tsc` to hide them.

## 2. Lint and format with Bun, never through a script

- Lint with `bun lint --no-script`. It reads `.oxlintrc.json`. Bun canary is
  the recommended way today: stable Bun has no `bun lint` yet, and Bun
  1.4.6-canary.1 gave the same results as `oxlint` on our files. Each project
  decides, each time, between a pinned Bun canary (the exact version) and
  stable Bun with `oxlint` and the same `.oxlintrc.json`; entering a canary is
  that project's maintainer's decision (docs/agents/dependency-policy.md).
  Moving later changes only the command.
- Check formatting with `bun fmt --no-script --check`. Its default style
  differs from oxfmt and Prettier, so a switch is one formatting commit by
  itself (Tidy First), with no other change in it.
- Always pass `--no-script`. When `package.json` has a script with the same
  name, `bun lint` and `bun fmt` run that script instead, and a script that
  exits 0 checks nothing. Prove each switch with a negative control: plant a
  violation, keep a same-name script that exits 0, and see the command fail.
- Turn on all seven categories as errors in `.oxlintrc.json`: `correctness`,
  `suspicious`, `pedantic`, `perf`, `style`, `restriction`, and `nursery`.
  By default only `correctness` is on.
- List every plugin that fits the code in `plugins`. The list replaces the
  default set, so keep the defaults in it.
- Turn on the type-aware rules with `"options": { "typeAware": true }` in
  `.oxlintrc.json`. `oxlint` also needs the `oxlint-tsgolint` package; `bun lint`
  reads the same option and takes its types from `bun check`.
- When a rule cannot hold in this repo, turn off that one rule by name and
  write the reason in a comment next to it. Never turn off a category, and
  never lower one to `warn`, to get a green run.
- While you run `oxlint`, install it and `oxlint-tsgolint` as dev dependencies
  with an exact version that has passed the cooldown
  (docs/agents/dependency-policy.md), and run `bunx --no-install oxlint`, so
  CI never fetches an unpinned copy.

## 3. Fill test shards by recorded time

Split the suite across CI machines with
`bun test --shard=<i>/<n> --parallel`. Without recorded durations each shard
gets the same number of files, and one shard can get all the slow ones.

- Every shard of one run reads the same recorded files: pass one
  `--timings=<file>` for each. The durations decide where the shards are
  cut, so shards that read different files can skip a test or run it twice.
- Each shard passes `--update-timings` and writes to its own file, in a
  folder the shards that are still running do not read. `--update-timings`
  writes to the first `--timings` path, so name the shard's own new file
  first and the recorded files after it. Put a recorded file first and the
  shard overwrites its input.

  ```sh
  bun test --parallel --shard=<i>/<n> --update-timings \
    --timings=timings/next/<i>.json \
    --timings=timings/1.json --timings=timings/2.json
  ```

- Collect those files in one job after every shard passed, and save them to
  the CI cache as the next run's input. Do it on every full run of the
  default branch and the merge queue. A failed or cancelled run saves nothing.
- Buy cores before shards: use a larger runner before you add a shard, and
  match the `--parallel` workers to its cores. Choose the number of shards
  from the recorded total, so that the slowest shard fits the target.
- Prove that the shards together ran every test file they were given. In a
  full run, compare the list of all test files with the files the shards
  report. In a selected run (rule 4), compare the files the selection chose,
  computed on their own, with the files the shards report. Fail on a missing
  file, a duplicate, or a shard that never ran (docs/agents/ci-speed.md).
- Run `bun test --parallel --isolate --randomize`. `--isolate` gives each file
  a fresh global and module registry, the workers are reused, and
  `--randomize` prints a seed; `--seed <n>` reproduces a failure.

## 4. On a pull request, run only the tests the diff can reach

- The whole suite is the default. Run
  `bun test --changed=$(git merge-base origin/<base branch> HEAD)` only when
  imports cover the diff: every changed file is a source or test module that
  the tests load with a static `import`.
- Pass the merge base, not the tip of the target branch. A branch that is
  behind its target would select the tests for the target's own newer changes:
  in a trial, `--changed=main` ran 2 of 2 test files, and the merge base ran
  only the 1 the pull request touched.
- `--changed` follows `import` statements only. A file the tests read
  another way (a fixture, a snapshot, a config file, `package.json`, the
  lockfile, the workflow, a path built at run time) selects no test, and the
  run passes with that test never run. When the diff touches any such file,
  or a file you cannot place, run the whole suite.
- One root `just` recipe decides which of the two runs, from the list of
  changed paths. Test that recipe: a changed fixture must give the whole
  suite.
- Fetch enough history that the merge base exists (`fetch-depth: 0` with
  `filter: blob:none`). A missing ref fails the run, which is the right
  result.
- The full suite runs before anything reaches the default branch: in the merge
  queue, or as a required job where there is no queue (docs/agents/ci-speed.md).

Rules 3 and 4 are for `bun:test` suites. Move Vitest and Jest suites to
`bun test` first; a test file may keep its `vitest` imports. End-to-end suites
and suites on another runner keep running as docs/agents/testing.md says; do
not drop one because these flags do not reach it.

## 5. Run lint, typecheck, build, and tests in parallel

- Make lint, typecheck, build, and each test shard separate jobs. None of
  them `needs` another, so the slowest one sets the time, not their sum.
  When a test needs build output, build it inside that job.
- Each job runs one root `just` recipe, so the gate on your machine and the
  gate in CI are the same command.
- Add one last job that `needs` every required job of this workflow, and
  make it the required check for this workflow. Give it `if: always()`
  together with the draft gate (docs/agents/draft-ci.md), and let it pass
  only when the result of every job it needs is `success`.
- A job with `needs` alone is skipped when a job it needs fails, and GitHub
  counts a skipped required check as passed.
- The last job covers its own workflow only. Checks that another workflow or
  an outside service reports stay required as they were.
- Keep the list of required jobs in one place, and check in the workflow
  lint that the last job needs every job on it, so a new required job cannot
  be left out of the merge gate.
