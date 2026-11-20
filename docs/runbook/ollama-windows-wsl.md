# Unifying Ollama across Windows and WSL

On hosts running both Windows and WSL, use only Scoop's `extras/ollama-full` as the Ollama runtime ([ADR-0062](../adr/0062-one-windows-ollama-for-wsl.md)).
Keep models and credentials on the Windows side as well.
Do not install Scoop's CLI edition `main/ollama`, the WinGet edition, the standalone installer, or the WSL Linux edition alongside it.
Installation on Linux without WSL and on macOS is unchanged.

## Windows setup

`dump/windows/scoop.json` declares `ollama-full`.
Fresh setups restore it via `just add-scoop`.
To migrate from the existing CLI edition, stop Ollama without deleting models or `~/.ollama`, then run:

```powershell
scoop uninstall ollama
scoop install extras/ollama-full
just deploy
just doctor
```

Configure the full Windows Ollama app to own `127.0.0.1:11434` on Windows.
Do not bind to `0.0.0.0` or the WSL gateway, and do not add firewall exceptions or portproxy rules.

### Move models before removing the standalone installer

The standalone installer (`%LOCALAPPDATA%\Programs\Ollama`) uninstaller deletes models at the default path `%USERPROFILE%\.ollama\models`.
If `models\blobs` exists at the default path, it selects "Remove models" by default and deletes `models\blobs` and `models\manifests` even under `/VERYSILENT`.
It ignores `OLLAMA_MODELS`.
If the default path is a link (junction or symlink) to another drive, the target files are deleted as well.
They bypass the Recycle Bin.

Before uninstalling, proceed in this order:

1. Stop all Ollama processes.
2. Copy models from the default path to another drive and verify each blob's SHA-256 matches its filename.
3. Point the User environment variable `OLLAMA_MODELS` to the new location and verify `ollama list` in a new terminal shows the same digests.
4. Leave neither a folder nor a link at the default path; create any convenience link under a different name.
5. Re-verify the destination after uninstalling.

Do not rely on unchecking "Remove models" in the UI; defaults and `/VERYSILENT` still delete them.

## WSL sharing

WSL network mode is determined inside WSL via `wslinfo --networking-mode` (WSL 2.0.4 or newer).
If `nat`, install the bridge described in this section.
If `mirrored`, do not install the bridge (see the next section).
Otherwise, or if unreadable, stop without creating a bridge; update WSL with `wsl --update`.

In NAT WSL, `just deploy` configures the user service `ollama-windows-bridge.service` when installing Pi extensions.
Both the full Windows edition and mise-managed Windows Python are required first; if missing, the Linux edition is never installed in WSL.
If user systemd or Windows interop is unavailable, the missing requirement is reported.
The helper is installed as a managed file at `~/.local/lib/dotfiles/ollama_host.py` and runs under `/usr/bin/python3`.
It does not depend on any worktree or temporary venv staying around.
Unrelated existing files, modified managed files, and symlinks are never overwritten.

```bash
just deploy
systemctl --user status ollama-windows-bridge.service
just doctor
```

The bridge listens only on `127.0.0.1:11434` and `[::1]:11434` inside WSL.
It launches the verified physical Windows Python binary in isolation (`-I -S -B -u`) and forwards byte streams to `127.0.0.1:11434` on Windows.
Both directions transfer raw binary in 32KiB chunks without a PowerShell text pipeline.
It supports Windows `MISE_DATA_DIR` and inspects only full-version directories in numeric order.
It tests up to the first 3 candidates in isolation for up to 3 seconds each, confirming native Windows Python and not a venv.
`~/.local/bin/ollama` is a managed shim calling the full Windows CLI rather than a local binary.
This shim is installed regardless of backend state so installers do not mistake a stopped backend for a missing Linux binary.
`serve`, `launch`, and unknown commands are rejected; only known client commands are forwarded after confirming the genuine backend is running.
`OLLAMA_HOST` passed to Windows is pinned to loopback while preserving other `WSLENV` entries.
WSL holds no Ollama binary or models and keeps `appendWindowsPath=false`.
Inside the user service, rather than pinning a per-session socket in config, it probes for an available interop socket.

On each connection, it checks the Windows listening PID and executable, connecting only when Scoop's full edition owns `127.0.0.1:11434`.
WSL's forwarding listener that Windows creates on `::1:11434` is not counted as a second Ollama runtime.
This exception applies only when the protected `Program Files/WSL/wslrelay.exe` path is exact, is not a symlink, and carries a valid Microsoft signature.
The same forwarding listener owning an IPv4 target never substitutes for the genuine backend, and unknown signatures or wildcard listeners are rejected.
Even when Windows localhost forwarding loops back to the WSL bridge, connections lacking a genuine Windows owner are rejected.
Concurrent transfers are capped at 8 connections with a 2-second wait, holding the slot until cleanup and child process reaping finish.
Windows socket timeout is 300 seconds per direction.
Even during an active upload, the receiver fails if no response arrives within 300 seconds.
Send-thread errors are also propagated as failures, and stdout carries transferred data only.
On port conflict, existing processes are never stopped and nothing binds to another address.

## Mirrored WSL (sharing loopback with Windows)

WSL configured with `networkingMode=mirrored` in `.wslconfig` shares `127.0.0.1` with Windows ([ADR-0064](../adr/0064-mirrored-wsl-uses-the-shared-loopback.md)).
Connecting to `127.0.0.1:11434` from WSL reaches the Windows runtime directly without a bridge.
Placing a bridge here would contend for the same port as Windows, so none is installed.
dotfiles never modifies `.wslconfig`.

