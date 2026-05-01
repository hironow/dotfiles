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
**devcontainer features only**, and install everything else via
**vendor-official artifacts** (apt repos with GPG, GitHub releases
with SHA verification) from a single shell script:

```jsonc
{
  "image": "mcr.microsoft.com/devcontainers/base:bookworm",
  "features": {
    "ghcr.io/devcontainers/features/common-utils:2":             { ... },
    "ghcr.io/devcontainers/features/github-cli:1":               {},
    "ghcr.io/devcontainers/features/docker-outside-of-docker:1": {},
    "ghcr.io/devcontainers/features/python:1":                   {},
    "ghcr.io/devcontainers/features/node:1":                     {}
  },
  "onCreateCommand": "bash .devcontainer/post-create.sh"
}
```

`.devcontainer/post-create.sh` installs:

| Tool | Source | Verification |
|------|--------|--------------|
| `gcloud`  | `packages.cloud.google.com/apt`     | apt repo GPG key |
| `mise`    | `mise.jdx.dev/deb`                  | apt repo GPG key |
| `uv`      | `astral-sh/uv` GitHub release       | `.tar.gz.sha256` sidecar |
| `just`    | `casey/just` GitHub release         | `SHA256SUMS` bulk file |
| `sheldon` | `rossmacarthur/sheldon` GitHub release | hardcoded SHA256 (vendor publishes none) |

No `curl | bash` pipes — semgrep blocks them with CWE-95.
Community devcontainer features (`devcontainers-extra`, `jdx`,
`va-h`, `dhoeric`, etc.) are explicitly **out** of the trust
boundary; only `ghcr.io/devcontainers/features/*` is allowed and
the `tests/test_devcontainer.py::test_devcontainer_declares_required_features`
assertion enforces this.

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
- **Drops INSTALL_SKIP_GCLOUD.** The `google-cloud-cli` feature
  installs gcloud at build time, so install.sh's `command -v gcloud`
  short-circuits the install branch on its own. One less env var to
  maintain across the agent startup_script.
- **Three alpine-only test functions deleted.** glibc shim assertions
  and apk-presence tests can no longer regress (they don't apply on
  debian).
- **Declarative.** Adding a tool means appending a feature ID, not
  writing a new RUN step + arch case + version pin + lint exception.

### Negative

- **devcontainers/ci is non-verified Marketplace creator** — the org
  Actions permissions UI must allowlist `devcontainers/ci@*` (same
  pattern as `jdx/mise-action`). One-time UI step.
- **Slightly slower build.** Feature resolution + apply adds ~30s to
  cold builds vs the flat Dockerfile. GHA cache from
  `cacheFrom: ghcr.io/<owner>/dotfiles-just-sandbox` recovers most of
  it on warm runs.
- **Pinned versions in post-create.sh.** uv, just, sheldon are
  pinned to specific tags; bumping them is a manual edit (or a
  Dependabot PR if we add a tracker). The trade-off vs feature
  auto-resolve is explicit and visible in code review.
- **No vendor-published .sha256 for sheldon.** SHA is hardcoded per
  arch; releases without a SUMS file get a manual review checkpoint.
- **remoteUser=root preserved.** Switching to the debian base image's
  `vscode` non-root user requires updating ~30 test path assertions
  and `install.sh` `DOTPATH` handling. Queued as a follow-up; not
  part of this migration.

### Neutral

- **Image size stays in 600-800 MB range.** Debian + features is
  similar in size to alpine + everything stacked on top once you
  include glibc + python + node + gcloud + docker-cli, but each
  binary now runs natively.
- **mise lifecycle moved to onCreate.** Was a Dockerfile RUN; now an
  `onCreateCommand` that runs once per container creation.
  devcontainers/ci pre-bakes it via the cache when configured.
- **Workspace template (Coder) requires no main.tf changes** — it
  reads `.devcontainer/devcontainer.json` via envbuilder, so the
  migration is automatic on next workspace create. Only the
  `INSTALL_SKIP_GCLOUD` env export was dropped from the agent
  startup_script.
