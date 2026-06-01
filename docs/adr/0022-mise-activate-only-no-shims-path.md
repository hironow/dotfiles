# 0022. Use `mise activate` only in interactive shells, drop manual `shims` PATH entries

**Date:** 2026-06-02
**Status:** Accepted

## Context

`~/.zshrc` historically wired mise two ways at once:

1. `eval "$(mise activate zsh)"` — installs a chpwd/precmd hook that
   prepends the resolved tool bin dirs (e.g.
   `~/.local/share/mise/installs/node/24.15.0/bin`) to `PATH` directly
   when needed.
2. `path_prepend "$HOME/.local/share/mise/shims"` — placed the shim
   wrapper directory on `PATH` so tools resolve through the
   `~/.local/share/mise/shims/<tool>` wrapper script.

Adding both made `mise doctor` emit:

```text
shims are on PATH and mise is also activated. You should only use one
of these methods.
```

This is not a fatal warning — both methods route to the same install
dir — but it persists on every shell start and during every `mise
doctor` run, and the duplication means the same tool can be resolved
two ways, which is a footgun when debugging which version a process is
actually using.

mise's getting-started doc is unambiguous: **for interactive shells use
`activate`, for CI/scripts/IDEs use `shims`.** The two are alternative
ways to expose the same install dir, not complements.

## Decision

In `~/.zshrc`:

1. Remove **both** manual `path_prepend "$HOME/.local/share/mise/shims"`
   calls (there were two: one inside the `if _cmd_exists mise` block,
   and one at the bottom "re-assert at the front" comment).
2. **Move `eval "$(mise activate zsh)"` to the end of the file**, after
   every other `PATH` mutation (vite-plus env, Antigravity, dbt Fusion,
   CF CLI completions, etc.). `mise doctor` flags
   `mise tool paths are not first in PATH` when later sections prepend
   their own dirs in front of mise's; running `activate` last makes
   mise's chpwd/precmd hook the final word.
3. Leave a breadcrumb comment at the historical location explaining
   why `eval` is at EOF, so future readers grep'ing for `mise activate`
   find both halves.

`~/.zshenv` (already exists) stays untouched. If a future need
arises for cron / launchd / IDE to resolve mise-managed tools without a
shell, `~/.zshenv` is the right place to add the shims dir — `.zshenv`
is sourced for every zsh invocation including non-interactive ones,
while `.zshrc` is interactive-only.

## Enforcement inventory

### Entry points

- Interactive zsh shells (terminal, ghostty, tmux panes).
- `mise doctor` itself (the test harness).
- Any subprocess that inherits `PATH` from the interactive parent
  (e.g. just recipes, npm scripts).

### Persistent / carried data needed at each enforcement point

- `eval "$(mise activate zsh)"` must run once per interactive shell.
  It installs the chpwd/precmd hook that maintains `PATH`.
- `mise` binary itself must be on `PATH` before line 122 runs — this
  is satisfied by `path_prepend "/opt/homebrew/bin"` earlier in the
  file.

### Bypass candidates

- **Cron / launchd jobs** run with a minimal `PATH` and never source
  `~/.zshrc`. If such a job needs a mise-managed tool, it must
  explicitly invoke `mise exec -- <tool>` or have `~/.zshenv` (or its
  own equivalent) put `~/.local/share/mise/shims` on `PATH`. This ADR
  intentionally does **not** ship that change; today no cron job in
  this repo needs mise tools.
- **IDEs (VS Code, etc.)** spawning shells without `.zshrc` (e.g.
  `bash -c`) miss the activate hook. Resolution: configure the IDE to
  use zsh as the integrated terminal shell (which sources `.zshrc`),
  or set `MISE_SHELL=zsh` + run `mise activate` in the IDE's terminal
  profile.
- **`PATH` reordering by later zshrc sections** (e.g. the Antigravity
  block, vite-plus env, dbt Fusion) was previously defended with a
  "re-assert mise shims at the front" call. The new placement of
  `activate` at EOF makes this defense unnecessary at startup time:
  mise's `eval` writes its PATH last, so it wins the initial ordering.
  The chpwd hook handles subsequent reorders inside the shell session.
  If a specific shell command between two cd events needs strict
  ordering, prefix it with `mise exec --`.

### Tests proving coverage

- `mise doctor` returns "No problems found" after `source ~/.zshrc`
  (both the original shims-and-activate warning and the
  "mise tool paths are not first in PATH" warning are gone).
- `command -v node` resolves to
  `~/.local/share/mise/installs/node/24.15.0/bin/node` rather than
  `~/.vite-plus/bin/node`. Same for `uv` → mise's 0.11.14 vs
  `~/.local/bin/uv` 0.11.8.
- `command -v rustc` resolves to `~/.cargo/bin/rustc` — this is
  expected: rust's toolchain manager installs the binary into cargo's
  bin dir even when invoked via mise. Version still matches mise's
  pinned `1.96.0`.
- `mise --version` reports the installed version.

## Consequences

### Positive

- `mise doctor` is clean.
- Tool resolution has a single, well-defined source: the chpwd hook
  installed by `mise activate`.
- Removing the bottom-of-file "re-assert" defense simplifies the
  PATH-edit story: later sections can no longer hide bugs behind that
  fallback.

### Negative

- Non-interactive subshells (e.g. `bash -c "node -v"` from a tool that
  doesn't source `.zshrc`) won't see mise tools. They never did
  reliably even with shims, because the shims dir was set in `.zshrc`,
  not `.zshenv`. So no regression vs the previous state — but the
  failure mode is now more discoverable (it fails immediately rather
  than appearing to work because of a coincidental fallback).
- A future cron job that needs mise tools requires deliberate setup
  (`mise exec --` or `.zshenv` shims), documented above.

### Neutral

- The change is `.zshrc`-only; `mise.toml`, `mise.toml` overrides, and
  the global config at `~/.config/mise/config.toml` (now a symlink
  into the repo per ADR 0021's sibling config layout) are unaffected.
- Tool resolution for mise-managed `node`, `uv`, etc. now beats their
  vite-plus / `~/.local/bin` counterparts because `activate` runs
  last. This is the intended consequence — it was an open question
  during the original draft of this ADR, captured here as
  retroactively confirmed.