In mirrored mode, `just deploy` installs only the CLI shim `~/.local/bin/ollama` and the helper, without writing the bridge unit.
If the bridge unit is enabled or active, a bridge process is running, or anything listens on 11434 in WSL, it stops without changing anything.
It also stops if those states cannot be read.
On machines switched from NAT to mirrored, stop the old bridge first.

```bash
systemctl --user disable --now ollama-windows-bridge.service
just deploy
just doctor
```

Even if an old bridge is started manually, it exits without listening in mirrored mode.
In mirrored mode, the CLI shim still verifies Windows ownership before calling the Windows CLI.

WSL doctor verifies in this order:
If any step fails, it makes zero network requests.

1. Network mode is confirmed as mirrored.
2. WSL listener inspection succeeds and nothing listens on 11434.
3. On Windows, `127.0.0.1:11434` is verified to be owned by the genuine runtime.
4. WSL queries `127.0.0.1:11434/api/version` once and gets the same version as Windows.

Checks that Windows doctor runs inside WSL do not receive the Windows-side verdict, so they make no network requests.
Tools connecting directly to `localhost:11434` over HTTP (such as Pi web search) bypass the bridge's per-connection check.
That is inherent to mirrored networking, so doctor checks the sequence above instead.
Because the runtime listens only on IPv4 loopback, tools that try `::1` first for `localhost` get refused and fall back to `127.0.0.1`.

## Allowing Tailscale forwarding only inside the tailnet (declared hosts only)

Some hosts are configured by the owner to expose 11434 to the tailnet via Tailscale TCP forwarding (e.g., `tailscale serve --bg --tcp=11434 tcp://localhost:11434`).
On those hosts, placing a user declaration file prevents the forwarder from counting as a second runtime or public exposure ([ADR-0063](../adr/0063-declared-tailnet-forward-of-ollama.md)).

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.config\dotfiles" | Out-Null
Set-Content -NoNewline "$env:USERPROFILE\.config\dotfiles\ollama-tailnet-forward" '11434'
```

The declaration is a per-user config choice, not an authorization boundary against the user.
Deleting the file restores the original verdict (forwarding listeners report ERR).
On hosts without the declaration, Tailscale commands are never run.
dotfiles never creates or removes Tailscale configuration.

Even with the declaration, a listener passes only if every check below holds (reject if any fails or cannot be read):

- Port is 11434.
- The listening process is the running Tailscale service itself or its direct child `tailscaled.exe`. If a child, the parent's creation time precedes the child's; afterward, re-read the service PID and confirm it has not changed.
- The service binary is `%ProgramFiles%\Tailscale\tailscaled.exe`, neither the file nor its parent folder is a link, and it has a valid Tailscale Inc. signature. The `tailscale.exe` CLI is used only after the same verification.
- The listening address is this host's address returned by `tailscale ip`, within `100.64.0.0/10` or `fd7a:115c:a1e0::/48`.
- No Funnel (`AllowFunnel`) is enabled anywhere in serve config (including foreground sessions).
- 11434 forwards to `127.0.0.1:11434`, or `localhost:11434` when nothing listens on `[::1]:11434`. No other handler (foreground, Tailscale Services, web, Tun) owns 11434, and no other forwarder or web proxy points to 11434.

An approved forwarder reports `OK ollama-tailnet-forward` in doctor.
If a declaration exists but the listener is rejected, `ERR ollama-tailnet-forward` prints the reason and the exposure ERR remains.
The tailnet ACL (`tofu/tailnet/acl.hujson`) permits Funnel on no machine.

## Doctor check scope

`just doctor` calls `scripts/ollama_host.py --check`.
Checks are read-only and never remediate or start services.
Because the Windows inspection script exceeds the Windows command-line length limit (32,767 characters), it is piped to PowerShell via stdin.

- Checks the full Windows edition, Scoop buckets, known duplicate installs, and the running Ollama executable.
- Inspects listening PIDs, ports, and addresses for runtime ownership and non-loopback exposure. On declared hosts, verifies tailnet-only Tailscale forwarding and exempts approved ones from exposure.
- Checks WSL for native binaries, packages, processes, system/user services, and model placement.
- In NAT WSL, verifies the bridge's managed unit, binary, PID, listening socket, and forwarded version response. In mirrored WSL, checks the shared loopback in the order above. Unknown network mode reports WARN.
- Stopped or unreachable WSL distros are not started and report uninspected WARN. Platform-managed distros (`docker-desktop`) cannot be Ollama clients, so they are skipped and reported as INFO.
- Distros kept stopped as rollback targets or backups can be listed one per line in `%USERPROFILE%\.config\dotfiles\wsl-retained-distros` using exact `wsl -l -q` names (`#` lines are comments). Listed distros are skipped and reported as INFO while stopped, and checked normally when running. Write the file in UTF-8 (BOM allowed); unreadable UTF-8 is treated as empty and stays WARN. Listing a distro does not authorize deleting it (ADR-0077). See below for format.
- A bridge with properly managed unit and socket that fails only because Windows is unreachable reports WARN as a normal stopped state, not a misconfiguration. Identity or version mismatches stay ERR.
- Docker / Podman containers sharing the WSL2 kernel lack Windows interop and are marked out of scope (N/A) for this policy.

Declare a retained stopped distro (e.g., `Ubuntu`) from Windows PowerShell as follows:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.config\dotfiles" | Out-Null
Add-Content -Encoding utf8 "$env:USERPROFILE\.config\dotfiles\wsl-retained-distros" 'Ubuntu'
```

This check does not guarantee that dormant copies outside known paths and running processes do not exist.
Misconfigurations are ERR and uninspectable or stopped genuine backends are WARN; HTTP responses alone never prove valid ownership.
The version response verifies connectivity and does not replace checking Ollama login state or Pi web search.

Stopping the Windows runtime causes WSL connections to fail.
Recover by starting the full Windows edition; never start `ollama serve` inside WSL instead.
