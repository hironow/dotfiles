# CA health and incident diagnostics

`just doctor`'s CA diagnostics run routine CA configuration checks and reviewed incident-specific rules.
They separate verified evidence from unverified scope and never declare an entire host safe.
They do not modify certificates, packages, or OS settings, and do not use administrator privileges.

## Running

Build explicitly on first use and after changing diagnostic sources.
This requires a local Go 1.27.4 or newer compiler and mise; it never downloads a compiler automatically.
Running the built diagnostic binary does not require Go.

```sh
just ca-doctor-build
just doctor
```

To run only CA diagnostics, use `just ca-doctor`.
`just doctor` passes `--summary`, omitting per-test-host `ca-chain-*` lines and summarizing one `ca-live-*` line per client.
Use `just ca-doctor` to see every host line.
To run without network access, use `just ca-doctor --offline`.
`CA_DOCTOR_OFFLINE=1 just doctor` also skips only network calls for CA checks.
On PowerShell, set `$env:CA_DOCTOR_OFFLINE='1'` first.
Checks skipped due to offline mode report `WARN`.

If the binary is missing, `doctor` prints `WARN ca-build` and build instructions.
An older binary that does not recognize `--summary` (returning only `ERR ca-arguments` and exit code 2) is also rejected as invalid output and triggers the same `WARN ca-build` rebuild prompt.
Go sources, tests, incident JSONs, and `go.mod` are embedded in the binary and compared byte-for-byte against the current checkout's file set.
If they mismatch, `doctor` rejects the output and asks for a rebuild.
This check detects stale builds, not malicious binary tampering.

`just ca-doctor-build-all` builds binaries for Linux, macOS, and Windows (both amd64 and arm64) in `output/ca-doctor/`.
To distribute to another machine, use the matching checkout and binary and place it in that directory as `ca-doctor` (`ca-doctor.exe` on Windows).
Windows recipes run from PowerShell through Git Bash.
Tools found only as `.cmd` or `.bat` wrappers are not executed and are reported as unverified.
A passing cross-build does not substitute for runtime verification on each OS.

## Common CA health checks

- Checks environment variables that disable TLS verification and Git's `http.sslVerify` in the current config context. Defining `GIT_SSL_NO_VERIFY`—even as `0`, `false`, or empty—disables verification and triggers `ERR`. Git is checked against the baseline URL `https://example.com/`; settings for other repos or URLs are not guaranteed.
- Checks that explicitly configured CA files exist, are readable, parse as PEM and X509, and are valid against the local clock. Each file is capped at 1MiB, and certificate contents, subjects, and config values are never printed.
- Checks only that CA directories can be opened; contents and backend effectiveness are not guaranteed. `SSL_CERT_DIR` and `GIT_SSL_CAPATH` are treated as colon-separated on Unix and semicolon-separated on Windows. Empty segments are marked unverified.
- Tests an HTTPS baseline connection separately with each TLS client: curl, Node.js TLS API, Python standard ssl, Bun fetch, and the Go HTTP client inside the diagnostic binary itself.
- Collects tool and CA package info, including Git, Go, uv, rustup, and rustc selected on the current PATH. On macOS, it also inspects `/usr/bin/curl` and `/usr/bin/python3` when they differ from PATH.

Checked CA file variables are `SSL_CERT_FILE`, `CURL_CA_BUNDLE`, `REQUESTS_CA_BUNDLE`, `PIP_CERT`, `GIT_SSL_CAINFO`, and `NODE_EXTRA_CA_CERTS`.
`REQUESTS_CA_BUNDLE` may also point to a directory.
Environment variable names are case-insensitive on Windows and case-sensitive on Unix.
Parsing a CA bundle does not prove its contents are trustworthy or that revocation checks run.
Expired root certificate handling also depends on the TLS implementation, so expiry alone does not mark one untrusted.

## Network and execution limits

