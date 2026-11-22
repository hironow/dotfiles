# ADR 0088 — A CI speed standard for every language, with three rules that outrank speed

- **id**: ADR-0088
- **title**: A CI speed standard for every language, with three rules that outrank speed
- **status**: Proposed
- **date**: 2026-11-22
- **decided-date**: —
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session)
- **author-contact**: @hironow
- **supersedes**: part of [ADR-0078](0078-frontend-ci-under-two-minutes.md), on acceptance: its two-minute target (now p50 under 1 minute, p95 under 2), the oxlint-only lint wording (D3), and "every push to the default branch runs the whole suite" (D5, now "before anything reaches the default branch"). The rest of 0078 stands.
- **superseded-by**: none
- **related**: [0044](0044-python-toolchain-uv-ruff-ty.md), [0051](0051-adopt-decision-queue-for-new-records.md), [0052](0052-renew-global-agent-instructions.md), [0069](0069-type-check-and-lint-for-every-os.md), [0078](0078-frontend-ci-under-two-minutes.md), [0079](0079-dotfiles-follows-the-frontend-ci-guide.md), [0080](0080-established-terms-not-private-ones.md), [0083](0083-git-hooks-run-no-whole-repository-check.md), [0084](0084-git-hooks-only-check.md)
- **consultation-trace**: the owner's request in a Claude Code session on 2026-11-22 (see "Consultation")

## Plain summary

The owner shared how another team got their full CI under one minute, and asked that those rules become the standard for our CI.
This adds one spoke, `docs/agents/ci-speed.md`, that holds the rules for every language we use, and reshapes the TypeScript spoke to be the TypeScript part of it.
Three rules come first: the full suite still runs before anything reaches the default branch, no failure is ever hidden, and no check is ever removed to save time.
Four things in the shared text do not fit this repository as written; they are listed below with the reason, and they are not adopted.

## Context

- On 2026-11-22 the owner asked that the following become the standard CI rules in the ROOT agent instructions: an author's report (full CI under 1 minute; `bun test`, `bun check`, `bun lint`, `bun fmt`; shards filled by recorded test time; PRs run only the tests the diff can reach; parallel jobs), two extra lines (pass the PR's Git merge base to `bun test --changed=<base>`; shards balanced by past runtimes), and the author's full prompt. The owner added that we run CI for TypeScript, Python, Go, Rust, Lean and Quint, plus actionlint and shellcheck.
- The prompt is a task prompt ("Make this repo's CI as fast as possible without letting it lie"). Its rules: target p50 under 1 minute and p95 under 2; three rules that outrank speed; audit the last 150 runs (waiting, setup, running); budgets per stage; shard rules; "fewer tests, on evidence"; selection with a list of inputs that rerun everything; fail any job over budget; one small PR per change; bring accounts, secrets and bills as one list with monthly cost.
- Today: `frontend-ci.md` (ADR-0078) covers TypeScript only, with a two-minute target. dotfiles' own CI (ADR-0079) runs oxlint, `bun check` and `vp fmt`; "Frontend CI" is the one required check. Observed on PRs #629 to #643: Frontend CI about 30 seconds; the unit job 5.5 to 9 minutes; the Windows unit job 9 to 14 minutes; the dev container job 21 to 26 minutes. This repository is far over the new budgets (see Consequences).
- ADR-0083 and ADR-0084 (Accepted) say a hook never writes a file and no checking hook runs at pre-push. The owner's cleanup (#660, #663) removes tests that only pin wording unless an ADR asks for one. `performance.md` says narrowing a check on purpose is a change to the spec, decided on its own.

Everything that goes into the spoke was run or read on 2026-11-22:

