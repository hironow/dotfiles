# 0019. Windows scoop manifest in `dump/` — record-only

**Date:** 2026-06-02
**Status:** Accepted

## Context

ADR 0018 (Accepted 2026-06-02) implemented Windows native MVP at the
`install.sh` / `justfile` level but explicitly deferred the full scoop
bootstrap layer ("`add-*` recipes equivalent to brew bundle / gcloud
components") to a future ADR. The reasoning was sound: bootstrap is a
much heavier commitment than dump.

But while ADR 0018's ink was still wet, two real tools were added to the
Windows host by hand — `shellcheck` (for the `just lint` pre-commit hook
during PR #128) and `jq` (for the `claude-code-warp` plugin's stop hook
right after merge). They were recorded only in a memory file
(`project_windows_plugin_hooks_need_unix_clis.md`), not in the repo.
Memory drifts: a second Windows host has no source of truth, and even
this host's record is invisible to anyone not in the same Claude
session.

The repo already has a precedent for the dump/install split:
`dump/npm-dlx` lists `pnpm dlx` packages the operator commonly runs but
deliberately does **not** auto-install them. The file is read-only
documentation; `just check-pnpm-dlx` grep-lists it; there is no
corresponding `add-pnpm-dlx`. That same shape fits scoop perfectly: dump
what's there, do not restore from it.

## Decision

Add a Windows branch to the existing `just dump` recipe that writes
`dump/scoop.json` via `scoop export`, normalized with `jq` for diff
stability. **No** `add-scoop` / `update-scoop` / `check-scoop` recipe.
The bootstrap layer remains exactly where ADR 0018 left it: future work,
out of scope.

Concretely, `dump`'s Windows branch:

```sh
windows)
  scoop export | jq '{
    buckets: [.buckets[] | {Name, Source}] | sort_by(.Name),
    apps:    [.apps[]    | {Name, Version, Source}] | sort_by(.Name)
  }' | tr -d '\r' > ./dump/scoop.json
  exit 0
  ;;
```

Three normalization choices matter and are pinned by tests:

1. **Drop `Updated` timestamps** (apps and buckets both carry per-app
   ISO-8601 install times that change on every `scoop install`).
2. **Drop `Manifests` counts** on buckets (changes whenever upstream
   buckets receive new manifests, independent of local state).
3. **`sort_by(.Name)`** for both arrays (scoop export emits in install
   order; without sort, every reinstall reorders the diff).

`tr -d '\r'` is belt-and-suspenders alongside `.gitattributes`
(`dump/scoop.json text eol=lf`): scoop on Windows can emit CRLF, and
either guard alone has failed in past experiences elsewhere.

The "documentation layer" / "bootstrap layer" split is the load-bearing
distinction:

- **Documentation layer (this ADR)**: declarative record of what is
  installed. Operator can inspect, diff, code-review. No install
  side-effects.
- **Bootstrap layer (ADR 0018 deferred)**: one-shot install from a
  declarative source on a fresh host. Heavy: needs scoop itself to
  bootstrap, needs Powershell / cmd integration for buckets, needs to
  reason about user vs system-wide installs, etc.

Keeping these layers separate means each can evolve independently and
each ADR has a single responsibility.

## Enforcement inventory

- **`justfile`**: `dump` recipe converted to shebang bash + `case
  "$(uname -s)"` dispatch (same pattern PR #128 introduced for
  `deploy`/`clean`). Windows branch writes `dump/scoop.json`; Mac/Linux
  tail (brew bundle / gitignore / gcloud) preserved verbatim. Missing-
  tool guards (`command -v scoop` / `command -v jq`) emit a hint and
  `exit 1` rather than producing a half-written file.
- **`dump/scoop.json`**: tracked in repo. Seeded by running `just dump`
  on the current Windows host once at ADR 0019 landing time.
- **`.gitattributes`** (new): one line, `dump/scoop.json text eol=lf`.
  Belt-and-suspenders with `tr -d '\r'` in the recipe.
- **`tests/test_justfile_windows_subset.py`**: five new tests pin the
  contract:
    - `test_dump_has_windows_branch`
    - `test_dump_windows_writes_scoop_json`
    - `test_dump_windows_normalizes_with_jq` (asserts `jq` + `sort_by`
      + that `Updated`/`Manifests` tokens are absent from the branch
      body — a re-include would defeat diff stability)
    - `test_dump_windows_has_no_install_side` (asserts `scoop install`
      does NOT appear — record-only invariant, separates this ADR from
      ADR 0018's deferred bootstrap)
    - `test_dump_windows_exits_before_unix_path` (asserts `exit 0`)
- **`README.md`**: the L68 Windows-native note is extended to mention
  the dump in addition to the existing subset and to cross-reference
  ADR 0019.
- **Memory** (`memory/project_windows_plugin_hooks_need_unix_clis.md`):
  the "currently installed list" sentence becomes a pointer to
  `dump/scoop.json`. The broader "hook needs Unix CLI → scoop install"
  pattern stays in memory.

## Consequences

**Positive**

- `shellcheck`, `jq`, and any future scoop-installed tools on the Win
  host are now tracked declaratively and reviewable in PR diffs. The
  memory layer for "what's installed where" becomes redundant for this
  slice and can shrink to the abstract pattern.
- A second Windows host has a single file to consult: "here are the
  tools the maintainer's host runs; install whichever you need by
  hand". This is exactly the relationship `dump/npm-dlx` has with `pnpm
  dlx`.
- `just dump` is now a single entry point regardless of OS — operators
  do not need to remember which subset their platform supports.
- The "documentation vs bootstrap" split is now codified, so the
  eventual bootstrap ADR can land without re-litigating where dump
  belongs.

**Negative**

- Fresh-host restore is still a manual walk through `dump/scoop.json`
  — same UX as `dump/npm-dlx`. Operators who expected `just add-scoop`
  symmetry with `just add-brew` will be momentarily surprised; the
  README note and ADR cross-reference are the mitigations.
- The Windows host depends on `jq` being installed before `just dump`
  works, which is mildly circular: `jq` came in via the very pattern
  this ADR documents. The missing-tool guard in the recipe handles it
  gracefully (`exit 1` with a `scoop install jq` hint).

**Neutral**

- ADR 0018's "scoop bootstrap = future ADR" stance is fully preserved.
  That future ADR is now strictly about the install side; this ADR
  removes the documentation-layer concern from its scope so it can be
  scoped tighter when it arrives.
- `dump/scoop.json` includes the `wangzq` bucket (one local-source
  bucket with 0 manifests visible at dump time) verbatim. Cleanup of
  unused buckets is an operator concern, not a `just dump` concern.