Diagnostics do not follow redirects or read curl config files.
They never add flags that disable TLS verification.
Node.js, Python, and Go connect directly, while curl and Bun may follow their respective proxy settings.
Node.js sends SNI (Server Name Indication) only when the target is a DNS name, and still verifies the certificate against the IP address when connecting by IP.
Baseline success does not guarantee reachability to other hosts.
Only when a baseline connection returns `unknown` does the same client retry up to 3 times total.
Attempt 2 uses IPv4 only, and attempt 3 returns to default networking.
If all 3 attempts return `unknown`, it stays `unknown`.
Incident test hosts are tried once with default networking.
One failure cannot answer whether that client can establish a TLS connection.
Attempt 2 uses IPv4 because the incident test hosts have only IPv4 addresses while the baseline (GitHub Pages) also has IPv6.
On Windows, roughly half of IPv6 connections to the baseline reset (2026-11-01, reset point unconfirmed); IPv4 did not reset.
Attempt 3 returns to default so IPv6-only networks still get a second chance.
Because Bun's fetch has no IPv4-only option, Bun retries 3 times with default networking.
Bun's `node:tls` can restrict to IPv4, but we do not use it because it connects directly without proxy settings and takes a different path from `fetch` against test hosts.

The diagnostic context times out at 30 seconds overall and 4 seconds per external command.
Concurrent connections are capped at 12 total across all clients.
Stdout and stderr are truncated at 4096 bytes each; exceeding this marks the check unverified.
External commands receive `GOTOOLCHAIN=local`, `MISE_AUTO_INSTALL=false`, and `RUSTUP_AUTO_INSTALL=0` to prevent Go, mise, and rustup from auto-downloading toolchains.
Missing tools are marked unverified rather than installed for diagnostics.
On command cancellation, child processes are terminated best-effort and output pipe waits are bounded.
On Windows, descendant termination uses System32's taskkill best-effort and depends on permissions and shim layout.
taskkill is located from the system directory returned by the Windows API, not from `SystemRoot`.
General OS I/O such as PATH lookups or file reads is not strictly wall-clock bounded.

## Results and limitations

`WARN` marks items to check or act on for this host.
Scope caveats and host facts are emitted as `INFO`.
`INFO` is neither a pass nor a problem; it counts toward `doctor`'s `info=` total and does not change the exit code.

| Output | Meaning |
| --- | --- |
| `OK ca-file-*` | Specified file parsed cleanly. Does not guarantee trust or revocation status |
| `OK ca-https-*` | That client accepted a TLS connection to the baseline. Observation applies only to that connection |
| `OK ca-version-*` | Meets the incident fix floor. Does not mean the effective CA bundle is safe |
| `ERR ca-version-*` | Older than the fixed version in a known affected branch |
| `ERR ca-live-*` / `ERR ca-chain-*` | Accepted a TLS connection to an incident test host. `ca-live-*` lists the accepted hostnames. Check the CA bundle and any TLS interception |
| `INFO ca-live-*` / `INFO ca-chain-*` with `certificate-rejected` | Baseline succeeded and all test host certificates were rejected. Does not pass because distrust of that CA cannot be proved as the cause |
| `WARN` and `unknown` | Network, execution, or parsing failed. Not judged safe |
| `WARN ca-version-*` (`outside the reviewed fix branches`) | Installed version is outside the branches with verified fixes. Two-part versions such as `24.0` are compared as `24.0.0` (incident rule fix floors use three parts) |
| `INFO ca-version-*` (`not installed`) | That Python has no certifi or pip installed. Nothing to compare |
| `INFO ca-tool-*` / `ca-env` (CA file vars) / `ca-git-verify` (no override) | Checked binaries, configured CA file variables, and unoverridden Git verification. Factual only; no action needed |
| `INFO ca-platform` / `ca-remediation` / `ca-advice-*` / `ca-rust` / `ca-os-bundle` / `ca-coverage` | Scope limits and OS-specific check targets |
| `WARN ca-env` (proxy, `NODE_OPTIONS`, `GODEBUG`, `PYTHONHTTPSVERIFY`, `NODE_TLS_REJECT_UNAUTHORIZED`) | Settings present that can alter TLS behavior |
| `WARN ca-policy-*` | Past review deadline. Review the rule against the publisher's advisories |

HTTP 4xx, 5xx, and redirects still mean a TLS connection was accepted.
Conversely, a certificate error alone does not prove incident mitigation.
Expired certificates, hostname mismatches, and bad proxy certificates produce the same class of errors.
When TLS interception is present, a successful connection alone does not prove the leaked certificate itself was accepted.