| Claim | How it was checked |
| ----- | ------------------ |
| `bun test --changed=<tip of main>` over-selects on a branch behind its target; the merge base does not | scratch git repo, bun 1.4.5: the tip ran 2 of 2 test files, the merge base ran 1 of 2; on a GitHub-style merge commit with the tip as base, 1 of 2 |
| Stable Bun has `bun check` and `bun fmt` but no `bun lint`; Bun canary has `bun lint` | bun 1.4.5 (2026-11-19, the latest release): `bun lint` prints "Script not found". Bun 1.4.6-canary.1 (binary unpacked in a scratch folder; the installed Bun was not changed) has `bun lint`, `bun fmt` and `bun check` |
| Canary `bun lint` matches pinned `oxlint` 1.92.0 on the same files and the same `.oxlintrc.json` | our 3 files: 0 findings in both (518 and 517 rules enabled); 11 planted violations: the same 11 rule names in both, including a type-aware one (`no-floating-promises`), exit 1 in both; `options.typeAware: false` turns the type-aware rule off in `bun lint`, so it reads that option; 145 vendored third-party files with no ignore: the same 142 rules reported, 134 with identical counts, 8 with different counts (`sort-vars` 2189 vs 1687, `no-unused-vars` 58 vs 90, and six more), 126,578 vs 126,070 findings in total. The cause of the differences and of the one rule fewer is not known |
| `bun fmt --check` does not match the formatter we run | it flags all 3 of our own JS/TS files, while `vp fmt --check` passes: the default styles differ |
| `bun lint` and `bun fmt` run a same-named script unless `--no-script` | canary, with a `package.json` script that exits 0: `bun lint` and `bun fmt --check` both ran the script and exited 0 over a planted violation; `bun lint --no-script` exited 1, and `bun fmt --no-script --check` exited 1 on an unformatted file. `bun check` was shown the same way on 2026-11-16 |
| `bun test` flags combine | `--parallel --randomize --isolate --shard=1/2` ran; `--seed` implies `--randomize` |
| A test file can keep its `vitest` imports | bun docs, test configuration (`globals`) |
| GitHub merge queues are not available to user-owned repositories | GitHub docs: public repositories owned by an organization, and private repositories on Enterprise Cloud; `hironow/dotfiles` has `owner.type=User`. A required check must also trigger on `merge_group`. One unverified community report (2026-11-19) says otherwise |
| A pull request can only restore caches from its branch, its base branch and the default branch | GitHub docs, dependency caching; 10 GB per repository, evicted after 7 days unread |
| Waiting time is measured from the REST job `created_at` | the latest main run of Frontend CI: four jobs created 20:38:44, started 20:38:46; the dependent job created 20:39:01 (when the last needed job finished), started 20:39:03 |
| Go reuses a cached pass for unchanged packages, and its file tracking stops at the module root | go 1.27.4, scratch module: after a real change only that package re-ran; `-shuffle=on` and `-count=1` re-ran everything. `cmd/go/internal/test/test.go`: "Do not recheck files outside the module, GOPATH, or GOROOT root". This repository has such a test: `tools/agent-hooks/internal/toolhookcorpus/pirtk/oracle_test.go` reads `config/pi/extensions/rtk.ts`, outside its module |
| nextest and pytest-split | nextest docs: `slice:`, `hash:`, balance by count only; pytest-split docs: `--store-durations`, `--splits`/`--group`, `least_duration` works with random order, no completeness check |
| Lake and Quint | Lean docs: trace files, an experimental artifact cache, `lake test`; Quint CLI 0.33: `typecheck`, `test`, `run`, `verify` |

## Decision

Proposed requirements (MUST), if the owner accepts option A:

