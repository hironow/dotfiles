# 0032. Windows scoop restore: add `add-scoop` (supersede ADR 0019's record-only)

**Date:** 2026-07-05
**Status:** Accepted
**Supersedes:** [0019](./0019-windows-scoop-dump-record-only.md) (only the
record-only stance — `just dump` still writes `dump/scoop.json` exactly as 0019
specified; this ADR adds the restore half that 0019 deferred).

## Context

ADR 0018 deferred the Windows scoop *bootstrap* layer as "heavy"; ADR 0019 then
made `dump/scoop.json` **record-only** — deliberately no `add-scoop` — mirroring
`dump/npm-dlx`. That was the right call while bootstrap looked heavy (would need
to bootstrap scoop itself, integrate PowerShell/cmd for buckets, reason about
user-vs-system installs).

In practice a fresh Windows host ends up with **zero of the recorded apps
installed** after a full dotfiles setup: the operator must hand-install all nine
(7zip, gh, jq, just, mise, nmap, nodejs, ollama, shellcheck) by reading the JSON.
And the "heavy" concern turned out not to apply: **`scoop import <file>` is a
native scoop command** that reads a `scoop export` JSON, adds its buckets, and
installs its apps idempotently. Verified on a live host: it parses the repo's
*normalized* `dump/scoop.json` (which drops `Updated`/`Manifests`) and skips
already-installed apps. Crucially it needs **no jq** — jq is itself one of the
recorded apps, so a jq-parsing restore would be self-defeating on a fresh host.

## Decision

Add an `add-scoop` recipe (symmetry with `add-brew`) that restores from the
per-host manifest via `scoop import`:

- **Windows-only** (`uname` guard); hard-fail with a hint if scoop is absent or
  the manifest is missing/empty (same shape as `add-brew`'s empty-file guard).
- Resolve the host via `scripts/dump_host.sh resolve-restore` (arg / env
  `DOTFILES_HOST` / `dump/.host` / lone host dir — ADR 0030 per-host layout),
  then `scoop import ./dump/<host>/scoop.json` — scoop adds missing buckets and
  installs missing apps; already-installed apps are skipped (idempotent).

`just dump`'s Windows branch (ADR 0019, path per ADR 0030) is **unchanged** — it
still writes the normalized record. This ADR only adds the restore half.

## Relationship to prior ADRs

- **Supersedes ADR 0019's** "no `add-scoop`" stance; the dump/record half stays
  in force verbatim (path moved to `dump/<host>/` by ADR 0030).
- **Completes ADR 0018's** deferred "scoop bootstrap layer".
- `add-scoop` is **not** wired into `add-all` (which is `add-gcloud` +
  `add-brew`, Unix-only); it is a standalone Windows recipe, invoked once on a
  fresh host.

## Consequences

- A fresh Windows host runs `just add-scoop` once to restore the recorded apps.
- Restore is best-effort per scoop (needs network for bucket updates) and
  re-runnable; it never uninstalls apps absent from the manifest.
