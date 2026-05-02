# 0005. Rationalise install paths across Mac host and Coder workspace (Linux)

**Date:** 2026-05-02
**Status:** Proposed

## Context

`hironow/dotfiles` is consumed from at least three platforms:

1. **Operator's macOS host** — primary daily driver. Uses Homebrew,
   `gcloud` SDK from Google's installer, and a sprinkling of
   developer tools that the operator wants on every machine.
2. **Coder workspace** (Linux container running on a debian-12 VM) —
   should expose "as much of the Mac toolchain as feasible" so the
   operator can SSH in and reuse muscle memory.
3. **CI sandbox** (the same dev container image, run via
   `devcontainers/ci`) — used by `tests/test_just_sandbox.py` and
   friends. Must run unattended.

A future Windows host is in mind: `scoop` + `mise` would replace
`brew` + `mise`. **Out of scope for this ADR; design must not
preclude it.**

### What "install" currently means

There are **four** install paths, scattered across the repo:

| Layer | File | Target | Trigger | Installs |
|---|---|---|---|---|
| (1) | `install.sh` (root) | macOS host (with Linux skip-hatches) | manual on host, or `coder dotfiles` | Homebrew, gcloud SDK, just, then `just add-all` + `just update-all` + `just clean` + `just deploy` |
| (2) | `.devcontainer/features/dotfiles-tools/install.sh` | dev container BUILD time (Linux) | `devcontainer build` (CI publish, local IDE) | apt: shellcheck/jq/gcloud/mise; tarball-pinned: uv/just/sheldon; mise.toml prebake |
| (3) | `tofu/exe/coder.tf` startup_script (control plane VM) | debian-12 GCE host VM | tofu apply / VM boot | Coder server, cloudflared, tailscaled |
| (4) | `exe/coder/templates/.../main.tf` startup_script (workspace VM + agent) | debian-12 GCE host VM + container | `cdr create` | host: tailscale, gcloud, docker; container: re-run (1) via `coder dotfiles` |

### The actual content the operator cares about

`dump/` carries the **declarative source of truth** for what
should be installed on a fully-set-up Mac host:

- `dump/Brewfile` (531 lines) — every brew formula / cask the
  operator uses
- `dump/gcloud` (30 lines) — gcloud component install list
- `dump/npm-global` (24 lines) — global npm packages
- `dump/gitignore-global` (66 lines) — git's global ignore

`mise.toml` (8 lines) carries a separate, smaller SoT for tools
that should follow `latest`-with-quarantine semantics:
just, markdownlint-cli2, prek, uv, vp.

### Symptoms of the current scattering

- **Mac-oriented core forces hatching for Linux.** install.sh
  always assumes brew + Google's interactive gcloud installer;
  Linux callers (Coder workspace, CI) toggle three skip env vars
  (`INSTALL_SKIP_HOMEBREW`, `INSTALL_SKIP_GCLOUD` — recently
  retired, `INSTALL_SKIP_ADD_UPDATE`) to make it usable.

- **Duplicate tool lists.** uv/just/sheldon are installed by both
  (2) [via tarball at devcontainer build time] and indirectly by
  (1) [via `just add-all` calls or implicit assumptions]. mise.toml
  is the SoT for workspace runtime but the dev container feature
  pre-bakes a parallel temporary mise.toml at build time.

- **`coder dotfiles` ties (4) to (1).** The Coder agent's
  `coder dotfiles -y URL` execs install.sh at the workspace
  container's `/root/dotfiles/install.sh` after `git clone`. So the
  Mac-shaped install.sh runs in a Linux container regardless of
  what (2) already did.

- **Trust boundary drift.** ADR 0001 + 0002 + 0003 set up a strict
  CI-side trust posture (SHA pinning, GPG fingerprint pin,
  attestation verify). install.sh runs `curl | bash` for Homebrew
  and `curl https://sdk.cloud.google.com | bash` for gcloud — both
  contradict that posture, but only run on the Mac host where
  attestation/sigstore tooling is harder to enforce.

## Decision

(Pending — three strategies considered.)

### Strategy α — OS dispatch

`install.sh` becomes a thin dispatcher that detects OS and routes:

```sh
case "$(uname -s)" in
  Darwin) exec "$DOTPATH/install/mac.sh" "$@" ;;
  Linux)  exec "$DOTPATH/install/linux.sh" "$@" ;;
esac
```

`install/mac.sh` keeps the brew + gcloud SDK + brew-bundle path.
`install/linux.sh` becomes a small script that does the
cross-platform parts (symlink + sheldon + mise install) and lets
the underlying environment provide everything else (apt-installed,
or pre-baked into the dev container image). Future
`install/windows.ps1` slots in alongside.

- Pros: simplest mental model. Each OS has one file.
- Cons: code duplication for shared logic (zgen clone, sheldon
  setup, just-install fallback).

### Strategy β — Mac-only install.sh, Linux runs nothing

Strip install.sh down to "Mac personal setup". Linux callers
(Coder, CI) **stop calling install.sh entirely**. The dev container
image already has every tool the workspace needs; the `coder
dotfiles` invocation is replaced with a thin `coder dotfiles -y`
invocation that ONLY does the symlink/sheldon work via a separate
`bin/dotfiles-deploy` (calling `just clean && just deploy`).

- Pros: **secure-by-default** posture wins — image is the SoT for
  Linux tools, no runtime install at all.
