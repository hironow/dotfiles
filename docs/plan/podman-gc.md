# Podman GC: scoped safety evidence

ADR 0067 authorizes this narrower image/container GC policy. It does **not**
retain ADR 0035's automatic build-cache growth guarantee. No real inventory,
engine, machine, package manager, or service is used by the simulations.

## What was found and how

| Finding | Evidence | Status |
| --- | --- | --- |
| Forced image removal can delete referencing containers | Previous shell's public engine-only entrypoint emitted unsafe commands under fake I/O; faithful fake refuses newly referenced images unless forced | Replaced with individual nonforced `rmi --no-prune`; no force escalation |
| Implicit parent pruning can delete a young dangling parent | Fake rejects any removal lacking `--no-prune`; fresh-parent regression and model counterexample | Parent pruning disabled |
| Podman local tags have a `localhost/` qualifier | Mixed-alias and custom/qualified-prefix regressions run the actual script | Strip only `localhost/` from prefix and every RepoTag; any match retains the image |
| Failed inspection can otherwise look like an old/unreferenced image | Invalid timestamps/tags/reference data and enumeration errors injected at CLI boundaries; a failed tag decoder hidden in process substitution reproduced a real keep-invariant failure | Fail closed; checked decoder capture and re-inspection immediately before deletion |
| Bash retention multiplication wrapped into an unsafe cutoff | Public-script fake replay of `5124095576030431h` removed a fresh image and stopped container; independent arbitrary-precision age witnesses failed | Normalize decimal strings, validate clock success/signed range, compare duration to `floor(now/unit)` before multiplication; invalid/excessive values retain both inventories |
| Native image enumeration and inspection use different full-ID forms | Parent read-only observation: enumeration `sha256:<64hex>`, inspect `.Id` bare `<64hex>`; positive public-script collection regression failed | One strict image-ID normalizer per language for enumeration/inspection/container references; canonical bare lowercase 64hex, separate container identity |
| Blanket cache reclamation has no proven age-safe equivalent | Owner-reviewed Podman 6.1.4 `images.go`: All or BuildCache invokes unfiltered mount-cache cleanup | No automatic image/system/builder/buildx prune or mount-cache GC |

## Model and implementation boundaries

`scripts/spec/podman_image_gc.qnt` models one candidate and its parent. Its
`Safety` contains only required properties. The initial observation and final
observation are separate actions. A keep alias, metadata failure or foreign job
may appear before final inspection. A container reference may appear after final
inspection; nonforced engine removal refuses it. Equality at the retention
threshold retains the image: deletion requires age **greater than** 7200 seconds.

| Model property/action | Unix guard / I/O boundary | PowerShell guard / I/O boundary | Real-code tests in `test_podman_gc_simulation.py` |
| --- | --- | --- | --- |
| `ForeignJobProtection` | `_foreign_worker`, ancestry exclusion, recheck before removal | `Test-ForeignWorker`, ancestry exclusion, recheck | `test_dry_run_and_foreign_job_do_not_delete`, `test_own_worker_ancestor_is_not_a_foreign_job` |
| `ConfigurationProtection` | successful clock query, `_decimal`, signed bound, `_retention_secs` digit/lexical bound before arithmetic | `Get-PodmanCutoff`: decimal digit bound before integral conversion, clock exception/range checks | `test_invalid_or_excessive_retention_retains_both_inventories`, `test_invalid_clock_retains_both_inventories`, `test_decimal_leading_zeros_and_explicit_zero_collect` |
| `AgeProtection` | `_podman_image_eligible`: parsed Created `< PODMAN_CUTOFF` | `Test-PodmanImageEligible`: parsed Created `< Cutoff` | `test_real_script_two_hour_boundary`, `test_invalid_image_metadata_retained` |
| `MetadataProtection` | strict jq schema, successful container/image enumeration and inspection | guarded CLI result, strict JSON/property checks, exceptions retain remaining inventory | `test_reference_and_metadata_failures_retain_images`, `test_invalid_engine_identity_fails_closed` |
| `ObservedKeepProtection`, `observe` | `_normalize_keep_name` applied to each RepoTag; second image inspect | ordinal prefix comparison on every normalized RepoTag; second inspect | `test_observed_keep_alias_protects_whole_image`, `late_keep` replay |
| `ReferenceProtection`, `acquireReference` | fresh independent container reference snapshot; nonforced `podman rmi` | `Get-PodmanContainers`; nonforced guarded rmi | `test_reference_and_metadata_failures_retain_images` (`new_reference`) |
| `ParentProtection` | explicit `rmi --no-prune` | guarded `@('rmi', '--no-prune', ...)` | `test_successful_child_removal_preserves_fresh_dangling_parent` |
| `DeletePrecondition`, `remove` | all guards before individual rmi | all guards before individual guarded rmi | `test_public_gc_uses_nonforced_no_parent_prune`, `test_model_and_real_retention_and_guards_lockstep` |

