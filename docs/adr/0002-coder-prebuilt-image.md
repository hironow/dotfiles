# 0002. Coder workspace template uses a prebuilt dev container image

**Date:** 2026-05-02
**Status:** Accepted

## Context

ADR 0001 migrated the local IDE / CI / Coder workspace contract to a
single SoT (`.devcontainer/devcontainer.json`) with debian-12 +
features. The Coder template at
`exe/coder/templates/dotfiles-devcontainer/` continued to use the
**envbuilder pattern** to materialise that contract on each workspace
VM:

1. GCE VM boots Ubuntu/Debian.
2. envbuilder image runs as a container.
3. envbuilder clones the dotfiles repo, reads `.devcontainer/devcontainer.json`,
   resolves features, and runs `docker buildx build` inside the VM.
4. The resulting image becomes the workspace container.

This works but has three operational drawbacks for a personal stack:

- **Workspace start time**: 3-5 minutes per `cdr create` (clone + apt
  install of buildkit + features download + image build).
- **CPU/memory headroom**: envbuilder + buildkit need an `e2-small`
  minimum. e2-micro OOMs.
- **Failure modes**: every workspace re-runs the build, so a
  transient apt mirror outage or feature registry hiccup blocks
  workspace boot.

## Decision

Replace the envbuilder-per-workspace pattern with a **prebuilt
image + gcp-vm-container pattern**:

1. **CI publishes the image once per main merge.** A new workflow
   `.github/workflows/publish-devcontainer.yaml` invokes
   `devcontainers/ci@<sha>` with `push: always`, tagging the image
   `<region>-docker.pkg.dev/<project>/dotfiles/devcontainer:main`
   (rolling) and `:<git-sha>` (immutable) in **Artifact Registry**.

2. **Workload Identity Federation, no SA keys.** The publish workflow
   authenticates via `google-github-actions/auth@<sha>` against a
   WIF pool restricted to `assertion.repository == 'hironow/dotfiles'`.
   The federated SA holds only `roles/artifactregistry.writer` on the
   `dotfiles` repo. WIF infra lives in `tofu/exe/iam.tf`.

3. **Workspace template pulls the image and runs it.** The new
   template (gcp-vm-container-style) keeps the debian-12 host VM,
   installs tailscale + gcloud + docker on first boot, then:

   ```sh
   gcloud --quiet auth configure-docker <region>-docker.pkg.dev
   docker pull <repo>/devcontainer:main
   docker run --network host --restart unless-stopped \
     --env CODER_AGENT_TOKEN=... --env CODER_AGENT_URL=http://exe-coder:7080 \
     <image> sh -c '<base64-encoded coder_agent init_script>'
   ```

   No envbuilder, no buildkit, no in-VM image build.

4. **Workspace SA gains `roles/artifactregistry.reader`** on the
   dotfiles repo. The existing `exe-workspace@…` SA is reused; the
   tofu binding is in `tofu/exe/iam.tf`.

## Consequences

### Positive

- **Workspace start time drops from minutes to ~30-60s** — only docker
  pull + container start, no build.
- **Smaller VM tier viable.** e2-micro is now sufficient for many
  workloads (no envbuilder/buildkit RAM pressure). The template
  exposes e2-micro as an option but defaults to e2-small for
  headroom.
- **Failure isolation**: image build problems surface in CI before
  any workspace tries to use the bad image. Workspace creation
  itself only depends on Artifact Registry availability.
- **Deterministic rollbacks.** The `:<git-sha>` immutable tag lets
  the template be pinned to a specific commit; reverting the image
  variable rolls back without a Coder template re-push.

### Negative

- **One more piece of CI infra to maintain.** The publish workflow
  must keep working; if it breaks, new commits to main do not flow
  into the rolling `:main` tag and operators silently get stale
  workspaces.
- **Artifact Registry storage cost.** Cleanup policies on the AR
  repo cap to 10 most-recent versions and delete untagged-after-7-days
  to bound this.
- **`devcontainers/ci` action is still non-verified Marketplace.**
  Same allowlist requirement as PR #53; covered already.
- **No build-time customisation per workspace.** envbuilder allowed
  per-workspace `cache_repo` / `fallback_image` / branch override.
  These are removed; if a developer needs to test a feature branch
  of the dev container itself, they push the image manually via
  `devcontainer build --push <tag>` and pin the workspace template
  to that tag.

### Neutral

- **Tailscale still on the host.** The workspace container is
  `--network host` so it shares the host's tailnet identity. We
  considered moving tailscale into the container (cleaner privacy
  boundary) but the host install is simpler and matches the prior
  template.
- **dotfiles_uri parameter retained.** Personalisation still flows
  through `coder dotfiles -y URL` after the agent starts. The
  prebuilt image already has gcloud / mise / uv / just / sheldon,
  so install.sh's `command -v gcloud` short-circuits the gcloud
  install branch — `INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_ADD_UPDATE=1`
  remain.
- **Operator-side WIF setup is one-time.** After `tofu apply`, set
  the GitHub repo variables:

  ```bash
  gh variable set GCP_WIF_PROVIDER --body "$(just exe-output -raw gcp_wif_provider_resource_name)"
  gh variable set GCP_PUBLISH_SA   --body "$(just exe-output -raw gcp_publish_sa_email)"
  ```
