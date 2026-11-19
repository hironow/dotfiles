# Running on native Windows hosts

This runbook covers common pitfalls when running this repository's recipes, scripts, and tests on native Windows (outside WSL).
Read it before changing justfile shell settings, `scripts/*.sh`, mise configuration, or Python code that runs on Windows.

## Shell for running just recipes

Windows resolves bare `bash` to `C:\Windows\System32\bash.exe` (the WSL entry point) ahead of PATH.
As a result, recipes using `bash` can fall into WSL (this does not happen on machines without WSL).
The impact splits in two depending on how the recipe is written:

- **Normal recipes** (`doctor`, `harden-env`, `deploy`, `clean`, and others calling `bash scripts/*.sh`): fixed by justfile's `set windows-shell := ["sh", …]` and wrapper preamble, so they run directly from PowerShell. Because System32 has no `sh.exe`, `sh` resolves to Git Bash, and the preamble prepends `/usr/bin` to PATH before starting the inner `/usr/bin/sh`. Plain MSYS `sh` keeps the caller's PATH order, so without this preamble the inner `bash` falls into WSL. The preamble applies only inside the recipe shell (guarded by `tests/unit/test_windows_shell_usr_bin_path.py` and `test_deploy_clean_linewise.py`).
- **Shebang recipes** (`dump`, `scaffold-agent-baseline`, and others starting with `#!/usr/bin/env bash`): ignore `set shell`, and `env` searches PATH for `bash`. Plain PowerShell fails because System32 comes first. Run these from Git Bash (where `/usr/bin` is first, so `bash` resolves to Git Bash).

Permanently prepending Git's `usr\bin` to PATH makes PowerShell work too, but shadows Windows commands like `find` and `sort` and is not recommended.
Running a shebang recipe from PowerShell without Git's `usr\bin` on PATH fails across the board with `could not find cygpath`.
`just harden-env` appends Git's `usr\bin` and `cmd` to User PATH.
`just doctor`'s Windows section detects missing `cygpath` and prints how to fix it (background in memory `project_windows_shell_msys_sh_path_order`).

