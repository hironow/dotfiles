# 0007. Coder server install hardening on the control-plane VM

**Date:** 2026-05-02
**Status:** Accepted (2026-05-02)

## Context

The exe.hironow.dev control-plane VM (`tofu/exe/coder.tf`) installs
the Coder server binary via:

```sh
# coder.tf:285-291 (current state, summarised)
export HOME=/root
curl -fsSL https://coder.com/install.sh | sh || true

if [[ ! -x /usr/local/bin/coder && ! -x /usr/bin/coder ]]; then
  coder_tag="$(curl -fsSL https://api.github.com/repos/coder/coder/releases/latest \
    | jq -r .tag_name)"
  curl -fsSL -o /tmp/coder.tar.gz \
    "https://github.com/coder/coder/releases/download/${coder_tag}/coder_${coder_tag#v}_linux_amd64.tar.gz"
  tar -xz -C /usr/local/bin -f /tmp/coder.tar.gz coder
  chmod 0755 /usr/local/bin/coder
fi
```

Three issues, in increasing order of severity:

1. **`curl | sh` of `coder.com/install.sh`** — TOFU on the HTTPS
   endpoint. A CDN compromise becomes immediate root RCE on the
   control-plane VM at first boot.
2. **`|| true` swallows the exit code**, and success is then
   probed only by checking whether `/usr/local/bin/coder` is an
   executable. A malicious script that exits 0 after writing
   anything to that path silently bypasses the fallback.
3. **The fallback resolves `latest` at boot** via
   `api.github.com/.../releases/latest`. There is no SHA / SLSA
   verification of the resulting tarball; whatever the API says
   is "latest" is what gets executed.

The control-plane VM issues workspace agent tokens. A compromise
here propagates to every workspace it later spawns; the blast
radius covers the operator's dev tooling on every workspace,
service tokens stored on those workspaces, and the tailnet
identity that the workspace VMs assume.

This was raised as a critical finding in the 2026-05-02 codex
review of ADR 0005 (audit table scope gap) and the post-amend
fact-check (the `|| true` masking nuance). The hardening is
out-of-scope for ADRs 0005 and 0006 because both of those scope
to *workspace*-side install paths and *cross-platform tool
management*, not the control-plane VM bootstrap. This ADR
captures the control-plane decision separately so that 0005/0006
can be implemented without blocking on it, and vice versa.

## Decision (Accepted 2026-05-02)

Replace the `curl | sh` + `|| true` + GitHub-API-`latest`-fallback
pattern with a **single tag-pinned tarball install path with
sha256 verification, optional SLSA attestation verification, and
fail-closed semantics**.

### Decision details

1. **Coder version is pinned in OpenTofu** as a variable
   (`var.coder_version`), defaulting to a specific release tag
   (e.g. `v2.18.0`). Operator bumps the tag explicitly via
   variable change + `tofu apply`.

2. **`coder.com/install.sh` is removed** from the bootstrap.
   No more curl-piped shell.

3. **Tarball download is direct from GitHub releases** at the
   pinned tag:

   ```sh
   curl -fsSL --proto '=https' --tlsv1.2 \
     -o /tmp/coder.tar.gz \
     "https://github.com/coder/coder/releases/download/${CODER_VERSION}/coder_${CODER_VERSION#v}_linux_amd64.tar.gz"
   ```

4. **SHA-256 verification** against a value that is **also pinned
   in OpenTofu** (`var.coder_sha256`). The operator looks up the
   sha256 from GitHub release assets at the time they bump the
   version, in the same change. The bootstrap aborts on mismatch:

   ```sh
   echo "${CODER_SHA256}  /tmp/coder.tar.gz" | sha256sum -c -
   ```

5. **Optional `gh attestation verify`** if Coder ships SLSA
   provenance for the release tarball. Verification is
   best-effort (skipped silently if `gh` is not authenticated
   on the VM, mirroring the pattern in
   `.devcontainer/features/dotfiles-tools/install.sh`). The
   sha256 pin in step 4 remains the primary integrity check;
   attestation is defence in depth.

6. **Fail-closed semantics**. The bootstrap exits non-zero on
   any failure in steps 3-5; no `|| true`. Terraform's startup-
   script execution then fails the VM provisioning, which is
   the desired behaviour (a control-plane VM that cannot install
   a verified Coder binary should not come up).

### Operator workflow when bumping Coder

```sh
# 1. Pick new tag from https://github.com/coder/coder/releases
# 2. Note its sha256 (release assets page or `gh release view`)
# 3. Update tofu/exe/coder.tf variables:
#    var.coder_version = "v2.19.0"
#    var.coder_sha256  = "abc123..."
# 4. just exe-apply
# 5. just exe-smoke
```

## Out of scope

- **The two `curl` apt-key fetches earlier in `coder.tf`**
  (Tailscale, Google Cloud) are still TOFU. Tracked in ADR 0005
  Open Q2 audit table; same hardening pattern applies but is
  separate work.
- **Workspace VM `coder agent` binary download** is over the
  tailnet (`exe-coder:7080`) per ADR 0004; it inherits the
  control-plane VM's binary, so this ADR's pin transitively
  covers it.

## Consequences

### Positive

- **Removes the largest single supply-chain attack surface** in
  the stack. Control-plane compromise no longer hinges on a
  CDN reading `coder.com/install.sh`.
- **Reproducible builds.** `tofu apply` with the same
  `coder_version` + `coder_sha256` produces the same binary
  every time.
- **Clear operator workflow** for version bumps.

### Negative

- **Manual upgrade cadence.** Operator must look up sha256 +
  update tofu variables, then `tofu apply`. No automated
  Dependabot-equivalent for tofu variables today.
- **Loss of "auto-pull-latest" semantics.** Stale-version drift
  is now possible. Mitigated by setting up a periodic reminder
  (e.g., a scheduled task to compare `var.coder_version` with
  the latest release tag).

### Neutral

- **Coder upstream's `install.sh`** is presumably reasonable
  software, but the supply-chain posture of this stack is
  "trust nothing on first download." This is consistent with
  how dev container features and PR #57 docker apt repo treat
  upstream installers.
