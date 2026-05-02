# 0001. Migrate dev container to debian-12 + features (single SoT)

**Date:** 2026-05-02
**Status:** Accepted

## Context

The repo's dev container shape was defined by
`tests/docker/JustSandbox.Dockerfile` with `BASE_IMAGE=alpine:3.19`.
Three downstream consumers depended on the same image:

1. **Local IDE** — `.devcontainer/devcontainer.json` referenced the
   Dockerfile via `build.dockerfile`.
2. **CI sandbox** — `.github/workflows/test-just.yaml` built the
   Dockerfile with `docker/build-push-action`, tagged it
   `dotfiles-just-sandbox:latest`, and ran `just test` against it.
3. **Coder workspace** — the template at
   `exe/coder/templates/dotfiles-devcontainer/main.tf` had envbuilder
   read `.devcontainer/devcontainer.json`, which transitively built
   the alpine Dockerfile.

The alpine + musl base introduced a chain of workarounds:

- `libc6-compat` + `gcompat` packages for glibc binaries (Coder
  agent, code-server) — without the shim, `/bin/sh` mis-detected ELF
  as script and emitted `syntax error: unexpected newline`.
- `INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_GCLOUD=1 INSTALL_SKIP_ADD_UPDATE=1`
  on the Coder workspace agent's startup_script because linuxbrew is
  glibc-only and alpine's apk repo has no `google-cloud-cli`.
- musl-targeted `just` and `sheldon` binaries downloaded by URL.
- `apk add docker-cli` to silence Coder agent's docker-ps poll.
- Three glibc-shim regression tests in `tests/test_just_sandbox.py`
  to lock the workaround in.

These workarounds aged: every new tool added to mise.toml or the
Coder workspace boot path had a non-zero chance of tripping the
musl/glibc seam.

## Decision

Migrate the dev container to **debian-12 (bookworm)** with the
official Microsoft devcontainer base image. Use Microsoft-curated
**devcontainer features** plus an in-repo **local feature** that
installs everything else from **vendor-official artifacts** at
**build time** (lifecycle commands like `onCreateCommand` are not
committed back to the saved image by `devcontainers/ci`, so
build-time installation is the only way for the binaries to reach
inner test containers).

```jsonc
{
  "image": "mcr.microsoft.com/devcontainers/base:bookworm",
  "features": {
    "ghcr.io/devcontainers/features/common-utils:2":             { ... },
    "ghcr.io/devcontainers/features/github-cli:1":               {},
    "ghcr.io/devcontainers/features/docker-outside-of-docker:1": {},
    "ghcr.io/devcontainers/features/python:1":                   {},
    "ghcr.io/devcontainers/features/node:1":                     {},
    "./features/dotfiles-tools":                                 {}
  },
  "onCreateCommand": "bash .devcontainer/post-create.sh"
}
```

`.devcontainer/features/dotfiles-tools/install.sh` (build-time)
installs:

| Tool | Source | Verification |
|------|--------|--------------|
| `gcloud`  | `packages.cloud.google.com/apt`     | GPG fingerprint pinned (`35BAA0...DC6315A3`) |
| `mise`    | `mise.jdx.dev/deb`                  | GPG fingerprint pinned (`24853E...7413A06D`) |
| `uv`      | `astral-sh/uv` GitHub release       | `.tar.gz.sha256` sidecar |
| `just`    | `casey/just` GitHub release         | `SHA256SUMS` bulk file |
| `sheldon` | `rossmacarthur/sheldon` GitHub release | hardcoded SHA256 (vendor publishes none) |

The GPG fingerprint pin is enforced by an
`import_apt_key_with_fingerprint()` helper that aborts the build
if the fetched key disagrees with the expected fingerprint. Closes
the TOFU window where a compromised TLS endpoint could swap key
and package in lock-step.

No `curl | bash` pipes — semgrep blocks them with CWE-95.
Community devcontainer features (`devcontainers-extra`, `jdx`,
`va-h`, `dhoeric`, etc.) are **out** of the trust boundary; only
`ghcr.io/devcontainers/features/*` (Microsoft) and `./<repo-path>`
(local feature) are allowed. The
`tests/test_devcontainer.py::test_devcontainer_declares_required_features`
assertion enforces this.

