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
| `test_the_gates_reopen_on_a_valid_lease` | 6.2 | L1 puts the router and the controller back on the new lease after `drained` (a Cancel of the old record; Reopen is for a gate shut with no record), and an extend during a drain restores both mid-drain (Cancel). |

`test_control_api_barrier.py` is plan F5 in one task, about 5 node-minutes
on top of a wake. The Control API authenticates its callers but does not
authorize them. An actor's TCP leaves through the egress gateway, so the
guest's path is closed by authentication, and the worker pod's path by
`tofu/exe-cluster/control_api.tf`:

| test | item | what it proves |
| --- | --- | --- |
| `test_a_task_cannot_authenticate_to_the_control_api` | 6.9 (F5) | An unauthenticated gRPC call from the task gets grpc-status 16 (UNAUTHENTICATED), and the guest has no /var/run/secrets. What the guest's handshake reaches through the gateway is recorded, not asserted. |
| `test_a_pod_in_the_atespace_reaches_the_api_only_without_the_policy` | F5 | A probe pod in the atespace, standing in for a worker pod: with `EXE_E2E_API_POLICY=absent` it gets an answer (the path exists), with `present` it gets none. |
| `test_the_callers_still_work_behind_the_policy` | F5 | With `present`: an L1 tick still reads Substrate, and the ax-controller still suspends and resumes a task. |

`test_forced_stop.py` runs alone, about 30 node-minutes (most of it L2's
20-minute heartbeat window), and only with the
operator on email:

| test | item | what it proves |
| --- | --- | --- |
| `test_forced_stop_pages` | 6.8 | With L1's CronJob suspended (restored afterwards whatever happens), an awake task, and the lease run out at once (`just exe-sleep`), L2 forces the stop after the heartbeat window (heartbeat_stale_ticks L2 ticks, 20 minutes) and within one L2 tick of it. The decision, read from Cloud Logging since a scheduled tick may force first, is logged at ERROR with notify set, which is what the "exe: L2 forced a stop" alert matches. |

The operator confirms by hand that the forced stop's email arrived: the
Monitoring API has no public call to read an incident. The forced stop takes
the awake task's actor down with the node, so that task is left behind; the
test prints its name, and it is deleted at the next wake.

## What every run leaves

- 0 nodes, unless `EXE_E2E_KEEP_AWAKE=1`. With it, the tasks are still
  deleted but the node stays up, so one wake serves several modules in a row
  (W3); the window's last run goes without it, and the lease stays the
  backstop.
- Without it: 0 nodes. The `exe` fixture deletes the test's tasks while a node is up,
  sleeps, and runs L2 until the node is gone, even when the test failed. If
  the node is still up 30 minutes later it fails loudly: page the operator.
- `measurements.jsonl` in `$EXE_E2E_OUT`, or in a fresh temp dir whose path
  the run prints. It has one JSON line per measurement: wake to ready, each
  drain record, the stop latency (setSize(0) to the node gone, from GKE's
  operations, plan D8), the first L1 tick after a wake, and the Control API
  probe. The phase report takes its numbers from there.
