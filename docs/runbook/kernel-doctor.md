# Kernel doctor

`just kernel-doctor` compares the Linux kernel version against a "reviewed, sourced fix floor" and outputs **evidence and uncertainty**, not a verdict.

**This repository does not bundle, build, or pin a Linux kernel.** So this tool does not and cannot fix kernels. It applies no patches, updates, or installs.
It never says "vulnerable". The closest it gets to "fixed" is `reviewed-vendor-build` on a full-string match against a recorded vendor build (`vendorBuilds`), which only establishes that the fix commit is in that build's tag, not the running patch state.

For certificates use [ca-doctor](ca-doctor.md), and for embedded binary contents use [brotli-doctor](brotli-doctor.md).
For WSL host settings see [windows-host](windows-host.md) and [ollama-windows-wsl](ollama-windows-wsl.md).

## How to run

```bash
just kernel-doctor-build   # Explicit build only; doctor does not auto-build
just kernel-doctor
just kernel-doctor --json
just kernel-doctor-build-all   # linux/darwin/windows × amd64/arm64
```

Inspect another host's version without running commands on that OS.
Passing `--osrelease` **skips reading** local `/proc` and `/etc/os-release`.

```bash
# Check a Windows host's WSL kernel from macOS
just kernel-doctor --osrelease="$(wsl.exe -d Ubuntu -- uname -r)"
```

Exit codes are 0 for no warnings, 1 for warnings or unverified results, and 2 for argument errors.
`INFO` lines (caveats on uninspected scope) do not raise the exit code.
**Do not treat 0 as "safe".** It only means no unverified lines were emitted.

On machines not running a Linux kernel (macOS, native Windows), it skips comparison and outputs a single `OK kernel-not-applicable` line. That line also notes that WSL or Linux VMs used from that machine were not inspected.
On machines where a kernel version was inspected (Linux, WSL, `--osrelease`), uninspected scope is output as `INFO kernel-coverage`.

Third-party numbers (`kernel-observed-*`) and recorded advice (`kernel-advice-*`) never depend on this machine's state, so `kernel-doctor` emits them as `INFO`.
Per-CVE warnings are `kernel-version-*` lines (below the fix floor or unverified) and sysctl lines.

## Reading the output

There are 6 version comparison outcomes. `patch_status` is **always `unverified`**. `backport_state` is also `unverified`, becoming `fix-commit-in-vendor-tag` (fix commit is in the vendor release tag) only for `reviewed-vendor-build`.

| Outcome | Meaning |
| --- | --- |
| `below-reviewed-fix-floor` | Clean upstream release form, below the fix floor for a reviewed branch |
| `at-or-above-reviewed-fix-floor` | Same form, at or above the fix floor. **Vendor backports and running patch state remain unverified** |
| `reviewed-vendor-build` | Full string matches a recorded vendor build (`vendorBuilds`). Fix commit is in that tag. **Cannot distinguish custom builds sharing the same string, and running patch state is unverified** |
| `unverified-vendor` | Vendor/distro kernel. Not compared because the third component is not an upstream patch level |
| `unverified-branch` | Clean form, but that branch has not been reviewed |
| `unverified-version` | Not a clean upstream `x.y.z` string. Not compared |

Line prefixes match doctor's `LEVEL name - detail` format (`scripts/doctor_lines.py`).

## Why vendor kernels are not judged

The third component of Ubuntu's `6.8.0-45-generic` or Debian's `6.1.0-28-amd64` is **not an upstream patch level**. It is the vendor's own ABI revision.
Comparing it numerically against an upstream fix floor **fails in both directions**: a fix may be backported to an older number, or vice versa.

So we compare only when both of the following hold:

- The **entire** string is a clean upstream release form `x.y.z`.
  Extracting only the first 3 components and discarding the rest would turn `6.6.159+` (which Linux actually appends), `6.6.159.2`, and `6.6.159garbage` into "6.6.159 or higher".
- `major.minor` matches a reviewed branch (or is at or above the mainline fixed version).

Everything else becomes `unverified` and lists the reviewed fix floors.
**Never count `unverified` as "fixed".** Failing conservative is intentional.

Branches **between** reviewed branches (e.g., 6.13-6.17) become `unverified-branch`. This is intentional; consult the fix floor list and that branch's own stable tree or vendor advisories.

### Recording a vendor build

Instead of numeric comparisons, verified builds can be added one by one to an incident's `vendorBuilds` (ADR 0065 Decision 3). Before adding one, verify all of the following:

1. The SHA of the commit that the incident's `source` (primary CVE source) names as the fix for that build's branch.
   It must match `fixCommit` for that branch in the record's `branches` (checked by ParseIncident).
2. The SHA of the commit pointed to by the vendor release tag (tags can move, so pin by SHA).
   Example: `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`.
3. Commit 1 is an ancestor of commit 2: `gh api repos/<owner>/<repo>/compare/<1>...<2>` returns `behind_by=0`.
4. The fix lines remain present (not reverted) in commit 2. **Always read** the files touched by the fix at commit 2 to verify the fix lines are there. Checking `commits?sha=<2>&path=<file>` for no revert is only supplementary (non-revert changes can also remove lines).
5. The full `uname -r` string (e.g., `6.18.58.1-microsoft-standard-WSL2`).

