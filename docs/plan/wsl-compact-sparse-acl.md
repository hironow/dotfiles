# Plan (rev 2): Fix `just wsl-compact` sparse detection and warn on overly broad vhdx ACLs

## Handling the re-review (APPROVE WITH CHANGES)

Implemented as follows:

- Do not resolve SIDs to names (reviewer measured that resolving `S-1-15-3-…` throws an exception). Keep `facts` to `allow <SID>` only, list SIDs in WARN, and tell the user to inspect names with `icacls`.
- Emit ACL results before the early exit for small slack. Added "small slack + untrusted SID" to tests.
- Fake fsutil returns English `"This file is NOT set as sparse"` and creates a marker file when called. Confirm the old implementation prints yes on this (Red).
- Omit the version number from printed text; state "listed in `wsl --help` on this machine's WSL (3.0.5)".
- The shared helper (`tests/unit/_bash_fakes.py`) was added in the first structural commit of this PR, not "merged to main in #635" as the reviewer said (misread from seeing untracked/uncommitted files in the worktree during review).

## Why

On 2026-11-17, moving a WSL distro to D: via `wsl --manage --move` cleared sparse on the vhdx (`fsutil sparse queryflag` returned `"スパースに設定されていません"` (not set as sparse), no `SparseFile` attribute, actual size on disk = logical size 227 GB).
Yet `just wsl-compact` printed `sparse    : yes`.

- Detection (`scripts/wsl_compact.sh:58`) runs `fsutil sparse queryflag … | grep -qi 'sparse'`, grepping locale-dependent text.
  In English, it matches both `"This file is set as sparse"` and `"This file is NOT set as sparse"`, returning yes for both.
  On this machine (cp932), running directly from Git Bash outputs Japanese text and fails to match (reviewer measurement).
  Why `just` printed yes (whether fsutil returned English via that path) is not identified. Either way, text matching cannot be reliable.