The scripted `*Test` runs include the old forced-removal/parent-pruning
counterexample (`forceParentCounterexampleTest`). That test explicitly asserts
**not** Safety after an unsafe command; the unsafe action is never in normal
`step`. It is not an exception added to Safety. The normal simulation checks
Safety after every step. Quint sampling is bounded bug finding, not exhaustive
verification or proof of arbitrary real-engine behavior.

## Seed replay of actual code

The Python harness launches the complete `runner_gc.sh` using its public
engine-only entrypoint, and launches the complete `runner_gc_win.ps1` with
`-PodmanOnly` when `pwsh` is available. `PODMAN_GC_TEST_PWSH` picks another
PowerShell; one that is not an executable fails the run instead of skipping.
Each run prints the PowerShell version and edition it used. It does not copy
or extract selectors.
Only external I/O is replaced. Unix process discovery/clock/disk output are
stubbed; engine commands reach a JSON-backed fake. PowerShell process discovery, clock
and Start-Process are stubbed; the same fake supplies CLI responses and a fake
process replays timeout/tree-kill behavior.

The fake checks deletion preconditions, foreign-job/age/metadata/observed-keep
protection, reference preservation and a designated fresh parent after every
engine I/O boundary. It records policy violations against actual deletion
witnesses; this oracle never selects candidates. It requires the final image inspection immediately
before rmi, rejects forced or cascading removal, and refuses a new reference or
multiple tags without escalation. Image enumeration, inspection and container
reference wire representations vary independently over full bare/prefixed IDs;
the fake adapter resolves identity only, never eligibility. Malformed IDs and
mismatched inspection IDs retain resources, while eligible native-shaped images
must actually be collected. Container inspection identity remains separate.
Malformed JSON IDs ending in newline or NUL are rejected without Bash's raw
string decoding silently removing them; PowerShell uses absolute regex anchors.

The age oracle uses Python arbitrary-precision integers to interpret configured
durations and signed-range clocks independently of the scripts. Actual image
**and stopped-container** deletion witnesses are checked after every engine I/O.
Regressions cover overflowing hours, huge h/m/d/s counts, invalid/failed clocks,
leading zeros (including `08h`/`0007200s`), and explicit zero. Excessive duration
means before the Unix epoch and retains both inventories. PowerShell's old
`AddSeconds` range exception already failed closed: no equivalent unsafe PS
integer-overflow deletion was demonstrated. Its new integral bound avoids
floating-point duration parsing and aligns the retain-before-epoch policy.

No subprocess can fall through to a real
engine. Unix engine-only replay exits before filesystem janitors, with destructive
commands also stubbed as tripwires. A separate synthetic-root replay checks the
owner reentry's exact arguments; it stubs runuser and root maintenance I/O, and
has no workspace/toolcache trees. PowerShell exits before filesystem janitors. HOME/profile
and state are disposable. Assertions include the seed and full CLI trace.

```bash
uv run --frozen --group dev pytest -q tests/unit/test_podman_gc_simulation.py
PODMAN_GC_SEED=23 uv run --frozen --group dev pytest -q tests/unit/test_podman_gc_simulation.py -k seeded
# Required Windows/isolated PowerShell acceptance: absent pwsh fails explicitly.
PODMAN_GC_REQUIRE_PWSH=1 uv run --frozen --group dev pytest -q tests/unit/test_podman_gc_simulation.py -k powershell
# The same cases on a chosen PowerShell.
PODMAN_GC_TEST_PWSH=/path/to/pwsh uv run --frozen --group dev pytest -q tests/unit/test_podman_gc_simulation.py -k powershell
```

Default coverage is 32 Unix seeds and 32 PowerShell seeds. Missing `jq` fails the
required Unix simulation. Missing `pwsh` is reported as unverified/skipped unless
the explicit required-platform gate above is selected. It is not PowerShell
acceptance. PowerShell 5.1 ASCII/source-compatibility checks run independently of
runtime availability.

`test-podman-gc-compat.yaml` runs `Get-PodmanJson` on native Windows PowerShell
5.1 (`tests/powershell/get_podman_json_51.ps1`): `Created` in UTC, with an
offset, and with nanoseconds stays the wire string; a one-element inspection
comes back as the object itself, with `RepoTags` still an array (5.1's
`ConvertFrom-Json` writes a top-level JSON array as one `Object[]`); and a bad
reply throws. The full replays run on native 5.1 with
`DOTFILES_TEST_PWSH=powershell.exe`, outside CI. The real watchdog and engine
remain platform acceptance work. The same workflow runs the PowerShell replays on
PowerShell 7.4.22 as an observation only; 7.4 is not supported. Its
`ConvertFrom-Json` has no `-DateKind`: a `Created` it reads as a date becomes
`DateTime`, and that item is kept. A form it does not read as a date, such as
nanoseconds, stays a string and passes the usual checks.