`release` is 5, `fixCommit` is 1, `tagCommit` is 2, and `reviewedAt` is the verification date. `source` is the vendor release page in the form `https://<host>/<owner>/<repo>/releases/tag/<tag>`. `evidence` is the compare URL from step 3 and must match `https://<host>/<owner>/<repo>/compare/<1>...<2>` in full (same host and owner/repo as `source`; tag names, other repos, extra path segments, encoded characters, `?`, and `#` are rejected by ParseIncident). Because these two use GitHub release and compare URL formats, tags containing `/` or builds on other forges cannot be recorded without code changes. A build's branch must appear in the incident's `branches`. After updating records, rebuild with `just kernel-doctor-build`.

## About CVE-2026-98432

`ipv4: free inet_opt and ireq_opt after an RCU grace period`. CNA is kernel.org, published 2026-10-15. Introduced in 2015 by commit `079096f103fa` (v4.4 era). Reviewed upstream fixed versions are 5.10.272 / 5.15.223 / 6.1.190 / 6.6.159 / 6.12.113 / 6.18.56 / 7.2.10, and mainline is 7.3. The fix changes `kfree()` to `kfree_rcu()` in `inet_sock_destruct()` and `tcp_v4_reqsk_destructor()`.

**Severity is disputed.** The two estimates below assess the same vulnerability differently:

| Source | Score | Attack complexity |
| --- | --- | --- |
| NVD / Tenable / Rapid7 | 9.8 | `AC:L` (low) |
| Oracle internal record (marked provisional) | 8.1 | `AC:H` (requires winning a race) |

Red Hat rates priority as **high** rather than critical (Bugzilla is `NEW`, fixed version unconfirmed).
EPSS is 0.00388 (about 0.4%), not listed in CISA KEV.
**Not listed in KEV at time of observation. This is not evidence of absence of active exploitation, public exploits, or CISA evaluation status.**

There are two triggers, both requiring specific conditions:

1. A race where another CPU processes a retransmitted SYN (building SYNACK while the child socket is freed).
   This path requires **sockets with IP options** (`ip_options_build()` reads `optlen`).
2. Request socket migration: `net.ipv4.tcp_migrate_req=1` **or** a `BPF_SK_REUSEPORT_SELECT_OR_MIGRATE` program.

This tool reads the one sysctl in trigger 2, but **0 does not clear the host** (the BPF path remains).
Because sysctls are per network namespace, the value read is for **the current namespace**.
Path 1 and BPF cannot be introspected externally, so they are **not inspected**.

IPv6 has an analogous issue (`ipv6_opt` in `tcp_v6_reqsk_destructor()`, set only with CALIPSO), handled by a **separate patch** outside this CVE's reviewed fix scope.

## Remediation by surface

| Surface | Kernel provider | Remediation |
| --- | --- | --- |
| WSL2 and self-hosted runner | Microsoft | Run `wsl --update` **on the Windows side** |
| Vendor kernels (Debian / Ubuntu / RHEL / SUSE / Amazon) | Vendor | Vendor advisories and package updates (`apt` / `dnf`) + **host reboot** |
| devcontainer / emulator / telemetry containers | Host Linux | Update the Podman machine / WSL2 / native Linux kernel yourself. **Updating the image does not change it** |
| macOS host | Apple | Not applicable |

WSL follows this fixed procedure. **The unit of restart is the kernel; restarting processes or containers has no effect.**

```bash
# Windows side (elevated PowerShell)
wsl --update
wsl --shutdown
# Verify it booted with the new kernel
wsl.exe -d <distro> -- uname -r
```

`wsl --shutdown` **stops all distros and the WSL2 VM**. Because the self-hosted runner runs inside WSL, run it **when no job is running** ([ADR 0035](../adr/0035-runner-disk-gc.md)).

WSL instances specifying a custom kernel via `kernel=` are managed separately and are not updated by `wsl --update`.
**"Update command succeeded = fixed" is false.** Verify the new kernel is running with `uname -r`.

## Limitations

- Version comparison checks only the "reported string" against the "reviewed upstream fix floor".
  Vendor backports are invisible except on an exact match to a recorded build. Running kernel patch state is invisible.
- Inside a container, `/proc/sys/kernel/osrelease` returns the **host** kernel.
  That is the right answer for exposure, but does not distinguish host from container.
- Path 1 (sockets with IP options) and BPF-based migration are not inspected.
  Network namespaces other than the current one are not inspected.
- It knows only recorded CVEs and is not a general vulnerability scanner.
- A passing cross-build does not prove observation on actual Windows or WSL hosts.
- Review records expire and emit `policy_freshness=overdue` past their deadline.
  Re-read primary sources and update the record.

## Primary sources

- upstream advisory: <https://git.kernel.org/pub/scm/linux/security/vulns.git/plain/cve/published/2026/CVE-2026-98432.mbox>
- CVE record: <https://osv.dev/vulnerability/CVE-2026-98432>
- Oracle assessment (8.1 / `AC:H`): <https://linux.oracle.com/cve/CVE-2026-98432.html>
- Red Hat Bugzilla 2553390: <https://bugzilla.redhat.com/show_bug.cgi?id=2553390>
- Tenable (9.8 / EPSS / KEV): <https://www.tenable.com/cve/CVE-2026-98432>
- Red Hat CVE page: <https://access.redhat.com/security/cve/CVE-2026-98432>

Reviewed on 2026-10-29; review deadline 2026-11-26.
The source of truth for records is `tools/kernel-doctor/incidents/`.