- Cons: `coder dotfiles` upstream contract assumes install.sh
  exists; we'd need a wrapper. Loses the "same install path
  everywhere" mental model.

### Strategy γ — OS-agnostic core + plugin directories (recommended)

Single `install.sh` at the root that does the **shared work** only:

1. Clone the dotfiles repo into `$DOTPATH` (or fast-forward).
2. Source `$DOTPATH/install/common.sh` for shared functions
   (zgen clone, sheldon lock, mise install, just clean+deploy).
3. Discover and run `$DOTPATH/install/<os>.d/*.sh` in lex order
   per detected OS, where `<os>` is `mac`, `linux`, or eventually
   `win`.

Per-OS plugin directories own their own concerns:

```
install/
  common.sh         (sourced by install.sh)
  mac.d/
    10-homebrew.sh        # brew install + brew bundle dump/Brewfile
    20-gcloud-installer.sh
    30-mac-defaults.sh    # macOS defaults write
  linux.d/
    10-apt-baseline.sh    # apt update; apt install ca-certs etc.
    20-no-runtime-network.sh   # marker: dev container already
                                # provides everything else
  win.d/                  # future
    10-scoop.sh
    20-winget.sh
```

`mise.toml` stays the canonical tool list (cross-platform) and
`common.sh` runs `mise install` once. `dump/Brewfile`,
`dump/gcloud`, `dump/npm-global` move to `install/mac.d/data/` (or
similar) since they are macOS-specific declarative sources.
`dump/gitignore-global` is OS-agnostic and stays addressable from
common.

- Pros: **DRY** core, **clean OS branching**, **future Windows
  ready**. mise.toml as the genuine cross-platform SoT.
- Cons: bigger refactor. Risks regressing Mac flow if not careful.

## Open questions to resolve before implementation

1. **`coder dotfiles` integration.** Upstream contract is
   "execute `install.sh` after clone." Do we keep install.sh as the
   entrypoint and have it no-op on Linux when the dev container
   already has everything (γ-friendly)? Or replace `coder dotfiles
   -y` with `coder dotfiles -y --command "$DOTPATH/bin/dotfiles-deploy"`
   (β-friendly)? Reading the Coder docs for `dotfiles_command`
   parameter is the answer.

2. **gcloud installer trust.** Google publishes a Debian apt repo
   (used in the local feature today) and an interactive `curl
   https://sdk.cloud.google.com | bash` installer for Mac. The Mac
   path is currently `curl | bash` against Google's CDN, no SHA
   verification. Worth replacing with the `--package` install for
   reproducibility.

3. **Brewfile hygiene.** 531 lines of `tap` + `brew` + `cask`
   declarations include things the operator may no longer use. A
   `brew bundle cleanup` + commit pass is a separate cleanup PR
   but should be flagged so install.sh's runtime is bounded.

4. **`just add-all` semantics.** Currently install.sh calls
   `just add-all` which re-dumps the host's installed brew/gcloud/
   pnpm globals back into `dump/` files. This means a pristine
   install.sh run on a half-set-up machine **mutates the dump/
   files** and could commit drift. Should `just add-all` move
   behind a `just sync-dumps` recipe that the operator runs
   intentionally rather than as part of every install?

5. **mise.toml as SoT for npm-backed tools.** vp + markdownlint-cli2
   are installed via mise's npm backend, which fails inside the
   workspace because `--volume /home/hironow:/root` masks the
   build-time-installed npm. Either (a) accept the WARN +
   binaries-on-PATH posture (current), (b) rebuild with
   non-overlapping volume mounts, (c) pull npm-backed tools out of
   mise.toml and treat them as pure brew (Mac) / apt (Linux).

6. **Windows readiness.** scoop + mise. Concretely: which
   tools in `dump/Brewfile` have scoop equivalents, and which need
   alternative installers (e.g. `gcloud` on Windows)?

## Consequences (regardless of chosen strategy)

### Positive

- **One coherent install model** instead of four scattered ones.
- **Trust boundary becomes documentable.** Each path has a single
  responsibility and can be tested.
- **Future Windows on-ramp** is straightforward.

### Negative

- **Refactor cost.** install.sh and the Coder template both touch
  the install path. PR scope is medium (estimated 200-500 LOC
  changed across install.sh, dump/, justfile, main.tf, README).
- **Test coverage.** install.sh has minimal coverage today
  (`tests/test_just_sandbox.py` indirectly exercises `just deploy`).
  Strategy γ requires per-OS plugin discovery tests, which is new
  ground.
- **Coder dotfiles command override.** May require a per-workspace
  Coder parameter for the install command, which is a UI change.

### Neutral

- **`mise.toml` stays the canonical cross-platform tool list**
  under all three strategies. The decision is mostly about where
  brew/Brewfile/gcloud/npm-global hooks live.
- **`dump/gitignore-global`** stays where it is or moves to
  `install/common/`; cross-platform regardless.

## Recommendation

**Strategy γ** (OS-agnostic core + plugin directories) is the
recommended direction. It keeps the Mac flow intact, gives Linux a
clear "no-op except sheldon/symlink" path that aligns with the
secure-by-default posture from ADR 0002, and prepares cleanly for
Windows.

Implementation should be a separate PR `feat/install-os-plugin-layout`
that reorganises files, ports the Mac flow into `mac.d/`, drops
`INSTALL_SKIP_*` env vars from the Coder template (they become
unnecessary because Linux's `linux.d/` is empty), and adds
characterization tests using the dev container.
