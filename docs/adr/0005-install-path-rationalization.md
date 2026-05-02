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
  (`INSTALL_SKIP_HOMEBREW`, `INSTALL_SKIP_GCLOUD`,
  `INSTALL_SKIP_ADD_UPDATE`) to make it usable. The Coder agent
  dropped `INSTALL_SKIP_GCLOUD` in PR #54 because gcloud is now
  baked into the dev container image, but install.sh itself
  still honours all three so the script remains usable from
  callers that do not have gcloud pre-installed.

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

**WITHDRAWN after codex review.** The strategy hinged on telling
Coder's `coder dotfiles` to run a custom command instead of
install.sh. Upstream `coder dotfiles` does NOT expose a
`--command` flag (per
<https://coder.com/docs/reference/cli/dotfiles>); the only
overrides are `--symlink-dir` and `--repo-dir`. Without a
supported way to point `coder dotfiles` at a different
entrypoint, β reduces to "rename install.sh and rely on Coder's
fallback discovery" — which is brittle and undocumented.

Keeping β here as historical context only. Pick α or γ.

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

1. **`coder dotfiles` integration.** Upstream contract per
   <https://coder.com/docs/reference/cli/dotfiles> is:

   ```sh
   coder dotfiles --repo-dir <path> --symlink-dir <path> <git-url>
   ```

   - The flags `--symlink-dir` and `--repo-dir` exist; the
     entrypoint script discovery is **not** overridable. After
     `git clone`, Coder probes the repo for a known entrypoint
     (install.sh, bootstrap.sh, etc.) and execs whichever it
     finds first.
   - `--repo-dir` defaults to a path relative to
     `$CODER_CONFIG_DIR` (typically `~/.config/coderv2`), NOT
     `$HOME/dotfiles` as the current main.tf assumes. The
     observed clone path of `/root/dotfiles` is incidental
     (a side-effect of how the agent's HOME and CODER_CONFIG_DIR
     happen to land on this stack).
   - Decision needed: pin `--repo-dir=$HOME/dotfiles` explicitly
     in the agent startup script OR move every consumer to use
     `$CODER_DOTFILES_REPO_DIR` env var.

2. **Trust boundaries for runtime installers (host AND container).**
   Open Question 2 is broader than "Mac gcloud installer." Audit
   every `curl | bash` / `curl | sh` / unsigned tarball pipe in
   the install paths, on both Mac and Linux:

   | Path | Source | Verification |
   |---|---|---|
   | install.sh `brew` install | `raw.githubusercontent.com/Homebrew/install/HEAD/install.sh` (Mac) | none (curl+bash) |
   | install.sh `gcloud` install | `sdk.cloud.google.com` (Mac) | none (curl+bash) |
   | install.sh `just` fallback | `just.systems/install.sh` (cross-platform) | none |
   | tofu/exe/coder.tf Coder server install | `coder.com/install.sh` (control-plane VM) | **none — curl+bash + `\|\| true`** |
   | tofu/exe/coder.tf Coder server fallback | `api.github.com/repos/coder/coder/releases/latest` → tarball | **none — `latest` resolves at boot, no SHA/SLSA verify** |
   | main.tf VM `tailscale` | `pkgs.tailscale.com` apt repo | apt key fetched fresh; not fingerprint-pinned |
   | main.tf VM `gcloud` | `packages.cloud.google.com` apt repo | apt key fetched fresh; not fingerprint-pinned |
   | main.tf VM `docker` | `download.docker.com` apt repo | **fingerprint pinned** ✅ (PR #57) |
   | feature install.sh `gcloud` apt | `packages.cloud.google.com` | **fingerprint pinned** ✅ (ADR 0001) |
   | feature install.sh `mise` apt | `mise.jdx.dev` | **fingerprint pinned** ✅ (ADR 0001) |
   | feature install.sh `uv`/`just`/`sheldon` | GitHub releases | **SHA verified** ✅ (ADR 0001) |

   The dev container feature is the only path with consistent
   verification. The other entrypoints inherit different
   postures. Implementation must converge them or document the
   asymmetry.

   The `tofu/exe/coder.tf` rows above are particularly load-
   bearing: that VM is the control plane that issues workspace
   tokens, so a compromised Coder binary on first boot would
   compromise every workspace it later spawns. Pinning here
   should be prioritised even if it's out of scope for this
   ADR's primary refactor.

   Additional concern at `coder.tf:290`: the install line is
   `curl -fsSL https://coder.com/install.sh | sh || true`. The
   `|| true` swallows any non-zero exit. Success is then probed
   only via `[[ ! -x /usr/local/bin/coder && ! -x /usr/bin/coder ]]`
   to decide whether to run the fallback. A compromised CDN
   could return a malicious script that exits 0 after writing
   anything to `/usr/local/bin/coder`, and the fallback path
   (`api.github.com/.../latest`) would be skipped. The pin
   strategy for this row must address both the unverified
   primary install AND the exit-code-suppressed failure mode.

3. **Brewfile hygiene.** 531 lines of `tap` + `brew` + `cask`
   declarations include things the operator may no longer use. A
   `brew bundle cleanup` + commit pass is a separate cleanup PR
   but should be flagged so install.sh's runtime is bounded.

4. **`dump/` mutation surface.** `install.sh` calls `just add-all`
   which **only consumes** `dump/Brewfile`, `dump/gcloud-list.txt`,
   `dump/pnpm-g.txt` (idempotent install). The actual mutator is
   `just dump`, which is **operator-invoked manually** and rewrites
   `dump/Brewfile` etc. with the current host state. That separation
   is already correct — there is no install-path-side mutation to
   fix here. The original premise of this question (an automatic
   re-dump during install) was incorrect; flagged by codex review
   2026-05-02. Remaining concern: should `just dump` gain a guard
   against accidental commits of host-specific drift (e.g., a
   pre-commit reminder that diff-noise in `dump/` indicates a
   manual sync was performed)? — minor follow-up only.

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

7. **mise version pinning strategy.** All five tools in mise.toml
   currently say `= "latest"`. The dev container feature pre-bakes
   resolved versions at build time (which `mise install` then
   matches), but workspace runtime resolves "latest" against
   GitHub fresh. CI reproducibility, supply-chain attestation, and
   "build-time-only network" posture all depend on what we choose
   here. Resolved in the follow-up
   `docs/adr/0006-mise-version-pinning.md`; this ADR is blocked
   until that one lands.

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