- D1: Add the spoke `docs/agents/ci-speed.md`: target (p50 under 1 minute, p95 under 2); the three rules that outrank speed; audit first; budgets (judged over many runs at p50 and p95, with a separate limit for a single run); waiting and setup; shape (parallel jobs, one folded job for the small checks); shards (including the proof that they ran every test, at the splitter's unit); selection (the merge base, the list of inputs that rerun everything, the hidden-change proof); before the default branch; fewer tests; tools; local hooks; how to work; and one table for TypeScript, Python, Go, Rust, Lean, Quint and the small checks.
- D2: `docs/agents/frontend-ci.md` becomes the TypeScript part: the same target; `bun lint --no-script` and `bun fmt --no-script --check` (Bun canary is the recommended way today, because stable Bun has no `bun lint` yet; each project decides, each time, between a pinned canary and stable Bun with `oxlint` and the same `.oxlintrc.json`; entering a canary stays that project's maintainer's decision, `dependency-policy.md`); the merge base for `--changed`; shard accounting; `--parallel --isolate --randomize`; Vitest and Jest suites move to `bun test` and may keep their `vitest` imports.
- D3: The hub gets one table row for `ci-speed.md`, and the existing bullet "Never weaken a check to make it pass" gains one sentence: in CI, no retries, no wider timeouts, no skipped tests. No new list item.
- D4: `draft-ci.md` says a workflow that runs in a merge queue also lists `merge_group`, and the draft gate does not apply to that event.
- D5: Before the default branch, use a merge queue where the repository can have one. Where it cannot (user-owned repositories), run the full suite as a required job on the pull request, require branches to be up to date, and let selection give early feedback only. Moving a repository to an organization is the human's decision.
- D6: Deleting a test is a change to the spec, decided with the human and never inside a speed change. Labels (`caught-regression`, `change-detector`) only nominate candidates; each assertion is checked before a deletion; tests for authorization, privacy, migrations and concurrency are never deleted.
- D7: The new spoke gets no wording test: no ADR asks for one, and #660 removed tests of that kind. ADR-0078 D8 stands for `frontend-ci.md`, and its test is updated to the new wording.

### Not adopted from the shared text

- **Local hooks that format, and a pre-push check that runs what CI runs (and `hk`).** ADR-0084 (Accepted) says a hook never writes a file and no checking hook runs at pre-push. The 9-second budget is adopted; what a hook may run stays in `enforcement.md`. The hook runner stays prek: nothing measured here argues for `hk`. If the owner wants ADR-0084 reversed, that is a new decision.
- **Moving every job to Blacksmith.** It needs an account and a bill. The spoke names it as the way to cut waiting time and puts it in the human's list; nothing is changed here.
- **Deleting oxlint everywhere.** The standard recommends `bun lint` through Bun canary, the only Bun that has it today, and the side-by-side run the prompt asks for was done (Context). Whether a project enters a canary or stays on stable Bun with `oxlint` is that project's decision each time, so nothing is deleted by this ADR. dotfiles stays on stable Bun with oxlint (ADR-0079) until its own decision.
- **A merge queue as written.** Not available to this repository; D5 is the fallback.

## Options Considered

| Option | Benefits | Costs and risks | Outcome (proposed) |
| ------ | -------- | --------------- | ------------------ |
| A) A language-independent spoke plus a TypeScript spoke (this proposal) | One place for the rules that hold in every language; the TypeScript details stay with the tools that have them; the unproven or conflicting parts of the shared text are named, not silently dropped | Two spokes to keep in step | Recommended |
| B) Put everything into `frontend-ci.md` | One file | The owner's scope is six languages; a TypeScript file would hold Go and Rust rules | Not recommended: wrong home |
| C) Add only hub bullets | The hub stays tiny | No room for the audit, budgets, the shard proof, or the per-language table | Not recommended: rules would not fit |
| D) Copy the author's prompt as a spoke | Nothing is lost | It is a task prompt with vendor and tool choices that conflict with ADR-0084, need accounts, and include a tool (`bun lint`) not in stable Bun | Not recommended: it cannot be followed as written |

## Consequences

- **Positive**: one standard for every language; the three rules put correctness first; each rule is something an agent can check, and the traps found while checking (a script that shadows `bun lint` and `bun fmt`; the tip of the target branch over-selecting; a Go test that reads a file outside its module; a file-level proof that cannot prove test-level shards) are written next to the rule.
- **Negative**:
    - dotfiles' own CI does not meet the budgets (see Context). Meeting them is a series of small PRs, one per change, each with before and after numbers. They are not part of this change: an audit recipe; caches seeded from main; shard accounting; one folded job for the small checks; `vp fmt` to `bun fmt` (a formatting commit, because all 3 of our files differ); oxlint to `bun lint` when stable Bun has it. Until the owner accepts this, dotfiles follows ADR-0078 and ADR-0079 as they are.
    - `bun lint` was compared side by side with `oxlint` (Context); `bun fmt` was not compared with the formatter we run (`vp fmt`), and the cause of the 8 differing rule counts is not known. The guide requires the comparison and a negative control at the time of each switch, per project.
    - This repository cannot have a merge queue, so the fallback runs the full suite on each pull request: selection gives early feedback but does not shorten the required result.
    - The Go result cache would serve a stale pass for `oracle_test.go` if it were relied on; the guide says to use `-count=1` for such tests.
