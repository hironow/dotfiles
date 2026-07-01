# 0030. Per-host dump layout (`dump/<host>/`)

**Date:** 2026-07-01
**Status:** Accepted
**Supersedes:** [0019](./0019-windows-scoop-dump-record-only.md) (partial — only
the fixed `dump/scoop.json` **path** moves to `dump/<host>/scoop.json`; ADR
0019's **record-only / no `add-scoop`** decision is unchanged and in force)

## Context

`just dump` wrote machine package manifests to single fixed files —
`dump/Brewfile`, `dump/gcloud`, `dump/scoop.json`. It dispatched only on OS
(`uname -s`), never on host identity. So two machines of the same OS
(mac mini vs MacBook) overwrote each other's `dump/Brewfile` last-writer-wins,
with no host tag and no committer signal to tell them apart. The difference
between two same-OS machines was therefore unrecoverable from the repo — ADR
0019 already named this hole ("a second Windows host has no source of truth").

Two facts shaped the design:

- An audit confirmed the committed `dump/Brewfile` / `dump/gcloud` were a
  byte-for-byte match for the maintainer's MacBook (delta = 0), so migrating
  them into a `dump/<this-mac>/` directory is provably correct — no other
  machine's state is entangled in them.
- Not every file under `dump/` is machine state. `gitignore-global` is **shared
  config** that `just deploy` distributes verbatim to every machine (ADR 0018);
  `dump/.gitconfig` is a tracked record (ADR 0021); `dump/npm-dlx` is a
  record-only doc (ADR 0017). Only Brewfile / gcloud / scoop.json actually
  differ per machine.

Because this repo is public, the per-host key must not leak the raw hostname
(the `scutil --get LocalHostName` slug). The key is a machine-chosen
**alias** (`macbook`, `windows`, …), not the hostname.

## Decision

Machine package manifests move under a per-host alias directory; shared config
stays at the `dump/` top level:

```
dump/
  <host>/            # per-host machine state (host = machine-chosen alias)
    Brewfile         #   mac/linux  (brew bundle)
    gcloud           #   mac/linux  (gcloud components)
    scoop.json       #   windows    (record-only, ADR 0019)
  gitignore-global   # SHARED — deployed to every machine (ADR 0018)
  .gitconfig         # SHARED tracked record (ADR 0021)
  npm-dlx            # SHARED record-only doc (ADR 0017)
  .host              # UNTRACKED machine-local alias (gitignore)
```

**Host alias resolution** is centralized in `scripts/dump_host.sh` (one helper,
not per-recipe copies) so `dump` and every `add-*` share one validator and one
fallback order:

- `resolve-dump`: `$DOTFILES_HOST` → `dump/.host` → **fail-loud**. You declare
  which host you are before recording it.
- `resolve-restore [host]`: positional arg → `$DOTFILES_HOST` → `dump/.host` →
  a **lone** `dump/<host>/` directory → fail (candidates listed) when 0 or >1.
  You can restore from any recorded host; ambiguity must be resolved explicitly.
- Both `$DOTFILES_HOST` and the untracked (hand-editable) `dump/.host` pass the
  **same** validator: one line, no surrounding whitespace, `^[a-z0-9][a-z0-9-]*$`.
  The slug rule alone rejects path traversal (`../x`), so no alias can escape
  `dump/`.

`just set-host <alias>` records the alias in the untracked `dump/.host`, so an
operator sets it once per machine without editing a shell profile. `$DOTFILES_HOST`
still wins over the file (and flows naturally into `install.sh`).

## Enforcement inventory

- **`scripts/dump_host.sh`** (new): `resolve-dump` / `resolve-restore` /
  `validate` / `set`. Reads `dump/` under the repo root, or `$DOTFILES_DUMP_DIR`
  when set (a test seam so resolution can be exercised in a tempdir without
  touching the real tracked `dump/`). shellcheck-clean.
- **`justfile`**: `dump` resolves the alias and writes `dump/$host/{Brewfile,gcloud}`
  (mac/linux) or `dump/$host/scoop.json` (windows); `gitignore-global` stays
  shared at `dump/gitignore-global`. `add-brew` / `add-gcloud` / `add-all` gain
  an optional `host` param and resolve via the helper. New `set-host` recipe.
- **`dump/<host>/`**: `dump/macbook/{Brewfile,gcloud}` and
  `dump/windows/scoop.json` seeded by `git mv` from the old fixed paths
  (history preserved).
- **`install.sh`**: mac restore resolves the host up front and dies with
  actionable guidance (`DOTFILES_HOST=<alias> bash install.sh` /
  `just set-host <alias>`) when a fresh multi-host machine cannot pick one.
- **`.gitattributes`**: `dump/scoop.json text eol=lf` widened to
  `dump/*/scoop.json text eol=lf`.
- **`.gitignore`**: `dump/.host` (machine-local alias).
- **`tests/test_justfile_windows_subset.py`**: static-parse guards that `dump`
  resolves per-host, keeps `gitignore-global` shared, and that `deploy`
  distributes only the shared copy; scoop assert updated to `dump/$host/scoop.json`.
- **`tests/test_just_sandbox.py`**: runtime guards for the empty-manifest error,
  dump fail-loud without an alias, `set-host` write/validate, and
  `resolve-restore` lone/multi/unknown. All host-writing cases run in an
  isolated `$DOTFILES_DUMP_DIR` tempdir and only ever ADD a synthetic
  `dump/testhost/`, so CI's bind-mounted checkout is never corrupted.
- **`README.md`**: dump section + Windows note updated to the per-host layout,
  cross-referencing this ADR.

## Consequences

**Positive**

- Same-OS machines coexist: `diff dump/macbook/Brewfile dump/macmini/Brewfile`
  is a real machine diff, not a time-conflated git-history guess.
- The per-host key is a public-safe alias; the raw hostname never enters git.
- One resolution helper means `dump` and `add-*` cannot drift in how they
  validate or pick a host.
- `git mv` preserves each manifest's history (`git log --follow` still works).

**Negative**

- `just dump` now fails until a host alias is set (`just set-host <alias>` or
  `DOTFILES_HOST`). This is the intended fail-loud, but it is one more step than
  the old zero-config `just dump`. The error message names the fix.
- A fresh machine with more than one recorded host must disambiguate the restore
  source explicitly; `install.sh` surfaces this rather than guessing.

**Neutral**

- Windows scoop stays exactly as record-only as ADR 0019 left it — no
  `add-scoop`, no bootstrap. Only its path is now per-host.
- Shared config (`gitignore-global`, `.gitconfig`, `npm-dlx`) is untouched;
  the deploy path is unchanged.