`.devcontainer/post-create.sh` (lifecycle, runtime) only resolves
mise.toml against the bind-mounted workspace — it cannot install
binaries that need to persist into the saved image.

`tests/docker/JustSandbox.Dockerfile` is **deleted**.
`.devcontainer/devcontainer.json` becomes the single source of truth
shared by all three consumers. CI uses the
`devcontainers/ci@<sha>` GitHub Action to build the same image graph
the local IDE and Coder workspace consume.

## Consequences

### Positive

- **Single SoT.** All three consumers (local IDE / CI / Coder
  workspace) build from one declarative file. Migrations like
  base-image bumps or feature additions ship in one diff.
- **glibc-native.** Drops the libc6-compat / gcompat shim, the
  musl-targeted just/sheldon downloads, and the entire class of
  ELF-as-script regressions.
- **Drops INSTALL_SKIP_GCLOUD.** gcloud is installed at build time
  by the local feature, so install.sh's `command -v gcloud`
  short-circuits the install branch on its own. One less env var to
  maintain across the agent startup_script.
- **Three alpine-only test functions deleted.** glibc shim assertions
  and apk-presence tests can no longer regress (they don't apply on
  debian).
- **Declarative.** Adding a Microsoft-curated tool means appending a
  feature ID; adding a vendor-only tool means a small block in the
  local feature install.sh — both auditable in PR review.
- **Tightened trust boundary** (vs. an earlier revision):
  `MISE_TRUSTED_CONFIG_PATHS` was scoped from `/root` down to
  `/root/dotfiles:/root/sandbox/dotfiles-fresh`, and
  `git config safe.directory` was scoped from `*` down to the same
  two paths. GHSA-436v-8fw5-4mj8 / CVE-2026-35533 informed the
  scoping decision.

### Negative

- **devcontainers/ci is non-verified Marketplace creator** — the org
  Actions permissions UI must allowlist `devcontainers/ci@*` (same
  pattern as `jdx/mise-action`). One-time UI step.
- **Slightly slower build.** Feature resolution + apply adds ~30s to
  cold builds vs the flat Dockerfile. GHA cache from
  `cacheFrom: ghcr.io/<owner>/dotfiles-just-sandbox` recovers most of
  it on warm runs.
- **Pinned versions in the local feature.** uv, just, sheldon are
  pinned to specific tags; bumping them is a manual edit (or a
  Dependabot PR if we add a tracker). The trade-off vs feature
  auto-resolve is explicit and visible in code review.
- **No vendor-published .sha256 for sheldon.** SHA is hardcoded per
  arch; releases without a SUMS file get a manual review checkpoint.
- **GPG fingerprint pins drift.** The Google and mise apt repos
  rotate their signing keys periodically; when they do, build fails
  with a fingerprint mismatch and an operator must update the
  hardcoded value after verifying the new key out-of-band. This is
  the trade-off vs blind TOFU acceptance.
- **remoteUser=root preserved.** Switching to the debian base image's
  `vscode` non-root user requires updating ~30 test path assertions
  and `install.sh` `DOTPATH` handling. Queued as a follow-up; not
  part of this migration.

### Neutral

- **Image size stays in 600-800 MB range.** Debian + features is
  similar in size to alpine + everything stacked on top once you
  include glibc + python + node + gcloud + docker-cli, but each
  binary now runs natively.
- **mise.toml resolution moved to onCreate.** Was a Dockerfile RUN;
  now an `onCreateCommand` because mise.toml lives in the bind
  mount which is established only at container start. Build-time
  pre-install in the local feature pre-populates the mise cache so
  the runtime resolution is fast.
- **CI passes GITHUB_TOKEN to the dev container** via the action's
  `env:` block, and the test fixture forwards it to inner one-shot
  containers. Mise's `latest` resolution then hits the
  authenticated 5000/hr GitHub API quota instead of the anonymous
  60/hr limit; flake risk under load is removed.
- **Workspace template (Coder) requires no main.tf changes** — it
  reads `.devcontainer/devcontainer.json` via envbuilder, so the
  migration is automatic on next workspace create. Only the
  `INSTALL_SKIP_GCLOUD` env export was dropped from the agent
  startup_script.