- Even when sparse is detected, it prints diskpart steps (`:109-131`). However, diskpart and Optimize-VHD reject sparse vhdx files with `"Virtual hard disk files must be uncompressed and unencrypted and must not be sparse"` (WSL issue #4103, MS Q&A 1526083). Following the printed steps fails after stopping runners with `wsl --shutdown`.
- During the same move, inheriting D:\'s default ACL (`Authenticated Users:(OI)(CI)(IO)(M)`, `Users:(OI)(CI)(IO)(GR,GE)`) made the vhdx readable and writable from `CodexSandboxOffline/Online` (a member of Users).
  The vhdx holds the entire distro, including runner credentials. Tightened manually this time, but nothing alerts on it.
- The fallback hint `wsl --manage <distro> --get-location` (`wsl_compact.sh:40`, `wsl_fsck.sh:38`) does not exist in WSL 3.0.5's `wsl --help`. Because the hint text was duplicated in two places, both broke together.

## What to change

1. `scripts/wsl_vhdx_lib.sh`:
    - `wsl_vhdx_path` reads `VhdFileName` from the registry (defaults to `ext4.vhdx`).
    - Consolidate the not-found hint into one function `wsl_vhdx_locate_hint`.
      The hint suggests `reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss" /s` (prints `DistributionName`, `BasePath`, and `VhdFileName` together).
      Call it from both `wsl_compact.sh` and `wsl_fsck.sh`.
    - `wsl_vhdx_facts <windows-path>` reads raw vhdx facts in a single PowerShell call and outputs one per line:
      `sparse 0|1|?`, `user <SID>`, `owner <SID>|?`, `allow <SID> <name>` (one per Allow ACE, including inherited ACEs), or `allow ?` if ACL cannot be read.
        - Do not use `Get-Acl`. On this machine, invoking it from Git Bash inherits pwsh 7's `PSModulePath` and fails with `CouldNotAutoloadMatchingModule` (measured). Use .NET `[IO.File]::GetAttributes` and `[IO.File]::GetAccessControl`, resetting `$env:PSModulePath=[IO.Path]::Combine($PSHOME,'Modules')` first (same as `scripts/jev_launch.py:40-51` and `scripts/ollama_host.py:47-49`).
        - Wrap attributes and ACL in separate `try` blocks so only unreadable items become `?` (attributes can be read even when ACL cannot).
        - Pass the path via an environment variable and strip CR from output.
    - `wsl_vhdx_untrusted_sids` is a pure function (no I/O) reading facts from stdin and outputting untrusted SIDs.
      Trusted SIDs: the user's SID, `S-1-5-18` (SYSTEM), `S-1-5-32-544` (Administrators), prefix `S-1-5-83-` (NT VIRTUAL MACHINE, added by WSL), and prefix `S-1-15-` (only affects AppContainer checks). Treat `S-1-3-4` (OWNER RIGHTS) as the owner.
      If the owner is untrusted, output that too. If ACL is unreadable, output `?`. Matches the allowlist design of `scripts/jev_core.py:383-401`.
2. `scripts/wsl_compact.sh`:
    - `sparse` is 3-valued: yes / no / unknown. Do not call fsutil.
    - When sparse: omit diskpart steps and print instead:
        - space freed inside the distro is returned automatically by fstrim;
        - diskpart and Optimize-VHD reject sparse vhdx files (WSL `--manage --compact` is also reported to reject them, unverified on this machine);
        - reclaiming remaining space requires `--set-sparse false` first, during which the vhdx can grow up to `logical - actual = N GB` (calculate N using values already held by the script; since growth is evidenced only by third-party measurements from VRAM Lab, write "up to").
    - When not sparse: print the existing diskpart steps, plus one line noting that `wsl --manage <distro> --compact` (WSL 3.0.1+) is unverified on this machine.
    - When unknown: print no steps; state that attributes could not be read.
    - If untrusted SIDs exist, emit `WARN`, list the found SIDs and names, and show an example `icacls` command to disable inheritance on the vhdx parent (`BasePath`) (`/inheritance:r /grant:r` preserves explicit ACEs added by WSL; tightening only the file resets when the next vhdx is created).
    - Update the header note claiming "`--allow-unsafe` is required" (`:16-18`) to match WSL 3.0.5's help (`--set-sparse` has no `--allow-unsafe`).
      Keep the policy of not switching to sparse unchanged (ADR 0035).
3. `scripts/wsl_fsck.sh`: switch the hint to `wsl_vhdx_locate_hint`.
4. Rewrite the `docs/runbook/runner-disk-gc.md` section on returning vhdx space to C: to match this PR:
   change "WSL vhdx is normally sparse" (`:103`) to "`--move` can clear sparse (observed 2026-11-17)",
   update "`--allow-unsafe` is required" (`:108`) to match 3.0.5 help,
   and add "After `wsl --manage --move`, run `just wsl-compact` to verify sparse and ACLs".

## What we will not do

- Switching sparse or running compact automatically: stay display-only as today.
- Verifying `wsl --manage --compact` behavior (deferred by operator decision; state clearly in guidance that it is unverified).
- Integrating ACL checks into `just doctor` (deferred to a separate PR by operator decision).
- Fixing stale descriptions in untouched docs (`config/wsl/wslconfig` and `scripts/wslconfig_conf.sh` rationale for `sparseVhd`) goes in a separate docs PR.

## TDD

- **[Refactor, structural commit first]** Turn `require_bash_fakes` in `tests/unit/test_podman_gc_simulation.py` into a shared helper taking a list of fakes (`tests/unit/_bash_fakes.py`). No behavior change.
- **[Red]** Create `tests/unit/test_wsl_compact.py`:
    - Fake `uname`, `reg.exe`, `cygpath`, `stat`, `du`, `wsl.exe`, and `powershell.exe` via `BASH_ENV` functions. Make `fsutil` exit 91 if ever called.
      Restrict PATH to Git's bash and usr/bin so System32 is unreachable.
      Pass `companions=(VHDX_LIB,)` to `run_bash`. Fake `cygpath -u` returns a relative path from cwd, where the test creates the file. Pre-verify with the shared helper before running.
    - Cases:
        - Reproduce old bug: when fake fsutil returns English `"This file is NOT set as sparse"`, old code prints yes (confirmed Red; new code never calls fsutil).
        - Not sparse, large slack: `sparse    : no`, diskpart steps and note that `--compact` is unverified appear.
        - Sparse, large slack: `sparse    : yes`, no diskpart steps; rejection note and N GB needed for `--set-sparse false` appear.
        - Unreadable attributes: `sparse    : unknown`, no steps appear.
        - ACL: ACEs measured on this machine (`S-1-5-83-1-…`, `S-1-15-3-1024-…`, 544, 18, user) emit no WARN.
          Adding `S-1-5-11`, `S-1-5-32-545`, or machine-specific `S-1-5-21-…-1009` emits WARN listing those SIDs; untrusted owner also emits WARN.
          Unreadable ACL emits unknown and does not claim safe.
        - vhdx not found: suggests `reg query … /s` rather than `--get-location` (also statically verify `wsl_fsck.sh` calls the same function).
        - If `VhdFileName` is in registry, measure that named file.
    - Test `wsl_vhdx_untrusted_sids` directly by sourcing the lib (pure function).
    - Windows-only real PowerShell test: set `$env:PSModulePath='C:/nonexistent-powershell7-modules'` and run `wsl_vhdx_facts` on a temp file, verifying `sparse 0` → `sparse 1` after `fsutil sparse setflag`, non-ASCII paths, and no trailing CR (`tests/unit/test_ollama_host.py:238-265` pattern).
    - Static check: no `powershell.exe` calls in `scripts/*.sh` use `Get-Acl`.
    - Remove the assertion in `tests/unit/test_runner_gc.py:954-957` requiring the string `fsutil sparse queryflag` (that string check let this false-positive bug through; rely on behavior tests).
- **[Green]** Implement items 1-3 above.
- **[Refactor]** Item 4 (runbook).

## How to verify

- `uvx pytest tests/unit/test_wsl_compact.py tests/unit/test_runner_gc.py tests/unit/test_podman_gc_simulation.py` (native Windows).
- Explicitly run `markdownlint-cli2` and `shellcheck` including newly added files (`just ci` selects files with `git ls-files`, so untracked files are skipped).
- `just ci` lint and unit tests.
- Physical machine: `just wsl-compact` reports `sparse    : no`, no ACL warnings, and diskpart steps for the vhdx on D: (read-only).
  Do not temporarily widen the vhdx parent's ACL to test.
