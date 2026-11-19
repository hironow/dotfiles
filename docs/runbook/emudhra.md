# eMudhra intermediate CA compromise diagnostics

CA doctor's incident rule `emudhra-2026` tests against fixed data from the [public diagnostic site](https://emudhra.we-have-a-problem.com/) as of 2026-10-23.
Build instructions, common CA health checks, output interpretation, and limitations are in [CA doctor](ca-doctor.md).

## Live chain connection checks

Using the public diagnostic site as the baseline, it checks all 14 hosts listed there.
For DV, OV, and EV across G3B and G3C, it separates the 12 hosts covering direct chains and AAA cross-signed chains.
To these it adds `dv-g3b-noct` and `dv-g3b-aaa-noct`, which serve certificates not logged to Certificate Transparency (CT) (rest of domain: `-emudhra.we-have-a-problem.com`).
Because CT-enforcing clients can reject unlogged certificates even while still trusting the CA, these 2 are separated from the standard 12.
14 is the number of chain presentations, not the number of compromised private keys.
Timeouts and DNS failures are unverified and never judged safe.
Rejecting certificates still reports `WARN`, because distrust of that CA cannot be proved as the cause.

## Fix version floors

| Target | Fix version floor |
| --- | --- |
| Go | 1.27.3 / 1.26.10 |
| Node.js | 22.23.4 / 24.22.1 / 26.12.1 |
| uv | 0.13.5 |
| mise | 2026.10.17 |
| certifi | 2026.10.19 |
| pip | 26.2.2 |
| rustup | 1.29.2 |
| Bun | 1.4.4 (1.4 branch) |

The source of truth is `tools/ca-doctor/incidents/emudhra-2026.json`, which also records the review deadline.
Go and Node.js compare only the branches shown in the table.
Target branches for other tools are also explicit in `branch` in the JSON; unlisted branches never pass by version comparison alone.
Bun canary builds are not judged against stable floors either.

## Pinned versions in SSOT

Pinned image versions live in `config/mise/image-tools.toml` and sync into install scripts via `just mise-versions-sync`.
Versions for Go, Node.js, uv, Bun, and initial Linux bootstrap mise must be at or above the incident rule floors.
rustup used for temporary builds inside images lives in a manually maintained feature block; update its version and per-CPU verified SHA-256 together.
Numeric fix floors live only in the incident JSON, and `tests/unit/test_ca_version_pins.py` checks SSOT and manual install pins against them (run by `just test-unit` and `just ci`).
Missing declarations or floors, unlisted branches, and pinned prereleases also fail the test.

`latest` and `lts` in host `config/mise/config.toml` are not pinned or minimum versions.
Keep them as-is, and verify installed tools on existing machines separately with `just ca-doctor` after updating.
Updating SSOT alone does not update running processes or existing images.

## OS-specific remediation

On Mac, native Windows, WSL, and Linux, check OS trust stores and each runtime's CA bundle separately.
Follow [CA doctor's OS-specific steps](ca-doctor.md#os-specific-checks-and-remediation) and re-run diagnostics on the same machine and launch environment.
Native Windows CPython accepts the 7 AAA-signed chains that Windows rejects; see [Python on Windows](ca-doctor.md#python-on-windows) for handling until a fixed CPython ships.
The [official rustup 1.29.2 announcement](https://blog.rust-lang.org/2026/10/20/Rustup-1.29.2/) recommends `rustup self update`, but also check the fetch path of the old updater itself.
Setting CA environment variables does not change statically compiled rustls trust settings.

Updating the Rust compiler alone does not update rustls/webpki dependencies in applications.
Check each app's Cargo.lock separately for rustls-webpki 0.103.16 and webpki-roots/webpki-root-certs 1.0.10 fixes or appropriate backports.
macOS OS revocation status alone does not mean PEM bundles such as `/etc/ssl/cert.pem` are fixed.
This diagnostic does not auto-apply fixes or guarantee every app is remediated.
