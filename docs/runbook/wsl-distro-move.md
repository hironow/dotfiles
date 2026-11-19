# Moving a WSL distro to another volume

Procedure for moving the vhdx of a WSL distro hosting a self-hosted runner to another volume using `wsl --manage <distro> --move`.
Use this when C: runs low on space.
This summarizes the steps and findings from moving an Ubuntu vhdx (227 GB logical) from an NVMe C: to an HDD D: on WSL 3.0.5 (stable as of 2026-11-03).

## What to know beforehand

- **The sparse attribute is lost.** Moving to another volume did not preserve the vhdx's sparse attribute.
  It used 97 GB on disk before the move, and occupied the full 227 GB logical size afterward. The destination needs free space equal to the logical size.
  If you move it back to C: afterward, C: will also need the full logical size.
- **Destination ACLs are inherited.** Default ACLs on D:\ inherit `Authenticated Users:(M)` and `Users:(GR,GE)` down to children.
  Moving directly lets other local users (such as the Codex sandbox user) open the vhdx (the entire distro, including runner credentials).
  Create the destination folder first and disable inheritance.
- **Export asks the distro to stop before writing.** In 3.0.5, `wsl --export` asks the distro to stop even if clients remain and waits up to 60 seconds.
  If it does not stop, it warns "Continuing without confirming that the distribution has stopped." and exports anyway.
  Stopping the runner and running `wsl --shutdown` beforehand avoids that path.
- **Do not call wsl.exe during the move.** While moving the file inside the service, move holds a per-user instance lock.
  Any wsl.exe call during that time (including `--list` or launching) blocks and waits. Do not mistake it for a hang and run `--shutdown --force`.
- **CI did not slow down on HDD.** `pool-infra gate` took 25-33 minutes after the move versus 34-41 minutes on SSD before.
  Note that this measurement covers only one night of jobs.

## Procedure

Run in unelevated PowerShell. Calling `icacls` or `reg` from Git Bash rewrites flags like `/inheritance:r` into Windows paths.

1. Create the destination folder and disable inheritance. For `<dest>`, use e.g. `D:\wsl`.

    ```powershell
    New-Item -ItemType Directory D:\wsl, D:\wsl\backup
    $me = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    icacls D:\wsl /inheritance:r /grant:r "*${me}:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F"
    icacls D:\wsl
    ```

    Do not write `"$env:USERDOMAIN\$env:USERNAME:(OI)(CI)F"`. PowerShell parses `$env:USERNAME:` as one variable name, leaving the username empty (`DESK\(OI)(CI)F`).
    Proceed only after the final `icacls D:\wsl` shows only yourself, SYSTEM, and Administrators, with zero `(I)` (inherited) entries.
    Do not create `D:\wsl\<distro>`; move creates it and inherits from `D:\wsl`.

2. Back up rollback data by exporting the distro's Lxss registry key.

    ```powershell
    reg export "HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss\{<distro GUID>}" D:\wsl\backup\lxss-pre-move.reg
    ```

3. Confirm no jobs are running and stop the runner (wait for `pgrep -x Runner.Worker` to be empty, then `systemctl stop 'actions.runner.*'`).
   Confirm the runner shows offline in the GitHub runners list.

4. Stop the keepalive task and shut down WSL.

    ```powershell
    Stop-ScheduledTask dotfiles-wsl-autostart
    wsl --shutdown
    ```

5. Take a backup export. Because it takes tens of minutes, detach from caller timeouts and save the exit code to a file.
   In PowerShell 5.1, `Start-Process -PassThru` leaves `ExitCode` empty without `-Wait` or retaining the handle. Use the call operator and `$LASTEXITCODE`.

    ```powershell
    & wsl.exe --export <distro> D:\wsl\backup\<distro>-pre-move.tar *> export.log; $LASTEXITCODE | Set-Content export.rc
    ```

   Treat `Timed out waiting` or `Continuing without confirming` in `export.log` as a failure.
   Verify the tar reads cleanly to the end. Windows `tar.exe` can return rc=1 on Unicode-named entries (such as Go toolcache test files).
   In that case, recount with Git Bash's GNU tar (`tar --warning=no-unknown-keyword -tf`). Sockets are excluded from tar (warnings appear in the export log and are harmless).

6. Gate: verify the distro is stopped. Because `wsl --list --running --quiet` outputs UTF-16, set `$env:WSL_UTF8='1'` and strip NULs before comparing.
   Before starting, verify this comparison finds the distro while it is running.

7. Move it. Run detached like step 5 and save the exit code to a file. Do not call wsl.exe until it finishes.

    ```powershell
    & wsl.exe --manage <distro> --move D:\wsl\<distro> *> move.log; $LASTEXITCODE | Set-Content move.rc
    ```

8. Verify the result:
    - Registry `BasePath` points to the new path, the new vhdx exists, and the old vhdx is gone.
    - Free space on C: increased by roughly the actual disk usage of the moved vhdx.
    - The new vhdx's ACL has neither `Users` nor `Authenticated Users`. Record sparse status and actual disk usage (`just wsl-compact` prints both).

9. Start the distro via the keepalive task (`Start-ScheduledTask dotfiles-wsl-autostart`).
   Check the following items, scoping `journalctl -b` to the current boot so old boot logs do not pass falsely:
    - `systemctl is-system-running` is running.
    - `systemctl --failed` matches before the move.
    - Runner service journal shows `Connected to GitHub` and `Listening for Jobs`.
    - Runner is online on GitHub.
    - `just status` is all OK.
    - Default user and `df /` match before the move.
    - The first job finishes `Succeeded`.

## Rollback

Do not stack retries. Keep all output and inspect state read-only first.

- **Move failed, and both the file and `BasePath` remain unchanged.** Nothing changed. Clean up leftovers at the destination and start from step 9.
- **Move finished copying, file is at the new path, and `BasePath` is still the old path.** When move fails to update the registry after copying, it tries to roll back the file.
  If losing sparse prevented it from fitting back on the original volume, rollback fails in this state. Update `BasePath` to the new path and start from step 9.
- **Waiter is still alive and no exit-code file exists.** Move is still running. Wait; do not judge progress by file size.
- **Exit code is 0, `BasePath` points to the new path, and the old vhdx still exists.** Copy succeeded and only deleting the source failed (MoveFileEx behavior).
  Delete the old vhdx only after step 9 checks pass.
- **The vhdx is corrupt and fails to boot.** Only then, `wsl --import` from the step 5 tar (which unregisters first).
  Without `sparseVhd` in `.wslconfig`, the imported vhdx is not sparse. The default user is restored via `[user] default=` in `/etc/wsl.conf`.

## Cleanup

- Delete the backup tar only after running cleanly at the new location for about a week.
- The Start menu distro icon keeps pointing to `shortcut.ico` at the old path, so the old folder remains for that one file.
- After moving, old VM swap files can remain at `%TEMP%\<VM GUID>\swap.vhdx`. Anything other than the running VM's GUID (`wslhost.exe --vm-id`) can be deleted.