When launching `bash` from a native process (such as Python), specify the actual Git Bash executable rather than bare `bash` (`resolve_bash()` in `tests/unit/_bash_hook.py` for tests).
Because Claude Code runs hooks in Git Bash, hook commands with `C:\` paths lose backslashes (write them with `/` separators).

## uv config file

Native Windows uv reads `%APPDATA%\uv\uv.toml`, not `~/.config/uv/uv.toml`.
Without it, supply-chain quarantine does not apply, `uv run` rewrites the committed `uv.lock`, and pre-commit lint blocks commits.
`just harden-env` writes both, and `just doctor` detects when it is missing (memory `project_windows_uv_appdata_config`).

## mise npm backend

Native Windows does not use pnpm (ADR 0070). `install.sh` does not set up corepack, and `just doctor` omits the pnpm line.

Set mise's npm backend package manager to `bun` (ADR 0036).
The default `auto` uses mise's built-in aube, which skips `claude-code`'s postinstall.
Then the native binary (about 263MB) is never extracted, leaving `bin/claude.exe` as a 500-byte stub, and running `node claude.exe` fails with `ERR_UNKNOWN_FILE_EXTENSION`.
The install reports success without any warning.
If a rogue npm-global copy shadows mise's version on PATH, `claude` appears to work until `just prune-rogue-npm-globals` removes the rogue copy and seems to break it.

- Changing the backend does not fix already-installed tools; they stay stubs until reinstalled with `mise uninstall` and `mise install`.
- bun puts shims in `<install>/bin/` instead of `node_modules/.bin`. Shells opened before `mise activate` still hold the old `.bin` on PATH, so reopen the shell (`mise env` returns the right `bin/`).
- On Windows, a running process continues even after its `.exe` is deleted. The current session keeps working after removal, then fails on the next launch (verify the real binary path with `ps -W`).
- A WinGet install stays hidden while a rogue copy wins on PATH, then surfaces once the rogue copy is removed. It may be older than mise's version and is flagged by `just doctor`'s `winget-shadow`.

The bun backend ignores `npm_args` (ADR 0040; bun reads only `bun_args`).
`claude-code`'s native binary works because it is on bun's default trust list so postinstall runs.
When adding an npm tool that needs postinstall and is not on the trust list, consider `bun_args` or trustedDependencies (memory `project_mise_npm_ignore_scripts`).

## self-hosted runner PATH

Because runner jobs skip `mise activate`, scoop shims, `.bun\bin`, and mise shims are added to Machine PATH (`install_runner_svc_win.ps1` and `restore_machine_path.ps1`).
Processes that skip `mise activate` (jobs and IDEs) pick earlier scoop or bun copies on PATH, which may differ slightly from mise versions.
Even when stopping the runner service to work interactively, User PATH lacks mise shims, so do not remove the shims from Machine PATH.

## Codex sandbox and mise tools

Codex's Windows sandbox runs commands as another user (a member of `CodexSandboxUsers`).
Codex grants inherited read permissions (`CodexSandboxUsers:(OI)(CI)(RX)`) on directories above your profile so that user can read them.
Directories with inheritance disabled do not receive this permission.
On machines where `%LOCALAPPDATA%\mise` had inheritance disabled, all mise tools (rtk, bun, just, etc.) failed inside the sandbox with "Access is denied", and commands rewritten to `rtk ...` by the rtk hook also failed.
`just codex-sandbox-tools` grants `CodexSandboxUsers` read and execute permissions only on mise directories (it also runs `just sync-agents x`, and `just doctor`'s `codex-sandbox` detects missing permissions).
Whether the sandbox is provisioned is checked by whether the `CodexSandboxUsers` group exists (`net localgroup CodexSandboxUsers`).
Where Codex applies read permissions varies by machine (some apply it to the profile itself, others only to direct entries like `~/.codex`), so ACLs alone cannot tell.
Re-enabling inheritance is avoided because it pulls in parent inherited permissions (such as `Users` modify permissions on a relocated `MISE_DATA_DIR` parent).
Revert with `icacls <dir> /remove:g CodexSandboxUsers`.

The same permission reaches files directly under your profile, making secrets in `~/.env` readable from the sandbox.
Because Codex reapplies permissions every time it prepares the sandbox, removing them with `icacls` does not stick.
Because Codex blocks access to `~/.config`, move secrets under it (put Jev's key in `~/.config/jev/env`).
`just doctor`'s `codex-sandbox-secrets` detects `~/.env` readable from the sandbox.

Because the sandbox user differs from the repository owner, git stops on its ownership check (`safe.directory`).
This is unrelated to rtk; plain `git status` stops the same way.
dotfiles never alters `safe.directory`.
Relaxing it would let your own git outside the sandbox execute `.git/config` settings (such as `core.fsmonitor`) planted by code inside the sandbox.
For repositories that need git inside the sandbox, add `safe.directory` manually only when you accept that risk, or run Codex without the sandbox (`just doctor`'s `codex-sandbox-git` prints the same guidance).

## Claude Code Git Bash

Native Windows Claude Code uses Git Bash for its Bash tool and searches in this order (2.1.285 implementation):

1. `CLAUDE_CODE_GIT_BASH_PATH` (an existing file named `bash` or `sh`)
2. `C:\Program Files\Git\bin\bash.exe` and `C:\Program Files (x86)\Git\bin\bash.exe`
3. `..\..\bin\bash.exe` relative to the first `git` found on PATH

On machines where Git was installed with scoop, the first `git` is the scoop shim (`~\scoop\shims\git.exe`), so step 3 also misses.
If missing, the Bash tool breaks, and both `j-cc` and `just jev-claude-verify` fail.
`just doctor`'s `claude-git-bash` detects this and prints the Git Bash path to set.
`just harden-env` sets the User variable `CLAUDE_CODE_GIT_BASH_PATH` only when Claude Code cannot find Git Bash on its own (this varies per machine, so tracked fragments omit it).
If the User environment variable already has a value, even a broken one, it is not overwritten (`claude-git-bash` warns so a human can fix it).

## Scheduled tasks running in interactive sessions

When Task Scheduler launches a console program (such as `powershell.exe`) directly in the owner's logon session, a console window flashes on every launch.
Because `dotfiles-runner-watchdog` runs every 5 minutes, a window flashed every 5 minutes (2026-11-18).
Tasks registered by dotfiles (`dotfiles-runner-watchdog`, `dotfiles-wsl-autostart`, `dotfiles-runner-gc`) launch `run-hidden.exe` followed by `powershell.exe` and the original arguments (ADR 0081).

- `run-hidden` (`tools/run-hidden`) builds with the Windows GUI subsystem (`just run-hidden-build`, `-ldflags=-H=windowsgui`) and has no console of its own.
- It spawns the child with `CREATE_NO_WINDOW`. The child has a console without a visible window, and `wsl.exe` works normally from it.
- It exits with the child's exit code. So task results (`LastTaskResult`) still reflect the payload, and `just status` checks stay the same.
- The installer copies `output/run-hidden/run-hidden.exe` to `%LOCALAPPDATA%\dotfiles\run-hidden\<first 16 hex digits of the SHA-256>\`, and tasks launch that copy.
    - Because the WSL keepalive task never exits, its launcher `.exe` stays locked in use and cannot be overwritten.
    - Content-addressed directories avoid recopying unchanged binaries and write a new directory when the binary changes. Old directories are left alone (a human deletes them after confirming no task uses them).
- With no window, inspect payload output in the logs: `%TEMP%\runner-watchdog-win.log` and `%TEMP%\wsl-autostart.log`.
- `just status` emits a WARN for any task not launched via `run-hidden.exe`.

Forms we do not use and why:

- `-WindowStyle Hidden`: creates a console first and hides it afterward, so a window flashes briefly.
- `conhost.exe --headless`: discards the child's exit code (returns 0 even when the child exits 7; verified on this machine on 2026-11-18), making task results always look successful.
- `conhost.exe --headless` from a shell: exits before starting the child when stdin is a closed pipe.

Re-registering tasks requires an elevated terminal.
Because tasks on this machine were registered in an elevated context, an unelevated installer cannot delete them and leaves them "keeping it as-is" (and does not take the UAC path for GC either).

Procedure to switch a running WSL autostart task (keepalive) to a new action (same steps to revert). The installer does not stop a running task: if registration fails afterward, the distro loses its last client and stops, killing running runner jobs.

1. Start a temporary client in another terminal to keep the distro alive: `wsl.exe -d Ubuntu-26.04 -e sleep 900`.
2. Run `Stop-ScheduledTask dotfiles-wsl-autostart`. Use `Get-CimInstance Win32_Process` to confirm neither `wsl.exe` with `dotfiles-wsl-keepalive` on its command line nor its parent powershell exists (the temporary client has a different command line).
3. In an elevated terminal, run `just runner-gc-install`. After registration, the installer starts autostart and the new keepalive connects. For watchdog, run `just runner-watchdog-install` (it finishes in seconds, so no stop step is needed).
4. Run `just status` to confirm keepalive is OK, tasks are Running, and there are no WARNs, then stop the temporary client. On failure, keep the temporary client running while fixing (it expires after 15 minutes, so restart it if needed).

## Python files and character encodings

On Japanese-edition Windows, the locale encoding is cp932.
Without `encoding=`, `Path.read_text()`, `write_text()`, `open()`, and `subprocess` with `text=True` read and write cp932.
Python code in this repository must always pass `encoding="utf-8"` for text I/O and `encoding="utf-8", errors="replace"` for subprocess output (enforced by `tests/unit/test_text_io_encoding.py`).
Scripts exchanging stdin/stdout with Claude Code or Pi call `jev_launch.use_utf8_stdio()` before reading.

Joining `C:\` paths with `:` in `PATH` passed to bash breaks on the drive colon.
Tests convert them to `/c/...` using `bash_path()` in `tests/unit/_bash_hook.py`.

## Writing Windows-compatible code and the checks that verify it

Bugs that fail only on Windows are invisible to checks on other OSes.
The following checks catch them even without a Windows host:

| Check | Where it runs | What it catches |
| --- | --- | --- |
| `just check-ty` (ty with `--python-platform` win32, linux, darwin) | `just check` (`just ci`, `just check-all`, CI dev container job) | Type errors in branches for other OSes |
| `just go-lint` (`golangci-lint run` for GOOS windows, linux, darwin) | `just check` | Errors in build-tagged files and functions called only from them (unused on other OSes) |
| `just test-unit` (CI `windows-unit`) | Unit Tests workflow; checkout uses Git for Windows default line endings (CRLF) | Tests failing on line endings, MSYS path conversion, Git gpg, or pwsh 7 |
| `just test-windows-powershell` | CI `windows-unit` and local Windows | Behavior differing only in Windows PowerShell 5.1 (GC, `bootstrap.ps1`, Podman install) |
| `just go-test go` (CI `windows-go`) | Unit Tests workflow | Go tests on Windows |
| `tests/unit/test_cross_platform_gates.py` | `just test-unit` | Removal of the above checks, or multi-command pwsh steps (which hide earlier command failures) |

Follow these rules when writing code:

- Branch on OS in Python using `sys.platform == "win32"`. ty narrows on both `sys.platform` and `os.name`, but `sys.platform` also distinguishes Linux from macOS, and typeshed uses it to gate OS-specific APIs.
- Names imported under an OS condition do not exist during type checking for other OSes; using them in annotations fails, and usage inside the body goes unchecked (verified with ty 0.0.91).
- Place imports of POSIX-only repository modules under `if TYPE_CHECKING or os.name != "nt":` (e.g., `scripts/sync_agents.py`) so their internals are checked on every OS.
- OS-specific standard library modules (`fcntl`, `pwd`, `grp`, `winreg`, `msvcrt`) are empty during type checking for other OSes even under `TYPE_CHECKING`. Use them only after a `sys.platform` check inside the same function, and never in annotations of functions read on all OSes.
- When skipping a test by OS, put `if sys.platform == "win32": pytest.skip(...)` at the top of the test body instead of `skipif`. ty narrows there, so subsequent POSIX APIs do not error during Windows type checking.
- Copy `os.environ` before modifying environment variables for PowerShell child processes. Building one by hand drops PATHEXT, SystemRoot, and SystemDrive, causing `python.exe` to open a new window whose output cannot be captured. Dropping `PSModuleAnalysisCachePath` forces Windows PowerShell 5.1 on windows-latest runners to re-analyze all installed modules on every start (turning 0.3s into 18-32s).
- PowerShell tests select PowerShell via `resolve_pwsh(os.environ)` in `tests/unit/_pwsh.py` (`DOTFILES_TEST_PWSH=powershell.exe` picks 5.1) and launch with production flags (`-NoProfile -NonInteractive -ExecutionPolicy Bypass -File`; without `-ExecutionPolicy Bypass`, 5.1 rejects scripts by default).
- Pass Git for Windows gpg `--homedir` in `/c/...` form; `C:\...` prevents the agent from starting.
- Write fake scripts generated by tests with `newline="\n"`; Git Bash treats CR as part of the command.
- Pass `MSYS_NO_PATHCONV=1` and `MSYS2_ARG_CONV_EXCL='*'` to stop MSYS from converting path arguments.
- The repository and temp directory may sit on different drives (windows-latest runners check out to `D:` and keep temp on `C:`). `os.path.relpath` raises `ValueError` across drives; test locally with pytest `--basetemp` on another drive.
- Git Bash's `$OSTYPE` is either `msys` or `cygwin` depending on the Git for Windows version. Identify WSL by checking that it is not `linux-gnu`.
- Add `.exe` to binaries built in Go tests on Windows.
- Pin byte-compared artifacts (recorded corpora, hash-recorded files) to `text eol=lf` in `.gitattributes` (enforced by `tests/unit/test_gitattributes_eol.py`).