- **Neutral**: no workflow, recipe, or ruleset changes in this PR. The required check stays "Frontend CI".

## Reversal

none

## Consistency with other decision records

All 87 records (0001 to 0087, 0046 absent) were scanned by title and status; the ones about CI, hooks, lint, type check, tests, Bun and workflows were read: 0044, 0069, 0078, 0079, 0083, 0084, 0085 and 0080. No PDRs.

- **Contradiction**: the shared text's pre-push check and format-on-commit hooks contradict 0084 (D1, D2). Not adopted (above). "No required job waits for another" would contradict 0078 D6 (the last job that gathers the results `needs` the others); the spoke exempts that one job. The rest does not contradict an Accepted record.
- **Partial supersession**: 0078 (target, lint wording, the default-branch rule), on acceptance; 0078's status line then says so and nothing else in it changes.
- **Duplication**: 0078 D4 to D6 (shards, selection, parallel jobs) are restated for every language in `ci-speed.md`; the TypeScript details stay in one place, `frontend-ci.md`.
- **Misreading**: `formal-methods.md` says Apalache (`quint verify`) is never a gate and that Lean is not used for the distributed-state model gate. The Quint row follows the first; the Lean row is for repositories that have Lean, as the owner said.
- **Channel rule**: `dependency-policy.md` makes entering a canary the decision of the repository's maintainer. The standard only recommends canary; each project decides, so this ADR moves no repository into a canary.
- **False relation, mistaken relationship**: 0083 and 0085 govern hooks, not CI jobs; 0085 is Proposed and unaffected. ADR-0079 stays in force: dotfiles' own conformance is follow-up work.

## Consultation

- 2026-11-22: the owner asked, in a Claude Code session, for the author's rules to become the standard CI rules in the ROOT agent instructions, and gave the author's full text and the list of our languages.
- The plan was reviewed by Codex in three rounds (REVISE with 6 findings, REVISE with 1, then APPROVE). Every finding was checked before it was adopted:
  `bun lint` and `bun fmt` run a same-named script unless `--no-script`; a file-level proof cannot show that test-level shards ran every test; the Go result cache is safe only for inputs inside the module; labels cannot justify deleting a test, and `performance.md` already makes it a spec decision; waiting time must come from the REST `created_at`, not the run's start; the hooks rule must point to ADR-0084 instead of restating it.
- Beyond the shared text, Claude added: the script-shadowing guard for `bun lint` and `bun fmt`; the proof at the splitter's unit; the Go module boundary; the REST measure for waiting time; "labels nominate, a human decides" for deleting tests; the user-owned repository fallback; and the `merge_group` sentence in `draft-ci.md`. The owner is asked to check these.
- 2026-11-22 13:36 JST: after seeing the side-by-side results, the owner decided that the standard recommends Bun canary (`bun lint` exists there today) and that each project decides, each time, which one to use. This replaces the first draft's "use `oxlint` until stable Bun has `bun lint`".

## Decision (pending)

- [ ] Accept A: finalize D1 to D7, record the public ruling, move the queue row to the decision log, and set 0078's status line to "Accepted; partly superseded by 0088".
- [ ] Accept with changes: specify the changes, revise the spokes and re-run the consistency check before settlement.
- [ ] Reject: remove the new spoke and restore `frontend-ci.md`.
- [ ] Defer: name a revisit condition.

Decision-maker: ____ (@hironow). Decision date: ____. Public ruling: ____.