curl certificate rejection is detected by exit code 60.
However, Windows curl (Schannel) returns 60 only for untrusted roots and hostname mismatches, and returns exit code 35 for revoked or expired certificates.
So on exit code 35, stderr names (`CRYPT_E_REVOKED`, `SEC_E_CERT_EXPIRED`, `SEC_E_CERT_WRONG_USAGE`) are counted as certificate rejections.
Failures to check revocation (such as `CRYPT_E_REVOCATION_OFFLINE`) are not counted as rejections and stay `unknown`.
Stderr text is never printed.

Standalone command exit codes are `0` for no warnings, `1` if unverified items exist, and `2` if `ERR` exists.
`doctor` verifies consistency between results and exit codes, aggregates them, and returns exit code 1 on `ERR` as previously specified.
Scope limits are always recorded as `INFO ca-coverage`.
Unverified items are never promoted to pass to reduce warnings; `INFO` is only for actionable-free caveats and facts.

Under WSL, only the Linux side is checked.
Running on native Windows does not verify inside WSL.
macOS Keychain revocation data and PEM bundles are separate.
Browser or OS revocation list delivery, other copies on PATH, separate virtualenvs, vendored CA bundles inside pip, Electron, containers, and existing static Go/Rust binaries are not covered.
OS package metadata is collected, but versions across different distributions are not compared directly.

## OS-specific checks and remediation

Even on the same OS, results vary by the binary chosen on PATH, virtualenvs, and explicit CA files.
First check the `ca-tool-*` binaries and `ca-env`, and record whether the baseline succeeded and the result for each incident test host.
Do not treat a check with remaining `unknown` items as complete.
`ca-remediation` only points to OS-specific check targets; it does not update or modify trust stores.
On machines using corporate CAs or TLS interception, check with your administrator before replacing CA bundles.

