# Brotli doctor

`just brotli-doctor` collects Brotli-related evidence from installed CLI binaries.
It does not assess CVE impact or guarantee that a binary "contains no Brotli".
For certificate diagnostics, use [ca-doctor](ca-doctor.md).

## How to run

Building requires an installed Go 1.27 or newer compiler.
It never installs compilers or packages during diagnostics.
Rebuild after updating the code.

```bash
just brotli-doctor-build
just brotli-doctor
just brotli-doctor --json
```

The default scan covers:

- Recursively scans every installation directory returned by `mise ls --installed --json`, including inactive versions.
- Inspects only direct entries in each PATH directory without recursing through symlinks into other directories.
- Selects regular files with an execute bit on Unix, or `.exe`/`.com` regular files on Windows.
- Parses ELF, Mach-O, and PE candidates; scripts and wrappers are not executed and are counted as non-native.

Symlinks pointing outside mise directories are skipped and reported as incomplete.
File symlinks directly in PATH resolve to their targets, and duplicate targets are scanned once.
Home root, its ancestors, and filesystem roots are rejected as recursive mise scan targets.
Empty or relative PATH entries are also skipped and reported.
Because mise itself runs from PATH, use a trusted PATH and mise.

To narrow the scope, run as follows.
When explicit files are passed, neither mise nor PATH is scanned.

```bash
just brotli-doctor --mise=false
just brotli-doctor --path=false
just brotli-doctor '/path/with spaces/tool'
just brotli-doctor --json ./output/brotli-doctor/brotli-doctor
```

`--max-bytes` caps per-file analysis size, defaulting to and capped at 512MiB.
Exceeding the cap, read errors, parse errors, and truncated scans result in incomplete status.
Scans are capped at 200,000 items and 8MiB of mise output.
`--timeout=2m` is a cooperative deadline for scanning and string reads, not a hard interrupt on file I/O.
It does not provide a consistent snapshot of actively changing directories or isolation against adversarial concurrent file swaps.

## Reading the output

| Output | Meaning |
| --- | --- |
| `dynamic-import` | Direct import of a Brotli-named library; check the resolved path and installed version |
| `c-defined-symbol` | Defined C API symbol; clues to embedded C code, not proof of static linking or actual calls |
| `c-undefined-symbol` | Undefined C API symbol; check the provider separately |
| `go-build` | Go build version; alone, not evidence of Brotli |
| `go-module` | Recorded Brotli-named Go module; prints any replacement alongside |
| `c-api-string` / `rust-path-string` | String clues; cannot determine link type, Rust crate version, or actual use |
| `UNKNOWN` | No Brotli evidence found for that architecture; does not mean unused |
| `HINT` | String clues only |
| `EVIDENCE` | Import, symbol, or module evidence found; does not mean vulnerable |
| `INCOMPLETE` | Part of the scan or analysis did not finish (`incomplete: true` in JSON) |

Even when Pure Go module names or Pure Rust-like strings appear, a C implementation can coexist in the same binary.
Finding dynamic linking does not rule out a separate statically linked copy.
Fat Mach-O binaries inspect each slice separately; unsupported formats or corrupt slices report incomplete.

Exit codes are 0 for complete analysis, 1 for incomplete, and 2 for argument errors.
**Never use 0 as a passing vulnerability check.**
If only non-native wrappers are found, a clean scan still exits 0.

## Impact assessment and updates

Direct imports do not trace transitive libraries loaded by those libraries.
`dlopen`, PE delay-loads, symbols stripped or optimized away, script targets, and environments inside containers are not traced automatically.
When Go build info is unreadable or Rust crate versions are unknown, check build logs, lockfiles, and SBOMs.

Confirm the affected implementation and fixed version in primary sources before updating.
After updating dynamic libraries, already-running processes may need a restart.
Binaries that statically embed affected code require a rebuild against updated dependencies and replacement.
Pure implementations can also have algorithmic issues or their own vulnerabilities, so check them separately from C implementations.
This command never updates, rebuilds, restarts, or queries CVEs over the network.

## Bun's embedded Brotli and CVE-2026-111497

Per official sources checked on 2026-10-24, Bun 1.4.4 includes this fix.
The evidence is as follows:

- [Proposed PR #46351](https://github.com/oven-sh/bun/pull/46351) adds `ERROR_FORMAT_BLOCK_SWITCH = -17` to the Rust FFI enum and updates Rust error mapping in addition to fixing C Brotli. That PR itself was unmerged when checked.
- The actual merge came via [merged PR #46392](https://github.com/oven-sh/bun/pull/46392) (`2a5cbbcb084770dec7d7e2f21cdfd4f7f49b1ee3`), updating to Brotli 1.2.1. A [compare](https://github.com/oven-sh/bun/compare/2a5cbbcb084770dec7d7e2f21cdfd4f7f49b1ee3...38afee6c84fcf48c0edb2466aa4b27d287a59c30) from that commit as base to Bun 1.4.4's resolved commit `38afee6c84fcf48c0edb2466aa4b27d287a59c30` as head shows `behind_by: 0`, confirming inclusion.
- [Bun 1.4.4's build definition](https://github.com/oven-sh/bun/blob/38afee6c84fcf48c0edb2466aa4b27d287a59c30/scripts/build/deps/brotli.ts) pins Brotli 1.2.1 (`db24a98aed38a16de78cc05ca15cdd8dc2a0d92d`) and compiles the C source into an archive. The [Rust FFI definition](https://github.com/oven-sh/bun/blob/38afee6c84fcf48c0edb2466aa4b27d287a59c30/src/brotli_sys/brotli_c.rs) also includes the new error value.
- The [official Brotli 1.2.1 release](https://github.com/google/brotli/releases/tag/v1.2.1) notes the out-of-bounds write fix for this CVE, and the [diff from 1.2.0](https://github.com/google/brotli/compare/v1.2.0...v1.2.1) includes fix commit `b418fa81c48262a86a95332b0bc6d62c30aa78b6`.

Therefore, saying "Rust is unaffected" is inaccurate.
The vulnerable code is the embedded C decoder, but the Rust side also needed to handle the new FFI error value.

Because `bun build --compile` embeds the runtime in its output, updating Bun on the build host does not update existing artifacts.
Rebuild artifacts with a fixed runtime and replace distributed binaries.
For containers, update Dockerfiles to the verified fixed tag and digest, rebuild, and redeploy normally.
Never treat a `latest` tag or the host Bun version alone as proof of a fix.

The diagnostic detects `Bun v...` or `bun-v...` version strings as candidates.
`runtime_reviews` in the output compares each candidate against 1.4.4, while `binary_identity` and `patch_status` always remain `unverified`.
`below-reviewed-release-threshold` means only that the candidate is older than the fixed release, and `at-or-above-reviewed-release-threshold` means only that its number is at or above that version.
It does not guarantee actual binary contents or that future versions retain the fix.
Backported older versions are not declared affected based on version strings alone.

Prereleases, malformed versions, versions over 256 characters, and versions cut off by truncated reads become `unverified-version`.
Valid build metadata is excluded from numeric comparison while kept in the candidate string.
When multiple candidates are found, up to 16 are shown rather than picking only the highest.
Exceeding the candidate cap is reported as incomplete.
Absence of a version string does not prove Bun is absent; check provenance and build logs.

In trusted runtime environments, operators can check versions with these commands.
These are not run automatically by `brotli-doctor`.

```bash
bun --version
# Replace placeholders with names from your actual environment before running
# podman exec <container> bun --version
# kubectl exec <pod> -c <container> -- bun --version
```

Check actual exploitability separately by inspecting usage of `fetch()` Brotli response decompression, `node:zlib`, `DecompressionStream("brotli")`, and similar APIs.
Blocking `Content-Encoding: br` on incoming requests at a proxy does not prevent decompressing external responses.
Never conclude from this diagnostic alone whether a service is reachable by the vulnerable code path.

## Distributing to other OSes

```bash
just brotli-doctor-build-all
```

Generates binaries for Linux, macOS, and Windows (both amd64 and arm64) in `output/brotli-doctor/`.
Place the target OS binary in that directory named `brotli-doctor` (`brotli-doctor.exe` on Windows).
On Windows, the recipe runs through Git Bash, while diagnostics run as a native Go binary.
It is not invoked automatically by `just doctor`.
