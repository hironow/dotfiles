# tests/e2e/exe

The exe stack's stop paths, end to end, against the real cluster (Phase 6
plan D13). Each test wakes the node, runs real tasks and stops the real pool,
so each one costs node time. Without `EXE_E2E=1` every test here is skipped;
`just exe-e2e` is the way in.

No mocks: a stand-in for the cluster would assert nothing about it, and
`.semgrep/rules/e2e/exe-e2e-no-mocks.yaml` fails `just check` on one.

## Running

```bash
just exe-ctx                                  # once: the kubeconfig
export EXE_E2E_IMAGE="$(just exe-image)"      # or an image already pushed
just exe-e2e tests/e2e/exe/test_graceful_stop.py  # W2: 6.2, 6.7, 6.9
just exe-e2e tests/e2e/exe/test_forced_stop.py    # W3: 6.8, operator on email
```

`EXE_E2E_IMAGE` is the task image every test runs, pinned by digest in the
exe-task repository. Extra words after `just exe-e2e` go to pytest. Check for a
running `UPGRADE_MASTER` operation before a run, and never run during
03:00-04:00 JST, the hour before the nightly stop.

## What each test does, and what it costs

`test_graceful_stop.py` is one scenario on the node, two sleeps and two wakes,
about 45 node-minutes; separate tests would each pay their own wake and sleep.
Two tasks, A and B, are awake with a marker in their workspace when the lease
runs out. B is resumed while the drain is `draining`, and A right after
`drained`. The scenario runs once in a module fixture, and each test asserts
its own part:

| test | item | what it proves |
| --- | --- | --- |
| `test_graceful_sleep_keeps_files` | 6.7 | L1 drains to `drained` for that lease, L2 stops with `stop-graceful` and no forced-stop or ERROR line, the node goes, and A comes back with its marker. |
| `test_a_resume_while_draining_still_ends_suspended` | 6.9 | B's resume during the drain still ends in `drained`. The first L1 tick of the next wake, which observes before it reopens anything, sees no actor awake, and B comes back with its marker. |
| `test_a_resume_after_drained_runs_at_the_next_wake` | 6.9 | A's resume after `drained` finds no controller pod, the stop stays graceful, and the resume runs by itself at the next wake, as the operator asked. |
| `test_a_task_cannot_reach_the_control_api` | 6.9 (F5) | From inside B, a TLS handshake with the Control API, by name and by ClusterIP, gets no answer. |
| `test_the_gates_reopen_on_a_valid_lease` | 6.2 | L1 puts the router and the controller back on the new lease after `drained` (a Cancel of the old record; Reopen is for a gate shut with no record), and an extend during a drain restores both mid-drain (Cancel). |

`test_forced_stop.py` runs alone, about 15 node-minutes, and only with the
operator on email:

| test | item | what it proves |
| --- | --- | --- |
| `test_forced_stop_pages` | 6.8 | With L1's CronJob suspended (restored afterwards whatever happens), an awake task and a 5-minute lease, L2 forces the stop after the heartbeat window and within one L2 tick of it. The decision is logged at ERROR with notify set, which is what the "exe: L2 forced a stop" alert matches. |

The operator confirms by hand that the forced stop's email arrived: the
Monitoring API has no public call to read an incident. The forced stop takes
the awake task's actor down with the node, so that task is left behind; the
test prints its name, and it is deleted at the next wake.

## What every run leaves

- 0 nodes. The `exe` fixture deletes the test's tasks while a node is up,
  sleeps, and runs L2 until the node is gone, even when the test failed. If
  the node is still up 30 minutes later it fails loudly: page the operator.
- `measurements.jsonl` in `$EXE_E2E_OUT`, or in a fresh temp dir whose path
  the run prints. It has one JSON line per measurement: wake to ready, each
  drain record, the stop latency (setSize(0) to the node gone, from GKE's
  operations, plan D8), the first L1 tick after a wake, and the Control API
  probe. The phase report takes its numbers from there.