| Environment | Check and remediation | Additional scope to verify |
| --- | --- | --- |
| macOS | Update OS, and check Homebrew `ca-certificates` and the actual PEM bundle in use | Keychain, `/etc/ssl/cert.pem`, and Python's default CA are not the same |
| native Windows | Check Windows Update and organizational certificate deployment | Schannel uses the OS store and Microsoft's blocklist (CTL). CPython's standard ssl uses only roots in the OS store ([Python on Windows](#python-on-windows)). Standalone PEM bundles such as Node.js must be updated separately |
| WSL | Update `ca-certificates` inside each distribution | Changes do not carry over from Windows host updates or other WSL distributions |
| Linux | Update the CA bundle via official distribution package updates | Containers, virtualenvs, static binaries, and standalone CA bundles must be checked separately |

On Linux and WSL, follow host policy and update CA packages with `apt` (Debian/Ubuntu), `dnf` (Fedora family), or `apk` (Alpine).
Because of backports, never compare version numbers across different distributions directly.
Do not substitute WSL for Windows diagnostics; run the Windows-built binary from PowerShell via `just ca-doctor` (the recipe runs through Git Bash).
After updating tools, re-run the same diagnostic from a new process.
Windows, WSL, and Linux results must each be verified on their actual host.
Success on Mac or a passing cross-build does not count as verification on other OSes.

### Selecting a user-space CA bundle on Mac

Update Homebrew's CA package, then verify both the file on disk and live connections.
It is usually `/opt/homebrew/etc/ca-certificates/cert.pem` on Apple Silicon and `/usr/local/etc/ca-certificates/cert.pem` on Intel Macs, though you should check the path per machine.
If existing CA environment variables are set, coordinate with their owner instead of changing precedence with extra variables.

On machines without existing CA overrides, you can set the updated CA bundle in your shell config as `SSL_CERT_FILE` (for supported Python standard ssl), `CURL_CA_BUNDLE` (curl), `REQUESTS_CA_BUNDLE` (Requests), and `PIP_CERT` (pip).
This configures individual clients rather than fixing the OS trust store.
It applies only to new processes started from that shell and not retroactively to already running editors, GUIs, or services.

In Apple-bundled Python/LibreSSL, `SSL_CERT_FILE` may appear as the displayed default path without actually being used for default TLS CA loading.
We observed this behavior on Mac Python 3.9.6 / LibreSSL 2.8.3, so do not judge remediation by the printed variable alone.
In that case, use a fixed managed Python or an application-provided CA setting.
Apps using Python's standard ssl can explicitly pass `ssl.create_default_context(cafile="<absolute path of the updated CA bundle>")`, though this does not automatically apply to other HTTP libraries.
If you continue using system Python and connections are still accepted, keep the `ERR`.

LibreSSL clients such as Apple-bundled Python read the OS PEM bundle `/private/etc/ssl/cert.pem` (verified again on 2026-11-09 with Python 3.9.6 / LibreSSL 2.8.3).
To remove incident `untrustedRoots` from this bundle, run two steps:

1. `just ca-os-bundle-candidate` (no root required): writes a candidate to `output/ca-os-bundle/cert.pem` and prints the input and candidate SHA-256, removed roots, and remaining certificate count. Inspect the diff between the candidate and the original bundle.
2. `just ca-os-bundle-apply <input SHA-256> <candidate SHA-256>` (sudo): replaces the bundle only if both the input and the regenerated candidate match the hashes from step 1. The original bundle is backed up and synced to `/private/etc/ssl/cert.pem.dotfiles-backup-<timestamp>` first.

To revert, run `sudo cp -p <backup path> /private/etc/ssl/cert.pem`.
If a macOS update restores the bundle, `ERR ca-live-*-system-python` returns, so repeat from step 1.
Clients using Keychain (such as Safari) are unaffected by this operation.
Never alter diagnostic code to swap CA bundles just for that connection, or add `sitecustomize.py` to silence warnings.
Separate OS-managed file or Keychain remediation from user environment variable changes, and obtain administrator approval.

### Python on Windows

Windows CPython's standard ssl loads certificates from the Windows ROOT and CA stores as trust anchors.
It ignores Microsoft's auto-updated blocklist (CTL) and the Disallowed store.
Therefore, even if Windows rejects an intermediate CA, Python accepts the connection as long as it chains to a root in the ROOT store.
In the eMudhra incident, the seven intermediate CAs signed by AAA Certificate Services (`-aaa-`) fall into this category.
Windows itself rejects these seven, so do not infer Python's result from Go or other tools that use the Windows verifier.

CPython's fix (gh-160040, CVE-2026-115557) rejects chains containing the leaked keys.
Once a fixed release ships, update Python on PATH and any Pythons managed by uv or other tools, then re-run `just ca-doctor`.
EOL branches receive no fix.

Until a fix ships, do not modify the intended purpose (EKU properties) of AAA Certificate Services in the OS store.
On 2026-10-26, we observed two issues when doing so:

- Windows root auto-update reverted the properties within about 30 minutes.
- While changed, chains for other roots cross-signed by AAA (such as SSL.com) failed in both the Windows verifier and Python; on machines lacking that root itself in the OS store, `https://example.com/` also failed.

Do not disable auto-update either, because that stops blocklist distribution.
Do not point only the diagnostic Python to another CA bundle or suppress warnings with `sitecustomize.py`.
Leave the `ERR` until a fixed release is available.

## Adding and updating incident rules

The source of truth is `tools/ca-doctor/incidents/*.json`.
Rules are never fetched externally at runtime.
Each JSON records the ID, check type, evidence URLs, verification date, review deadline, baseline URL, incident test hosts, per-tool fix floors, unfixed tools, and verification caveats.
If needed, list up to 16 roots that test chains chain to (and that are absent from fixed CA bundles) under `untrustedRoots` by lowercase 64-hex-char DER SHA-256 and subject; `ca-doctor os-bundle` removes them from the OS CA bundle ([Selecting a user-space CA bundle on Mac](#selecting-a-user-space-ca-bundle-on-mac)).

Currently the only check type is `tls-endpoint-and-version`, which checks connection acceptance to target hosts and known fix floors.
Other incident types require code and test additions; JSON alone cannot run arbitrary diagnostics or commands.
Adding a floor for a tool whose version cannot be collected fails manifest validation.
Unlisted release branches, development builds, and unparseable versions report `WARN`.

When changing rules, verify the publisher's fix advisories and evidence URLs, and update tests and incident docs for review.
Expired review deadlines emit warnings, and outdated rules never mark a machine safe.
Any addition, removal, or change requires a rebuild.

For recorded incidents, see [eMudhra intermediate CA compromise](emudhra.md).