## Parent integration contract

The parent reports this formal recipe is already wired in its separate worktree;
this lane does not edit the shared justfile or require a new interface snippet.
The integration contract remains **one** pinned variable
(the existing canonical host/image pin remains unchanged):

```just
QUINT := "mise x npm:@informalsystems/quint@0.33.0 -- quint"
```

Keep the following required recipe, and `just spec-check` before the final success
line of `check`. No checker absence or failed loop iteration is a success.
The TypeScript evaluator is explicitly selected; it needs no downloaded Rust
backend or optional Apalache/JVM verifier.

```just
[group('Lint')]
spec-check:
    #!/usr/bin/env bash
    set -euo pipefail
    for spec in scripts/spec/*.qnt; do
        {{QUINT}} typecheck "$spec"
        {{QUINT}} test "$spec" --backend typescript --max-samples 100
        {{QUINT}} run "$spec" --backend typescript --invariant Safety --max-samples 1000 --max-steps 12 --seed 565 --verbosity 1
    done
    {{UV_RUN}} --group dev pytest -q tests/unit/test_podman_gc_simulation.py
```

Caller names: `RUNNER_GC_DOCKER_ONLY=1` → `RUNNER_GC_PODMAN_ONLY=1`,
`-SkipDocker` → `-SkipPodman`, `-DockerTimeoutSec N` → `-PodmanTimeoutSec N`.
The only pre-migration production occurrence was the root-owner reentry, now
updated inside `runner_gc.sh`; the shared justfile has no old flags to replace.
Deprecated aliases remain restrictive and still use only Podman. Existing
`bash scripts/runner_gc.sh` and installed payload paths are unchanged. The root justfile describes cleanup of stopped Podman containers and
individually selected aged images, explicitly excluding build/mount cache.
Unix requires existing `jq`; no new dependency or permanent install is added.

## Remediation regression receipts

Before production fixes, the full-digest structural fixture baseline passed
12 tests. The two selected public-script regressions then failed real assertions:
`test_invalid_or_excessive_retention_retains_both_inventories` with
`5124095576030431h` recorded fresh-container/image deletion age violations, and
`test_native_full_image_identity_collects[True-False-shell]` collected nothing
instead of its eligible image. These are not missing-tool/import/mock failures.
The same regressions pass after the checked cutoff and normalization changes.
A further strict-ID assertion exposed Bash substitution stripping a terminal
newline from malformed inspect metadata; lossless capture and pre-decode NUL
rejection now pass the control-suffix regressions.
PowerShell equivalents are authored but require the parent's runtime acceptance;
source checks are not evidence of PowerShell execution.

Remediation checks: focused runner/replay/text-encoding tests passed 186 with 96
explicit platform skips (PowerShell/native Windows unavailable). Ruff lint and
format, ty, shellcheck and Bash syntax passed. Pinned Quint 0.33.0 typechecked;
all 10 scripted tests passed with the TypeScript backend and `--max-samples 100`.
Safety sampling found no violation in 1000 traces, 12 steps, seed 565 (`0x235`),
TypeScript backend. Replay seed 23 passed on Unix; PowerShell skipped. Selecting
`PODMAN_GC_REQUIRE_PWSH=1` explicitly failed its mandatory runtime assertion, as
required on this host; that failure is not PowerShell acceptance.

## Exclusions and remaining acceptance

- Quint's `configurationOk` abstracts fail-closed configuration/clock validation;
  mathematical integers do not model Bash machine overflow. Concrete full-ID
  representations/JSON/date parsing are also omitted from the abstraction.
  Public-script fake-I/O regressions, not Quint, check those implementation details.
- Arbitrary third-party retag **after** final inspection is not atomically fenced.
- Foreign-job checks are point-in-time observations, not a global lock. The
  existing explicit FORCE override is outside `ForeignJobProtection` in the model.
- Unchanged workspace, toolcache, apt/journal, WSL compaction and disk-cache
  policies are outside the new image-GC model. Unix dry-run restricts itself to
  the engine leg; Windows retains its existing full dry-run semantics.
- Native Podman command semantics, selected owner contexts, machine/socket
  configuration, Windows 5.1 runtime and real timeout termination require the
  parent's isolated/platform acceptance. No child performs live GC, even dry-run.
