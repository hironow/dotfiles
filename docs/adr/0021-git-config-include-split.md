# 0021. Split git config via `[include]` so dotfiles owns aliases + shared settings

**Date:** 2026-06-02
**Status:** Accepted

## Context

`~/.gitconfig` historically held everything in one file: the PC-local
identity and credentials (`user.email`, `user.signingkey`,
`gpg.program`, `credential.<host>.helper = !/opt/homebrew/...`,
`lfs "customtransfer.xet"`), the shared workflow defaults
(`commit.gpgsign`, `push.autoSetupRemote`, `rerere.enabled`,
`rebase.autoSquash`, etc.), and ~24 aliases including non-trivial
multi-line `!f() { ... }; f` worktree helpers.

Mixing the three categories in a single file blocked symlinking the
file from dotfiles: pushing `~/.gitconfig` wholesale to git either
leaks the GPG signing key id / credential helper paths, or forces
per-machine secrets into a single tracked file.

git already has the primitive for this: the `[include]` directive.
A `~/.gitconfig` can contain `[include] path = ...` lines that pull
in additional files, and the resulting config is the union of all
files (with later entries winning on key conflicts).

## Decision

Split `~/.gitconfig` into three files:

1. `~/.gitconfig` — **PC-local only.** Holds `user.email`,
   `user.signingkey`, `gpg.program`, `lfs "customtransfer.xet"`,
   `credential.*.helper`, and a trailing `[include]` block that pulls
   in the two dotfiles-managed files. Not symlinked, not tracked.
2. `~/dotfiles/config/git/shared.gitconfig` — workflow defaults
   shared across machines: `user.name`, `column`, `branch`, `init`,
   `diff`, `push`, `fetch`, `help`, `commit`, `rerere`, `rebase`,
   `filter "lfs"`, `tag`. Tracked.
3. `~/dotfiles/config/git/aliases.gitconfig` — all `[alias]` entries
   including the 24 worktree / workflow helpers. Tracked.

`~/.gitconfig` is left for the operator to set up by hand on each
machine because identity + signing key + credential paths legitimately
differ between hosts; symlinking would either force them into git or
require a separate secrets store.

## Enforcement inventory

### Entry points

- `git config --get <key>` lookups by any tool (git itself, gh CLI,
  tracked tools).
- `git <alias>` invocations.
- `commit.gpgsign = true` is read on every commit.

### Persistent / carried data needed at each enforcement point

- `~/.gitconfig` must contain a `[include]` block referencing both
  dotfiles files.
- `~/dotfiles/config/git/shared.gitconfig` must exist on disk before
  the first git command runs (otherwise `commit.gpgsign` / `user.name`
  fall back to defaults).
- `~/dotfiles/config/git/aliases.gitconfig` must exist before any
  aliased command resolves.

### Bypass candidates

- A new machine cloning dotfiles but not editing `~/.gitconfig` will
  miss the `[include]` lines and silently use stock git defaults
  (no aliases, no gpgsign, default push behaviour). Mitigation: this
  ADR doubles as the setup instruction; operators paste the include
  block once per machine.
- `git config --global --get-regexp '^alias\.'` returns 0 results
  even though `git <alias>` works, because `--global` only enumerates
  keys that physically live in `~/.gitconfig`. Use
  `git config --show-origin --get-regexp '^alias\.'` (no `--global`)
  to see the include-resolved set.
- A CI runner without a GPG key will fail every commit because
  `shared.gitconfig` forces `commit.gpgsign = true`. Mitigation: CI
  jobs set `GIT_CONFIG_GLOBAL=/dev/null` or run with
  `-c commit.gpgsign=false`.

### Tests proving coverage

- Manual smoke after deploy: `git config --show-origin --get-regexp '^alias\.' | wc -l` returns the count baked into
  `aliases.gitconfig` (currently 24).
- Manual smoke: `git config --show-origin --get commit.gpgsign`
  reports `file:.../shared.gitconfig\ttrue`.
- `git ss` (a tracked alias) resolves to `git status --short --branch`
  with no extra args.

## Consequences

### Positive

- Aliases and shared workflow defaults ride through git review.
- PC-local secrets (`user.signingkey`, credential helpers with
  homebrew paths) stay in the untracked `~/.gitconfig` and never get
  committed.
- Adding or tweaking an alias on one machine and pushing to
  `hironow/dotfiles` immediately propagates to every machine that
  pulls.
- `~/.gitconfig` shrinks from ~270 lines to ~30, making the local
  secrets visually obvious.

### Negative

- New-machine setup needs one manual edit of `~/.gitconfig` to add
  the `[include]` block — this cannot ride on `just deploy` because
  the file legitimately contains per-machine secrets.
- `git config --global` is now an unreliable enumeration of the
  effective settings; operators must learn to use `--show-origin`
  without `--global` for surveys.
- A CI runner pulling dotfiles will inherit `commit.gpgsign = true`
  and start failing commits unless overridden — captured under
  "Bypass candidates" above.

### Neutral

- `~/.gitconfig.bak.YYYYMMDD` files left behind by the migration
  remain untracked and are safe to delete manually after the new
  setup is verified.
