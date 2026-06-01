# 0018. Windows native: minimum-viable deploy with explicit-skip step_*

**Date:** 2026-06-02
**Status:** Accepted

## Context

ADR 0005 (Accepted 2026-05-02) made `install.sh` OS-aware by routing every
install responsibility through a `step_*` helper that branches on
`DOTFILES_OS`. On Mac and Linux these branches run real install logic; on
Windows native they all called a placeholder `_todo_windows "<step>"` that
emitted a noisy `windows TODO (scoop bootstrap to be implemented)` line and
moved on. ADR 0005 explicitly deferred the concrete Windows port to a
"future ADR + PR when an actual Windows host enters the picture."

That future has arrived: an actual Windows native host is in regular use
(Powered by `mise`, `scoop`, and `corepack`-backed `pnpm`). Observing what
the host actually needed exposed that **most of the deferred step_*
functions are not "not yet implemented" — they are intentionally out of
scope for Windows native**:

- `brew`/`brew bundle` and the gcloud bundle have no Homebrew equivalent on
  Windows native; provisioning happens through scoop and the official
  Cloud SDK installer, both of which are operator-driven and not
  part of `install.sh`'s remit.
- `sheldon` is a zsh plugin manager and zsh is not used on Windows native
  (the zsh story lives entirely in WSL).
- `step_update_all` is a brew/apt/mise composite update; on Windows native
  updates flow through scoop and `mise self-update` separately.

Two pieces, however, *are* cross-platform-meaningful and currently
unreachable on Windows because they share the `_todo_windows` stub:

- **`step_corepack`**: `corepack` ships with Node.js and works on
  Windows. We need it to enable per-repo `packageManager`-driven pnpm
  resolution (ADR 0017's whole reason for being). The Windows-specific
  wrinkle is that the Program Files Node install is typically read-only
  for the operator account, so `corepack enable` EPERMs when it writes
  pnpm shims there; routing through `mise exec --` fixes that.
- **`just deploy` / `just clean`**: of the six artifacts deploy places,
  only `starship.toml` and `dump/gitignore-global` make sense on Windows
  native. The remaining four (`.zshrc`, sheldon plugins, tmux.conf,
  ghostty config) are zsh/Unix-only.

Leaving these on a single `_todo_windows` stub conflates "intentionally
skipped" with "not yet implemented" and trains operators to ignore noisy
TODO log lines that will never be acted on.

## Decision

Replace the `_todo_windows` placeholder with two separate concrete shapes
per step:

1. **`_skip_windows "<step>" "<reason>"`** — a new helper that requires a
   reason argument. Used by the six steps that are out of scope on
   Windows native: `step_homebrew`, `step_gcloud_components`,
   `step_brew_bundle`, `step_gcloud_bundle`, `step_update_all`,
   `step_sheldon`. (`step_just_bootstrap` already short-circuits via the
   `command -v just` guard at the top of its body, so its windows branch
   is a `_skip_windows` for the unlikely case where just is somehow not
   installed.)
2. **Real implementation** — used by `step_corepack`:

   ```sh
   windows)
     if command -v mise >/dev/null 2>&1; then
       mise exec -- corepack enable
     elif command -v corepack >/dev/null 2>&1; then
       corepack enable
     else
       echo "[install] step_corepack: corepack not on PATH; skipping ..."
     fi
     ;;
   ```

For the dotfiles placement layer, add an MSYS/MINGW/CYGWIN case at the
top of the `deploy` and `clean` recipes in `justfile`. On Windows native
the recipes:

- `deploy`: `cp -f` `starship.toml` and `gitignore-global` into
  `~/.config/`, then `exit 0` before the Unix-only `ln -sf` block.
  `cp -f` is preferred over `ln -sf` on Windows because symlinks require
  Developer Mode or admin privileges and degrade to copies in MSYS
  anyway.
- `clean`: remove only what the Windows `deploy` placed
  (`~/.config/starship.toml`, `~/.config/git/ignore`).

Full scoop-based provisioning (brew-equivalent), PowerShell `$PROFILE`
integration for starship, and Windows CI runners remain **explicitly out
of scope** for this ADR and are deferred to future work.

## Enforcement inventory

- **`install.sh`**: `_todo_windows()` removed; `_skip_windows()` added.
  Eight `windows)` branches rewritten — seven `_skip_windows` calls with
  explicit reasons, one real `corepack enable` implementation in
  `step_corepack`.
- **`justfile`**: `deploy` and `clean` recipes converted to shebang-style
  bash bodies so a `case "$(uname -s)"` dispatch can early-return for
  Windows. Linux/macOS paths preserved verbatim below the switch.
- **`tests/test_install_os_dispatch.py`**: three new tests pin the
  contract:
    - `test_install_sh_no_todo_windows_stub_remains` — `_todo_windows` token
    must not reappear.
    - `test_install_sh_windows_step_corepack_implemented` — `step_corepack`
    windows branch must contain `corepack enable` (not `_skip_windows`).
    - `test_install_sh_skip_windows_calls_have_reason` — every
    `_skip_windows` invocation must be the 2-arg shape with a non-empty
    reason.
- **`tests/test_justfile_windows_subset.py`** (new): static-parses the
  `deploy` / `clean` recipes and asserts the Windows branch contains the
  expected subset (starship + git ignore) and no Unix-only tokens
  (zsh/sheldon/tmux/ghostty/fzf-tab), plus an `exit 0` to short-circuit.
- **`README.md`**: the L68 note is rewritten from "Windows native (scoop)
  is unsupported" to "Windows native supports the minimum subset; full
  scoop bootstrap is future work — see ADR 0018".
- **`mise.toml`**: the L4 "(future scoop host)" comment is refreshed to
  point at ADR 0018.

## Consequences

**Positive**

- `bash install.sh` on Windows native completes without noisy TODO log
  lines; the only Windows-relevant work (corepack enable + subset deploy)
  actually happens.
- The boundary between "deferred" and "deliberately skipped" becomes
  explicit and reviewable — the reason argument to `_skip_windows`
  documents *why* each step is out of scope so a future contributor does
  not "fix the TODO" by accident.
- starship and the global gitignore now stay in sync on Windows hosts
  the same way they do on Mac/Linux, instead of drifting because they
  were never placed.

**Negative**

- Windows-side tool provisioning (brew, gcloud bundle, sheldon, the
  composite `update-all`) still requires manual operator action. ADR 0018
  legitimizes the gap rather than closing it.
- The Linux-only `test_just_sandbox.py` cannot exercise the Windows
  branch end-to-end; the new `test_justfile_windows_subset.py` is
  static-parse only. A genuine Windows CI runner would be required for
  full coverage and is out of scope here.

**Neutral**

- The `_todo_windows` removal narrows ADR 0005's "future ADR" commitment:
  the dispatch shape is unchanged, but the Windows column is now
  explicit per-step instead of a single placeholder. A future scoop
  bootstrap ADR can replace any of the seven `_skip_windows` calls with
  real implementations without further structural changes.
